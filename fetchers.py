"""
fetchers.py
-----------
Funciones que traen datos de cada fuente y los devuelven SIEMPRE en el mismo
formato "largo" (tidy): un DataFrame con columnas
    fecha (datetime) | valor (float)

Cada fuente tiene su propia función; el orquestador (run.py) elige cuál usar
según el campo "fuente" de cada indicador en el config.

Fuentes soportadas:
  - datos_gob      -> apis.datos.gob.ar/series (EMAE, IPC, monetarias, fiscal, empleo...)
  - argentinadatos -> api.argentinadatos.com   (inflación, riesgo país)
  - dolar          -> api.argentinadatos.com/v1/cotizaciones/dolares (histórico por casa)
  - bcra           -> api.bcra.gob.ar/estadisticas (reservas diarias, etc.)
  - rem_bcra       -> Excel histórico único del REM (bcra.gob.ar), expectativas de mercado
"""
from __future__ import annotations
import io
import json
import time
from pathlib import Path
import requests
import pandas as pd

TIMEOUT = 30
HEADERS = {"User-Agent": "coyuntura-tracker/1.0 (uso académico)"}


def _get(url: str, params: dict | None = None, reintentos: int = 3) -> requests.Response:
    """GET con reintentos simples y backoff."""
    ultimo_error = None
    for intento in range(reintentos):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            ultimo_error = e
            time.sleep(2 * (intento + 1))
    raise RuntimeError(f"Falló la consulta a {url}: {ultimo_error}")


# ---------------------------------------------------------------------------
# 1) apis.datos.gob.ar/series  -> el backbone: +30.000 series oficiales
# ---------------------------------------------------------------------------
LIMITE_PAGINA_DATOS_GOB = 5000  # tope máximo de filas por página que acepta la API (400 si se pide más)


def fetch_datos_gob(serie_id: str, start_date: str | None = None) -> pd.DataFrame:
    """
    Trae una serie de la API de Series de Tiempo de la Nación, paginando con
    el parámetro 'start' (offset de filas) hasta cubrir el 'count' total que
    informa la API. Necesario para series diarias largas (BADLAR, etc.) que
    ya superan las 5000 observaciones: sin paginar, quedan cortadas para
    siempre en la fila 5000 y el indicador se congela en silencio.

    serie_id : id de la serie (ej '143.3_NO_PR_2004_A_21'). Buscalos con buscar_series.py
    """
    url = "https://apis.datos.gob.ar/series/api/series/"
    data = []
    offset = 0
    total = None
    while total is None or offset < total:
        params = {"ids": serie_id, "format": "json", "limit": LIMITE_PAGINA_DATOS_GOB, "start": offset}
        if start_date:
            params["start_date"] = start_date
        payload = _get(url, params=params).json()
        pagina = payload.get("data", [])
        if not pagina:
            break
        data.extend(pagina)
        total = payload.get("count", len(data))
        offset += len(pagina)
        if len(pagina) < LIMITE_PAGINA_DATOS_GOB:
            break  # última página (vino incompleta)

    if not data:
        return pd.DataFrame(columns=["fecha", "valor"])

    df = pd.DataFrame(data, columns=["fecha", "valor"])
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    return df.dropna().drop_duplicates(subset="fecha").sort_values("fecha").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 2) ArgentinaDatos -> inflación, riesgo país (endpoints tipo {fecha, valor})
# ---------------------------------------------------------------------------
def fetch_argentinadatos(endpoint: str, start_date: str | None = None) -> pd.DataFrame:
    """
    endpoint : ruta relativa, ej 'finanzas/indices/riesgo-pais'
               o 'finanzas/indices/inflacion'
    """
    url = f"https://api.argentinadatos.com/v1/{endpoint}"
    data = _get(url).json()
    if not data:
        return pd.DataFrame(columns=["fecha", "valor"])

    df = pd.DataFrame(data)
    # estos endpoints devuelven {'fecha': ..., 'valor': ...}
    df = df.rename(columns={"fecha": "fecha", "valor": "valor"})
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df = df.dropna().sort_values("fecha")
    if start_date:
        df = df[df["fecha"] >= pd.to_datetime(start_date)]
    return df[["fecha", "valor"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# 3) Dólar histórico por casa (ArgentinaDatos)
# ---------------------------------------------------------------------------
def fetch_dolar(casa: str, start_date: str | None = None) -> pd.DataFrame:
    """
    casa : oficial | blue | bolsa (MEP) | contadoconliqui (CCL) | mayorista | tarjeta | cripto
    Devuelve el valor de VENTA por fecha.
    """
    url = f"https://api.argentinadatos.com/v1/cotizaciones/dolares/{casa}"
    data = _get(url).json()
    if not data:
        return pd.DataFrame(columns=["fecha", "valor"])

    df = pd.DataFrame(data)
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["valor"] = pd.to_numeric(df["venta"], errors="coerce")
    df = df.dropna(subset=["valor"]).sort_values("fecha")
    if start_date:
        df = df[df["fecha"] >= pd.to_datetime(start_date)]
    return df[["fecha", "valor"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# 4) BCRA -> reservas internacionales diarias, otros datos diarios
# ---------------------------------------------------------------------------
def _parsear_respuesta_bcra(data: dict) -> list[dict]:
    """Extrae filas {fecha, valor} de una respuesta de la API de estadísticas del BCRA."""
    filas = []
    results = data.get("results")
    if not results:
        return filas
    # v4.0/v3.0: [{"idVariable":1,"detalle":[{fecha,valor},...]}]. v2.0: lista directa de {fecha,valor}.
    if isinstance(results, list) and len(results) > 0 and results[0].get("detalle"):
        items = [d for item in results for d in item.get("detalle", [])]
    else:
        items = results
    for item in items:
        try:
            fecha_str = item.get("fecha")
            valor = item.get("valor")
            if fecha_str and valor is not None:
                filas.append({"fecha": fecha_str, "valor": float(valor)})
        except (ValueError, KeyError, TypeError):
            pass
    return filas


def fetch_bcra(id_variable: int, start_date: str | None = None) -> pd.DataFrame:
    """
    Trae datos de la API del BCRA (Estadísticas Monetarias).
    Usa v4.0 (preferido), con fallbacks a v3.0 y v2.0.

    id_variable: número de variable (ej: 1 para reservas internacionales diarias)
    Devuelve DataFrame con fecha (diaria) y valor.

    Resiliente a la inestabilidad conocida de api.bcra.gob.ar (502 intermitentes):
    para cada versión de la API, prueba ventanas de fecha cada vez más cortas
    (2 años · 6 meses · 1 mes) y reintenta cada una con backoff antes de pasar
    a la siguiente. Si todo falla, loguea el error y devuelve un DataFrame vacío
    SIN tocar el histórico ya guardado (storage.py sólo agrega, nunca borra).
    """
    end_date = pd.Timestamp.today()
    ventanas_dias = [730, 180, 30]  # 2 años, 6 meses, 1 mes
    versiones = ["v4.0", "v3.0", "v2.0"]
    reintentos_por_ventana = 2
    filas = []
    ultimo_error = None

    for version in versiones:
        for dias in ventanas_dias:
            desde = (end_date - pd.Timedelta(days=dias)).strftime("%Y-%m-%d")
            hasta = end_date.strftime("%Y-%m-%d")
            url = f"https://api.bcra.gob.ar/estadisticas/{version}/monetarias/{id_variable}"
            params = {"desde": desde, "hasta": hasta, "limit": 1000}

            for intento in range(reintentos_por_ventana):
                try:
                    try:
                        r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT, verify=True)
                        r.raise_for_status()
                    except (requests.exceptions.SSLError, requests.exceptions.ConnectionError):
                        r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT, verify=False)
                        r.raise_for_status()
                    filas = _parsear_respuesta_bcra(r.json())
                    if filas:
                        break
                except (requests.RequestException, ValueError, KeyError, TypeError) as e:
                    ultimo_error = f"{version} desde={desde}: {e}"
                    time.sleep(2 * (intento + 1))  # backoff antes del próximo reintento
            if filas:
                break
        if filas:
            break

    if not filas:
        print(f"  [ADVERTENCIA] fetch_bcra id_variable={id_variable}: sin datos tras probar "
              f"{len(versiones)} versiones x {len(ventanas_dias)} ventanas. Último error: {ultimo_error}")
        return pd.DataFrame(columns=["fecha", "valor"])

    df = pd.DataFrame(filas)
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df = df.dropna().sort_values("fecha")
    if start_date:
        df = df[df["fecha"] >= pd.to_datetime(start_date)]
    return df[["fecha", "valor"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# 5) REM (BCRA) -> Relevamiento de Expectativas de Mercado
# ---------------------------------------------------------------------------
REM_XLSX_URL = ("https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/"
                "informes/historico-relevamiento-expectativas-mercado.xlsx")
REM_FRESCURA_DIAS = 7  # el BCRA publica una encuesta nueva por mes: con 1 vez por semana alcanza de sobra
_CACHE_DIR = Path(__file__).resolve().parent / "data"
_REM_CACHE_CSV = _CACHE_DIR / "_cache_rem.csv"
_REM_CACHE_META = _CACHE_DIR / "_cache_rem_meta.json"


def _descargar_y_transformar_rem() -> pd.DataFrame:
    """
    Descarga el Excel histórico ÚNICO del REM (misma URL fija, ~1,5 MB) y
    devuelve TODAS las variables/referencias de la hoja "Base de Datos
    Completa" ya reducidas a "expectativa a un mes vista": para cada
    encuesta, sólo el pronóstico cuyo Período es el mes INMEDIATAMENTE
    siguiente al de la encuesta. Se transforman todas las variables de una
    sola pasada (no sólo la pedida) para que la caché sirva de una sola
    descarga a cualquier indicador REM que se agregue más adelante.
    """
    r = _get(REM_XLSX_URL)
    with io.BytesIO(r.content) as buf:
        df = pd.read_excel(buf, sheet_name="Base de Datos Completa", skiprows=1, engine="openpyxl")
    df = df.iloc[:, :5]
    df.columns = ["encuesta", "variable", "referencia", "periodo", "mediana"]
    df["encuesta"] = pd.to_datetime(df["encuesta"], errors="coerce")
    df["periodo"] = pd.to_datetime(df["periodo"], errors="coerce")
    df = df.dropna(subset=["encuesta", "periodo"])
    df["mes_encuesta"] = df["encuesta"].dt.to_period("M")
    df["mes_periodo"] = df["periodo"].dt.to_period("M")
    df = df[df["mes_periodo"] == df["mes_encuesta"] + 1].copy()
    df["fecha"] = df["mes_periodo"].dt.to_timestamp("M")
    df["valor"] = pd.to_numeric(df["mediana"], errors="coerce")
    df["variable"] = df["variable"].astype(str).str.strip()
    df["referencia"] = df["referencia"].astype(str).str.strip()
    df = df.dropna(subset=["valor"]).sort_values("fecha").drop_duplicates(subset=["variable", "referencia", "fecha"])
    return df[["variable", "referencia", "fecha", "valor"]].reset_index(drop=True)


def fetch_rem_variable(variable: str, referencia: str, start_date: str | None = None) -> pd.DataFrame:
    """
    Serie de "expectativa a un mes vista, siempre la más reciente disponible
    para cada mes" para la variable/referencia pedida (tal como figuran en
    las columnas "Variable"/"Referencia" de la hoja, ej. "Precios minoristas
    (IPC nivel general; INDEC)" / "var. % mensual"). El resultado queda
    indexado por Período (el mes al que corresponde la expectativa, no la
    fecha de la encuesta), normalizado a fin de mes para alinear con
    "Inflación mensual (IPC)" (ArgentinaDatos) en los gráficos de overlay.

    El Excel del BCRA se actualiza una vez por mes (una encuesta nueva) pero
    pesa ~1,5 MB; para no descargarlo de nuevo en cada corrida diaria del
    pipeline sin necesidad (tráfico contra el servidor del BCRA sin ningún
    dato nuevo la gran mayoría de los días), la tabla ya extraída (todas las
    variables, no sólo ésta) se cachea en data/_cache_rem.csv con una marca
    de fecha en data/_cache_rem_meta.json: sólo se vuelve a descargar si la
    caché tiene más de REM_FRESCURA_DIAS días o todavía no tiene la variable
    pedida (ej. la primera vez que se agrega un indicador REM nuevo).
    """
    completo = None
    if _REM_CACHE_META.exists() and _REM_CACHE_CSV.exists():
        try:
            meta = json.loads(_REM_CACHE_META.read_text(encoding="utf-8"))
            descargado = pd.to_datetime(meta.get("descargado"))
            if (pd.Timestamp.today().normalize() - descargado).days < REM_FRESCURA_DIAS:
                cache = pd.read_csv(_REM_CACHE_CSV, parse_dates=["fecha"])
                if ((cache["variable"] == variable) & (cache["referencia"] == referencia)).any():
                    completo = cache
        except (ValueError, KeyError, OSError, json.JSONDecodeError):
            completo = None

    if completo is None:
        completo = _descargar_y_transformar_rem()
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        completo.to_csv(_REM_CACHE_CSV, index=False)
        _REM_CACHE_META.write_text(
            json.dumps({"descargado": pd.Timestamp.today().normalize().isoformat()}), encoding="utf-8")

    sub = completo[(completo["variable"] == variable) & (completo["referencia"] == referencia)]
    if sub.empty:
        return pd.DataFrame(columns=["fecha", "valor"])
    df = sub[["fecha", "valor"]].sort_values("fecha").drop_duplicates(subset="fecha").reset_index(drop=True)
    if start_date:
        df = df[df["fecha"] >= pd.to_datetime(start_date)]
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Dispatcher: elige el fetcher según el config del indicador
# ---------------------------------------------------------------------------
def traer(indicador: dict, start_date: str | None = None) -> pd.DataFrame:
    fuente = indicador["fuente"]
    if fuente == "datos_gob":
        return fetch_datos_gob(indicador["id"], start_date)
    if fuente == "argentinadatos":
        return fetch_argentinadatos(indicador["endpoint"], start_date)
    if fuente == "dolar":
        return fetch_dolar(indicador["casa"], start_date)
    if fuente == "bcra":
        return fetch_bcra(indicador["id_variable"], start_date)
    if fuente == "rem_bcra":
        return fetch_rem_variable(indicador["variable"], indicador["referencia"], start_date)
    raise ValueError(f"Fuente desconocida: {fuente}")

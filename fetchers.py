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
import xlrd
import pdfplumber

TIMEOUT = 30
# Sin tildes/caracteres no-ASCII a propósito: un User-Agent con "é" (mal codificado en la
# cabecera HTTP) causaba un 502 consistente y reproducible en api.bcra.gob.ar -- probado en
# vivo, era la causa real de que "Reservas internacionales (BCRA)" no se actualizara.
HEADERS = {"User-Agent": "coyuntura-tracker/1.0 (uso academico)"}


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
    # v4.0: [{"idVariable":1,"detalle":[{fecha,valor},...]}].
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
    Trae datos de la API del BCRA (Estadísticas Monetarias), sólo v4.0.

    id_variable: número de variable (ej: 1 para reservas internacionales diarias)
    Devuelve DataFrame con fecha (diaria) y valor.

    v3.0 y v2.0 quedaron confirmadas MUERTAS (410 Gone y 404 Not Found
    respectivamente, no "inestables" -- probado en vivo, nunca van a responder)
    y se sacaron del todo: antes cada corrida fallida desperdiciaba 12 de 18
    intentos pegándole a esos dos endpoints muertos en vez de reintentar contra
    la única versión viva. Resiliente a la inestabilidad conocida de v4.0 (502
    intermitentes, confirmado que a veces responde y a veces no incluso con la
    misma request repetida en minutos): prueba ventanas de fecha cada vez más
    cortas (2 años · 6 meses · 1 mes) y reintenta cada una varias veces con
    backoff. Si todo falla, loguea el error y devuelve un DataFrame vacío SIN
    tocar el histórico ya guardado (storage.py sólo agrega, nunca borra).
    """
    end_date = pd.Timestamp.today()
    ventanas_dias = [730, 180, 30]  # 2 años, 6 meses, 1 mes
    reintentos_por_ventana = 4
    filas = []
    ultimo_error = None

    for dias in ventanas_dias:
        desde = (end_date - pd.Timedelta(days=dias)).strftime("%Y-%m-%d")
        hasta = end_date.strftime("%Y-%m-%d")
        url = f"https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/{id_variable}"
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
                ultimo_error = f"v4.0 desde={desde}: {e}"
                time.sleep(2 * (intento + 1))  # backoff antes del próximo reintento
        if filas:
            break

    if not filas:
        print(f"  [ADVERTENCIA] fetch_bcra id_variable={id_variable}: sin datos tras probar "
              f"{len(ventanas_dias)} ventanas x {reintentos_por_ventana} reintentos (sólo v4.0, "
              f"v3.0/v2.0 confirmadas muertas). Último error: {ultimo_error}")
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
# 6) BCRA: componentes de "reservas ajustadas" (swap China + organismos internacionales)
# ---------------------------------------------------------------------------
BCRA_BALANCE_XLS_URL = "https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/Serieanual.xls"
BCRA_SDDS_URL_TPL = "https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/temp{mes:02d}{anio2:02d}.pdf"
ORGANISMOS_FRESCURA_DIAS = 7  # el balance semanal se actualiza ~4 veces por mes, no hace falta bajarlo a diario
SWAP_CHINA_INICIO = pd.Timestamp("2022-12-31")  # antes de esta fecha el swap no tiene fila propia en la planilla SDDS
_ORGANISMOS_CACHE_CSV = _CACHE_DIR / "_cache_organismos_internacionales.csv"
_ORGANISMOS_CACHE_META = _CACHE_DIR / "_cache_organismos_internacionales_meta.json"
_SWAP_CACHE_CSV = _CACHE_DIR / "_cache_swap_china.csv"


def fetch_bcra_organismos_internacionales() -> pd.DataFrame:
    """
    "Obligaciones con organismos internacionales" (BCRA, dataset del Balance
    Semanal -- Serie Anual de Balances Semanales, un único Excel histórico
    desde 1998, se actualiza ~4 veces por mes). El propio BCRA documenta este
    rubro como "las operaciones y cuentas de depósito del F.M.I., Banco
    Internacional de Pagos de Basilea (B.I.S.) y otros organismos" (más el
    Uso del Tramo de Reservas y su contrapartida) -- es un AGREGADO FMI+BIS+
    otros, no BIS aislado. Viene en miles de $ y se convierte a millones de
    USD con el tipo de cambio de referencia de la misma planilla.

    El archivo pesa ~1,8 MB: se cachea (mismo mecanismo que el REM) para no
    volver a descargarlo en cada corrida diaria sin necesidad.
    """
    completo = None
    if _ORGANISMOS_CACHE_META.exists() and _ORGANISMOS_CACHE_CSV.exists():
        try:
            meta = json.loads(_ORGANISMOS_CACHE_META.read_text(encoding="utf-8"))
            descargado = pd.to_datetime(meta.get("descargado"))
            if (pd.Timestamp.today().normalize() - descargado).days < ORGANISMOS_FRESCURA_DIAS:
                completo = pd.read_csv(_ORGANISMOS_CACHE_CSV, parse_dates=["fecha"])
        except (ValueError, KeyError, OSError, json.JSONDecodeError):
            completo = None

    if completo is None:
        completo = _descargar_y_transformar_organismos()
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        completo.to_csv(_ORGANISMOS_CACHE_CSV, index=False)
        _ORGANISMOS_CACHE_META.write_text(
            json.dumps({"descargado": pd.Timestamp.today().normalize().isoformat()}), encoding="utf-8")
    return completo[["fecha", "valor"]].reset_index(drop=True)


def _descargar_y_transformar_organismos() -> pd.DataFrame:
    r = _get(BCRA_BALANCE_XLS_URL)
    wb = xlrd.open_workbook(file_contents=r.content)
    filas = []
    for nombre_hoja in wb.sheet_names():
        if "serie semanal" not in nombre_hoja.lower():
            continue
        ws = wb.sheet_by_name(nombre_hoja)
        # Las filas se buscan por ETIQUETA (no por índice fijo): la posición cambia de año a año
        # dentro del mismo archivo. "startswith" (no "in") porque el activo tiene un rubro parecido
        # ("- Pago Obligaciones con Organismos Internacionales", un adelanto al Gobierno Nacional,
        # NADA que ver) que un simple "contiene" matchearía por error.
        fila_organismos = fila_tc = fila_fechas = None
        for r_ in range(ws.nrows):
            etiqueta = str(ws.cell_value(r_, 0)).strip().upper()
            if etiqueta.startswith("OBLIGACIONES CON ORGANISMOS") and fila_organismos is None:
                fila_organismos = r_
            if etiqueta == "TIPO DE CAMBIO" and fila_tc is None:
                fila_tc = r_
        for r_ in range(ws.nrows):
            v = ws.cell_value(r_, 1)
            if isinstance(v, float) and 20000 < v < 60000:  # rango plausible de fecha serial de Excel
                fila_fechas = r_
                break
        if fila_organismos is None or fila_tc is None or fila_fechas is None:
            continue
        for c in range(1, ws.ncols):
            serial, miles_pesos, tc = (ws.cell_value(fila_fechas, c), ws.cell_value(fila_organismos, c),
                                        ws.cell_value(fila_tc, c))
            if not (isinstance(serial, float) and isinstance(miles_pesos, float)
                    and isinstance(tc, float) and tc > 0):
                continue
            fecha = xlrd.xldate.xldate_as_datetime(serial, wb.datemode)
            filas.append({"fecha": fecha, "valor": miles_pesos * 1000 / tc / 1e6})
    df = pd.DataFrame(filas, columns=["fecha", "valor"])
    return df.drop_duplicates(subset="fecha").sort_values("fecha").reset_index(drop=True)


def _parse_num_ar(s) -> float | None:
    """'-17.869,31' -> -17869.31 (formato numérico argentino: punto de miles, coma decimal)."""
    if not s or not str(s).strip():
        return None
    try:
        return float(str(s).strip().replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _leer_swap_china_mes(periodo: pd.Period) -> float | None:
    """
    Descarga (si existe) la planilla mensual "Reservas Internacionales/Liquidez
    en Moneda Extranjera" (formato estándar SDDS del FMI) de un mes puntual y
    busca la fila "swaps de monedas" (sección II.2) en cualquier página de la
    tabla -- devuelve None si el mes todavía no se publicó (404) o si el PDF
    no tiene esa fila (versiones viejas, antes de dic-2022, donde el swap
    estaba mezclado con otra sección).
    """
    url = BCRA_SDDS_URL_TPL.format(mes=periodo.month, anio2=periodo.year % 100)
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200 or not r.content.startswith(b"%PDF"):
            return None
    except requests.RequestException:
        return None
    try:
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            for page in pdf.pages:
                for tabla in page.extract_tables():
                    for fila in tabla:
                        etiqueta = (fila[0] or "").replace("\n", " ").lower()
                        if "swaps de monedas" in etiqueta:
                            valor = _parse_num_ar(fila[2] if len(fila) > 2 else None)
                            if valor is not None:
                                return abs(valor)
    except Exception:
        return None
    return None


def fetch_bcra_swap_china() -> pd.DataFrame:
    """
    Posición de swap de monedas BCRA-PBOC (Banco Popular de China), sección
    II.2 ("swaps de monedas") de la planilla mensual SDDS del BCRA. Sólo
    tiene fila propia desde el cierre de dic-2022 (antes estaba mezclado con
    pases en otra sección, según nota del propio BCRA); no se rellena hacia
    atrás con ninguna otra fuente -- la serie arranca ahí y punto.

    Cachea cada mes ya conseguido de forma PERMANENTE en un CSV (los meses
    ya publicados no cambian retroactivamente): en cada corrida sólo intenta
    bajar los meses que todavía faltan en la caché (normalmente el último,
    a veces ninguno si el BCRA no publicó todavía el mes en curso).
    """
    cache = pd.DataFrame(columns=["fecha", "valor"])
    if _SWAP_CACHE_CSV.exists():
        cache = pd.read_csv(_SWAP_CACHE_CSV, parse_dates=["fecha"])

    meses_tenidos = set(cache["fecha"].dt.to_period("M")) if not cache.empty else set()
    mes_cursor = SWAP_CHINA_INICIO.to_period("M")
    mes_final = pd.Timestamp.today().to_period("M")
    nuevas = []
    while mes_cursor <= mes_final:
        if mes_cursor not in meses_tenidos:
            valor = _leer_swap_china_mes(mes_cursor)
            if valor is not None:
                nuevas.append({"fecha": mes_cursor.to_timestamp("M"), "valor": valor})
        mes_cursor += 1

    if nuevas:
        cache = pd.DataFrame(nuevas) if cache.empty else pd.concat([cache, pd.DataFrame(nuevas)], ignore_index=True)
        cache = cache.drop_duplicates(subset="fecha").sort_values("fecha")
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.to_csv(_SWAP_CACHE_CSV, index=False)
    return cache[["fecha", "valor"]].sort_values("fecha").reset_index(drop=True)

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

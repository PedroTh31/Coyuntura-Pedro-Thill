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
"""
from __future__ import annotations
import time
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
def fetch_datos_gob(serie_id: str, start_date: str | None = None) -> pd.DataFrame:
    """
    Trae una serie de la API de Series de Tiempo de la Nación.

    serie_id : id de la serie (ej '143.3_NO_PR_2004_A_21'). Buscalos con buscar_series.py
    """
    params = {"ids": serie_id, "format": "json", "limit": 5000}
    if start_date:
        params["start_date"] = start_date

    r = _get("https://apis.datos.gob.ar/series/api/series/", params=params)
    data = r.json().get("data", [])
    if not data:
        return pd.DataFrame(columns=["fecha", "valor"])

    df = pd.DataFrame(data, columns=["fecha", "valor"])
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    return df.dropna().sort_values("fecha").reset_index(drop=True)


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
    raise ValueError(f"Fuente desconocida: {fuente}")

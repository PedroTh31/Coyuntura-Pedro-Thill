"""
fuentes_mercados.py
-------------------
Fuentes de la pestaña Mercados que necesitan más que un fetch suelto (bloque MAE, decisiones de Pedro del
08/11/2026; diagnóstico en docs_internos/PENDIENTES.md #8, #13, #20, #22, #24):

1. Cauciones (MAE, `fuente: mae_caucion`): histórico de cierre `mercado/titulo/historicocauciones` (endpoint
   que usa el propio sitio marketdata.mae.com.ar, sin clave, no documentado oficialmente), hasta el día
   hábil anterior que informa el MAE (`mercado/fechahabilanterior`). Por día: la tasa promedio ponderada
   (`tasaPP`) del plazo MÁS CORTO operado ese día (001 de lunes a jueves, 003 los viernes, 004/006 antes de
   un feriado: el "1 día hábil"). Una tasa 0 o un monto 0 = sin dato (el campo `ultimo` que se leía antes
   viene siempre en 0 en el cierre, #13).
2. UST 10Y (`fuente: tesoro_ust`): CSV de la curva par del Tesoro de EE.UU. (daily_treasury_yield_curve, un
   archivo por año, columna "10 Yr") como principal y el H.15 de la Fed (RIFLGFCY10_N.B, la misma serie que
   el DGS10 de FRED) como respaldo. FRED se sacó: nunca respondió desde GitHub Actions (Akamai retiene la
   conexión sin contestar, #8). Si falla el Tesoro entra H.15 con alerta; si fallan los dos, el histórico
   queda como está, con alerta.
3. Extras de run.py (muro de vencimientos, dólar futuro): último dato válido en data/extras_ultimo.json.
   Si la fuente viene vacía, la card se arma con ese último dato + aviso (#20).
4. TIR y duración modificada de AL30/GD30/GD35 (`fuente: byma_bono`): cierres de BYMA + flujo de fondos del
   MAE, sólo días posteriores al último pago (BYMA ajusta hacia atrás sus cierres en cada pago); spread contra
   el Treasury interpolado a la duración modificada (`spread_duracion`). Sección 5 (#28).
5. Alertas a Pedro de todo lo anterior: como mucho 1 mail por corrida (enviar_alerta de fuentes_indec), el
   primer día de cada motivo y después una vez por semana mientras siga. Estado: data/mercados_estado.json.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd

import fetchers

RAIZ = Path(__file__).resolve().parent
ESTADO = RAIZ / "data" / "mercados_estado.json"
EXTRAS = RAIZ / "data" / "extras_ultimo.json"

AVISO_EXTRA_VACIO = "La fuente no devolvió datos en esta corrida"

# Motivos de alerta de ESTA corrida: (clave, texto). Los junta cada función y los manda cerrar_corrida().
ALERTAS: list[tuple[str, str]] = []
# Resumen de la corrida para ultima_corrida.json (clave `mercados`).
RESUMEN: dict = {}


def _alerta(clave: str, texto: str):
    print(f"::warning title=Mercados::{texto}")
    ALERTAS.append((clave, texto))


# ---------------------------------------------------------------------------------------------
# 1) Cauciones (MAE)
# ---------------------------------------------------------------------------------------------
CAUCION_INICIO = "2024-01-01"   # decisión de Pedro: la serie se reconstruye desde ene-2024
_CACHE_CAUCIONES: dict = {}


def fecha_habil_anterior(hoy: pd.Timestamp) -> pd.Timestamp:
    """Día hábil anterior a `hoy` según el MAE (mercado/fechahabilanterior)."""
    r = fetchers._get(f"{fetchers._MAE_BASE}/mercado/fechahabilanterior", params={"fecha": hoy.strftime("%Y-%m-%d")})
    return pd.Timestamp(r.json()["fechaHabilAnterior"]).normalize()


def caucion_del_dia(details: list[dict], ticker: str) -> dict | None:
    """Caución del plazo más corto OPERADO ese día para `ticker` ("CAARS" pesos, "CAUSD" dólares): tasa
    promedio ponderada (`tasaPP`) y monto concertado. Si el plazo tiene más de una fila (segmentos), la tasa
    es el promedio ponderado por monto. Tasa o monto en 0 = no operado (sin dato). None si no hay."""
    ops = []
    for d in details:
        if d.get("ticker") != ticker:
            continue
        try:
            tasa, monto, plazo = float(d.get("tasaPP") or 0), float(d.get("montoConcertado") or 0), int(d["plazo"])
        except (KeyError, TypeError, ValueError):
            continue
        if tasa > 0 and monto > 0:
            ops.append((plazo, tasa, monto))
    if not ops:
        return None
    corto = min(p for p, _, _ in ops)
    del_plazo = [(t, m) for p, t, m in ops if p == corto]
    monto = sum(m for _, m in del_plazo)
    return {"plazo": corto, "tasa": sum(t * m for t, m in del_plazo) / monto, "monto": monto}


def bajar_historico_cauciones(desde: pd.Timestamp, hasta: pd.Timestamp) -> list[dict]:
    """Días del histórico de cauciones del MAE entre `desde` y `hasta`, en ventanas de 3 meses (con 6 meses
    responde, con un año da 400: el endpoint tiene un tope de rango). Si una ventana falla, falla todo (nunca
    una historia con huecos)."""
    clave = (desde, hasta)
    if clave in _CACHE_CAUCIONES:
        return _CACHE_CAUCIONES[clave]
    dias, ini = [], desde
    while ini <= hasta:
        fin = min(ini + pd.DateOffset(months=3) - pd.Timedelta(days=1), hasta)
        o = json.dumps({"fechaDesde": ini.strftime("%Y-%m-%d"), "fechaHasta": fin.strftime("%Y-%m-%d")})
        r = fetchers._get(f"{fetchers._MAE_BASE}/mercado/titulo/historicocauciones", params={"oTitulo": o})
        data = r.json()
        if not isinstance(data, list):
            raise ValueError(f"historicocauciones {o}: respuesta inesperada ({type(data).__name__})")
        dias.extend(data)
        ini = fin + pd.Timedelta(days=1)
    _CACHE_CAUCIONES[clave] = dias
    return dias


def serie_caucion(ticker: str, desde: str | None = None) -> pd.DataFrame:
    """Serie diaria (fecha, valor) de la caución del plazo más corto de cada día, hasta el día hábil
    anterior que informa el MAE. Columnas extra `plazo` y `monto` (diagnóstico; run.py guarda sólo valor)."""
    hasta = fecha_habil_anterior(fetchers.hoy_ar())
    inicio = max(pd.Timestamp(desde or CAUCION_INICIO), pd.Timestamp(CAUCION_INICIO))
    filas = []
    for dia in bajar_historico_cauciones(inicio, hasta):
        c = caucion_del_dia(dia.get("details") or [], ticker)
        if c is not None:
            filas.append({"fecha": pd.Timestamp(dia["fecha"]).normalize(), "valor": c["tasa"],
                          "plazo": c["plazo"], "monto": c["monto"]})
    if not filas:
        return pd.DataFrame(columns=["fecha", "valor"])
    df = pd.DataFrame(filas).sort_values("fecha").drop_duplicates("fecha").reset_index(drop=True)
    df, fuera = filtrar_monto_minimo(df)
    for _, f in fuera.iterrows():
        print(f"  [info]   caución {ticker} {f['fecha']:%d/%m/%Y}: plazo {f['plazo']:03d} con ${f['monto'] / 1e6:,.0f} MM "
              f"({f['rel']:.1%} de la mediana de los {UMBRAL_MONTO_VENTANA} días previos): sin dato")
    return df


UMBRAL_MONTO_RELATIVO = 0.05   # decisión de Pedro del 08/11/2026
UMBRAL_MONTO_VENTANA = 20


def filtrar_monto_minimo(df: pd.DataFrame, umbral: float = UMBRAL_MONTO_RELATIVO,
                         ventana: int = UMBRAL_MONTO_VENTANA) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(días que quedan, días descartados). Un día cuyo plazo más corto operó menos del `umbral` de la mediana
    del monto de los `ventana` días operados previos (misma moneda: `df` es de un solo ticker) queda SIN DATO;
    no se lo sustituye por otro plazo. Con menos de 5 días previos (comienzo del histórico) no se filtra."""
    mediana = df["monto"].rolling(ventana, min_periods=5).median().shift(1)
    rel = df["monto"] / mediana
    malo = rel < umbral
    return df[~malo].reset_index(drop=True), df[malo].assign(rel=rel[malo]).reset_index(drop=True)


# ---------------------------------------------------------------------------------------------
# 2) Rendimiento del Treasury (Tesoro de EE.UU. + H.15 de la Fed)
# ---------------------------------------------------------------------------------------------
URL_TESORO = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
              "daily-treasury-rates.csv/{anio}/all")
URL_H15 = "https://www.federalreserve.gov/datadownload/Output.aspx"
H15_PAQUETE = "bf17364827e38702b42a58cf8eaa3f78"   # paquete H.15 de rendimientos del Tesoro (constant maturity)
H15_SERIE = {"10 Yr": "RIFLGFCY10_N.B", "6 Mo": "RIFLGFCM06_N.B", "1 Yr": "RIFLGFCY01_N.B", "2 Yr": "RIFLGFCY02_N.B",
             "3 Yr": "RIFLGFCY03_N.B"}   # ids verificados en la fila "Time Period" del CSV del H.15 (08/11/2026)
TESORO_INICIO = 1990   # primer año de la curva par diaria del Tesoro
_CACHE_UST: dict = {}


def parsear_tesoro(texto: str, plazo: str) -> pd.DataFrame:
    """CSV anual del Tesoro: 'Date' (MM/DD/AAAA) + una columna por plazo ("10 Yr")."""
    df = pd.read_csv(io.StringIO(texto))
    if "Date" not in df.columns or plazo not in df.columns:
        raise ValueError(f"CSV del Tesoro sin las columnas 'Date'/'{plazo}': {list(df.columns)[:6]}")
    out = pd.DataFrame({"fecha": pd.to_datetime(df["Date"], format="%m/%d/%Y"),
                        "valor": pd.to_numeric(df[plazo], errors="coerce")}).dropna()
    return out


def parsear_h15(texto: str, plazo: str) -> pd.DataFrame:
    """CSV del Data Download Program de la Fed: 5 filas de metadatos y la fila 'Time Period' con los ids."""
    lineas = texto.splitlines()
    i = next((k for k, l in enumerate(lineas) if l.startswith('"Time Period"')), None)
    if i is None:
        raise ValueError("CSV del H.15 sin la fila 'Time Period'")
    df = pd.read_csv(io.StringIO("\n".join(lineas[i:])))
    col = H15_SERIE[plazo]
    if col not in df.columns:
        raise ValueError(f"CSV del H.15 sin la serie {col}")
    return pd.DataFrame({"fecha": pd.to_datetime(df["Time Period"], errors="coerce"),
                         "valor": pd.to_numeric(df[col], errors="coerce")}).dropna()   # "ND" = sin dato


def fetch_tesoro(plazo: str, start_date: str | None = None) -> pd.DataFrame:
    """Un archivo por año desde el año de start_date (mín. 1990) hasta el actual. Falla si algún año falla."""
    hoy = fetchers.hoy_ar()
    anio0 = max(pd.Timestamp(start_date).year if start_date else TESORO_INICIO, TESORO_INICIO)
    partes = []
    for anio in range(anio0, hoy.year + 1):
        r = fetchers._get(URL_TESORO.format(anio=anio), params={
            "type": "daily_treasury_yield_curve", "field_tdr_date_value": anio, "page": "", "_format": "csv"})
        if anio == hoy.year or r.text.strip():
            partes.append(parsear_tesoro(r.text, plazo))
    df = pd.concat(partes, ignore_index=True)
    if start_date:
        df = df[df["fecha"] >= pd.Timestamp(start_date)]
    return df.sort_values("fecha").drop_duplicates("fecha").reset_index(drop=True)


def fetch_h15(plazo: str, start_date: str | None = None) -> pd.DataFrame:
    """H.15 de la Fed (Data Download Program). El rango necesita `from` Y `to` (MM/DD/AAAA) con las barras
    sin codificar: con `%2F`, o con sólo `from`, la Fed devuelve una respuesta vacía (verificado el 08/11/2026)."""
    desde = pd.Timestamp(start_date or "1990-01-01")
    hasta = fetchers.hoy_ar()
    url = (f"{URL_H15}?rel=H15&series={H15_PAQUETE}&lastobs=&from={desde:%m/%d/%Y}&to={hasta:%m/%d/%Y}"
           f"&filetype=csv&label=include&layout=seriescolumn")
    r = fetchers._get(url)
    df = parsear_h15(r.text, plazo)
    return df[df["fecha"] >= desde].sort_values("fecha").reset_index(drop=True)


def serie_ust(plazo: str = "10 Yr", start_date: str | None = None) -> pd.DataFrame:
    """Tesoro; si falla, H.15 con alerta; si fallan los dos, serie vacía con alerta (el histórico queda)."""
    if plazo in _CACHE_UST:
        return _CACHE_UST[plazo]
    try:
        df = fetch_tesoro(plazo, start_date)
        if df.empty:
            raise ValueError("el CSV del Tesoro no trajo filas")
        RESUMEN[f"ust:{plazo}"] = {"fuente": "tesoro", "ultimo": df["fecha"].max().date().isoformat()}
    except Exception as e_t:
        motivo_t = f"{type(e_t).__name__}: {e_t}"
        try:
            df = fetch_h15(plazo, start_date)
            if df.empty:
                raise ValueError("el CSV del H.15 no trajo filas")
            _alerta(f"ust:{plazo}:h15", f"UST {plazo}: falló el CSV del Tesoro ({motivo_t}); se usó el H.15 "
                                        f"de la Fed (último dato {df['fecha'].max().date()}).")
            RESUMEN[f"ust:{plazo}"] = {"fuente": "h15", "motivo": motivo_t,
                                       "ultimo": df["fecha"].max().date().isoformat()}
        except Exception as e_h:
            _alerta(f"ust:{plazo}:sin_datos", f"UST {plazo}: fallaron el Tesoro ({motivo_t}) y el H.15 de la Fed "
                                              f"({type(e_h).__name__}: {e_h}); el histórico guardado queda intacto.")
            RESUMEN[f"ust:{plazo}"] = {"fuente": "error", "motivo": motivo_t}
            df = pd.DataFrame(columns=["fecha", "valor"])
    _CACHE_UST[plazo] = df
    return df


# ---------------------------------------------------------------------------------------------
# 3) Último dato válido de los extras de run.py (muro, dólar futuro)
# ---------------------------------------------------------------------------------------------
def _leer_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _escribir_json(path: Path, datos: dict):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(datos, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def extra_con_respaldo(nombre: str, ec: dict | None, hoy: pd.Timestamp) -> tuple[dict | None, pd.Timestamp | None]:
    """(extra a mostrar, fecha de su dato). Con dato nuevo lo guarda como último válido; sin dato, devuelve
    el último válido (o None si nunca hubo) con el aviso y deja la alerta para Pedro."""
    guardados = _leer_json(EXTRAS)
    if ec is not None:
        guardados[nombre] = {"fecha": hoy.date().isoformat(), "extra": ec}
        _escribir_json(EXTRAS, guardados)
        RESUMEN[f"extra:{nombre}"] = {"estado": "ok"}
        return ec, hoy
    previo = guardados.get(nombre)
    if previo is None:
        _alerta(f"extra:{nombre}", f"{nombre}: la fuente no devolvió datos y no hay un dato anterior guardado; "
                                   f"la card no se publica.")
        RESUMEN[f"extra:{nombre}"] = {"estado": "sin_datos"}
        return None, None
    fecha = pd.Timestamp(previo["fecha"])
    _alerta(f"extra:{nombre}", f"{nombre}: la fuente no devolvió datos en esta corrida; se muestra el último "
                               f"dato válido, del {fecha:%d/%m/%Y}.")
    RESUMEN[f"extra:{nombre}"] = {"estado": "respaldo", "fecha": previo["fecha"]}
    ec = dict(previo["extra"])
    ec["card"] = dict(ec["card"], aviso=AVISO_EXTRA_VACIO)
    return ec, fecha


# ---------------------------------------------------------------------------------------------
# 4) Cierre de la corrida: un mail a Pedro como mucho
# ---------------------------------------------------------------------------------------------
def a_avisar(avisos: dict, alertas: list[tuple[str, str]], activas_previas: list[str], hoy: str) -> list[tuple[str, str]]:
    """Las alertas que tocan hoy (función pura): un motivo nuevo (no estaba activo en la corrida anterior)
    sale siempre; uno que sigue, una vez por semana."""
    from fuentes_indec import _toca_aviso, DIAS_REPETICION
    return [(c, t) for c, t in alertas
            if c not in activas_previas or _toca_aviso(avisos, c, hoy, DIAS_REPETICION)]


def cerrar_corrida() -> dict:
    from fuentes_indec import _hoy, enviar_alerta
    hoy = _hoy()
    estado = _leer_json(ESTADO)
    avisos = estado.setdefault("avisos", {})
    items = a_avisar(avisos, ALERTAS, estado.get("activas", []), hoy)
    if items and enviar_alerta("[Coyuntura] Mercados: " + "; ".join(t.split(":")[0] for _, t in items),
                               "\n\n".join(t for _, t in items) + "\n\nEstado: data/mercados_estado.json en el repo.",
                               titulo="Mercados"):
        for clave, _ in items:
            avisos[clave] = hoy
    estado["activas"] = sorted({c for c, _ in ALERTAS})
    estado["ultima"] = {"fecha": hoy, "resumen": RESUMEN}
    _escribir_json(ESTADO, estado)
    return dict(RESUMEN, alertas=[t for _, t in ALERTAS])


# ---------------------------------------------------------------------------------------------
# 5) TIR de bonos hard-dollar: cierres de BYMA + flujo de fondos del MAE (#28)
# ---------------------------------------------------------------------------------------------
# Decisión de Pedro del 08/11/2026. Convención: TIR efectiva anual, base ACT/365, liquidación T+1 hábil,
# precio = cierre (`c`) de BYMA de "<ticker>D 24HS" tal cual (sin sumar cupón corrido), flujos del MAE por 100
# de VN original (`emisiones/flujofondos/{ticker}`, campo cashFlow). EN REVISIÓN hasta verificarla contra el
# snapshot del MAE (precio + TIR + MD juntos): tests/manual_verificar_tir_mae.py, PENDIENTES #28.
#
# BYMA ajusta hacia atrás su serie de cierres en cada pago de renta/amortización (verificado el 08/11/2026:
# sin caída de precio en los pagos de jul-2025, ene-2026 y jul-2026; GD30 a 49,3 en BYMA y 73 en el MAE el
# 03/12/2024). Por eso sólo se calculan los días POSTERIORES al último pago: los anteriores, ya guardados,
# no se recalculan nunca (el merge de storage los conserva tal cual).
BYMA_HISTORIA = f"{fetchers._BYMA_BASE}/chart/historical-series/history"
BONO_DESDE = "2026-07-10"   # día hábil siguiente al último pago de AL30/GD30/GD35 (09/07/2026)
PLAZO_ANIOS = {"1 Mo": 1 / 12, "3 Mo": 0.25, "6 Mo": 0.5, "1 Yr": 1.0, "2 Yr": 2.0, "3 Yr": 3.0,
               "5 Yr": 5.0, "7 Yr": 7.0, "10 Yr": 10.0}
_CACHE_BONOS: dict = {}


def flujos_bono(ff: dict) -> list[tuple[pd.Timestamp, float]]:
    """(fecha de pago, cashFlow por 100 de VN original) del flujo de fondos del MAE, ordenado."""
    return sorted((pd.Timestamp(x["fechaPago"][:10]), float(x["cashFlow"])) for x in ff["detalle"])


def ultimo_pago(flujos: list[tuple[pd.Timestamp, float]], hoy: pd.Timestamp) -> pd.Timestamp:
    """Fecha del último pago ya hecho. Si el MAE todavía lista un pago con fecha <= hoy, ése; si ya lo sacó,
    el primer pago futuro menos el período entre los dos primeros (semestral en AL30/GD30/GD35)."""
    pasados = [f for f, _ in flujos if f <= hoy]
    if pasados:
        return max(pasados)
    fechas = [f for f, _ in flujos]
    if len(fechas) < 2:
        raise ValueError("flujo de fondos con menos de 2 pagos: no se puede deducir el último pago")
    meses = round((fechas[1] - fechas[0]).days / 30.44)
    return fechas[0] - pd.DateOffset(months=meses)


def _futuros(flujos, liq):
    fl = [(f, cf) for f, cf in flujos if f > liq]
    if not fl:
        raise ValueError(f"sin pagos posteriores a la liquidación {liq:%d/%m/%Y}")
    return [(f - liq).days / 365 for f, _ in fl], [cf for _, cf in fl]


def tir_efectiva(precio: float, liq: pd.Timestamp, flujos: list[tuple[pd.Timestamp, float]]) -> float:
    """TIR efectiva anual (%), ACT/365: precio = Σ CF_i / (1 + TIR)^(días_i / 365), días desde la liquidación,
    sólo pagos posteriores a la liquidación. Bisección (el valor presente decrece con la tasa)."""
    t, cf = _futuros(flujos, liq)

    def exceso(y):
        return sum(c / (1 + y) ** ti for c, ti in zip(cf, t)) - precio

    a, b = -0.99, 10.0
    if exceso(a) < 0 or exceso(b) > 0:
        raise ValueError(f"precio {precio} fuera de rango para el flujo")
    for _ in range(200):
        m = (a + b) / 2
        if exceso(m) > 0:
            a = m
        else:
            b = m
        if b - a < 1e-12:
            break
    return (a + b) / 2 * 100


def duracion_modificada(tir_pct: float, liq: pd.Timestamp, flujos: list[tuple[pd.Timestamp, float]]) -> float:
    """MD (años) = duración de Macaulay / (1 + TIR), con la misma convención que tir_efectiva."""
    y = tir_pct / 100
    t, cf = _futuros(flujos, liq)
    vp = [c / (1 + y) ** ti for c, ti in zip(cf, t)]
    return sum(ti * v for ti, v in zip(t, vp)) / sum(vp) / (1 + y)


def fetch_byma_cierres(ticker: str, desde: pd.Timestamp) -> pd.DataFrame:
    """Cierres diarios de "<ticker>D 24HS" en BYMA (fecha, precio). Mismo endpoint gratuito y mismo criterio de
    certificado que fetch_byma_indice (verify=False). Sólo responde el plazo 24HS (CI/48HS: no_data)."""
    import time

    import requests
    params = {"symbol": f"{ticker}D 24HS", "resolution": "D", "from": int(pd.Timestamp(desde).timestamp()),
              "to": int(time.time())}
    ultimo = None
    for intento in range(3):
        try:
            r = requests.get(BYMA_HISTORIA, params=params, headers=fetchers.HEADERS, timeout=fetchers.TIMEOUT,
                             verify=False)
            r.raise_for_status()
            data = r.json()
            break
        except (requests.RequestException, ValueError) as e:
            ultimo = e
            time.sleep(2 * (intento + 1))
    else:
        raise RuntimeError(f"BYMA {ticker}D 24HS: {ultimo}")
    if data.get("s") not in ("ok", "no_data"):
        raise RuntimeError(f"BYMA {ticker}D 24HS: respuesta {data.get('s')!r}")
    fechas = (pd.to_datetime(pd.Series(data.get("t") or [], dtype="int64"), unit="s", utc=True)
              .dt.tz_convert("America/Argentina/Buenos_Aires").dt.tz_localize(None).dt.normalize())
    df = pd.DataFrame({"fecha": fechas, "precio": pd.to_numeric(pd.Series(data.get("c") or [], dtype=float))})
    return df[df["precio"] > 0].sort_values("fecha").reset_index(drop=True)


def calcular_bono(cierres: pd.DataFrame, flujos, desde: pd.Timestamp, hoy: pd.Timestamp,
                  no_habiles: set) -> pd.DataFrame:
    """TIR y MD por día hábil (función pura). Sólo días posteriores al último pago y >= `desde`: antes de un
    pago, BYMA reescribe los cierres ajustados, y esos días ya guardados no se tocan."""
    import calendario_indec
    corte = max(pd.Timestamp(desde), ultimo_pago(flujos, hoy) + pd.Timedelta(days=1))
    filas = []
    for f, p in zip(cierres["fecha"], cierres["precio"]):
        if f < corte or f > hoy or not calendario_indec.es_habil(f.date(), no_habiles):
            continue
        liq = pd.Timestamp(calendario_indec.sumar_dias_habiles(f.date(), 1, no_habiles))
        tir = tir_efectiva(float(p), liq, flujos)
        filas.append({"fecha": f, "tir": tir, "md": duracion_modificada(tir, liq, flujos)})
    return pd.DataFrame(filas, columns=["fecha", "tir", "md"])


def serie_bono(ticker: str, campo: str = "tir", desde: str | None = None) -> pd.DataFrame:
    """`fuente: byma_bono` -> fecha | valor (campo "tir" en % anual o "md" en años). Vacía (con aviso en el
    log) si falla BYMA o el flujo del MAE: el histórico guardado queda como está."""
    if campo not in ("tir", "md"):
        raise ValueError(f"byma_bono: campo {campo!r} (tir|md)")
    if ticker not in _CACHE_BONOS:
        import calendario_indec
        try:
            ff = fetchers.fetch_mae_flujofondos_ticker(ticker)
            if ff is None:
                raise RuntimeError("el MAE no devolvió el flujo de fondos")
            flujos = flujos_bono(ff)
            hoy = fetchers.hoy_ar()
            no_habiles = calendario_indec.feriados(calendario_indec.cargar_config())
            corte = max(pd.Timestamp(desde or BONO_DESDE), ultimo_pago(flujos, hoy) + pd.Timedelta(days=1))
            df = calcular_bono(fetch_byma_cierres(ticker, corte), flujos, corte, hoy, no_habiles)
            RESUMEN[f"bono:{ticker}"] = {"filas": len(df), "desde": corte.date().isoformat(),
                                         "ultimo": df["fecha"].max().date().isoformat() if len(df) else None}
        except Exception as e:
            print(f"  [ADVERTENCIA] byma_bono {ticker}: {type(e).__name__}: {e}")
            RESUMEN[f"bono:{ticker}"] = {"error": f"{type(e).__name__}: {e}"}
            df = pd.DataFrame(columns=["fecha", "tir", "md"])
        _CACHE_BONOS[ticker] = df
    df = _CACHE_BONOS[ticker]
    return df[["fecha", campo]].rename(columns={campo: "valor"}).reset_index(drop=True)


def spread_duracion(tir: pd.DataFrame, md: pd.DataFrame, ust: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Spread (pb) de la TIR de un bono contra el Treasury interpolado lineal en plazo a su duración
    modificada (función pura). `ust` = {plazo del CSV del Tesoro ("6 Mo", "1 Yr", ...): fecha | valor}.
    Para cada fecha del bono se toma el último dato de cada plazo a esa fecha o antes (merge_asof, tolerancia
    5 días: el Tesoro publica con el calendario de EE.UU.); con una MD fuera del rango de los plazos se usa el
    plazo extremo (sin extrapolar)."""
    import numpy as np
    s = tir.rename(columns={"valor": "tir"}).merge(md.rename(columns={"valor": "md"}), on="fecha")
    s["fecha"] = pd.to_datetime(s["fecha"])
    s = s.sort_values("fecha")
    plazos = sorted(ust, key=lambda p: PLAZO_ANIOS[p])
    for p in plazos:
        u = ust[p].rename(columns={"valor": p}).assign(fecha=lambda d: pd.to_datetime(d["fecha"])).sort_values("fecha")
        s = pd.merge_asof(s, u[["fecha", p]], on="fecha", direction="backward", tolerance=pd.Timedelta(days=5))
    s = s.dropna(subset=["tir", "md"] + plazos)
    if s.empty:
        return pd.DataFrame(columns=["fecha", "valor"])
    xs = [PLAZO_ANIOS[p] for p in plazos]
    s["ust"] = [float(np.interp(m, xs, fila)) for m, fila in zip(s["md"], s[plazos].to_numpy(dtype=float))]
    s["valor"] = (s["tir"] - s["ust"]) * 100
    return s[["fecha", "valor"]].reset_index(drop=True)

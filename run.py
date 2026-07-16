"""
run.py  ·  Punto de entrada.  Corré:  python run.py

Flujo:
  1. lee indicadores.yaml
  2. trae cada serie de su fuente (con la historia completa)
  3. calcula las series DERIVADAS (M1 = suma de componentes; salario real = nominal/IPC)
  4. mergea con el histórico guardado (sin perder datos viejos)
  5. regenera los CSV (largo + ancho) y el dashboard HTML
"""
from pathlib import Path
import yaml
import pandas as pd

from fetchers import traer, fetch_datos_gob, fetch_dolar
import storage
import dashboard

RAIZ = Path(__file__).resolve().parent
CONFIG = RAIZ / "indicadores.yaml"


def _fila(serie, ind):
    return (serie.assign(indicador=ind["nombre"], bloque=ind["bloque"],
                         unidad=ind.get("unidad", ""))
            [["fecha", "indicador", "bloque", "unidad", "valor"]])


def _calcular(ind, start):
    """Series derivadas: 'suma' (ej. M1) o 'real' (ej. salario real deflactado por IPC)."""
    tipo = ind["calculo"]
    if tipo == "suma":
        partes = [fetch_datos_gob(cid, start) for cid in ind["componentes"]]
        s = partes[0].rename(columns={"valor": "v0"})[["fecha", "v0"]]
        for k, d in enumerate(partes[1:], 1):
            s = s.merge(d.rename(columns={"valor": f"v{k}"})[["fecha", f"v{k}"]],
                        on="fecha", how="inner")
        cols = [c for c in s.columns if c.startswith("v")]
        s["valor"] = s[cols].sum(axis=1)
        return s[["fecha", "valor"]]
    if tipo == "real":
        nom = fetch_datos_gob(ind["nominal_id"], start).rename(columns={"valor": "nom"})
        ipc = fetch_datos_gob(ind["deflactor_id"], start).rename(columns={"valor": "ipc"})
        s = nom.merge(ipc, on="fecha", how="inner")
        s = s[s["ipc"] > 0].sort_values("fecha")
        if s.empty:
            return s.assign(valor=[])[["fecha", "valor"]]
        s["valor"] = s["nom"] / s["ipc"]
        s["valor"] = s["valor"] / s["valor"].iloc[0] * 100   # base 100 al inicio de la serie
        return s[["fecha", "valor"]]
    if tipo == "brecha":
        # brecha = (paralelo / oficial - 1) * 100, sobre cotizaciones diarias
        alto = fetch_dolar(ind["casa_alta"], start).rename(columns={"valor": "alto"})
        base = fetch_dolar(ind["casa_base"], start).rename(columns={"valor": "base"})
        s = alto.merge(base, on="fecha", how="inner").sort_values("fecha")
        s = s[s["base"] > 0]
        s["valor"] = (s["alto"] / s["base"] - 1) * 100
        return s[["fecha", "valor"]]
    if tipo == "interanual":
        # Variación interanual: (valor_t / valor_t-12m - 1) * 100 (o -1año si frecuencia no es mensual)
        base_id = ind.get("base_id")
        if not base_id:
            raise ValueError(f"Cálculo 'interanual' requiere 'base_id' en {ind['nombre']}")
        s = fetch_datos_gob(base_id, start).sort_values("fecha").copy()
        s = s[s["valor"] > 0]
        if len(s) < 2:
            return s.assign(valor=[])[["fecha", "valor"]]
        # Crear serie lagged (12 meses antes)
        s_prev = s.rename(columns={"valor": "valor_prev"})[["fecha", "valor_prev"]].copy()
        s_prev["fecha"] = s_prev["fecha"] + pd.DateOffset(years=1)
        m = pd.merge_asof(s, s_prev, on="fecha", direction="nearest", tolerance=pd.Timedelta(days=20))
        m = m.dropna(subset=["valor_prev"])
        m = m[m["valor_prev"] > 0]
        m["valor"] = (m["valor"] / m["valor_prev"] - 1) * 100
        return m[["fecha", "valor"]].dropna().reset_index(drop=True)
    if tipo == "mensual":
        # Variación mes a mes: (valor_t / valor_t-1 - 1) * 100, de un índice de nivel
        base_id = ind.get("base_id")
        if not base_id:
            raise ValueError(f"Cálculo 'mensual' requiere 'base_id' en {ind['nombre']}")
        s = fetch_datos_gob(base_id, start).sort_values("fecha").copy()
        s = s[s["valor"] > 0]
        s["valor"] = s["valor"].pct_change() * 100
        return s[["fecha", "valor"]].dropna().reset_index(drop=True)
    if tipo == "variacion_real_mensual":
        # Variación % mensual REAL: deflacta la serie nominal por IPC antes de calcular la
        # variación mes a mes, con media móvil opcional (en meses) para suavizar.
        nominal_id = ind.get("nominal_id")
        deflactor_id = ind.get("deflactor_id")
        if not nominal_id or not deflactor_id:
            raise ValueError(f"Cálculo 'variacion_real_mensual' requiere 'nominal_id' y 'deflactor_id' en {ind['nombre']}")
        nom = fetch_datos_gob(nominal_id, start).rename(columns={"valor": "nom"})
        ipc = fetch_datos_gob(deflactor_id, start).rename(columns={"valor": "ipc"})
        s = nom.merge(ipc, on="fecha", how="inner").sort_values("fecha")
        s = s[s["ipc"] > 0]
        s["real"] = s["nom"] / s["ipc"]
        s["valor"] = s["real"].pct_change() * 100
        ventana = ind.get("media_movil")
        if ventana:
            s["valor"] = s["valor"].rolling(ventana, min_periods=ventana).mean()
        return s[["fecha", "valor"]].dropna().reset_index(drop=True)
    if tipo == "combinado":
        # Promedio ponderado de varios índices de nivel (ej. sectores del EMAE agrupados en
        # "Urbano"/"Rural"), con rebase opcional a una fecha y media móvil opcional.
        # 'componentes': [{"id": "...", "peso": 0.58}, ...] — los pesos NO necesitan sumar 1
        # (se renormalizan acá), así se puede pasar el peso ya ponderado dentro del grupo.
        componentes = ind.get("componentes")
        if not componentes:
            raise ValueError(f"Cálculo 'combinado' requiere 'componentes' en {ind['nombre']}")
        suma_pesos = sum(c["peso"] for c in componentes)
        partes = [fetch_datos_gob(c["id"], start).rename(columns={"valor": "v"}) for c in componentes]
        s = partes[0][["fecha", "v"]].rename(columns={"v": "v0"})
        for k, d in enumerate(partes[1:], 1):
            s = s.merge(d.rename(columns={"v": f"v{k}"}), on="fecha", how="inner")
        s["valor"] = sum(s[f"v{k}"] * (componentes[k]["peso"] / suma_pesos) for k in range(len(componentes)))
        s = s[["fecha", "valor"]].sort_values("fecha")
        ventana = ind.get("media_movil")
        if ventana:
            s["valor"] = s["valor"].rolling(ventana, min_periods=ventana).mean()
            s = s.dropna(subset=["valor"])
        rebase_fecha = ind.get("rebase_fecha")
        if rebase_fecha:
            ref = s.loc[s["fecha"] == pd.to_datetime(rebase_fecha), "valor"]
            if len(ref):
                s["valor"] = s["valor"] / ref.iloc[0] * 100
        return s[["fecha", "valor"]].dropna().reset_index(drop=True)
    raise ValueError(f"cálculo desconocido: {tipo}")


def _avisar(nombre: str, motivo: str, titulo: str = "Indicador sin datos"):
    """Advertencia visible: imprime en el log Y emite una anotación de GitHub
    Actions (aparece en el resumen del run, sin tener que abrir el log)."""
    print(f"  [ADVERTENCIA]  {nombre}: {motivo}")
    print(f"::warning title={titulo}::{nombre} — {motivo}")


MULTIPLICADOR_REZAGO = 4  # tolerancia: n veces el intervalo típico entre observaciones
PISO_DIAS_REZAGO = 14     # nunca avisar antes de esto, ni para series diarias


def chequear_frescura(historico: pd.DataFrame, indicadores: list[dict]):
    """
    Compara la última fecha de cada serie contra su propia frecuencia habitual
    (mediana de intervalos entre observaciones en los últimos 2 años) y avisa
    si el rezago actual supera esa frecuencia por un margen amplio. Data-driven
    por indicador (no una frecuencia fija por nombre) para tolerar los rezagos
    normales de publicación de INDEC/BCRA (ej. EMAE suele publicarse con ~2-3
    meses de rezago) sin generar falsos positivos.

    Los indicadores marcados 'marca_fecha: true' en el yaml (discontinuaciones
    ya documentadas y con nota, ej. tasa de política monetaria) se excluyen:
    ya avisan de otra forma (nota + badge en el dashboard) y no deben generar
    ruido repetido en cada corrida.

    Un indicador puede declarar 'rezago_normal_dias: N' si tiene un rezago de
    publicación estructural conocido y documentado en su 'nota' (ej. el TCR
    multilateral depende del IPC de varios países y llega ~5-6 meses tarde
    de forma sistemática, no por una falla puntual); ese valor pone un piso
    adicional al umbral para no repetir la misma alerta todos los días.
    """
    hoy = pd.Timestamp.today().normalize()
    nombres_excluidos = {ind["nombre"] for ind in indicadores if ind.get("marca_fecha")}
    rezago_normal = {ind["nombre"]: ind["rezago_normal_dias"] for ind in indicadores if ind.get("rezago_normal_dias")}
    rezagados = []

    for nombre, g in historico.groupby("indicador"):
        if nombre in nombres_excluidos:
            continue
        g = g.sort_values("fecha")
        ultima = g["fecha"].max()
        dias_atraso = (hoy - ultima).days

        reciente = g[g["fecha"] >= ultima - pd.DateOffset(years=2)]
        gaps = reciente["fecha"].diff().dt.days.dropna()
        gap_tipico = gaps.median() if len(gaps) >= 2 else None
        umbral = max(gap_tipico * MULTIPLICADOR_REZAGO, PISO_DIAS_REZAGO) if gap_tipico else 45
        umbral = max(umbral, rezago_normal.get(nombre, 0))

        if dias_atraso > umbral:
            motivo = (f"último dato del {ultima.date()}, {dias_atraso} días de rezago "
                      f"(umbral tolerado ~{round(umbral)} días para su frecuencia habitual)")
            _avisar(nombre, motivo, titulo="Serie con rezago anormal")
            rezagados.append((nombre, dias_atraso, round(umbral)))

    if rezagados:
        print(f"\n{len(rezagados)} indicador(es) con rezago mayor al esperado (chequeo de frescura):")
        for nombre, dias, umbral in rezagados:
            print(f"  - {nombre}: {dias} días de rezago (umbral ~{umbral})")
    return rezagados


UMBRAL_FRACCION_SIN_ESCALAR = 1.5  # si una serie en "%" nunca supera esto, probablemente es 0-1 sin *100
UMBRAL_CAMBIO_ESCALA = 50          # ratio (o su inverso) a partir del cual se avisa un salto de orden de magnitud


def chequear_plausibilidad(historico: pd.DataFrame, indicadores: list[dict]):
    """
    Detecta el mismo tipo de error que 'Tasa de desempleo' tenía (fuente publica una
    tasa como fracción 0-1 pese a declararla en '%'), para que no haga falta encontrarlo
    a mano de nuevo. Dos chequeos:

    1. Fracción sin escalar: si 'unidad' contiene '%' y el máximo histórico absoluto de
       la serie nunca supera ~1.5, es sospechoso — una serie realmente en puntos
       porcentuales casi siempre cruza el 1% alguna vez en su historia.
    2. Cambio abrupto de escala entre corridas: si la fuente cambia de convención (ej.
       empieza a publicar en otra unidad) el valor de una misma fecha ya existente puede
       aparecer multiplicado/dividido por ~100 respecto a lo que ya teníamos guardado.
    """
    sospechosos = []
    for ind in indicadores:
        unidad = (ind.get("unidad") or "")
        if "%" not in unidad:
            continue
        nombre = ind["nombre"]
        g = historico[historico["indicador"] == nombre]
        if g.empty:
            continue
        maximo = g["valor"].abs().max()
        if maximo < UMBRAL_FRACCION_SIN_ESCALAR:
            motivo = (f"unidad declarada '{unidad}' pero el máximo histórico es {maximo:.4g} "
                      f"(nunca superó {UMBRAL_FRACCION_SIN_ESCALAR}) — probable fracción sin escalar (¿falta 'factor: 100'?)")
            _avisar(nombre, motivo, titulo="Posible fracción sin escalar")
            sospechosos.append(nombre)
    return sospechosos


def chequear_cambio_escala(previo: pd.DataFrame, nuevos: pd.DataFrame):
    """
    Compara, para las fechas que YA estaban guardadas y volvieron a traerse esta
    corrida, el valor viejo contra el nuevo. Si difieren por un factor grande
    (~100x, ~0.01x, etc.) en vez de ser iguales o levemente distintos (una fuente
    puede corregir un dato), es señal de que la fuente cambió de escala/unidad de
    un día para el otro.
    """
    saltos = []
    comunes = previo.merge(nuevos, on=["fecha", "indicador"], suffixes=("_previo", "_nuevo"))
    comunes = comunes[(comunes["valor_previo"].abs() > 1e-9) & (comunes["valor_nuevo"].abs() > 1e-9)]
    if comunes.empty:
        return saltos
    comunes["ratio"] = comunes["valor_nuevo"] / comunes["valor_previo"]
    for nombre, g in comunes.groupby("indicador"):
        ratio_mediana = g["ratio"].median()
        if ratio_mediana > UMBRAL_CAMBIO_ESCALA or ratio_mediana < 1 / UMBRAL_CAMBIO_ESCALA:
            motivo = (f"el valor de fechas ya guardadas cambió ~{ratio_mediana:.3g}x respecto a lo que "
                      f"había ({len(g)} fecha(s) comparada(s)) — posible cambio de escala/unidad en la fuente")
            _avisar(nombre, motivo, titulo="Cambio abrupto de escala")
            saltos.append(nombre)
    return saltos


def main():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    start = cfg.get("start_date")
    indicadores = cfg["indicadores"]
    filas = []
    problemas = []  # (nombre, motivo) de indicadores que no trajeron datos

    for ind in indicadores:
        nombre = ind["nombre"]
        if ind.get("vista") in ("overlay", "incidencia_stack", "burbujas"):
            continue  # no trae datos propios: dashboard.py lo arma referenciando otros indicadores
        try:
            if "calculo" in ind:
                serie = _calcular(ind, start)
            else:
                serie = traer(ind, start_date=start)
            if serie.empty:
                _avisar(nombre, "la fuente no devolvió datos (serie vacía)")
                problemas.append((nombre, "vacío"))
                continue
            if ind.get("factor"):
                serie = serie.assign(valor=serie["valor"] * ind["factor"])
            filas.append(_fila(serie, ind))
            print(f"  [ok]     {nombre}  ({len(serie)} obs, ult. {serie['fecha'].max().date()})")
        except Exception as e:
            _avisar(nombre, f"error al traer/calcular la serie: {e}")
            problemas.append((nombre, f"error: {e}"))

    if problemas:
        print(f"\n{len(problemas)} indicador(es) sin datos en esta corrida:")
        for nombre, motivo in problemas:
            print(f"  - {nombre}: {motivo}")
        print("(el histórico ya guardado de esos indicadores NO se toca; se reintentará en la próxima corrida)")

    if not filas:
        print("No se trajo ningun dato.")
        return

    nuevos = pd.concat(filas, ignore_index=True)
    previo = storage.cargar_largo()
    chequear_cambio_escala(previo, nuevos)
    historico = storage.actualizar(nuevos)
    print(f"\nHistorico total: {len(historico)} filas, "
          f"{historico['indicador'].nunique()} indicadores.")
    chequear_frescura(historico, indicadores)
    chequear_plausibilidad(historico, indicadores)
    dashboard.generar(historico, indicadores)
    print("Listo -> data/series_largo.csv, data/series_ancho.csv, docs/index.html")


if __name__ == "__main__":
    main()

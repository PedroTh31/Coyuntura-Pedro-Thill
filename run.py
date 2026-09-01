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

from fetchers import (traer, fetch_datos_gob, fetch_dolar, fetch_bcra,
                       fetch_bcra_organismos_internacionales, fetch_bcra_swap_china,
                       fetch_deuda_bruta, fetch_mae_ddf, fetch_mae_bono_campo, fetch_mae_flujofondos,
                       fetch_fred, fetch_data912)
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
    if tipo == "resta":
        a = fetch_datos_gob(ind["minuendo_id"], start).rename(columns={"valor": "a"})
        b = fetch_datos_gob(ind["sustraendo_id"], start).rename(columns={"valor": "b"})
        s = a.merge(b, on="fecha", how="inner")
        s["valor"] = s["a"] - s["b"]
        return s[["fecha", "valor"]]
    if tipo == "ratio":
        # Cociente de dos series de datos_gob (ej. salario / costo de una canasta):
        # numerador_id / denominador_id, sin rebase ni indexar -- el valor crudo del
        # cociente es la unidad que importa (ej. "canastas que compra un salario").
        num = fetch_datos_gob(ind["numerador_id"], start).rename(columns={"valor": "num"})
        den = fetch_datos_gob(ind["denominador_id"], start).rename(columns={"valor": "den"})
        s = num.merge(den, on="fecha", how="inner").sort_values("fecha")
        s = s[s["den"] > 0]
        s["valor"] = s["num"] / s["den"]
        return s[["fecha", "valor"]].dropna().reset_index(drop=True)
    if tipo == "deuda_pbi":
        # Deuda pública bruta (USD, mensual, fetch_deuda_bruta) / PBI nominal (pesos
        # corrientes, trimestral, id en 'pbi_id') convertido a USD con el tipo de cambio
        # OFICIAL PROMEDIO de cada trimestre (decisión de Pedro: promedio trimestral, no
        # tipo de cambio de cierre -- mismo criterio que usan comparaciones internacionales
        # tipo FMI, evita que un salto puntual del dólar en la fecha de corte distorsione
        # el ratio). Resultado en %. No es un 'calculo' genérico como 'ratio': mezcla 3
        # fuentes de frecuencias distintas (mensual/trimestral/diaria) con una conversión
        # de moneda de por medio, específico para este ratio.
        deuda = fetch_deuda_bruta(start).rename(columns={"valor": "deuda_usd"})
        pbi = fetch_datos_gob(ind["pbi_id"], start).rename(columns={"valor": "pbi_ars"}).sort_values("fecha")
        dolar = fetch_dolar("oficial", start).sort_values("fecha")
        tc_prom_trim = dolar.set_index("fecha")["valor"].resample("QS").mean()
        pbi["tc_prom"] = pbi["fecha"].map(tc_prom_trim)
        # La deuda es mensual: se toma el mes de CIERRE de cada trimestre (stock a fin de
        # período, mismo criterio de "foto" que usa el resto del proyecto para stocks).
        pbi["fecha_deuda"] = pbi["fecha"] + pd.DateOffset(months=2)
        s = pbi.merge(deuda.rename(columns={"fecha": "fecha_deuda"}), on="fecha_deuda", how="inner")
        s = s[(s["tc_prom"] > 0) & (s["pbi_ars"] > 0)]
        s["pbi_usd"] = s["pbi_ars"] / s["tc_prom"]
        s["valor"] = s["deuda_usd"] / s["pbi_usd"] * 100
        return s[["fecha", "valor"]].dropna().sort_values("fecha").reset_index(drop=True)
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
    if tipo == "acumulado_12m":
        # Suma móvil de los últimos 12 meses de una serie de datos_gob (ej. resultado fiscal
        # acumulado de 12 meses, para comparar con series de flujo/nivel de otra frecuencia
        # como riesgo país). A diferencia de 'interanual', no filtra valores <= 0: series como
        # el resultado fiscal son negativas en meses de déficit, sin que eso sea un dato inválido.
        base_id = ind.get("base_id")
        if not base_id:
            raise ValueError(f"Cálculo 'acumulado_12m' requiere 'base_id' en {ind['nombre']}")
        s = fetch_datos_gob(base_id, start).sort_values("fecha").copy()
        s["valor"] = s["valor"].rolling(12, min_periods=12).sum()
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
    if tipo == "reservas_ajustadas":
        # Reservas brutas (diarias) - swap China (mensual, sección II.2 de la planilla SDDS del
        # BCRA) - organismos internacionales (Balance Semanal del BCRA). Se resamplea todo a fin
        # de mes (la cadencia más gruesa, el swap) y se hace join interno: la serie arranca sola
        # donde el swap tiene datos (dic-2022), sin rellenar hacia atrás con nada.
        brutas = fetch_bcra(1, start).sort_values("fecha")
        if brutas.empty:
            return brutas
        brutas_m = brutas.set_index("fecha")["valor"].resample("ME").last()
        swap = fetch_bcra_swap_china().set_index("fecha")["valor"]
        organismos = fetch_bcra_organismos_internacionales().set_index("fecha")["valor"].resample("ME").last()
        s = pd.DataFrame({"brutas": brutas_m}).join(swap.rename("swap"), how="inner") \
            .join(organismos.rename("organismos"), how="inner")
        s["valor"] = s["brutas"] - s["swap"] - s["organismos"]
        s = s.reset_index().rename(columns={"index": "fecha"})
        return s[["fecha", "valor"]].dropna().sort_values("fecha").reset_index(drop=True)
    if tipo == "spread_bono_ust":
        # Spread soberano PROXY (Punto 4, Ronda 2 financiera): TIR de un bono hard-dollar
        # argentino (MAE, snapshot del día, sin historia propia) menos el rendimiento del
        # Treasury americano comparable (FRED, histórico real), en puntos básicos. NO es el
        # EMBI+ oficial (ver 'Riesgo país (EMBI)' en la pestaña macro) -- metodología
        # simplificada, compara TIR puntual contra un Treasury de plazo fijo (ej. 10 años),
        # sin ajustar por la duración exacta del bono argentino. Como la TIR del bono sólo
        # tiene UN dato por día (hoy) y sin backfill posible, el merge con la serie completa
        # de FRED sólo produce un punto por corrida -- la serie se acumula día a día desde
        # que el pipeline empieza a trackearla, igual que el resto de los datos del MAE.
        bono = fetch_mae_bono_campo(ind["ticker_bono"], "tir").rename(columns={"valor": "tir"})
        ust = fetch_fred(ind["fred_id"], start).rename(columns={"valor": "ust"})
        if bono.empty or ust.empty:
            return pd.DataFrame(columns=["fecha", "valor"])
        # merge_asof (no merge exacto): la TIR del bono es de HOY, pero FRED suele publicar
        # el cierre de UST10Y con 1 día hábil de rezago (fines de semana/feriados EEUU) -- un
        # merge por fecha exacta casi nunca matchea. Se toma el último UST10Y disponible a
        # esa fecha o antes (tolerancia 5 días, cubre un fin de semana largo sin arrastrar un
        # dato demasiado viejo).
        s = pd.merge_asof(bono.sort_values("fecha"), ust.sort_values("fecha"), on="fecha",
                           direction="backward", tolerance=pd.Timedelta(days=5))
        s = s.dropna(subset=["ust"])
        if s.empty:
            return pd.DataFrame(columns=["fecha", "valor"])
        s["valor"] = (s["tir"] - s["ust"]) * 100
        return s[["fecha", "valor"]]
    raise ValueError(f"cálculo desconocido: {tipo}")


_TICKERS_MURO = ["AL30", "GD30", "GD35"]
_COLORES_MURO = {"AL30": "#0767A7", "GD30": "#EF6C00", "GD35": "#6A1B99"}


def _muro_vencimientos(anios_adelante=10):
    """
    Amortización de capital de AL30/GD30/GD35 por año de pago (Punto 5, Ronda 2
    financiera), a partir del flujo de fondos del MAE (fetch_mae_flujofondos,
    campo 'detalle' de cada bono: fechaPago + amortizacion). 'amortizacion'
    viene en % del valor nominal ORIGINAL de cada bono -- bases distintas entre
    bonos, así que se arma como gráfico de barras AGRUPADAS (no apiladas), ver
    la nota en dashboard.py/muroOpts. Devuelve un dict {card, serie_js, nota}
    para 'extra_charts' de dashboard.generar(), o None si no hay datos.
    """
    bonos = fetch_mae_flujofondos("H")
    hoy = pd.Timestamp.today()
    anio_max = hoy.year + anios_adelante
    por_anio = {}
    for b in bonos:
        ticker = b.get("especie")
        if ticker not in _TICKERS_MURO:
            continue
        for cupon in b.get("detalle", []):
            try:
                fecha = pd.to_datetime(cupon["fechaPago"])
                monto = float(cupon.get("amortizacion") or 0)
            except (KeyError, ValueError, TypeError):
                continue
            if monto <= 0 or fecha.year < hoy.year or fecha.year > anio_max:
                continue
            por_anio.setdefault(fecha.year, {})[ticker] = por_anio.setdefault(fecha.year, {}).get(ticker, 0) + monto
    if not por_anio:
        return None
    anios = sorted(por_anio.keys())
    datasets = []
    for ticker in _TICKERS_MURO:
        if not any(ticker in por_anio[a] for a in anios):
            continue
        datasets.append(dict(label=ticker, color=_COLORES_MURO[ticker],
            y=[round(por_anio[a].get(ticker, 0), 1) for a in anios]))
    if not datasets:
        return None
    card = dict(nombre="Muro de vencimientos (AL30/GD30/GD35)", bloque="mercados", grupo="Renta fija",
        color=dashboard.ACENTO["mercados"], unidad="% VN", valor="—", pct=None, marca_fecha=None,
        maxv="—", minv="—", sube_es_bueno=False, neutral=True, sin_filtros=True,
        subtitulo="Pagos de capital por año, en % del valor nominal original de cada bono")
    serie_js = dict(kind="muro", x=[str(a) for a in anios], datasets=datasets, unidad="% VN")
    nota = ("Amortización de capital de AL30, GD30 y GD35 por año de pago, en % del valor nominal "
            "ORIGINAL de cada bono (campo 'amortizacion' del flujo de fondos del MAE, endpoint "
            "emisiones/flujofondoscotiz, no documentado oficialmente por el MAE). Barras agrupadas, "
            "NO apiladas: cada bono amortiza sobre SU PROPIO valor nominal -- apilar sumaría "
            "porcentajes de bases distintas en una altura sin significado. Universo acotado a estos "
            "3 bonos hard-dollar (alcance definido por Pedro para esta ronda, no incluye LECAPs/"
            "BONCAPs en pesos ni otros soberanos).")
    return {"card": card, "serie_js": serie_js, "nota": nota}


def _ddf_chart():
    """Punto 9, Ronda 2 financiera: reemplaza la tabla de dólar futuro por un gráfico de barras."""
    ddf = fetch_mae_ddf()
    if not ddf:
        return None
    labels, valores = dashboard.ordenar_ddf(ddf)
    card = dict(nombre="Dólar futuro (DDF)", bloque="mercados", grupo="Dólar futuro",
        color=dashboard.ACENTO["mercados"], unidad="$", valor=_fmt_ultimo(valores[0] if valores else None),
        pct=None, marca_fecha=None, maxv=_fmt_ultimo(max(valores)) if valores else "—",
        minv=_fmt_ultimo(min(valores)) if valores else "—", sube_es_bueno=False, neutral=True,
        sin_filtros=True, subtitulo="Curva de contratos por vencimiento mensual")
    serie_js = dict(kind="bar", x=labels, y=valores, color=dashboard.ACENTO["mercados"], unidad="$")
    nota = ('Curva de contratos de dólar futuro (DDF) por vencimiento mensual, Mercado Abierto '
            'Electrónico (MAE, endpoint emisiones/resumen/DDF, no documentado oficialmente por el '
            'MAE, datos delayed 5-15 min intradía). Snapshot del día -- no es una serie histórica '
            '(los contratos cambian de nombre mes a mes).')
    return {"card": card, "serie_js": serie_js, "nota": nota}


def _fmt_ultimo(v):
    return f"{v:,.0f}".replace(",", ".") if v is not None else "—"


def _ranking_data912(endpoint, sufijos_dedup="CD"):
    """
    Ranking de instrumentos de data912 por monto operado (volumen × último precio),
    de-dupe por símbolo base (ej. 'AALC'/'AALD' -> 'AAL', variantes de liquidación
    contado/48hs del mismo subyacente). Recalculado en cada corrida -- ranking
    data-driven, no una lista fija de símbolos "más líquidos" congelada en el yaml.
    """
    items = fetch_data912(endpoint)
    ranked = []
    for it in items:
        try:
            monto = float(it.get("v") or 0) * float(it.get("c") or 0)
            ranked.append({"simbolo": it["symbol"], "precio": float(it["c"]),
                            "pct_change": float(it.get("pct_change") or 0), "monto": monto})
        except (KeyError, ValueError, TypeError):
            continue
    ranked.sort(key=lambda x: x["monto"], reverse=True)
    vistos, top = set(), []
    for r in ranked:
        base = r["simbolo"][:-1] if r["simbolo"] and r["simbolo"][-1] in sufijos_dedup else r["simbolo"]
        if base in vistos:
            continue
        vistos.add(base)
        top.append(r)
    return top


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

    Sólo se chequean los indicadores TODAVÍA declarados en el yaml. El histórico
    (data/series_largo.csv) conserva datos de indicadores ya eliminados por completo
    del dashboard (merge idempotente, nunca se purga solo) -- si se los siguiera
    chequeando acá, un indicador descontinuado y sacado del yaml (no sólo marcado
    con 'marca_fecha') generaría una alerta de rezago todos los días para siempre,
    ya que nadie vuelve a actualizar esos datos ni hay forma de "resolverla".

    Un indicador puede declarar 'rezago_normal_dias: N' si tiene un rezago de
    publicación estructural conocido y documentado en su 'nota' (ej. el TCR
    multilateral depende del IPC de varios países y llega ~5-6 meses tarde
    de forma sistemática, no por una falla puntual); ese valor pone un piso
    adicional al umbral para no repetir la misma alerta todos los días.
    """
    hoy = pd.Timestamp.today().normalize()
    nombres_activos = {ind["nombre"] for ind in indicadores}
    nombres_excluidos = {ind["nombre"] for ind in indicadores if ind.get("marca_fecha")}
    rezago_normal = {ind["nombre"]: ind["rezago_normal_dias"] for ind in indicadores if ind.get("rezago_normal_dias")}
    rezagados = []

    for nombre, g in historico.groupby("indicador"):
        if nombre not in nombres_activos or nombre in nombres_excluidos:
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
    indicadores_financiera = cfg.get("indicadores_financiera", [])
    filas = []
    problemas = []  # (nombre, motivo) de indicadores que no trajeron datos

    for ind in indicadores + indicadores_financiera:
        nombre = ind["nombre"]
        if ind.get("solo_referencia"):
            continue  # sólo re-muestra en financiera.html un indicador ya fetcheado por la lista macro
        if ind.get("vista") in ("overlay", "incidencia_stack", "sectores_bar", "balance_cambiario", "comercio_espejo", "combo_barras_linea", "combo_2lineas"):
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
            if ind.get("rebase_100"):
                # Rebasa a 100 en el primer valor disponible -- genérico, para overlays que
                # combinan series de magnitud muy distinta (ej. M1/M2/M3) donde mostrar
                # niveles absolutos aplastaría a la más chica contra el eje.
                serie = serie.sort_values("fecha").copy()
                primero = serie["valor"].iloc[0] if len(serie) else None
                if primero:
                    serie = serie.assign(valor=serie["valor"] / primero * 100)
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
    financiera_propios = [i for i in indicadores_financiera if not i.get("solo_referencia")]
    chequear_frescura(historico, indicadores + financiera_propios)
    chequear_plausibilidad(historico, indicadores + financiera_propios)

    nav_a_financiera = '<a href="financiera.html" class="nav-pagina">Financiera →</a>'
    nav_a_macro = '<a href="index.html" class="nav-pagina">← Macro</a>'
    dashboard.generar(historico, indicadores, nav_extra=nav_a_financiera)

    if indicadores_financiera:
        fecha_hoy = pd.Timestamp.today().strftime("%d/%m/%Y")
        extra_charts = [ec for ec in (_ddf_chart(), _muro_vencimientos()) if ec is not None]
        acciones = _ranking_data912("/live/arg_stocks")[:18]
        cedears = _ranking_data912("/live/arg_cedears")[:15]
        extra_html = {"mercados":
            dashboard.tabla_acciones("Acciones más operadas (MERVAL)", acciones, fecha_hoy) +
            dashboard.tabla_acciones("CEDEARs más operados", cedears, fecha_hoy)}
        dashboard.generar(historico, indicadores_financiera, archivo_salida="financiera.html",
                           extra_html=extra_html, extra_charts=extra_charts, nav_extra=nav_a_macro,
                           titulo_pagina="Monitor financiero · Argentina")
        print("Listo -> data/series_largo.csv, data/series_ancho.csv, docs/index.html, docs/financiera.html")
    else:
        print("Listo -> data/series_largo.csv, data/series_ancho.csv, docs/index.html")


if __name__ == "__main__":
    main()

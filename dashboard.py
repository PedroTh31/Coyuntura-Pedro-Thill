"""
dashboard.py  ·  genera docs/index.html (gráficos interactivos con Chart.js)

Diseño:
  - Cada indicador = una CELDA: tarjeta (valor, variación, máx/mín) ARRIBA y
    su gráfico interactivo DEBAJO. Al pasar el cursor, el gráfico muestra el valor.
  - Agrupado por subtítulos; orden fijo de bloques.
  - Semáforo del EMAE y desagregado de comercio exterior como tablas.
No genera imágenes: embebe los datos como JSON y los dibuja Chart.js en el navegador.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
import json
import pandas as pd

import frescura
import titulares
from tema import TEMA

DESDE_GENERAL = "2024-01-01"
OUT = Path(__file__).resolve().parent / "docs"
MAX_PUNTOS_VIEJOS = 600  # tope de puntos para el tramo >2 años en series diarias largas
UMBRAL_DISCONTINUADA_DIAS = frescura.UMBRAL_DISCONTINUADA_DIAS  # días sin datos para "sin datos nuevos" (una sola fuente de verdad)
UMBRAL_HISTORIA_MINIMA = 30  # por debajo de esto, no se muestra gráfico de línea (ver "acumulando historia")

# Colores: TODOS salen de tema.py (Bloque C, paleta de prensa económica en azules + arena para los
# negativos) y los aplica el tema único de Chart.js del template (ver _escribir_html): ningún gráfico se
# estiliza por separado. ACENTO/AZUL_* quedan sólo por compatibilidad (run.py arma extra_charts con
# ACENTO["mercados"]); el campo 'color' de cards/series ya no se usa para dibujar.
ACENTO = {"precios": "#C62828", "monetario_financiero": "#0767A7",
          "externo": "#EF6C00", "real": "#50B7B2", "social": "#6A1B99", "fiscal": "#8D2D04",
          "mercados": "#0767A7"}
AZUL_MARCA = "#232D4F"     # --arg-azul: navy institucional (header, footer, texto fuerte)
AZUL_ENLACE = "#0767A7"    # --arg-enlace: azul de interacción (links, botón activo)
TINTA = "#141414"; PAPEL = "#FFFFFF"; GRIS = "#555555"
# NOTA: "mercados" alimenta docs/financiera.html (ver dashboard_financiera vía run.py,
# generar() con archivo_salida="financiera.html"). Convive en las mismas listas que los
# bloques macro porque generar()/_escribir_html() son genéricos: un bloque sin tarjetas
# para el config_indicadores que se le pasó simplemente no imprime sección (ver el "continue"
# en _escribir_html), así que agregarlo acá no afecta a docs/index.html.
ORDEN_BLOQUES = ["precios", "monetario_financiero", "externo", "real", "social", "fiscal", "mercados"]
TITULO_BLOQUE = {"precios": "Precios", "monetario_financiero": "Monetario y financiero",
                 "real": "Actividad real", "externo": "Sector externo",
                 "social": "Social y empleo", "fiscal": "Fiscal", "mercados": "Mercados"}
ORDEN_GRUPOS = ["Precios", "Dólar", "Brecha y TCR", "Riesgo país", "Reservas",
                "Agregados monetarios", "Tasas de interés", "Crédito",
                "Comercio exterior", "Exportaciones por rubro", "Importaciones por uso",
                "Actividad", "Social", "Fiscal",
                "Tipo de cambio y brechas", "Tasas y CER", "Acciones", "Dólar futuro", "Renta fija"]


def _fmt_num(v) -> str:
    if v is None or pd.isna(v):
        return "s/d"
    if abs(v) >= 1000:
        return f"{v:,.0f}".replace(",", ".")
    s = f"{v:,.1f}" if abs(v) >= 10 else f"{v:,.2f}"
    return s.replace(",", "@").replace(".", ",").replace("@", ".")


def _slug(s: str) -> str:
    import re
    s = s.lower()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _interanual(serie):
    s = serie.sort_values("fecha").copy()
    prev = s.rename(columns={"valor": "valor_prev"})[["fecha", "valor_prev"]].copy()
    prev["fecha"] = prev["fecha"] + pd.DateOffset(years=1)
    m = pd.merge_asof(s, prev, on="fecha", direction="nearest", tolerance=pd.Timedelta(days=20))
    m = m.dropna(subset=["valor_prev"]); m = m[m["valor_prev"] != 0]
    m["valor"] = (m["valor"] / m["valor_prev"] - 1) * 100
    return m[["fecha", "valor"]].dropna().reset_index(drop=True)


def _metricas_sector(serie):
    s = serie.sort_values("fecha").reset_index(drop=True)
    ia = _interanual(s); v_ia = ia["valor"].iloc[-1] if not ia.empty else None
    v_men = (s["valor"].iloc[-1] / s["valor"].iloc[-2] - 1) * 100 if len(s) >= 2 and s["valor"].iloc[-2] else None
    v_acum = None
    u = s["fecha"].iloc[-1]
    este = s[(s["fecha"].dt.year == u.year) & (s["fecha"].dt.month <= u.month)]
    prev = s[(s["fecha"].dt.year == u.year - 1) & (s["fecha"].dt.month <= u.month)]
    if len(este) and len(prev) and prev["valor"].mean():
        v_acum = (este["valor"].mean() / prev["valor"].mean() - 1) * 100
    return v_ia, v_men, v_acum


def _variacion(serie):
    if len(serie) < 2:
        return (serie["valor"].iloc[-1] if len(serie) else None), None
    ult, prev = serie["valor"].iloc[-1], serie["valor"].iloc[-2]
    return ult, (((ult - prev) / prev * 100) if prev else None)


def _serie_reservas_combo(idx, color, unidad, serie, desde):
    """
    Arma los datos para el gráfico combo de reservas: barras = variación
    mensual del stock, línea = stock. Ambas series comparten el mismo eje
    de fechas (fin de cada mes) para poder graficarse juntas en Chart.js.
    """
    sm_full = serie.sort_values("fecha").set_index("fecha")["valor"].resample("MS").last()
    flujo_full = sm_full.diff()

    sm_s = sm_full[sm_full.index >= pd.to_datetime(desde)]
    if len(sm_s) < 2:
        sm_s = sm_full
    flujo_s = flujo_full.reindex(sm_s.index)

    def _vals(serie_valores):
        return [round(float(v), 2) if pd.notna(v) else None for v in serie_valores]

    return dict(i=idx, color=color, unidad=unidad, kind="combo",
        x=[d.strftime("%m/%y") for d in sm_s.index], y=_vals(sm_s), flujo=_vals(flujo_s),
        full_x=[d.strftime("%m/%y") for d in sm_full.index], full_y=_vals(sm_full),
        full_flujo=_vals(flujo_full), full_dates=[d.isoformat() for d in sm_full.index],
        min_date=serie["fecha"].min().isoformat(), max_date=serie["fecha"].max().isoformat())


def _serie_balance_cambiario(idx, ind, historico):
    """
    Combo de DOS indicadores YA presentes en 'historico' (a diferencia de
    _serie_reservas_combo, que deriva barras y línea de una sola serie propia):
    barras = ind['series'][0] (ej. compras netas de divisas del BCRA, ya
    mensual), línea = ind['series'][1] (ej. stock de reservas brutas, diario
    -> resampleado a fin de mes para poder graficarlo junto a la serie
    mensual). Reusa el mismo formato 'combo' que ya entiende el JS.
    """
    nombre_barras, nombre_linea = ind["series"]
    g_barras = historico[historico["indicador"] == nombre_barras].sort_values("fecha")
    g_linea = historico[historico["indicador"] == nombre_linea].sort_values("fecha")
    if g_barras.empty or g_linea.empty:
        return None

    linea_full = g_linea.set_index("fecha")["valor"].resample("MS").last()
    barras_full = g_barras.set_index("fecha")["valor"].resample("MS").last()
    fechas_full = linea_full.index.union(barras_full.index).sort_values()
    linea_full = linea_full.reindex(fechas_full)
    barras_full = barras_full.reindex(fechas_full)

    desde = ind.get("desde", DESDE_GENERAL)
    fechas_s = fechas_full[fechas_full >= pd.to_datetime(desde)]
    if len(fechas_s) < 2:
        fechas_s = fechas_full
    linea_s = linea_full.reindex(fechas_s)
    barras_s = barras_full.reindex(fechas_s)

    def _vals(s):
        return [round(float(v), 2) if pd.notna(v) else None for v in s]

    ult, pct = _variacion(g_linea)
    # El valor de la card es el de la LÍNEA: si la línea tiene otra unidad que las barras (ej. reservas en
    # USD vs. compras netas en pesos), `unidad_linea` del yaml rotula el valor y el tooltip de la línea.
    unidad_linea = ind.get("unidad_linea", ind.get("unidad", ""))
    card = dict(i=idx, nombre=ind["nombre"], bloque=ind["bloque"], grupo=ind.get("grupo", "Otros"),
        color=ACENTO.get(ind["bloque"], AZUL_ENLACE), unidad=unidad_linea,
        valor=_fmt_num(ult), pct=pct, marca_fecha=None,
        maxv=_fmt_num(g_linea["valor"].max()), minv=_fmt_num(g_linea["valor"].min()), nota_num=None,
        subtitulo=ind.get("subtitulo"),
        sube_es_bueno=ind.get("sube_es_bueno", False), neutral=ind.get("neutral", False))

    serie_js = dict(i=idx, color=ACENTO.get(ind["bloque"], AZUL_ENLACE), unidad=ind.get("unidad", ""),
        unidad_linea=unidad_linea, kind="combo",
        # Rótulo de las barras: acá son las compras netas del BCRA, no la variación del stock (que es lo
        # que dibuja el combo de 'Reservas internacionales', mismo kind "combo").
        label_barras="Compras netas", titulo_barras=f"Compras netas ({ind.get('unidad', '')})",
        x=[d.strftime("%m/%y") for d in fechas_s], y=_vals(linea_s), flujo=_vals(barras_s),
        full_x=[d.strftime("%m/%y") for d in fechas_full], full_y=_vals(linea_full),
        full_flujo=_vals(barras_full), full_dates=[d.isoformat() for d in fechas_full],
        min_date=fechas_full.min().isoformat(), max_date=fechas_full.max().isoformat())
    return card, serie_js


def _serie_comercio_espejo(idx, ind, historico):
    """
    Gráfico espejo (mirror / diverging bars) de comercio exterior: exportaciones
    como barras positivas (arriba), importaciones como barras negativas (abajo
    -- mismo valor, sólo se invierte el signo PARA EL GRÁFICO, el dato guardado
    en el histórico no cambia), saldo comercial superpuesto como línea sobre el
    mismo eje. ind['series'] = [exportaciones, importaciones, saldo].
    """
    nombre_expo, nombre_impo, nombre_saldo = ind["series"]
    g_expo = historico[historico["indicador"] == nombre_expo].sort_values("fecha")
    g_impo = historico[historico["indicador"] == nombre_impo].sort_values("fecha")
    g_saldo = historico[historico["indicador"] == nombre_saldo].sort_values("fecha")
    if g_expo.empty or g_impo.empty:
        return None

    fechas_full = sorted(set(g_expo["fecha"]) | set(g_impo["fecha"]) | set(g_saldo["fecha"]))
    desde = ind.get("desde", DESDE_GENERAL)
    fechas_default = [d for d in fechas_full if d >= pd.to_datetime(desde)]
    if len(fechas_default) < 2:
        fechas_default = fechas_full

    expo_por_fecha = dict(zip(g_expo["fecha"], g_expo["valor"]))
    impo_por_fecha = dict(zip(g_impo["fecha"], g_impo["valor"]))
    saldo_por_fecha = dict(zip(g_saldo["fecha"], g_saldo["valor"]))

    def _en(fechas_, vpf, signo=1):
        return [round(float(vpf[d]) * signo, 2) if d in vpf else None for d in fechas_]

    ult, pct = _variacion(g_saldo if not g_saldo.empty else g_expo)
    card = dict(i=idx, nombre=ind["nombre"], bloque=ind["bloque"], grupo=ind.get("grupo", "Otros"),
        color=ACENTO.get(ind["bloque"], AZUL_ENLACE), unidad=ind.get("unidad", ""),
        valor=_fmt_num(ult), pct=pct, marca_fecha=None,
        maxv=_fmt_num(g_expo["valor"].max()), minv=_fmt_num(-g_impo["valor"].max()), nota_num=None,
        subtitulo=ind.get("subtitulo"),
        sube_es_bueno=ind.get("sube_es_bueno", False), neutral=ind.get("neutral", False))

    serie_js = dict(i=idx, kind="espejo", unidad=ind.get("unidad", ""),
        x=[d.strftime("%m/%y") for d in fechas_default],
        full_x=[d.strftime("%m/%y") for d in fechas_full],
        full_dates=[d.isoformat() for d in fechas_full],
        expo=_en(fechas_default, expo_por_fecha), impo=_en(fechas_default, impo_por_fecha, signo=-1),
        saldo=_en(fechas_default, saldo_por_fecha),
        full_expo=_en(fechas_full, expo_por_fecha), full_impo=_en(fechas_full, impo_por_fecha, signo=-1),
        full_saldo=_en(fechas_full, saldo_por_fecha))
    return card, serie_js


def _serie_combo_2lineas(idx, ind, historico):
    """
    Combo genérico de DOS líneas ya existentes en dos ejes (izquierda/derecha), para
    cuando sus magnitudes no son comparables en un mismo eje compartido (ej. un
    índice base 100 vs. un nivel concreto en otra unidad) -- a diferencia de
    'overlay', que comparte un solo eje y sólo tiene sentido cuando las series son
    de magnitud parecida. ind['linea_izq']/ind['linea_der'] son nombres de
    indicadores ya existentes; unidad_izq/unidad_der etiquetan cada eje. Todo se
    resamplea a fin de mes antes de unir fechas (mismo criterio que
    _serie_combo_barras_linea), por si las dos series tienen frecuencias distintas.
    """
    nombre_izq, nombre_der = ind["linea_izq"], ind["linea_der"]
    g_izq = historico[historico["indicador"] == nombre_izq].sort_values("fecha")
    g_der = historico[historico["indicador"] == nombre_der].sort_values("fecha")
    if g_izq.empty or g_der.empty:
        return None
    izq_m = g_izq.set_index("fecha")["valor"].resample("MS").last()
    der_m = g_der.set_index("fecha")["valor"].resample("MS").last()
    fechas_full = izq_m.index.union(der_m.index).sort_values()
    izq_full = izq_m.reindex(fechas_full)
    der_full = der_m.reindex(fechas_full)

    desde = ind.get("desde", DESDE_GENERAL)
    fechas_s = fechas_full[fechas_full >= pd.to_datetime(desde)]
    if len(fechas_s) < 2:
        fechas_s = fechas_full

    def _vals(s):
        return [round(float(v), 2) if pd.notna(v) else None for v in s]

    unidad_izq, unidad_der = ind.get("unidad_izq", ""), ind.get("unidad_der", "")
    ult, pct = _variacion(g_izq)
    card = dict(i=idx, nombre=ind["nombre"], bloque=ind["bloque"], grupo=ind.get("grupo", "Otros"),
        color=ACENTO.get(ind["bloque"], AZUL_ENLACE), unidad=unidad_izq,
        valor=_fmt_num(ult), pct=pct, marca_fecha=None,
        maxv=_fmt_num(g_izq["valor"].max()), minv=_fmt_num(g_izq["valor"].min()), nota_num=None,
        subtitulo=ind.get("subtitulo"), grande=ind.get("grande", False),
        sube_es_bueno=ind.get("sube_es_bueno", False), neutral=ind.get("neutral", False))

    serie_js = dict(i=idx, kind="combo_2lineas", unidad_izq=unidad_izq, unidad_der=unidad_der,
        label_izq=nombre_izq, label_der=nombre_der,
        x=[d.strftime("%m/%y") for d in fechas_s],
        full_x=[d.strftime("%m/%y") for d in fechas_full],
        full_dates=[d.isoformat() for d in fechas_full],
        izq=_vals(izq_full.reindex(fechas_s)), full_izq=_vals(izq_full),
        der=_vals(der_full.reindex(fechas_s)), full_der=_vals(der_full))
    return card, serie_js


def _serie_combo_barras_linea(idx, ind, historico):
    """
    Combo genérico de 1-2 barras + 1 línea, dos ejes (barras a la izquierda, línea a la
    derecha). Cada elemento de ind['barras'] es {serie: "...", signo: 1|-1 (opcional,
    default 1)} -- 'signo: -1' invierte el signo SOLO para el gráfico (ej. mostrar un gasto
    como resta visual sobre una barra positiva, mismo mecanismo que ya usa comercio_espejo
    con las importaciones), el dato guardado en el histórico no cambia. ind['linea'] es el
    nombre de un único indicador ya existente en 'historico'. Usado para los combos de
    foco fiscal (superávit gemelos, riesgo país vs. resultado acumulado, primario vs.
    intereses) pero no es específico de fiscal: sirve para cualquier combo de 1-2 barras +
    1 línea sobre dos indicadores/cálculos ya existentes.
    """
    # Todo se resamplea a fin de mes ("MS", mismo criterio que _serie_balance_cambiario) antes
    # de unir fechas: si la línea es de frecuencia distinta a las barras (ej. riesgo país
    # diario vs. resultado fiscal mensual), unir las fechas CRUDAS deja un eje categórico con
    # cientos de categorías diarias y sólo un puñado de barras mensuales -- cada barra queda
    # apenas un pixel de ancho, casi invisible. Resamplear ambos lados a la misma frecuencia
    # mensual antes de graficar evita ese problema de raíz.
    barras_cfg = ind["barras"]
    nombre_linea = ind["linea"]
    g_linea = historico[historico["indicador"] == nombre_linea].sort_values("fecha")
    if g_linea.empty:
        return None
    linea_m = g_linea.set_index("fecha")["valor"].resample("MS").last()

    series_barras = []
    for b in barras_cfg:
        g = historico[historico["indicador"] == b["serie"]].sort_values("fecha")
        if g.empty:
            continue
        series_barras.append((b["serie"], g.set_index("fecha")["valor"].resample("MS").last(), b.get("signo", 1)))
    if not series_barras:
        return None

    fechas_full = linea_m.index
    for _, serie_m, _ in series_barras:
        fechas_full = fechas_full.union(serie_m.index)
    fechas_full = fechas_full.sort_values()
    linea_full = linea_m.reindex(fechas_full)

    desde = ind.get("desde", DESDE_GENERAL)
    fechas_s = fechas_full[fechas_full >= pd.to_datetime(desde)]
    if len(fechas_s) < 2:
        fechas_s = fechas_full

    def _vals(s, signo=1):
        return [round(float(v) * signo, 2) if pd.notna(v) else None for v in s]

    barras_js = []
    for i, (nombre_b, serie_m, signo) in enumerate(series_barras):
        serie_full = serie_m.reindex(fechas_full)
        barras_js.append(dict(label=nombre_b,
            y=_vals(serie_full.reindex(fechas_s), signo), full_y=_vals(serie_full, signo)))

    unidad_linea = ind.get("unidad_linea", ind.get("unidad", ""))
    ult, pct = _variacion(g_linea)
    card = dict(i=idx, nombre=ind["nombre"], bloque=ind["bloque"], grupo=ind.get("grupo", "Otros"),
        color=ACENTO.get(ind["bloque"], AZUL_ENLACE), unidad=unidad_linea,
        valor=_fmt_num(ult), pct=pct, marca_fecha=None,
        maxv=_fmt_num(g_linea["valor"].max()), minv=_fmt_num(g_linea["valor"].min()), nota_num=None,
        subtitulo=ind.get("subtitulo"), grande=ind.get("grande", False),
        sube_es_bueno=ind.get("sube_es_bueno", False), neutral=ind.get("neutral", False))

    serie_js = dict(i=idx, kind="combo_bl",
        unidad_barras=ind.get("unidad", ""), unidad_linea=unidad_linea,
        x=[d.strftime("%m/%y") for d in fechas_s],
        full_x=[d.strftime("%m/%y") for d in fechas_full],
        full_dates=[d.isoformat() for d in fechas_full],
        barras=barras_js, linea_label=nombre_linea,
        linea=_vals(linea_full.reindex(fechas_s)), full_linea=_vals(linea_full))
    return card, serie_js


def _serie_combo_rezago(idx, ind, historico):
    """
    Combo de dos líneas en dos ejes CON selector de rezago (Punto 2.1 del checklist
    storytelling, PROMPT_fix_graficos_y_storytelling.md): para explorar la relación entre
    una serie de emisión/política (ind['linea_izq']) y una de resultado (ind['linea_der'])
    SIN que el equipo elija un rezago "correcto" e imponga una lectura -- se precalculan
    server-side todas las variantes de ind.get('rezagos', [0,3,6,12]) (meses que se
    desplaza linea_izq hacia adelante) y el usuario elige cuál ver con un toggle
    client-side (ver .rezago-btn); Python no recomienda ninguna por default más allá de
    "sin rezago" (0), que es la variante que se muestra al cargar la página.
    """
    nombre_izq, nombre_der = ind["linea_izq"], ind["linea_der"]
    g_izq = historico[historico["indicador"] == nombre_izq].sort_values("fecha")
    g_der = historico[historico["indicador"] == nombre_der].sort_values("fecha")
    if g_izq.empty or g_der.empty:
        return None
    izq_m = g_izq.set_index("fecha")["valor"].resample("MS").last()
    der_m = g_der.set_index("fecha")["valor"].resample("MS").last()

    desde = ind.get("desde", DESDE_GENERAL)
    rezagos = ind.get("rezagos", [0, 3, 6, 12])

    def _vals(s):
        return [round(float(v), 2) if pd.notna(v) else None for v in s]

    variantes_js = {}
    for r in rezagos:
        izq_shift = izq_m.copy()
        izq_shift.index = izq_shift.index + pd.DateOffset(months=r)
        fechas_full = izq_shift.index.union(der_m.index).sort_values()
        fechas_s = fechas_full[fechas_full >= pd.to_datetime(desde)]
        if len(fechas_s) < 2:
            fechas_s = fechas_full
        # Cada variante trae su vista por defecto (desde 'desde') Y la historia completa
        # (full_*), para que los filtros de fecha funcionen sobre el rezago elegido: el JS
        # copia la variante activa a los campos de primer nivel y reusa la misma lógica de
        # filtrado que combo_2lineas.
        variantes_js[str(r)] = dict(x=[d.strftime("%m/%y") for d in fechas_s],
                                     izq=_vals(izq_shift.reindex(fechas_s)), der=_vals(der_m.reindex(fechas_s)),
                                     full_x=[d.strftime("%m/%y") for d in fechas_full],
                                     full_dates=[d.isoformat() for d in fechas_full],
                                     full_izq=_vals(izq_shift.reindex(fechas_full)),
                                     full_der=_vals(der_m.reindex(fechas_full)))

    unidad_izq, unidad_der = ind.get("unidad_izq", ""), ind.get("unidad_der", "")
    ult, pct = _variacion(g_der)  # la card resume con la serie de "resultado" (der)
    card = dict(i=idx, nombre=ind["nombre"], bloque=ind["bloque"], grupo=ind.get("grupo", "Otros"),
        color=ACENTO.get(ind["bloque"], AZUL_ENLACE), unidad=unidad_der,
        valor=_fmt_num(ult), pct=pct, marca_fecha=None,
        maxv=_fmt_num(g_der["valor"].max()), minv=_fmt_num(g_der["valor"].min()), nota_num=None,
        subtitulo=ind.get("subtitulo"), grande=True, rezagos=rezagos,
        sube_es_bueno=ind.get("sube_es_bueno", False), neutral=ind.get("neutral", False))

    serie_js = dict(i=idx, kind="combo_rezago", unidad_izq=unidad_izq, unidad_der=unidad_der,
        label_izq=nombre_izq, label_der=nombre_der, rezago_default=0, variantes=variantes_js,
        **variantes_js["0"])  # campos de primer nivel = variante activa al cargar (sin rezago)
    return card, serie_js


def _serie_combo_barras_evento(idx, ind, historico):
    """
    Combo de una serie CONTINUA (barra, eje izquierdo) + una de EVENTO DISCRETO (marcadores
    puntuales sin conectar, eje derecho) -- Punto 1 del checklist de
    PROMPT_fix_graficos_y_storytelling.md: una serie que ocurre pocas veces (ej. Transferencia
    de Utilidades del BCRA al Tesoro, 1-2 veces al año) no se grafica compartiendo eje/línea
    continua con una serie mensual real -- el pico aplasta al resto contra el piso. Genérico,
    no específico de Asistencia BCRA: sirve para cualquier par continua/evento ya existente.
    ind['barra']/ind['evento'] son nombres de indicadores ya existentes en 'historico'.
    """
    nombre_barra, nombre_evento = ind["barra"], ind["evento"]
    g_barra = historico[historico["indicador"] == nombre_barra].sort_values("fecha")
    g_evento = historico[historico["indicador"] == nombre_evento].sort_values("fecha")
    if g_barra.empty:
        return None
    barra_m = g_barra.set_index("fecha")["valor"].resample("MS").last()
    evento_m = (g_evento.set_index("fecha")["valor"].resample("MS").last()
                if not g_evento.empty else pd.Series(dtype=float))
    fechas_full = barra_m.index.union(evento_m.index).sort_values()
    barra_full = barra_m.reindex(fechas_full)
    evento_full = evento_m.reindex(fechas_full)

    desde = ind.get("desde", DESDE_GENERAL)
    fechas_s = fechas_full[fechas_full >= pd.to_datetime(desde)]
    if len(fechas_s) < 2:
        fechas_s = fechas_full

    def _vals(s):
        return [round(float(v), 2) if pd.notna(v) else None for v in s]

    def _vals_evento(s):
        # 0 (o casi 0) = "sin evento ese mes" -> null, no se dibuja marcador (a diferencia de
        # _vals: acá un cero es "nada pasó", no un dato real en cero).
        return [round(float(v), 2) if pd.notna(v) and abs(v) > 1e-6 else None for v in s]

    unidad_evento = ind.get("unidad_evento", ind.get("unidad", ""))
    ult, pct = _variacion(g_barra)
    card = dict(i=idx, nombre=ind["nombre"], bloque=ind["bloque"], grupo=ind.get("grupo", "Otros"),
        color=ACENTO.get(ind["bloque"], AZUL_ENLACE), unidad=ind.get("unidad", ""),
        valor=_fmt_num(ult), pct=pct, marca_fecha=None,
        maxv=_fmt_num(g_barra["valor"].max()), minv=_fmt_num(g_barra["valor"].min()), nota_num=None,
        subtitulo=ind.get("subtitulo"), grande=ind.get("grande", False),
        sube_es_bueno=ind.get("sube_es_bueno", False), neutral=ind.get("neutral", False))

    serie_js = dict(i=idx, kind="combo_evento", unidad_barra=ind.get("unidad", ""), unidad_evento=unidad_evento,
        label_barra=nombre_barra, label_evento=nombre_evento,
        x=[d.strftime("%m/%y") for d in fechas_s],
        full_x=[d.strftime("%m/%y") for d in fechas_full],
        full_dates=[d.isoformat() for d in fechas_full],
        barra=_vals(barra_full.reindex(fechas_s)), full_barra=_vals(barra_full),
        evento=_vals_evento(evento_full.reindex(fechas_s)), full_evento=_vals_evento(evento_full))
    return card, serie_js




def _serie_overlay(idx, ind, historico):
    """
    Gráfico de líneas superpuestas a partir de varios indicadores YA
    presentes en 'historico' (ind['series']: sus nombres tal cual figuran
    ahí). Comparten un solo eje — sólo tiene sentido si todos comparten
    unidad — y llevan leyenda para prender/apagar cada serie.
    La tarjeta muestra como "valor" principal la ÚLTIMA serie de la lista
    (por convención: la métrica resumen, ej. saldo comercial).
    """
    partes = []
    fechas_todas = set()
    for nombre_serie in ind["series"]:
        g = historico[historico["indicador"] == nombre_serie].sort_values("fecha")
        if g.empty:
            continue
        partes.append((nombre_serie, g))
        fechas_todas.update(g["fecha"])
    if not partes:
        return None
    fechas_full = sorted(fechas_todas)

    desde = ind.get("desde", DESDE_GENERAL)
    fechas_default = [d for d in fechas_full if d >= pd.to_datetime(desde)]
    if len(fechas_default) < 2:
        fechas_default = fechas_full

    datasets = []
    for i, (nombre_serie, g) in enumerate(partes):
        valores_por_fecha = dict(zip(g["fecha"], g["valor"]))
        def _en(fechas_, vpf=valores_por_fecha):
            return [round(float(vpf[d]), 2) if d in vpf else None for d in fechas_]
        datasets.append(dict(label=nombre_serie,
            y=_en(fechas_default), full_y=_en(fechas_full)))

    # Marca de "cambio de liderazgo": la fecha en la que la serie que termina arriba (la de
    # mayor valor en el último dato disponible) pasó a ser la más alta de forma DEFINITIVA
    # (sin volver a perder el primer puesto hasta el final). Genérico -- no depende de qué
    # serie es cuál, ni de fechas hardcodeadas -- sirve para cualquier overlay donde "quién
    # lidera" cambie con el tiempo y ese cambio sea el dato más importante del gráfico, pero
    # las líneas se crucen en un ángulo demasiado cerrado para notarlo a simple vista.
    cruce = None
    if ind.get("marcar_cruce_maximo") and len(datasets) > 1:
        lideres = []
        for i in range(len(fechas_full)):
            vals = {d["label"]: d["full_y"][i] for d in datasets if d["full_y"][i] is not None}
            lideres.append(max(vals, key=vals.get) if vals else None)
        if lideres and lideres[-1] is not None:
            lider_final = lideres[-1]
            j = len(lideres) - 1
            while j > 0 and lideres[j - 1] == lider_final:
                j -= 1
            if j > 0:
                cruce = dict(fecha=fechas_full[j].strftime("%m/%y"),
                             texto=f"'{lider_final}' pasa a ser la serie más alta de acá en adelante")

    nombre_resumen, g_resumen = partes[-1]
    ult, pct = _variacion(g_resumen)
    card = dict(i=idx, nombre=ind["nombre"], bloque=ind["bloque"], grupo=ind.get("grupo", "Otros"),
        color=ACENTO.get(ind["bloque"], AZUL_ENLACE), unidad=ind.get("unidad", ""),
        valor=_fmt_num(ult), pct=pct, marca_fecha=None,
        maxv=_fmt_num(g_resumen["valor"].max()), minv=_fmt_num(g_resumen["valor"].min()), nota_num=None,
        grande=ind.get("grande", False), subtitulo=ind.get("subtitulo"),
        sube_es_bueno=ind.get("sube_es_bueno", False), neutral=ind.get("neutral", False))

    serie_js = dict(i=idx, kind="overlay", unidad=ind.get("unidad", ""),
        x=[d.strftime("%m/%y") for d in fechas_default],
        full_x=[d.strftime("%m/%y") for d in fechas_full],
        full_dates=[d.isoformat() for d in fechas_full],
        datasets=datasets, radio_punto=ind.get("radio_punto", 0), cruce=cruce,
        escala_log=ind.get("escala_log", False), barras=ind.get("barras", False))
    return card, serie_js




def _serie_incidencia(idx, ind, historico, indicadores_por_nombre):
    """
    Barras apiladas de incidencia mensual: para cada indicador listado en
    ind['series'] (un índice de nivel, ej. una división del IPC), calcula su
    variación % mes a mes y la multiplica por su 'peso_nacional' declarado en
    el yaml. La suma de las barras apiladas de un mes aproxima la variación
    del total (ver 'nota' del indicador para la fuente del ponderador).
    """
    partes = []
    fechas_todas = set()
    for nombre_serie in ind["series"]:
        peso = indicadores_por_nombre.get(nombre_serie, {}).get("peso_nacional")
        g = historico[historico["indicador"] == nombre_serie].sort_values("fecha")
        if g.empty or peso is None:
            continue
        g = g.copy()
        g["incidencia"] = g["valor"].pct_change() * 100 * peso
        g = g.dropna(subset=["incidencia"])
        partes.append((nombre_serie, peso, g))
        fechas_todas.update(g["fecha"])
    if not partes:
        return None
    fechas_full = sorted(fechas_todas)

    desde = ind.get("desde", DESDE_GENERAL)
    fechas_default = [d for d in fechas_full if d >= pd.to_datetime(desde)]
    if len(fechas_default) < 2:
        fechas_default = fechas_full

    # Top N por peso_nacional + "Resto" agrupado: con muchas categorías apiladas (ej. las 12
    # divisiones de consumo del IPC) cada franja queda demasiado angosta para distinguirla a
    # simple vista -- estándar de cómo se comunica inflación en informes serios. El corte es
    # genérico y data-driven (ordena por el peso_nacional ya declarado en cada componente, no
    # una lista fija de nombres hardcodeada): si el día de mañana cambia el ponderador de una
    # división, el top N se recalcula solo, sin tocar código.
    top_n = ind.get("top_n")
    if top_n and len(partes) > top_n:
        partes_ordenadas = sorted(partes, key=lambda t: t[1], reverse=True)
        principales, resto = partes_ordenadas[:top_n], partes_ordenadas[top_n:]
    else:
        principales, resto = partes, []

    datasets = []
    for i, (nombre_serie, peso, g) in enumerate(principales):
        etiqueta = nombre_serie.replace("IPC división: ", "")
        valores_por_fecha = dict(zip(g["fecha"], g["incidencia"]))
        def _en(fechas_, vpf=valores_por_fecha):
            return [round(float(vpf[d]), 3) if d in vpf else None for d in fechas_]
        datasets.append(dict(label=etiqueta,
            y=_en(fechas_default), full_y=_en(fechas_full)))

    # Detalle de "Resto" por mes (Punto 11, Ronda 4): las divisiones agrupadas en "Resto" no
    # tienen su propia barra de color (con las 12 completas apiladas cada franja queda
    # ilegible), pero su aporte no es marginal -- en vez de obligar a abrir el CSV para verlo,
    # queda disponible en el tooltip de cada mes: qué divisiones son y cuánto aportó cada una
    # ESE mes en particular (no una lista fija, cambia con el dato real de cada período).
    resto_detalle = None
    if resto:
        valores_por_fecha_resto = {}
        resto_detalle = {}
        for nombre_serie, _, g in resto:
            etiqueta_resto = nombre_serie.replace("IPC división: ", "")
            for f, v in zip(g["fecha"], g["incidencia"]):
                valores_por_fecha_resto[f] = valores_por_fecha_resto.get(f, 0.0) + v
                resto_detalle.setdefault(f.strftime("%m/%y"), []).append(
                    dict(nombre=etiqueta_resto, valor=round(float(v), 3)))
        for label in resto_detalle:
            resto_detalle[label].sort(key=lambda d: abs(d["valor"]), reverse=True)
        def _en_resto(fechas_):
            return [round(float(valores_por_fecha_resto[d]), 3) if d in valores_por_fecha_resto else None for d in fechas_]
        datasets.append(dict(label=f"Resto ({len(resto)} divisiones)",
            y=_en_resto(fechas_default), full_y=_en_resto(fechas_full)))

    # tarjeta: suma de incidencias del último mes (aproxima la variación del nivel general)
    ultima_fecha = fechas_full[-1]
    total_ultimo = sum(d["y"][-1] or 0 for d in datasets if fechas_default and fechas_default[-1] == ultima_fecha)
    valores_totales = [sum(v or 0 for v in vals) for vals in zip(*[d["y"] for d in datasets])] if datasets else []
    card = dict(i=idx, nombre=ind["nombre"], bloque=ind["bloque"], grupo=ind.get("grupo", "Otros"),
        color=ACENTO.get(ind["bloque"], AZUL_ENLACE), unidad=ind.get("unidad", ""),
        valor=_fmt_num(total_ultimo), pct=None, marca_fecha=None,
        maxv=_fmt_num(max(valores_totales)) if valores_totales else "s/d",
        minv=_fmt_num(min(valores_totales)) if valores_totales else "s/d", nota_num=None,
        grande=ind.get("grande", False), subtitulo=ind.get("subtitulo"))

    # Autoescala robusta: el eje "normal" se calcula sobre el percentil 95 de la incidencia
    # total mensual (positiva y negativa por separado, con margen del 15%), no sobre el máximo
    # histórico. Así un pico aislado (ej. el shock devaluatorio de comienzos de 2024, con varias
    # divisiones subiendo 15-25% en un solo mes) no aplasta la lectura de todos los demás meses
    # -- y el mecanismo es genérico: si en el futuro aparece otro pico grande, se vuelve a marcar
    # solo, sin volver a romper la escala. Los meses que superan ese rango no se pierden: quedan
    # en 'atipicos' (con su valor real) para que el gráfico los señale aparte en vez de estirar
    # el eje para incluirlos.
    #
    # El percentil 95 se recalcula por separado para cada ventana de filtro (Default/1A/5A/Desde
    # 2008/Todo, ver 'ejes' más abajo): calcularlo una sola vez sobre el histórico completo dejaba
    # el eje sobredimensionado en la ventana default (18 meses) frente a un pico como el shock de
    # 2024, que quedó fuera de esa ventana -- la mayor parte del gráfico quedaba vacía arriba.
    totales_por_fecha = {}
    for i, fecha in enumerate(fechas_full):
        vals = [d["full_y"][i] for d in datasets]
        pos = sum(v for v in vals if v and v > 0)
        neg = sum(v for v in vals if v and v < 0)
        totales_por_fecha[fecha] = (pos, neg)
    MARGEN_EJE = 1.15

    def _eje(fechas_subset):
        subset = set(fechas_subset)
        positivos = [p for f, (p, n) in totales_por_fecha.items() if f in subset and p > 0]
        negativos = [abs(n) for f, (p, n) in totales_por_fecha.items() if f in subset and n < 0]
        y_max_ = round(float(pd.Series(positivos).quantile(0.95)) * MARGEN_EJE, 2) if positivos else None
        y_min_ = round(-float(pd.Series(negativos).quantile(0.95)) * MARGEN_EJE, 2) if negativos else None
        atipicos_ = {}
        for f in fechas_subset:
            pos, neg = totales_por_fecha[f]
            if (y_max_ is not None and pos > y_max_) or (y_min_ is not None and neg < y_min_):
                atipicos_[f.strftime("%m/%y")] = round(pos + neg, 2)
        return dict(y_max=y_max_, y_min=y_min_, atipicos=atipicos_)

    hoy = fechas_full[-1]
    cortes = {
        "default": pd.to_datetime(desde),
        "6m": hoy - pd.DateOffset(months=6),
        "1a": hoy - pd.DateOffset(years=1),
        "5a": hoy - pd.DateOffset(years=5),
        "2008": pd.to_datetime("2008-01-01"),
        "todo": pd.to_datetime("1900-01-01"),
    }
    ejes = {rango: _eje([f for f in fechas_full if f >= corte]) for rango, corte in cortes.items()}

    serie_js = dict(i=idx, kind="incidencia", unidad=ind.get("unidad", ""),
        x=[d.strftime("%m/%y") for d in fechas_default],
        full_x=[d.strftime("%m/%y") for d in fechas_full],
        full_dates=[d.isoformat() for d in fechas_full],
        datasets=datasets, y_max=ejes["default"]["y_max"], y_min=ejes["default"]["y_min"],
        atipicos=ejes["default"]["atipicos"], ejes=ejes, resto_detalle=resto_detalle)
    return card, serie_js


def _serie_sectores_bar(idx, ind, historico):
    """
    Barras categóricas con burbuja: eje X = sector (categórico), ordenados por el
    VALOR de este mismo gráfico -- variación % interanual de actividad, de menor a
    mayor (la caída más fuerte al extremo izquierdo, el mayor crecimiento al
    extremo derecho) -- NO por peso de empleo (referencia visual: slide de MAP
    LATAM que mandó Pedro). Eje Y: variación % interanual de actividad (EMAE por
    sector). El tamaño de la burbuja dibujada sobre cada columna sigue
    representando el % del empleo registrado total que representa el sector (dato
    que antes definía el orden, ahora es sólo una dimensión visual adicional). Cada
    sector tiene su propia posición en el eje X: no puede haber superposición entre
    sectores como en el bubble chart original de dos ejes continuos, así que no
    hace falta cerca de Tukey ni toggle de zoom. El EMAE (mensual) se remuestrea a
    trimestres calendario (misma definición que usa la fuente de empleo,
    nativamente trimestral: ene-mar/abr-jun/jul-sep/oct-dic) antes de comparar,
    para que la variación de actividad y el peso de empleo representen el mismo
    período exacto.
    """
    pares = []
    for par in ind["sectores"]:
        g_emae = historico[historico["indicador"] == par["emae"]].sort_values("fecha")
        g_emp = historico[historico["indicador"] == par["empleo"]].sort_values("fecha")
        if g_emae.empty or g_emp.empty:
            continue
        emae_q = g_emae.set_index("fecha")["valor"].resample("QS").mean()
        emp_q = g_emp.set_index("fecha")["valor"]
        pares.append((par["emae"].replace("EMAE · ", ""), emae_q, emp_q))
    if not pares:
        return None

    # último trimestre presente en TODOS los sectores (para comparar todos al mismo período)
    fecha_comun = min(min(emae_q.index.max(), emp_q.index.max()) for _, emae_q, emp_q in pares)
    fecha_prev = fecha_comun - pd.DateOffset(years=1)

    puntos = []
    for nombre_sector, emae_q, emp_q in pares:
        if fecha_comun not in emae_q.index or fecha_prev not in emae_q.index:
            continue
        if fecha_comun not in emp_q.index or fecha_prev not in emp_q.index:
            continue
        if emae_q[fecha_prev] <= 0 or emp_q[fecha_prev] <= 0:
            continue
        var_actividad = (emae_q[fecha_comun] / emae_q[fecha_prev] - 1) * 100
        puntos.append(dict(nombre=nombre_sector, var_actividad=var_actividad, empleo=float(emp_q[fecha_comun])))
    if not puntos:
        return None

    total_empleo = sum(p["empleo"] for p in puntos)
    for p in puntos:
        p["pct_empleo"] = round(p["empleo"] / total_empleo * 100, 2)
    puntos.sort(key=lambda p: p["var_actividad"])

    trimestre = f"T{(fecha_comun.month - 1) // 3 + 1} {fecha_comun.year}"
    card = dict(i=idx, nombre=ind["nombre"], bloque=ind["bloque"], grupo=ind.get("grupo", "Otros"),
        color=ACENTO.get(ind["bloque"], AZUL_ENLACE), unidad="",
        valor=trimestre, pct=None, marca_fecha=None, maxv="s/d", minv="s/d", nota_num=None,
        sin_filtros=True, subtitulo=ind.get("subtitulo"), grande=True)

    serie_js = dict(i=idx, kind="bar_sectores", fecha=fecha_comun.strftime("%m/%Y"),
        x=[p["nombre"] for p in puntos], y=[round(p["var_actividad"], 2) for p in puntos],
        empleo_pct=[p["pct_empleo"] for p in puntos])
    return card, serie_js


def _con_huecos_explicitos(df):
    """
    Punto 3 del checklist (PROMPT_fix_graficos_y_storytelling.md): si una serie tiene un
    hueco de historia mucho más grande que su cadencia habitual (ej. Reservas ajustadas,
    sin datos entre dic-2022 y jul-2024, nota *10), Chart.js conecta el último punto antes
    del hueco con el primero después con una línea recta -- sugiere una transición suave
    que no existe. Se inserta un punto sintético con valor None a mitad del hueco para que
    Chart.js corte la línea ahí (spanGaps no está activado en baseOpts/overlayOpts para el
    caso base, así que un None sí corta). Genérico y data-driven: el umbral de "hueco
    grande" sale de la mediana real de intervalos de CADA serie, no de una fecha fija --
    aplica a cualquier serie con huecos, no sólo a Reservas ajustadas.
    """
    if len(df) < 3:
        return df
    deltas = df["fecha"].diff().dropna().dt.days
    if deltas.empty:
        return df
    mediana = deltas.median()
    if mediana <= 0:
        return df
    umbral = max(mediana * 4, 45)  # piso de 45 días: no reaccionar al jitter normal de series diarias
    filas = [df.iloc[0]]
    fechas = df["fecha"].reset_index(drop=True)
    valores = df["valor"].reset_index(drop=True)
    for i in range(1, len(df)):
        gap_dias = (fechas[i] - fechas[i - 1]).days
        if gap_dias > umbral:
            fecha_media = fechas[i - 1] + pd.Timedelta(days=gap_dias // 2)
            filas.append(pd.Series({"fecha": fecha_media, "valor": None}))
        filas.append(pd.Series({"fecha": fechas[i], "valor": valores[i]}))
    return pd.DataFrame(filas).reset_index(drop=True)


_CLAVES_REFERENCIA = ("series", "sectores", "barras", "linea", "linea_izq", "linea_der", "barra", "evento")


def _usos_indec(ind, fuentes_indec):
    """Usos de la API del INDEC (o de su fallback) del indicador y de los indicadores que referencia
    (vistas compuestas: overlay, incidencia, sectores, combos). Lista vacía si no usa datos del INDEC."""
    if not fuentes_indec:
        return []
    nombres = [ind["nombre"]]
    for k in _CLAVES_REFERENCIA:
        v = ind.get(k)
        for x in (v if isinstance(v, list) else [v]):
            if isinstance(x, str):
                nombres.append(x)
            elif isinstance(x, dict):
                nombres.extend(y for y in x.values() if isinstance(y, str))
    usos = []
    for n in nombres:
        for u in fuentes_indec.get(n, []):
            if u not in usos:
                usos.append(u)
    return usos


# Fuentes del encabezado ("fuentes: ...") de cada página, armadas a partir de los indicadores que
# esa página muestra (no una lista fija): así financiera.html no lista el INDEC, y si una serie del
# INDEC cae al fallback, el encabezado lo refleja.
FUENTES_HEADER_DEFAULT = "API del INDEC · apis.datos.gob.ar · ArgentinaDatos · BCRA"
ORDEN_FUENTES = ["API del INDEC", "apis.datos.gob.ar", "ArgentinaDatos", "BCRA",
                 "Secretaría de Finanzas", "BYMA", "MAE", "FRED", "data912"]
ETIQUETA_FUENTE = {"datos_gob": "apis.datos.gob.ar", "argentinadatos": "ArgentinaDatos",
                   "dolar": "ArgentinaDatos", "bcra": "BCRA", "rem_bcra": "BCRA",
                   "bcra_morosidad_lineas": "BCRA", "deuda_bruta": "Secretaría de Finanzas",
                   "byma": "BYMA", "mae_bono": "MAE", "mae_resumen": "MAE", "fred": "FRED"}
ETIQUETA_USO_INDEC = {"indec_api": "API del INDEC", "datos_gob_ar": "apis.datos.gob.ar",
                      "argentinadatos": "ArgentinaDatos"}
# Fuentes que un `calculo:` usa por fuera de sus ids de datos.gob (ver _calcular en run.py).
FUENTES_CALCULO = {"brecha": ["ArgentinaDatos"], "reservas_ajustadas": ["BCRA"],
                   "tasa_real_expost": ["BCRA"], "spread_bono_ust": ["MAE", "FRED"],
                   "deuda_pbi": ["Secretaría de Finanzas", "ArgentinaDatos"]}
CAMPOS_ID_DG = ("id", "base_id", "nominal_id", "deflactor_id", "numerador_id", "denominador_id",
                "minuendo_id", "sustraendo_id", "pbi_id", "ipc_base_id")


def _fuentes_de_indicador(ind, fuentes_indec):
    """Etiquetas de fuente de un indicador: la declarada en el yaml y, para las series del
    INDEC, la que el resolver usó de verdad (API o fallback)."""
    if ind.get("vista"):
        return set()   # las vistas sólo combinan indicadores que ya cuentan por su cuenta
    usos = fuentes_indec.get(ind["nombre"], [])
    etiquetas = {ETIQUETA_USO_INDEC.get(u["fuente"], u["fuente"]) for u in usos}
    cubiertos = {u["clave"].split(":")[0] for u in usos} | {ind["nombre"]}
    if ind.get("fuente_primaria") == "indec_api" and not usos:
        etiquetas.add("API del INDEC")   # sin registro de esta corrida: la fuente declarada
    if ind.get("fuente") in ETIQUETA_FUENTE:
        if ind["fuente"] != "datos_gob" or ind.get("id") not in cubiertos:
            etiquetas.add(ETIQUETA_FUENTE[ind["fuente"]])
    calculo = ind.get("calculo")
    if calculo:
        etiquetas.update(FUENTES_CALCULO.get(calculo, []))
        ids = [ind[c] for c in CAMPOS_ID_DG if isinstance(ind.get(c), str)]
        ids += [c if isinstance(c, str) else c.get("id") for c in ind.get("componentes", [])]
        if any(i and i not in cubiertos for i in ids):
            etiquetas.add("apis.datos.gob.ar")
    return etiquetas


def fuentes_de_pagina(config_pagina, fuentes_indec=None, todos_los_indicadores=None, extra=()):
    """Texto del encabezado 'fuentes: ...' de una página. `todos_los_indicadores` resuelve los
    `solo_referencia` (el dato lo trae un indicador de la otra lista, con el mismo nombre);
    `extra`: fuentes de lo que se inyecta por fuera del yaml (extra_charts/extra_html)."""
    fuentes_indec = fuentes_indec or {}
    por_nombre = {i["nombre"]: i for i in (todos_los_indicadores or []) if not i.get("solo_referencia")}
    etiquetas = set(extra)
    for ind in config_pagina:
        if ind.get("solo_referencia"):
            ind = por_nombre.get(ind["nombre"], ind)
        etiquetas |= _fuentes_de_indicador(ind, fuentes_indec)
    orden = [e for e in ORDEN_FUENTES if e in etiquetas] + sorted(etiquetas - set(ORDEN_FUENTES))
    return " · ".join(orden)


def _nota_con_fuente(nota, usos):
    """Nota metodológica + 'Fuente: INDEC (API ...)' o 'Fuente: INDEC vía ...' (Bloque A4)."""
    from fuentes_indec import describir_fuente
    fuente = describir_fuente(usos)
    if not fuente:
        return nota
    return f"{nota} {fuente}" if nota else fuente


def _registrar_nota(nota, nombre, notas_dict):
    """Registra (o encuentra) el número de asterisco de una nota, dedupe por texto."""
    if not nota:
        return None
    if nota not in notas_dict:
        nota_num = len(notas_dict) + 1
        notas_dict[nota] = {"numero": nota_num, "indicadores": [nombre]}
    else:
        nota_num = notas_dict[nota]["numero"]
        notas_dict[nota]["indicadores"].append(nombre)
    return nota_num


# Serie que resume cada card compuesta (la misma que usa su _serie_* para el valor de la card):
# de ella sale la línea de frescura (Bloque B2). sectores_bar no lleva línea (es la foto de un período).
def _serie_resumen(ind):
    v = ind.get("vista")
    if v in ("overlay", "incidencia_stack"):
        return ind["series"][-1] if v == "overlay" else ind["series"][0]
    return {"balance_cambiario": lambda: ind["series"][1],
            "comercio_espejo": lambda: ind["series"][2],
            "combo_2lineas": lambda: ind["linea_izq"],
            "combo_barras_linea": lambda: ind["linea"],
            "combo_rezago": lambda: ind["linea_der"],
            "combo_barras_evento": lambda: ind["barra"]}.get(v, lambda: ind["nombre"])()


def _series_de_card(ind):
    """Todas las series que dibuja una card (para detectar cards mixtas: alguna frenada y otra no)."""
    v = ind.get("vista")
    if v in ("overlay", "incidencia_stack", "balance_cambiario", "comercio_espejo"):
        return list(ind["series"])
    if v in ("combo_2lineas", "combo_rezago"):
        return [ind["linea_izq"], ind["linea_der"]]
    if v == "combo_barras_linea":
        return [b["serie"] for b in ind["barras"]] + [ind["linea"]]
    if v == "combo_barras_evento":
        return [ind["barra"], ind["evento"]]
    return [ind["nombre"]]


def _linea_frescura(ind, historico, ctx, indicadores_por_nombre):
    """(HTML de la línea de frescura del B2, ¿la serie que resume la card está en rezago grave?)."""
    if ctx is None or ind.get("vista") == "sectores_bar":
        return "", False
    estados = []
    for nombre in _series_de_card(ind):
        # cada serie con su propia config (ej. rezago_normal_dias del TCR dentro de un overlay)
        cfg = indicadores_por_nombre.get(nombre, ind)
        fechas = historico.loc[historico["indicador"] == nombre, "fecha"]
        estados.append((nombre, frescura.calcular(cfg, nombre, fechas, ctx)))
    resumen = _serie_resumen(ind)
    ctx.registro[ind["nombre"]] = (estados, resumen)   # avisos del mail diario (Bloque B3)
    grave = any(n == resumen and getattr(f, "grave", False) for n, f in estados)
    return frescura.html_card(estados, resumen), grave


_MESES_ABREV_C = ["", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _desde_txt(desde):
    d = pd.to_datetime(desde)
    return f"desde {_MESES_ABREV_C[d.month]}-{str(d.year)[2:]}"


def _completar_card(card, ind, historico, indicadores_por_nombre, grave, con_titulares, anio, serie_js=None):
    """Bloque C: titular por reglas (sólo con_titulares, pestaña macro), variación de la card contra lo
    mismo que el titular (D13; pp en tasas, D4) y valor con decimales según la unidad (D4). Todo sobre la
    serie que resume la card (la misma de la línea de frescura). Ver titulares.py."""
    card["desde_txt"] = _desde_txt(ind.get("desde", DESDE_GENERAL))
    card["titular"], card["cambio"] = None, None
    if ind.get("vista") == "sectores_bar":
        return
    nombre_r = _serie_resumen(ind)
    cfg_r = indicadores_por_nombre.get(nombre_r, ind)
    unidad_r = cfg_r.get("unidad", card.get("unidad", ""))
    g = historico[historico["indicador"] == nombre_r].sort_values("fecha")
    serie = pd.Series(g["valor"].values, index=pd.to_datetime(g["fecha"].values)).dropna()
    if serie.empty:
        return
    freq = titulares.frecuencia(serie.index)
    comparar = titulares.comparar_de(ind, freq) if con_titulares else "anterior"
    if ind.get("vista") != "incidencia_stack":
        # `ocultar_variacion: true` (yaml): sin variación bajo el valor mientras se revisa un dato dudoso
        # (ej. base monetaria, PENDIENTES #14)
        if not ind.get("ocultar_variacion"):
            card["cambio"] = titulares.cambio(serie, unidad_r, comparar, freq)
        card["valor"] = titulares.fmt_valor(serie.iloc[-1], unidad_r)
    if not con_titulares:
        return
    if ind.get("titular_regla") == "aporte":
        if grave or not serie_js or not serie_js.get("datasets"):
            return
        candidatos = [(d["full_y"][-1], d["label"]) for d in serie_js["datasets"]
                      if not d["label"].startswith("Resto") and d.get("full_y") and d["full_y"][-1] is not None]
        if candidatos:
            valor, nombre = max(candidatos)
            card["titular"] = titulares.titular_aporte(ind, nombre, valor, serie_js["full_dates"][-1], anio)
        return
    card["titular"] = titulares.titular(ind, serie, unidad_r, anio, grave=grave, freq=freq)


def _extender_hasta_hoy(sj, hoy):
    """Serie frenada (franja ⏸): el eje sigue hasta hoy con nulls (gaps como null, nunca interpolados)
    y el tema sombrea el tramo sin datos (plugin tramoSinDatos, D9)."""
    fechas = pd.to_datetime(sj["full_dates"])
    if len(fechas) < 2:
        return
    paso = pd.Series(fechas).diff().dropna().tail(12).median().days
    ult = fechas[-1]
    if paso <= 7:
        nuevas = pd.bdate_range(ult + pd.Timedelta(days=1), hoy)
    elif paso <= 45:
        nuevas = pd.date_range(ult, hoy, freq="ME" if ult.is_month_end else "MS")[1:]
    else:
        nuevas = pd.date_range(ult, hoy, freq="QS" if ult.day == 1 else "QE")[1:]
    if not len(nuevas):
        return
    fmt = "%d/%m/%y" if paso <= 7 else "%m/%y"
    etiquetas = [d.strftime(fmt) for d in nuevas]
    sj["full_x"] = list(sj["full_x"]) + etiquetas
    sj["full_y"] = list(sj["full_y"]) + [None] * len(nuevas)
    sj["full_dates"] = list(sj["full_dates"]) + [d.isoformat() for d in nuevas]
    if "x" in sj:
        sj["x"] = list(sj["x"]) + etiquetas
        sj["y"] = list(sj["y"]) + [None] * len(nuevas)
    sj["frenada"] = True


def generar(historico, config_indicadores, archivo_salida="index.html", extra_html=None,
            extra_charts=None, nav_extra="", titulo_pagina="Monitor de coyuntura · Argentina",
            fuentes_indec=None, fuentes_pagina=None, frescura_ctx=None, con_titulares=False):
    """frescura_ctx: frescura.Contexto (Bloque B2) para mostrar la línea de frescura en cada card;
    None = sin línea (pestaña financiera, fuera de esa ronda).
    con_titulares: titulares por reglas del Bloque C (sólo la pestaña macro, decisión de Pedro D1); sin
    ellos, la variación bajo el valor de cada card compara contra el dato anterior."""
    if frescura_ctx is not None:
        anio, hoy = frescura_ctx.ahora.year, pd.Timestamp(frescura_ctx.ahora).normalize()
    else:
        anio, hoy = datetime.now().year, pd.Timestamp.today().normalize()
    OUT.mkdir(parents=True, exist_ok=True)
    charts, series_js, semaforo, fecha_sem = [], [], [], ""
    tablas = defaultdict(list)
    notas_dict = {}  # {numero_nota: {"texto": ..., "indicadores": [...]}}
    indicadores_por_nombre = {i["nombre"]: i for i in config_indicadores}
    usos_semaforo = []  # fuente de los datos de la tabla semáforo del EMAE (pie "Fuente: INDEC")
    idx = 0
    for ind in config_indicadores:
        nombre = ind["nombre"]; bloque = ind["bloque"]; grupo = ind.get("grupo", "Otros")
        unidad = ind.get("unidad", ""); color = ACENTO.get(bloque, AZUL_ENLACE)
        usos = _usos_indec(ind, fuentes_indec)
        nota = _nota_con_fuente(ind.get("nota"), usos)
        if ind.get("solo_componente"):
            continue  # sólo alimenta un 'vista' compuesta; no tiene tarjeta propia
        if ind.get("vista") in ("overlay", "incidencia_stack", "sectores_bar", "balance_cambiario", "comercio_espejo", "combo_barras_linea", "combo_2lineas", "combo_barras_evento", "combo_rezago"):
            if ind["vista"] == "overlay":
                entrada = _serie_overlay(idx, ind, historico)
            elif ind["vista"] == "incidencia_stack":
                entrada = _serie_incidencia(idx, ind, historico, indicadores_por_nombre)
            elif ind["vista"] == "balance_cambiario":
                entrada = _serie_balance_cambiario(idx, ind, historico)
            elif ind["vista"] == "comercio_espejo":
                entrada = _serie_comercio_espejo(idx, ind, historico)
            elif ind["vista"] == "combo_barras_linea":
                entrada = _serie_combo_barras_linea(idx, ind, historico)
            elif ind["vista"] == "combo_2lineas":
                entrada = _serie_combo_2lineas(idx, ind, historico)
            elif ind["vista"] == "combo_barras_evento":
                entrada = _serie_combo_barras_evento(idx, ind, historico)
            elif ind["vista"] == "combo_rezago":
                entrada = _serie_combo_rezago(idx, ind, historico)
            else:
                entrada = _serie_sectores_bar(idx, ind, historico)
            if entrada is None:
                continue
            card, serie_js_compuesta = entrada
            card["nota_num"] = _registrar_nota(nota, nombre, notas_dict)
            card["fuente_indec"] = bool(usos)
            card["frescura"], grave = _linea_frescura(ind, historico, frescura_ctx, indicadores_por_nombre)
            _completar_card(card, ind, historico, indicadores_por_nombre, grave, con_titulares, anio,
                            serie_js_compuesta)
            charts.append(card)
            series_js.append(serie_js_compuesta)
            idx += 1
            continue
        serie = historico[historico["indicador"] == nombre].sort_values("fecha").reset_index(drop=True)
        if serie.empty:
            continue
        if ind.get("semaforo"):
            ia, men, acum = _metricas_sector(serie)
            fecha_sem = serie["fecha"].iloc[-1].strftime("%m/%Y")
            semaforo.append(dict(nombre=nombre.replace("EMAE · ", ""), ia=ia, men=men, acum=acum))
            usos_semaforo.extend(u for u in usos if u not in usos_semaforo)
            continue
        if ind.get("tabla"):
            ia = _interanual(serie)
            tablas[ind["tabla"]].append(dict(nombre=nombre, bloque=bloque, grupo=grupo,
                valor=serie["valor"].iloc[-1],
                yoy=(ia["valor"].iloc[-1] if not ia.empty else None),
                fecha=serie["fecha"].iloc[-1].strftime("%m/%Y")))
            continue
        desde = ind.get("desde", DESDE_GENERAL)
        s = serie[serie["fecha"] >= pd.to_datetime(desde)]
        if len(s) < 2:
            s = serie
        ult, pct = _variacion(serie)
        nota_num = _registrar_nota(nota, nombre, notas_dict)
        linea_fr, grave = _linea_frescura(ind, historico, frescura_ctx, indicadores_por_nombre)
        # Marca de "datos hasta MM/AAAA" para series que pueden discontinuarse (ej. tasa
        # de política monetaria). Se calcula de la última fecha REAL de la serie en cada
        # corrida: si la fuente retoma la publicación, la marca se actualiza o desaparece
        # sola (no queda un texto fijo desactualizado).
        # Con la línea de frescura (Bloque B2) el rezago grave lo muestra esa línea, para todas las
        # series: el cartel viejo queda sólo para las páginas sin línea (financiera).
        marca_fecha = None
        if ind.get("marca_fecha") and frescura_ctx is None:
            dias_atraso = (pd.Timestamp.today().normalize() - serie["fecha"].max()).days
            if dias_atraso > UMBRAL_DISCONTINUADA_DIAS:
                marca_fecha = f"Sin datos nuevos desde {serie['fecha'].max().strftime('%m/%Y')}"
        # Punto 4 del checklist (PROMPT_fix_graficos_y_storytelling.md): una serie con muy
        # pocos puntos porque recién empieza a trackearse (ej. datos de snapshot del MAE, que
        # no tienen historia previa posible) se ve como un gráfico de línea roto/vacío -- se
        # muestra sólo el valor puntual en la card, sin canvas ni filtros, hasta acumular
        # suficiente historia. Se recalcula solo en cada corrida (no una fecha fija): en
        # cuanto la serie cruza el umbral, el gráfico completo vuelve a aparecer sin tocar código.
        acumulando = (f"Acumulando historia — disponible en unas semanas "
                      f"({len(serie)}/{UMBRAL_HISTORIA_MINIMA} observaciones)"
                      if len(serie) < UMBRAL_HISTORIA_MINIMA else None)
        charts.append(dict(i=idx, nombre=nombre, bloque=bloque, grupo=grupo, color=color,
            unidad=unidad, valor=titulares.fmt_valor(ult, unidad), pct=pct, marca_fecha=marca_fecha,
            maxv=titulares.fmt_valor(s["valor"].max(), unidad), minv=titulares.fmt_valor(s["valor"].min(), unidad),
            nota_num=nota_num,
            sube_es_bueno=ind.get("sube_es_bueno", False), neutral=ind.get("neutral", False),
            subtitulo=ind.get("subtitulo"), acumulando=acumulando, sin_filtros=bool(acumulando),
            fuente_indec=bool(usos), frescura=linea_fr))
        _completar_card(charts[-1], ind, historico, indicadores_por_nombre, grave, con_titulares, anio)
        if acumulando:
            idx += 1
            continue
        if ind.get("vista") == "reservas_combo":
            series_js.append(_serie_reservas_combo(idx, color, unidad, serie, desde))
        else:
            # Embeber los datos históricos para permitir filtrado client-side.
            # El tramo reciente (últimos 2 años) queda a resolución diaria completa
            # (así "1A" no pierde detalle); el tramo viejo se submuestrea si es muy
            # largo, para no inflar el HTML en series diarias de décadas (dólar, tasas).
            corte_reciente = serie["fecha"].max() - pd.DateOffset(years=2)
            reciente = serie[serie["fecha"] >= corte_reciente]
            vieja = serie[serie["fecha"] < corte_reciente]
            if len(vieja) > MAX_PUNTOS_VIEJOS:
                paso = -(-len(vieja) // MAX_PUNTOS_VIEJOS)  # ceil division
                vieja = vieja.iloc[::paso]
            full = pd.concat([vieja, reciente]).sort_values("fecha")
            full = _con_huecos_explicitos(full)
            full_x = [d.strftime("%d/%m/%y") for d in full["fecha"]]
            full_y = [round(float(v), 2) if pd.notna(v) else None for v in full["valor"]]
            full_dates = [d.isoformat() for d in full["fecha"]]  # ISO para comparación
            # Datos filtrados (para vista por defecto)
            s_gap = _con_huecos_explicitos(s)
            s_x = [d.strftime("%d/%m/%y") for d in s_gap["fecha"]]
            s_y = [round(float(v), 2) if pd.notna(v) else None for v in s_gap["valor"]]
            series_js.append(dict(i=idx, color=color, unidad=unidad,
                kind="bar" if ind.get("barras") else "line",
                x=s_x, y=s_y,  # Datos filtrados (default)
                full_x=full_x, full_y=full_y, full_dates=full_dates,  # Todos los datos
                min_date=serie["fecha"].min().isoformat(), max_date=serie["fecha"].max().isoformat(),
                eventos=ind.get("eventos")))
            if grave:
                _extender_hasta_hoy(series_js[-1], hoy)
        idx += 1
    # extra_charts: tarjetas/gráficos armados fuera del loop yaml-driven de arriba (ej. muro de
    # vencimientos, curvas snapshot) -- fetchers.py/run.py los arma ya con card/serie_js casi
    # completos, acá sólo se les asigna el índice 'i' que les toca según el orden de inserción.
    for ec in (extra_charts or []):
        card = dict(ec["card"], i=idx)
        card.setdefault("cambio", None)
        card.setdefault("titular", None)
        if ec.get("nota"):
            card["nota_num"] = _registrar_nota(ec["nota"], card["nombre"], notas_dict)
        serie_js_extra = dict(ec["serie_js"], i=idx)
        charts.append(card)
        series_js.append(serie_js_extra)
        idx += 1
    from fuentes_indec import describir_fuente
    _escribir_html(charts, series_js, semaforo, fecha_sem, tablas, notas_dict,
                    archivo_salida=archivo_salida, extra_html=extra_html or {},
                    nav_extra=nav_extra, titulo_pagina=titulo_pagina,
                    semaforo_fuente=describir_fuente(usos_semaforo) or "",
                    fuentes_pagina=fuentes_pagina,
                    etiquetas={i["nombre"]: i["etiqueta"] for i in config_indicadores if i.get("etiqueta")})


def _color_semaforo(v):
    """Celdas de tabla (Bloque C): +1% o más en azul de contexto, -1% o menos en un tinte del arena (el
    color de los negativos), en el medio sin color. Todo de tema.py."""
    if v is None or pd.isna(v):
        return "transparent", TEMA["texto_3"]
    if v > 1:  return TEMA["azul_contexto"], TEMA["azul_1"]
    if v < -1: return _mezclar(TEMA["negativo"], 0.35), TEMA["texto"]
    return "transparent", TEMA["texto_2"]


def _tabla_semaforo(semaforo, fecha_sem, fuente_html=""):
    if not semaforo:
        return ""
    orden = sorted(semaforo, key=lambda x: (x["ia"] is None, -(x["ia"] or -999)))
    def celda(v):
        bg, fg = _color_semaforo(v)
        return f'<td style="background:{bg};color:{fg}">{(f"{v:+.1f}%" if v is not None else "s/d")}</td>'
    filas = "".join(f'<tr><td class="sec">{s["nombre"]}</td>{celda(s["ia"])}{celda(s["men"])}{celda(s["acum"])}</tr>' for s in orden)
    return (f'<h3 class="sub">EMAE por sector <span class="ref">({fecha_sem})</span></h3>'
            '<p class="nota">Interanual · mensual (serie original, con estacionalidad) · acumulado del año. '
            'Azul: +1% o más · sin color: entre -1% y +1% · arena: -1% o menos.</p>'
            '<table class="tabla"><thead><tr><th>Sector</th><th>Interanual</th><th>Mensual</th><th>Acum. año</th></tr></thead>'
            f'<tbody>{filas}</tbody></table>'
            + (f'<p class="fuente-pie fuente-tabla">{fuente_html}</p>' if fuente_html else ""))


def _tabla_valores(titulo, filas):
    if not filas:
        return ""
    fecha = filas[0].get("fecha", "")
    def celda(v):
        bg, fg = _color_semaforo(v)
        return f'<td style="background:{bg};color:{fg}">{(f"{v:+.1f}%" if v is not None else "s/d")}</td>'
    cuerpo = "".join(f'<tr><td class="sec">{f["nombre"]}</td><td class="num">{_fmt_num(f["valor"])}</td>{celda(f["yoy"])}</tr>' for f in filas)
    return (f'<h3 class="sub">{titulo} <span class="ref">({fecha})</span></h3>'
            '<table class="tabla"><thead><tr><th>Rubro</th><th>Último (USD M)</th><th>Interanual</th></tr></thead>'
            f'<tbody>{cuerpo}</tbody></table>')


_MESES_ABREV = ["", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def ordenar_ddf(contratos):
    """
    Ordena la curva DDF (MAE) por (año, mes) real del ticker "DLRMMAAAA" y
    devuelve (labels "mes/año", valores último). NO por orden alfabético del
    ticker (pondría "DLR012027" antes que "DLR092026" pese a vencer después).
    Usado por run.py para armar la tarjeta/gráfico de dólar futuro (Ronda 2:
    reemplaza a la tabla de la Ronda 1 -- ver Punto 9).
    """
    def _clave(c):
        t = c["ticker"]
        try:
            return (int(t[5:9]), int(t[3:5]))
        except (ValueError, IndexError):
            return (9999, 99)
    labels, valores = [], []
    for c in sorted(contratos, key=_clave):
        mm, aaaa = c["ticker"][3:5], c["ticker"][5:9]
        try:
            labels.append(f"{_MESES_ABREV[int(mm)]}/{aaaa}")
        except (ValueError, IndexError):
            labels.append(c["ticker"])
        valores.append(round(c["ultimo"], 2))
    return labels, valores


def tabla_acciones(titulo, filas, fecha_str):
    """
    Tabla de acciones/CEDEARs más operados por monto (data912), snapshot del
    día -- ranking recalculado en cada corrida (no una lista fija de
    símbolos), mismo criterio que evitar hardcodear qué es "lo más líquido"
    de una vez y para siempre.
    """
    if not filas:
        return ""
    def celda_var(v):
        bg, fg = _color_semaforo(v)
        return f'<td style="background:{bg};color:{fg}">{(f"{v:+.2f}%" if v is not None else "s/d")}</td>'
    cuerpo = "".join(f'<tr><td class="sec">{f["simbolo"]}</td><td class="num">{_fmt_num(f["precio"])}</td>'
                      f'{celda_var(f["pct_change"])}</tr>' for f in filas)
    return (f'<h3 class="sub">{titulo} <span class="ref">({fecha_str})</span></h3>'
            '<table class="tabla"><thead><tr><th>Símbolo</th><th>Último ($)</th><th>Variación diaria</th></tr></thead>'
            f'<tbody>{cuerpo}</tbody></table>')


def _card_cell(c):
    """Card del Bloque C: (kicker con el nombre +) titular o nombre, valor con su variación contra lo mismo
    que el titular (D13, triángulo gris sin juicio, D3), línea de frescura del B2 tal cual, leyenda en
    prosa (la llena el JS con los colores reales de cada serie), gráfico, selector "Vista" (D5) y pie con
    fuente · máx/mín (D11) · asterisco de la nota."""
    i = c["i"]
    tit = c.get("titular")
    if tit == c["nombre"]:
        tit = None   # override manual con el nombre de la card (ej. base monetaria): sin repetirlo arriba
    cabeza = (f'<div class="cn">{c["nombre"]}</div><div class="ct">{tit}</div>' if tit
              else f'<div class="ct">{c["nombre"]}</div>')
    subtitulo_html = f'<div class="csub">{c["subtitulo"]}</div>' if c.get("subtitulo") else ""
    chg = ""
    if c.get("cambio"):
        ch = c["cambio"]
        tri = {1: "▲", -1: "▼"}.get(ch["signo"], "•")
        chg = f'<span class="chg"><span class="tri">{tri}</span>{ch["texto"]} vs. {ch["ref"]}</span>'
    fila = (f'<div class="cm"><span class="cv">{c["valor"]}</span>'
            f'<span class="uni">{c.get("unidad", "")}</span>{chg}</div>')
    # Pie (D11): atribución del INDEC exigida para los datos de su API (Bloque A6) · máx/mín de la vista
    # inicial · asterisco numerado y clickeable que salta a su nota en el pie de página.
    pie = []
    if c.get("fuente_indec"):
        pie.append("Fuente: INDEC")
    if c.get("maxv") not in (None, "s/d") and not c.get("acumulando"):
        pie.append(f'máx. {c["maxv"]} · mín. {c["minv"]}')
    if c.get("nota_num"):
        pie.append(f'<a href="#nota-{c["nota_num"]}">*{c["nota_num"]}</a>')
    pie_html = f'<div class="fuente-pie">{" · ".join(pie)}</div>' if pie else ""
    # Marca "sin datos nuevos desde MM/AAAA" (dinámica, ver generar(); sólo páginas sin línea de frescura)
    marca_html = f'<div class="marca-fecha">⏸ {c["marca_fecha"]}</div>' if c.get("marca_fecha") else ""
    # Selector de rango (D5): "Vista: desde mmm-aa · 6M · 1A · 5A · Máx · Rango…". La vista inicial es el
    # `desde` del yaml. Mismos atributos de siempre (class="filtro" data-rango="..."): el JS de filtrado
    # (calcFechaCorte/filtrarDatos/aplicarFiltro) no cambia salvo el corte nuevo de 6 meses.
    filtros = ""
    if not c.get("sin_filtros"):
        opciones = [("default", c.get("desde_txt") or "Inicial"), ("6m", "6M"), ("1a", "1A"), ("5a", "5A"),
                    ("todo", "Máx"), ("personalizado", "Rango…")]
        botones = "".join(f'<button class="filtro{" active" if k == "default" else ""}" data-rango="{k}">{t}</button>'
                          for k, t in opciones)
        filtros = (f'<div class="filtros" data-idx="{i}"><span class="vista">Vista:</span>{botones}</div>'
                   f'<div class="rango-custom" data-idx="{i}"><input type="date" class="rango-desde">'
                   '<span>a</span><input type="date" class="rango-hasta"><button class="rango-aplicar">Aplicar</button></div>')
    # Selector de rezago (Punto 2.1 del checklist storytelling): variantes precalculadas en Python
    # (_serie_combo_rezago), el click sólo cambia qué array se muestra.
    rezago_btns = ""
    if c.get("rezagos"):
        botones = "".join(
            f'<button class="rezago-btn{" active" if r == 0 else ""}" data-rezago="{r}">'
            f'{"Sin rezago" if r == 0 else f"+{r}m"}</button>'
            for r in c["rezagos"])
        rezago_btns = f'<div class="rezago-btns" data-idx="{i}"><span class="vista">Rezago:</span>{botones}</div>'
    grande = c.get("grande") or (c.get("sin_filtros") and not c.get("acumulando"))
    cell_cls = "cell cell-ancha" if grande else "cell"
    cbox_cls = "cbox cbox-grande" if grande else "cbox"
    frescura_html = c.get("frescura", "")
    # "Acumulando historia" (Punto 4 del checklist): sin canvas ni pantalla completa, un mensaje corto.
    if c.get("acumulando"):
        return (f'<div class="{cell_cls}">{cabeza}{subtitulo_html}{fila}{frescura_html}'
                f'<div class="acumulando">⏳ {c["acumulando"]}</div>{pie_html}</div>')
    # Ícono de pantalla completa (Punto 11): el JS compartido expande el .cell entero.
    fs_btn = '<button class="fs-btn" title="Pantalla completa" aria-label="Pantalla completa">⛶</button>'
    return (f'<div class="{cell_cls}">{fs_btn}{cabeza}{subtitulo_html}{fila}{frescura_html}{marca_html}'
            f'<div class="cdesc" data-idx="{i}"></div>'
            f'<div class="{cbox_cls}"><canvas id="ch{i}"></canvas></div>{filtros}{rezago_btns}{pie_html}</div>')


def _mezclar(hex_color, a):
    """Color `hex_color` con opacidad `a` sobre blanco, como hex (para fondos de celdas de tabla)."""
    r, g, b = (int(hex_color[k:k + 2], 16) for k in (1, 3, 5))
    return "#" + "".join(f"{round(255 - (255 - v) * a):02X}" for v in (r, g, b))


def _escribir_html(charts, series_js, semaforo, fecha_sem, tablas, notas_dict,
                    archivo_salida="index.html", extra_html=None, nav_extra="",
                    titulo_pagina="Monitor de coyuntura · Argentina", semaforo_fuente="",
                    fuentes_pagina=None, etiquetas=None):
    extra_html = extra_html or {}
    ahora = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).strftime("%d/%m/%Y %H:%M")
    grupo_tabla = {}
    for titulo, filas in tablas.items():
        if filas:
            grupo_tabla[filas[0]["grupo"]] = (titulo, filas)

    # Construir sección de notas metodológicas
    notas_html = ""
    if notas_dict:
        notas_ordenadas = sorted(notas_dict.items(), key=lambda x: x[1]["numero"])
        notas_items = []
        for nota_texto, nota_info in notas_ordenadas:
            num = nota_info["numero"]
            notas_items.append(f'<li id="nota-{num}"><strong>*{num}</strong> {nota_texto}</li>')
        notas_html = '<h3 class="sub">Notas metodológicas y fuentes</h3><ul class="notas-list">' + "".join(notas_items) + '</ul>'

    nav, secciones = "", ""
    for bloque in ORDEN_BLOQUES:
        cb = [c for c in charts if c["bloque"] == bloque]
        grupos_chart = {c["grupo"] for c in cb}
        grupos_tabla = {g for g, (t, fs) in grupo_tabla.items() if fs[0]["bloque"] == bloque}
        tiene_sem = (bloque == "real" and semaforo)
        if not cb and not grupos_tabla and not tiene_sem and bloque not in extra_html:
            continue
        nav += f'<a href="#{bloque}">{TITULO_BLOQUE.get(bloque, bloque)}</a>'
        grupos = [g for g in ORDEN_GRUPOS if g in grupos_chart or g in grupos_tabla]
        multi = len(grupos) > 1 or tiene_sem
        cuerpo = ""
        for g in grupos:
            if g in grupos_tabla:
                titulo, filas = grupo_tabla[g]
                cuerpo += _tabla_valores(titulo, filas)
            else:
                if multi:
                    cuerpo += f'<h3 class="grupo">{g}</h3>'
                celdas = "".join(_card_cell(c) for c in cb if c["grupo"] == g)
                cuerpo += f'<div class="grid">{celdas}</div>'
        if tiene_sem:
            cuerpo += _tabla_semaforo(semaforo, fecha_sem, semaforo_fuente)
        if bloque in extra_html:
            cuerpo += extra_html[bloque]
        secciones += (f'<section class="bloque" id="{bloque}"><h2>{TITULO_BLOQUE.get(bloque, bloque)}</h2>'
                      f'{cuerpo}</section>')
    # El link cruzado entre páginas va al final de la barra, empujado a la derecha (CSS .nav-pagina).
    nav += nav_extra

    css_vars = "\n".join(f"    --{k.replace('_', '-')}: {v};" for k, v in TEMA.items() if k != "fuente")
    fuente_css = '"Helvetica Neue", ' + TEMA["fuente"]
    tema_js = dict(TEMA, fuente=fuente_css)

    plantilla = """<!doctype html><html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITULO__</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  /* Bloque C: colores y tipografía de tema.py (una sola fuente de verdad, la misma que el mail). */
  :root {
__VARS__
    --linea:#E3E8ED; --grilla:#EEEEEE;
  }
  * { box-sizing:border-box; }
  html { scroll-behavior:smooth; }
  body { margin:0; background:var(--fondo); color:var(--texto); font-family:__FUENTE__; line-height:1.45; -webkit-font-smoothing:antialiased; }
  a { color:var(--azul-2); text-decoration:none; } a:hover { text-decoration:underline; }
  .wrap { max-width:1180px; margin:0 auto; padding:0 32px; }
  main.wrap { padding-bottom:60px; }
  header.masthead { border-top:4px solid var(--azul-1); padding:26px 0 16px; }
  header h1 { font-size:30px; line-height:1.15; margin:0; font-weight:700; letter-spacing:-.01em; }
  header .sub { font-size:14px; color:var(--texto-2); margin-top:6px; }
  nav.secciones { position:sticky; top:0; z-index:20; background:var(--fondo); border-bottom:1px solid var(--linea); }
  nav.secciones .wrap { display:flex; align-items:center; gap:22px; overflow-x:auto; scrollbar-width:none; }
  nav.secciones .wrap::-webkit-scrollbar { display:none; }
  nav.secciones a { flex:none; font-size:14px; color:var(--texto-2); padding:12px 0 10px; border-bottom:3px solid transparent; }
  nav.secciones a.activo { color:var(--texto); font-weight:700; border-bottom-color:var(--azul-1); }
  nav.secciones a:hover { color:var(--texto); text-decoration:none; }
  nav.secciones a.nav-pagina { margin-left:auto; color:var(--azul-2); font-weight:600; }
  section.bloque { padding-top:34px; scroll-margin-top:44px; }
  section.bloque > h2 { font-size:24px; margin:0; padding-top:10px; border-top:1px solid var(--texto); font-weight:700; }
  h3.grupo { font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--texto-3); font-weight:600; margin:26px 0 0; }
  .sub { font-size:14px; font-weight:700; margin:26px 0 8px; color:var(--texto); }
  .ref { color:var(--texto-3); font-weight:400; font-size:13px; }
  .nota { color:var(--texto-2); font-size:12px; margin:4px 0 12px; }
  .notas-list { margin:10px 0 14px 20px; padding:0; font-size:12px; color:var(--texto-2); }
  .notas-list li { margin:6px 0; scroll-margin-top:50px; }
  .notas-list strong { color:var(--texto); }
  .grid { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); column-gap:44px; }
  .cell { position:relative; border-top:1px solid var(--linea); padding:16px 0 22px; min-width:0; background:var(--fondo); }
  .fs-btn { position:absolute; top:12px; right:0; z-index:5; width:24px; height:24px; padding:0; border:0;
    background:none; color:var(--texto-3); font-size:13px; line-height:1; cursor:pointer; opacity:.7; }
  .fs-btn:hover { opacity:1; color:var(--texto); }
  .cell:fullscreen, .cell:-webkit-full-screen { overflow:auto; background:var(--fondo); display:flex; flex-direction:column; padding:24px; }
  .cell:fullscreen .cbox, .cell:-webkit-full-screen .cbox { flex:1 1 auto; height:auto !important; }
  .cell.fs-fallback { position:fixed; inset:12px; z-index:1000; overflow:auto; display:flex; flex-direction:column;
    padding:16px; box-shadow:0 4px 24px rgba(0,0,0,.25); }
  .cell.fs-fallback .cbox { flex:1 1 auto; height:auto !important; }
  .cn { font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--texto-3); font-weight:600; padding-right:30px; }
  .ct { font-size:18px; line-height:1.28; font-weight:700; margin:5px 0 0; color:var(--texto); padding-right:30px; }
  .csub { font-size:13px; color:var(--texto-2); margin-top:3px; line-height:1.35; }
  .cm { display:flex; align-items:baseline; flex-wrap:wrap; gap:4px 10px; margin-top:8px; }
  .cv { font-size:26px; font-weight:700; color:var(--azul-1); font-variant-numeric:tabular-nums; letter-spacing:-.01em; }
  .uni { font-size:13px; color:var(--texto-2); }
  /* D3: variación en gris azulado, sin juicio (el arena queda reservado a los valores negativos). */
  .chg { font-size:13px; color:var(--texto-2); font-variant-numeric:tabular-nums; }
  .chg .tri { font-size:11px; margin-right:3px; }
  /* Línea de frescura (Bloque B2, frescura.py). Grises de la paleta del Bloque C + azul para
     "al día". NUNCA el arena #C9A66B (en el Bloque C es el color de los valores negativos) ni rojo.
     El estado nunca va sólo en color: lleva ícono y texto. */
  .cf { font-size:11px; color:#7A8C9A; margin-top:5px; line-height:1.35; }
  .cf .per { color:#4A5A68; font-weight:600; }
  .cf .ok { color:#3A7CA5; font-weight:600; }
  .cf .atr { color:#2E3A45; font-weight:700; }
  .cf.grave { color:#2E3A45; background:#EEF1F4; border-left:3px solid #4A5A68; padding:4px 8px; border-radius:0 4px 4px 0; }
  .cf.grave .per { color:#2E3A45; }
  .marca-fecha { font-size:11px; color:var(--atrasado); background:var(--franja-fondo); border-left:3px solid var(--franja-borde);
    padding:4px 8px; border-radius:0 4px 4px 0; margin-top:6px; }
  .cdesc { font-size:13px; line-height:1.4; color:var(--texto-2); margin:10px 0 4px; }
  .cdesc:empty { display:none; }
  .ley { display:inline-block; max-width:100%; margin-right:12px; }
  .sw { display:inline-block; width:10px; height:10px; margin-right:5px; vertical-align:-1px; }
  .sw.sw-l { width:18px; height:0; vertical-align:middle; margin-bottom:2px; }
  .ley-x { display:inline-block; }
  .acumulando { color:var(--texto-2); font-size:12px; text-align:center; padding:20px 14px; background:var(--franja-fondo); margin-top:10px; }
  .cbox { position:relative; height:250px; margin-top:4px; }
  /* Pedro quiere TODAS las tarjetas del mismo tamaño por ahora (flags grande/sin_filtros siguen en el yaml):
     .cbox-grande { height:400px; } .cell-ancha { grid-column: span 2; } */
  .filtros, .rezago-btns { display:flex; align-items:baseline; flex-wrap:wrap; gap:2px; font-size:12px; color:var(--texto-3); margin-top:6px; }
  .vista { margin-right:6px; }
  .filtro, .rezago-btn { font:inherit; background:none; border:0; padding:2px 5px; color:var(--texto-2); cursor:pointer; border-bottom:2px solid transparent; }
  .filtro:hover, .rezago-btn:hover { color:var(--texto); }
  .filtro.active, .rezago-btn.active { color:var(--texto); font-weight:700; border-bottom-color:var(--azul-1); }
  .rango-custom { display:none; align-items:center; gap:6px; margin-top:6px; font-size:12px; color:var(--texto-2); }
  .rango-custom input[type=date] { font:inherit; font-size:12px; padding:2px 4px; border:1px solid var(--linea); background:var(--fondo); color:var(--texto); }
  .rango-aplicar { font:inherit; font-size:12px; background:var(--azul-1); color:#fff; border:0; padding:3px 10px; cursor:pointer; }
  .fuente-pie { font-size:11px; color:var(--texto-3); line-height:1.45; margin-top:6px; }
  .fuente-pie a { color:var(--texto-3); text-decoration:underline; text-decoration-color:#C9D3DC; }
  .fuente-tabla { margin:4px 0 14px; }
  .tabla { width:100%; border-collapse:collapse; font-size:13px; margin-bottom:8px; font-variant-numeric:tabular-nums; }
  .tabla th { text-align:right; color:var(--texto-3); font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:.04em; padding:6px 10px; border-bottom:1px solid var(--texto); }
  .tabla th:first-child { text-align:left; }
  .tabla td { padding:7px 10px; text-align:right; border-bottom:1px solid var(--linea); font-weight:600; }
  .tabla td.sec { text-align:left; font-weight:400; }
  .tabla td.num { color:var(--texto); font-weight:400; }
  footer { margin:40px 0 0; padding-top:12px; border-top:1px solid var(--texto); font-size:11px; color:var(--texto-3); }
  @media (max-width:760px) {
    .wrap { padding:0 16px; }
    header.masthead { padding:18px 0 12px; }
    header h1 { font-size:23px; }
    header .sub { font-size:13px; }
    .grid { grid-template-columns:minmax(0, 1fr); }
    section.bloque { padding-top:24px; }
    section.bloque > h2 { font-size:21px; }
    .ct { font-size:17px; }
    .cv { font-size:24px; }
    .cbox { height:220px; }
    nav.secciones a { font-size:13px; }
    .tabla { font-size:12px; } .tabla td, .tabla th { padding:6px 5px; }
  }
</style></head>
<body>
<header class="masthead"><div class="wrap">
  <h1>__TITULO__</h1>
  <div class="sub">Actualizado __AHORA__ · fuentes: __FUENTES__</div>
</div></header>
<nav class="secciones"><div class="wrap">__NAV__</div></nav>
<main class="wrap">
  __SECCIONES__
  __NOTAS__
  <footer>Pasá el cursor sobre cualquier gráfico para ver el valor. Editá indicadores en indicadores.yaml.</footer>
</main>
<script>
const SERIES = __DATA__;
const TEMA = __TEMA__;
const ETIQUETAS = __ETIQUETAS__;
const charts = {};
// Lookup por s.i (el idx de la tarjeta), NO por posición en SERIES: las tarjetas "acumulando
// historia" consumen un idx sin agregar serie.
const SERIE_POR_I = {};
SERIES.forEach(s => { SERIE_POR_I[s.i] = s; });

/* ---------- C1: tema único. Todos los gráficos heredan de acá; ninguno se estiliza por separado ---------- */
const FUENTE = TEMA.fuente;
const GRILLA = '#EEEEEE';
const NIVEL = [TEMA.azul_1, TEMA.azul_2, TEMA.azul_3, TEMA.azul_contexto];   // jerarquía: 0 = protagonista
const ANCHO = [2.5, 1.75, 1.75, 1.25];
const TRAZO = [[], [], [5, 3], [2, 2]];
const alfa = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; };
const esPP = u => u === 'p.p.' || u === 'pp';
const esPct = u => !!u && (u.includes('%') || esPP(u));
// Decimales según la unidad (D4, mismo criterio que titulares.decimales en Python)
function decDe(u, v) {
  if (esPct(u)) return esPP(u) ? 2 : 1;
  if (u && /millones|miles|puntos/.test(u)) return 0;
  const a = Math.abs(v || 0); return a >= 1000 ? 0 : a >= 10 ? 1 : 2;
}
const sufijo = u => esPP(u) ? ' pp' : (esPct(u) ? '%' : '');
const fmtN = (v, d) => v == null ? 's/d' : v.toLocaleString('es-AR', {minimumFractionDigits:d, maximumFractionDigits:d}).replace('-', '−');
const fmtU = (v, u) => fmtN(v, decDe(u, v));
const nivel = (i, n) => Math.min(n - 1 - i, 3);   // overlays: la ÚLTIMA serie es la protagonista (resume la card)
function ultimoIdx(arr) { let k = (arr || []).length - 1; while (k >= 0 && arr[k] == null) k--; return k; }
const colorSigno = (pos, neg) => c => (c.raw != null && c.raw < 0) ? neg : pos;
const tieneNeg = arr => (arr || []).some(v => v != null && v < 0);

Chart.defaults.font.family = FUENTE;
Chart.defaults.font.size = 11;
Chart.defaults.color = TEMA.texto_3;
Chart.defaults.responsive = true;
Chart.defaults.maintainAspectRatio = false;
Chart.defaults.animation = false;
Chart.defaults.plugins.legend.display = false;          // leyenda en prosa, sobre el gráfico (.cdesc)
Chart.defaults.elements.point.radius = 0;
Chart.defaults.elements.point.hoverRadius = 3;
Chart.defaults.elements.point.hitRadius = 8;
Chart.defaults.elements.line.borderWidth = 2;
Chart.defaults.elements.line.tension = 0;
Chart.defaults.elements.bar.borderWidth = 0;
Chart.defaults.interaction = { mode:'index', intersect:false };
Chart.defaults.scale.grid.color = GRILLA;
Chart.defaults.scale.border.display = false;
Chart.defaults.scale.ticks.color = TEMA.texto_3;
Object.assign(Chart.defaults.plugins.tooltip, {
  backgroundColor:'#FFFFFF', borderColor:TEMA.azul_contexto, borderWidth:1, titleColor:TEMA.texto,
  bodyColor:TEMA.texto_2, footerColor:TEMA.texto_2, padding:8, cornerRadius:2, boxWidth:8, boxHeight:8,
  titleFont:{ weight:'700' }, filter: it => it.raw != null,
});
const ejeX = (extra) => Object.assign({ grid:{ display:false }, ticks:{ maxTicksLimit:6, autoSkip:true, maxRotation:0 } }, extra || {});
const ejeY = (extra) => Object.assign({ grid:{ color:GRILLA, drawTicks:false },
  ticks:{ padding:6, maxTicksLimit:5, callback:(v) => Number(v).toLocaleString('es-AR') } }, extra || {});
const tituloEje = (t) => ({ display:!!t, text:t, font:{ size:10 }, color:TEMA.texto_3 });

// Etiquetas directas (C1): al final de cada línea (o arriba del último punto en gráficos de dos ejes) y
// sobre la barra destacada, con anti-superposición vertical simple. Reemplazan a la leyenda.
function textoEtiqueta(e, v) { return (e.texto ? e.texto + ' ' : '') + fmtU(v, e.u) + sufijo(e.u); }
const etiquetasDirectas = {
  id:'etiquetasDirectas',
  beforeUpdate(chart) {
    const x = chart.options.scales && chart.options.scales.x;
    if (x && x.ticks && chart.width && chart.width < 500) x.ticks.maxTicksLimit = 4;   // pantallas angostas
    const ctx = chart.ctx; let ancho = 0;
    ctx.save(); ctx.font = `700 12px ${FUENTE}`;
    chart.data.datasets.forEach(ds => {
      const e = ds.etiqueta; if (!e || e.arriba !== undefined) return;
      const k = (e.idx !== undefined && e.idx !== null) ? e.idx : ultimoIdx(ds.data); if (k < 0) return;
      const w = ctx.measureText(textoEtiqueta(e, ds.data[k])).width;
      // barra: la etiqueta va centrada sobre la barra, sólo necesita media etiqueta de margen
      ancho = Math.max(ancho, e.barra ? w / 2 : w);
    });
    ctx.restore();
    chart.options.layout.padding = { top:18, right: ancho ? ancho + 12 : 8, left:0, bottom:0 };
  },
  afterDatasetsDraw(chart) {
    const { ctx } = chart, items = [];
    chart.data.datasets.forEach((ds, i) => {
      const e = ds.etiqueta; if (!e || !chart.isDatasetVisible(i)) return;
      const k = (e.idx !== undefined && e.idx !== null) ? e.idx : ultimoIdx(ds.data);
      if (k < 0 || ds.data[k] == null) return;
      const el = chart.getDatasetMeta(i).data[k]; if (!el) return;
      const txt = textoEtiqueta(e, ds.data[k]);
      if (e.barra) items.push({ x:el.x, y: ds.data[k] < 0 ? el.y + 11 : el.y - 8, txt, color:TEMA.texto, align:'center', bold:true });
      else if (e.arriba !== undefined) items.push({ x:el.x - 2, y:el.y + e.arriba, txt, color:e.color || ds.borderColor, align:'right', bold:e.bold });
      else items.push({ x:el.x + 6, y:el.y, txt, color:e.color || ds.borderColor, align:'left', bold:e.bold });
    });
    items.filter(o => o.align === 'left').sort((a, b) => a.y - b.y).forEach((o, j, arr) => {
      if (j && o.y - arr[j - 1].y < 13) o.y = arr[j - 1].y + 13;
    });
    ctx.save(); ctx.textBaseline = 'middle';
    items.forEach(o => {
      ctx.font = `${o.bold ? '700' : '400'} 12px ${FUENTE}`;
      ctx.textAlign = o.align;
      const w = ctx.measureText(o.txt).width;
      const x0 = o.align === 'left' ? o.x - 2 : o.align === 'right' ? o.x - w - 2 : o.x - w / 2 - 2;
      ctx.fillStyle = 'rgba(255,255,255,.85)'; ctx.fillRect(x0, o.y - 7, w + 4, 14);
      ctx.fillStyle = o.color; ctx.fillText(o.txt, o.x, o.y);
    });
    ctx.restore();
  },
};
// Serie frenada (franja ⏸ del B2, D9): el eje sigue hasta hoy y se sombrea el tramo sin datos.
const tramoSinDatos = {
  id:'tramoSinDatos',
  beforeDatasetsDraw(chart, _a, opts) {
    if (!opts || !opts.activo) return;
    const d = chart.data.datasets[0].data, k = ultimoIdx(d);
    if (k < 0 || k >= d.length - 1) return;
    const a = chart.chartArea, x0 = chart.scales.x.getPixelForValue(k), { ctx } = chart;
    ctx.save();
    ctx.fillStyle = TEMA.franja_fondo; ctx.fillRect(x0, a.top, a.right - x0, a.bottom - a.top);
    ctx.fillStyle = TEMA.texto_3; ctx.font = `11px ${FUENTE}`; ctx.textAlign = 'center';
    ctx.fillText('sin datos', (x0 + a.right) / 2, a.top + 10);
    ctx.restore();
  },
};
// Línea del cero, fina y oscura, en todo gráfico con negativos.
const lineaCero = {
  id:'lineaCero',
  beforeDatasetsDraw(chart) {
    const y = chart.scales.y; if (!y || y.type === 'logarithmic' || !(y.min < 0 && y.max > 0)) return;
    const p = y.getPixelForValue(0), a = chart.chartArea, { ctx } = chart;
    ctx.save(); ctx.strokeStyle = TEMA.texto_2; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(a.left, p); ctx.lineTo(a.right, p); ctx.stroke(); ctx.restore();
  },
};
Chart.register(etiquetasDirectas, tramoSinDatos, lineaCero);

// Leyenda en prosa (C1): muestras con el color real de cada serie, sobre el gráfico.
function escribirLeyenda(i, items, extra) {
  const el = document.querySelector(`.cdesc[data-idx='${i}']`); if (!el) return;
  const partes = items.filter(it => it.label).map(it => {
    const sw = it.linea
      ? `<span class="sw sw-l" style="border-top:${it.ancho || 2}px ${it.dash ? 'dashed' : 'solid'} ${it.color}"></span>`
      : `<span class="sw" style="background:${it.color}"></span>`;
    return `<span class="ley">${sw}${it.label}</span>`;
  });
  if (extra) partes.push(`<span class="ley-x">${extra}</span>`);
  el.innerHTML = partes.join('');
}

// 'eventos' (opcional): [{fecha:"dd/mm/yy", texto:"..."}, ...] -- anotaciones de eventos puntuales
// dibujadas por eventosPlugin; el texto sale en el tooltip normal (afterBody).
function eventoTooltip(eventos) {
  return (items) => {
    if (!eventos || !eventos.length || !items.length) return [];
    const ev = eventos.find(e => e.fecha === items[0].label);
    return ev ? [`▾ ${ev.texto}`] : [];
  };
}

function eventosPlugin(eventos) {
  return {
    id:'eventosPolitica',
    afterDatasetsDraw(chart) {
      if (!eventos || !eventos.length) return;
      const { ctx, chartArea, scales } = chart;
      eventos.forEach(ev => {
        const i = chart.data.labels.indexOf(ev.fecha);
        if (i === -1) return;
        const x = scales.x.getPixelForValue(i);
        ctx.save(); ctx.strokeStyle = TEMA.texto_2; ctx.setLineDash([4, 3]); ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
        ctx.setLineDash([]); ctx.fillStyle = TEMA.texto_2; ctx.font = `10px ${FUENTE}`; ctx.textAlign = 'center';
        ctx.fillText('▾', x, chartArea.top - 1); ctx.restore();
      });
    }
  };
}

function calcFechaCorte(rango) {
  const hoy = new Date();
  const hace = (meses) => new Date(hoy.getFullYear(), hoy.getMonth() - meses, hoy.getDate()).toISOString().split('T')[0];
  switch(rango) {
    case '6m': return hace(6);
    case '1a': return hace(12);
    case '5a': return hace(60);
    case 'todo': return '1900-01-01';
    default: return null;
  }
}

function filtrarDatos(s, rango) {
  if (s.kind === 'overlay' || s.kind === 'incidencia') {
    if (rango === 'default') {
      return { x: s.x, datasets: s.datasets.map(d => ({ label: d.label, y: d.y })) };
    }
    const fechaCorte = calcFechaCorte(rango);
    const indices = s.full_dates.map((d, i) => d >= fechaCorte ? i : -1).filter(i => i >= 0);
    if (indices.length === 0) {
      return { x: s.x, datasets: s.datasets.map(d => ({ label: d.label, y: d.y })) };
    }
    return {
      x: indices.map(i => s.full_x[i]),
      datasets: s.datasets.map(d => ({ label: d.label, y: indices.map(i => d.full_y[i]) }))
    };
  }
  if (s.kind === 'espejo') {
    if (rango === 'default') {
      return { x: s.x, expo: s.expo, impo: s.impo, saldo: s.saldo };
    }
    const fechaCorte = calcFechaCorte(rango);
    const indices = s.full_dates.map((d, i) => d >= fechaCorte ? i : -1).filter(i => i >= 0);
    if (indices.length === 0) {
      return { x: s.x, expo: s.expo, impo: s.impo, saldo: s.saldo };
    }
    return {
      x: indices.map(i => s.full_x[i]),
      expo: indices.map(i => s.full_expo[i]),
      impo: indices.map(i => s.full_impo[i]),
      saldo: indices.map(i => s.full_saldo[i]),
    };
  }
  if (s.kind === 'combo_bl') {
    if (rango === 'default') {
      return { x: s.x, barras: s.barras.map(b => ({ label: b.label, y: b.y })), linea: s.linea };
    }
    const fechaCorte = calcFechaCorte(rango);
    const indices = s.full_dates.map((d, i) => d >= fechaCorte ? i : -1).filter(i => i >= 0);
    if (indices.length === 0) {
      return { x: s.x, barras: s.barras.map(b => ({ label: b.label, y: b.y })), linea: s.linea };
    }
    return {
      x: indices.map(i => s.full_x[i]),
      barras: s.barras.map(b => ({ label: b.label, y: indices.map(i => b.full_y[i]) })),
      linea: indices.map(i => s.full_linea[i]),
    };
  }
  if (s.kind === 'combo_2lineas' || s.kind === 'combo_rezago') {
    if (rango === 'default') {
      return { x: s.x, izq: s.izq, der: s.der };
    }
    const fechaCorte = calcFechaCorte(rango);
    const indices = s.full_dates.map((d, i) => d >= fechaCorte ? i : -1).filter(i => i >= 0);
    if (indices.length === 0) {
      return { x: s.x, izq: s.izq, der: s.der };
    }
    return {
      x: indices.map(i => s.full_x[i]),
      izq: indices.map(i => s.full_izq[i]),
      der: indices.map(i => s.full_der[i]),
    };
  }
  if (s.kind === 'combo_evento') {
    if (rango === 'default') {
      return { x: s.x, barra: s.barra, evento: s.evento };
    }
    const fechaCorte = calcFechaCorte(rango);
    const indices = s.full_dates.map((d, i) => d >= fechaCorte ? i : -1).filter(i => i >= 0);
    if (indices.length === 0) {
      return { x: s.x, barra: s.barra, evento: s.evento };
    }
    return {
      x: indices.map(i => s.full_x[i]),
      barra: indices.map(i => s.full_barra[i]),
      evento: indices.map(i => s.full_evento[i]),
    };
  }
  if (rango === 'default') {
    return { x: s.x, y: s.y, flujo: s.flujo };
  }
  const fechaCorte = calcFechaCorte(rango);
  const indices = s.full_dates.map((d, i) => d >= fechaCorte ? i : -1).filter(i => i >= 0);
  if (indices.length === 0) {
    return { x: s.x, y: s.y, flujo: s.flujo };
  }
  return {
    x: indices.map(i => s.full_x[i]),
    y: indices.map(i => s.full_y[i]),
    flujo: s.full_flujo ? indices.map(i => s.full_flujo[i]) : undefined
  };
}

// Percentil con interpolación lineal (mismo método que pandas .quantile() por defecto),
// para que el eje calculado en el navegador para un rango "Personalizado" arbitrario sea
// consistente con el que ya viene precalculado en Python para Default/1A/5A/2008/Todo.
function percentil(arr, p) {
  if (!arr.length) return null;
  const orden = [...arr].sort((a, b) => a - b);
  const idx = p * (orden.length - 1);
  const lo = Math.floor(idx), hi = Math.ceil(idx);
  if (lo === hi) return orden[lo];
  return orden[lo] + (orden[hi] - orden[lo]) * (idx - lo);
}

// Recalcula el eje (percentil 95 + atípicos) de incidencia_stack para un rango de fechas
// arbitrario (ver Punto 6): mismo mecanismo que _serie_incidencia en Python, pero aplicado a
// los índices que caen dentro del rango "Personalizado" que eligió el usuario, ya que ese rango
// no es uno de los 5 precalculados server-side.
function calcularEjeIncidencia(s, indices) {
  const MARGEN = 1.15;
  const totales = indices.map(i => {
    let pos = 0, neg = 0;
    s.datasets.forEach(d => { const v = d.full_y[i]; if (v > 0) pos += v; else if (v < 0) neg += v; });
    return [pos, neg];
  });
  const positivos = totales.filter(([p]) => p > 0).map(([p]) => p);
  const negativos = totales.filter(([, n]) => n < 0).map(([, n]) => Math.abs(n));
  const yMax = positivos.length ? Math.round(percentil(positivos, 0.95) * MARGEN * 100) / 100 : undefined;
  const yMin = negativos.length ? Math.round(-percentil(negativos, 0.95) * MARGEN * 100) / 100 : undefined;
  const atipicos = {};
  indices.forEach((i, k) => {
    const [pos, neg] = totales[k];
    if ((yMax !== undefined && pos > yMax) || (yMin !== undefined && neg < yMin)) {
      atipicos[s.full_x[i]] = Math.round((pos + neg) * 100) / 100;
    }
  });
  return { y_max: yMax, y_min: yMin, atipicos };
}

// Filtro de rango personalizado (Punto 6): reutiliza los mismos arrays full_* que ya alimentan
// filtrarDatos(), sólo cambia el criterio de selección de índices (desde/hasta elegidos por el
// usuario en vez de uno de los 5 rangos fijos).
function filtrarDatosPersonalizado(s, desde, hasta) {
  const hastaCmp = hasta + 'T23:59:59';
  const indices = s.full_dates.map((d, i) => (d >= desde && d <= hastaCmp) ? i : -1).filter(i => i >= 0);
  if (s.kind === 'overlay' || s.kind === 'incidencia') {
    const resultado = { x: indices.map(i => s.full_x[i]), datasets: s.datasets.map(d => ({ label: d.label, y: indices.map(i => d.full_y[i]) })) };
    if (s.kind === 'incidencia') resultado.eje = calcularEjeIncidencia(s, indices);
    return resultado;
  }
  if (s.kind === 'espejo') {
    return {
      x: indices.map(i => s.full_x[i]),
      expo: indices.map(i => s.full_expo[i]),
      impo: indices.map(i => s.full_impo[i]),
      saldo: indices.map(i => s.full_saldo[i]),
    };
  }
  if (s.kind === 'combo_bl') {
    return {
      x: indices.map(i => s.full_x[i]),
      barras: s.barras.map(b => ({ label: b.label, y: indices.map(i => b.full_y[i]) })),
      linea: indices.map(i => s.full_linea[i]),
    };
  }
  if (s.kind === 'combo_2lineas' || s.kind === 'combo_rezago') {
    return {
      x: indices.map(i => s.full_x[i]),
      izq: indices.map(i => s.full_izq[i]),
      der: indices.map(i => s.full_der[i]),
    };
  }
  if (s.kind === 'combo_evento') {
    return {
      x: indices.map(i => s.full_x[i]),
      barra: indices.map(i => s.full_barra[i]),
      evento: indices.map(i => s.full_evento[i]),
    };
  }
  return {
    x: indices.map(i => s.full_x[i]),
    y: indices.map(i => s.full_y[i]),
    flujo: s.full_flujo ? indices.map(i => s.full_flujo[i]) : undefined
  };
}

const tooltipU = (unidad) => (c) => ` ${c.dataset.label ? c.dataset.label + ': ' : ''}${c.parsed.y == null ? 's/d' : fmtU(c.parsed.y, unidad)} ${unidad || ''}`;

const baseOpts = (s) => ({
  plugins:{ tramoSinDatos:{ activo: !!s.frenada },
    tooltip:{ callbacks:{ label: tooltipU(s.unidad), afterBody: eventoTooltip(s.eventos) } } },
  scales:{ x: ejeX(s.x && s.x.length < 30 && !s.full_dates ? { ticks:{ maxRotation:0, autoSkip:true } } : undefined),
           y: s.kind === 'bar' ? { display:false, grace:'8%' } : ejeY() },
});

const espejoOpts = (unidad) => ({
  plugins:{ tooltip:{ callbacks:{ label:(c) => {
      const v = c.dataset.type === 'line' ? c.parsed.y : Math.abs(c.parsed.y);
      return ` ${c.dataset.label}: ${v == null ? 's/d' : fmtU(v, unidad)} ${unidad}`;
    } } } },
  scales:{ x: ejeX({ stacked:true }), y: ejeY({ stacked:true, ticks:{ padding:6, maxTicksLimit:5, callback:(v) => Math.abs(v).toLocaleString('es-AR') } }) },
});

const overlayOpts = (s) => ({
  // spanGaps: series superpuestas de frecuencias distintas (ej. trimestral + diaria) dejan huecos (null)
  // en el eje compartido; sin esto la de menor frecuencia no se dibuja como línea.
  spanGaps: true,
  plugins:{ tooltip:{ callbacks:{ label: tooltipU(s.unidad),
      afterBody:(items) => (s.cruce && items.length && items[0].label === s.cruce.fecha) ? [`◆ ${s.cruce.texto}`] : [] } } },
  scales:{ x: ejeX(), y: ejeY({ type: s.escala_log ? 'logarithmic' : 'linear' }) },
  elements:{ point:{ radius: s.radio_punto || 0 } },
});

// Barras AGRUPADAS (no apiladas): cada bono amortiza en % de SU PROPIO valor nominal.
const muroOpts = (unidad) => ({
  plugins:{ tooltip:{ callbacks:{ label: tooltipU(unidad) } } },
  scales:{ x:{ grid:{ display:false } }, y: ejeY() },
});

// Marca vertical de "cambio de liderazgo" en un overlay (ver 'cruce' en _serie_overlay).
function cruceOverlayPlugin(cruce) {
  return {
    id:'cruceOverlay',
    afterDatasetsDraw(chart) {
      if (!cruce) return;
      const i = chart.data.labels.indexOf(cruce.fecha);
      if (i === -1) return;
      const { ctx, chartArea, scales } = chart;
      const x = scales.x.getPixelForValue(i);
      ctx.save(); ctx.strokeStyle = TEMA.texto_2; ctx.setLineDash([4, 3]); ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
      ctx.setLineDash([]); ctx.fillStyle = TEMA.texto_2; ctx.font = `bold 11px ${FUENTE}`; ctx.textAlign = 'center';
      ctx.fillText('◆', x, chartArea.top - 2); ctx.restore();
    }
  };
}

const comboOpts = (unidad, unidadLinea, tituloBarras) => ({
  plugins:{ tooltip:{ callbacks:{ label:(c) => { const u = c.dataset.yAxisID === 'y1' ? (unidadLinea || unidad) : unidad;
      return ` ${c.dataset.label}: ${c.parsed.y == null ? 's/d' : fmtU(c.parsed.y, u)} ${u}`; } } } },
  scales:{ x: ejeX(), y: ejeY({ position:'left', title: tituloEje(tituloBarras || 'Var. mensual') }),
           y1: ejeY({ position:'right', grid:{ display:false }, title: tituloEje('Stock') }) },
});

// Combo genérico de 1-2 barras + 1 línea (ver _serie_combo_barras_linea en Python).
const comboBLOpts = (unidadBarras, unidadLinea) => ({
  plugins:{ tooltip:{ callbacks:{ label:(c) => { const u = c.dataset.yAxisID === 'y1' ? unidadLinea : unidadBarras;
      return ` ${c.dataset.label}: ${c.parsed.y == null ? 's/d' : fmtU(c.parsed.y, u)} ${u}`; } } } },
  scales:{ x: ejeX(), y: ejeY({ position:'left', title: tituloEje(unidadBarras) }),
           y1: ejeY({ position:'right', grid:{ display:false }, title: tituloEje(unidadLinea) }) },
});

// Alinea el cero de los ejes 'y' e 'y1' del gráfico de eventos (decisión de Pedro): ver _planCero.
const N_INTERVALOS_CERO = 6;
function _pasoRedondo(x) {
  const p = Math.pow(10, Math.floor(Math.log10(x)));
  const m = x / p;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
}
function _planCero(chart) {
  const rangos = { y: { min: 0, max: 0 }, y1: { min: 0, max: 0 } };  // el 0 siempre entra
  chart.data.datasets.forEach(d => {
    const r = rangos[d.yAxisID || 'y'];
    if (!r || chart.getDatasetMeta(chart.data.datasets.indexOf(d)).hidden) return;
    (d.data || []).forEach(v => { if (v != null && isFinite(v)) { r.min = Math.min(r.min, v); r.max = Math.max(r.max, v); } });
  });
  const N = N_INTERVALOS_CERO;
  let mejor = null;
  for (let k = 0; k <= N; k++) {  // k = cantidad de intervalos debajo del cero
    let costo = 0, pasos = {}, posible = true;
    for (const [id, r] of Object.entries(rangos)) {
      if (r.max === r.min) { pasos[id] = null; continue; }  // eje sin rango: se resuelve abajo
      const abajo = r.min < 0 ? (k ? -r.min / k : Infinity) : 0;
      const arriba = r.max > 0 ? (k < N ? r.max / (N - k) : Infinity) : 0;
      const necesario = Math.max(abajo, arriba);
      if (!isFinite(necesario)) { posible = false; break; }
      pasos[id] = _pasoRedondo(necesario);
      costo += N * pasos[id] / (r.max - r.min);  // 1 = sin desperdicio
    }
    if (posible && (!mejor || costo < mejor.costo)) mejor = { k, pasos, costo };
  }
  if (!mejor) return null;
  // Eje sin rango (todo en 0): toma el paso del otro eje en vez de una escala 0..N inventada
  // (en este gráfico los dos ejes están en la misma unidad); 1 si ninguno tiene rango.
  const otroPaso = Object.values(mejor.pasos).find(p => p !== null) || 1;
  for (const id of Object.keys(mejor.pasos)) if (mejor.pasos[id] === null) mejor.pasos[id] = otroPaso;
  return { k: mejor.k, N, pasos: mejor.pasos };
}
function alinearCeroLimites(scale) {
  const plan = _planCero(scale.chart);
  if (!plan) return;
  const paso = plan.pasos[scale.id];
  scale.min = -plan.k * paso || 0;  // "|| 0": evita un -0 en el eje
  scale.max = (plan.N - plan.k) * paso;
}
function alinearCeroTicks(scale) {
  const plan = _planCero(scale.chart);
  if (!plan) return;
  const paso = plan.pasos[scale.id];
  scale.ticks = Array.from({ length: plan.N + 1 }, (_, i) => ({ value: (i - plan.k) * paso || 0 }));
}

const comboEventoOpts = (unidadBarra, unidadEvento) => ({
  plugins:{ tooltip:{ callbacks:{ label:(c) => {
      if (c.parsed.y == null) return null;
      const u = c.dataset.yAxisID === 'y1' ? unidadEvento : unidadBarra;
      return ` ${c.dataset.label}: ${fmtU(c.parsed.y, u)} ${u}`;
    } } } },
  scales:{ x: ejeX(),
           y:{ position:'left', afterDataLimits: alinearCeroLimites, afterBuildTicks: alinearCeroTicks, grid:{ color:GRILLA, drawTicks:false }, title: tituloEje(unidadBarra) },
           y1:{ position:'right', afterDataLimits: alinearCeroLimites, afterBuildTicks: alinearCeroTicks, grid:{ display:false }, title: tituloEje(unidadEvento) } },
});

// Combo de DOS líneas en dos ejes (ver _serie_combo_2lineas en Python).
const combo2LOpts = (unidadIzq, unidadDer) => ({
  plugins:{ tooltip:{ callbacks:{ label:(c) => { const u = c.dataset.yAxisID === 'y1' ? unidadDer : unidadIzq;
      return ` ${c.dataset.label}: ${c.parsed.y == null ? 's/d' : fmtU(c.parsed.y, u)} ${u}`; } } } },
  scales:{ x: ejeX(), y: ejeY({ position:'left', title: tituloEje(unidadIzq) }),
           y1: ejeY({ position:'right', grid:{ display:false }, title: tituloEje(unidadDer) }) },
});

const incidenciaOpts = (unidad, yMax, yMin) => ({
  plugins:{ tooltip:{ callbacks:{
      label:(c) => ` ${c.dataset.label}: ${c.parsed.y == null ? 's/d' : fmtN(c.parsed.y, 2)} pp`,
      afterBody:(items) => {
        if (!items.length) return [];
        const lineas = [];
        const atipicos = items[0].chart.$atipicos;
        const total = atipicos ? atipicos[items[0].label] : undefined;
        if (total !== undefined) {
          lineas.push(`⚠ Valor atípico, fuera de escala del gráfico — total real: ${total > 0 ? '+' : ''}${fmtN(total, 2)} pp`);
        }
        // Detalle de "Resto": qué divisiones lo componen y cuánto aportó cada una ESE mes.
        const restoDetalle = items[0].chart.$restoDetalle;
        const detalle = restoDetalle ? restoDetalle[items[0].label] : null;
        if (detalle && detalle.length) {
          lineas.push('Detalle de "Resto":');
          detalle.forEach(d => lineas.push(`  ${d.nombre}: ${d.valor > 0 ? '+' : ''}${fmtN(d.valor, 2)} pp`));
        }
        return lineas;
      } } } },
  scales:{ x: ejeX({ stacked:true }), y: ejeY({ stacked:true, max: yMax ?? undefined, min: yMin ?? undefined }) },
});

// Marca los meses "atípicos" (fuera del rango normal del eje) con un ⚠ arriba o abajo de la barra recortada.
const atipicosIncidenciaPlugin = {
  id:'atipicosIncidencia',
  afterDatasetsDraw(chart) {
    const atipicos = chart.$atipicos;
    if (!atipicos || !Object.keys(atipicos).length) return;
    const { ctx, chartArea, scales } = chart;
    ctx.save(); ctx.font = `bold 12px ${FUENTE}`; ctx.fillStyle = TEMA.texto_2; ctx.textAlign = 'center';
    chart.data.labels.forEach((label, i) => {
      if (atipicos[label] === undefined) return;
      const x = scales.x.getPixelForValue(i);
      ctx.fillText('⚠', x, atipicos[label] >= 0 ? chartArea.top - 2 : chartArea.bottom + 16);
    });
    ctx.restore();
  }
};

// "Actividad por sector": una columna por sector, ordenadas por la variación de actividad, con burbuja
// de % del empleo en la punta (radio ~ raíz del %, para que el ÁREA sea proporcional al peso).
const sectorBarOpts = (empleoPct) => ({
  layout:{ padding:{ top:18 } },
  plugins:{ tooltip:{ callbacks:{
      label:(c) => [`Actividad (EMAE, i.a.): ${c.parsed.y > 0 ? '+' : ''}${fmtN(c.parsed.y, 1)}%`,
                    `% del empleo total: ${fmtN(empleoPct[c.dataIndex], 1)}%`] } } },
  scales:{ x:{ grid:{ display:false }, ticks:{ font:{ size:9 }, maxRotation:60, minRotation:60 } },
           y: ejeY({ title: tituloEje('Variación % interanual de actividad (EMAE)') }) },
});
function burbujaSectorPlugin(empleoPct) {
  return {
    id:'burbujaSector',
    afterDatasetsDraw(chart) {
      const meta = chart.getDatasetMeta(0), { ctx } = chart;
      ctx.save();
      meta.data.forEach((bar, i) => {
        const r = Math.max(3, Math.sqrt(empleoPct[i] || 0) * 6);
        ctx.beginPath(); ctx.arc(bar.x, bar.y, r, 0, Math.PI * 2);
        ctx.fillStyle = alfa(TEMA.azul_1, .55); ctx.strokeStyle = TEMA.azul_1; ctx.lineWidth = 1;
        ctx.fill(); ctx.stroke();
      });
      ctx.restore();
    }
  };
}

const NEG_TXT = 'Valores negativos en arena.';
SERIES.forEach(s => {
  const el = document.getElementById('ch' + s.i);
  if (!el) return;
  const ctx = el.getContext('2d');
  let ley = [], extra = '';
  if (s.kind === 'combo') {
    charts[s.i] = new Chart(ctx, { data:{ labels:s.x, datasets:[
        { type:'bar', label: s.label_barras || 'Variación mensual', data:s.flujo, backgroundColor: colorSigno(TEMA.azul_3, TEMA.negativo), yAxisID:'y', order:1 },
        { type:'line', label:'Stock', data:s.y, borderColor:TEMA.azul_1, backgroundColor:TEMA.azul_1, yAxisID:'y1', order:0,
          etiqueta:{ u:s.unidad_linea || s.unidad, arriba:-12, bold:true } }
      ]}, options: comboOpts(s.unidad, s.unidad_linea, s.titulo_barras) });
    ley = [{ label:'Stock (eje derecho)', color:TEMA.azul_1, linea:true },
           { label: (s.label_barras ? s.label_barras.toLowerCase() + ', ' + s.unidad : 'variación mensual') + ' (eje izquierdo)', color:TEMA.azul_3 }];
    if (tieneNeg(s.full_flujo || s.flujo)) extra = s.label_barras ? 'Ventas netas (negativos) en arena.' : 'Caídas en arena.';
  } else if (s.kind === 'overlay') {
    const n = s.datasets.length;
    const dss = s.datasets.map((d, i) => {
      const r = nivel(i, n), col = NIVEL[r];
      if (s.barras) {
        const neg = r === 0 ? TEMA.negativo : alfa(TEMA.negativo, .5);
        return { label:d.label, data:d.y, backgroundColor: colorSigno(col, neg), order:r };
      }
      return { label:d.label, data:d.y, borderColor:col, backgroundColor:col, borderWidth:ANCHO[r], borderDash:TRAZO[r], order:r,
               etiqueta:{ texto: ETIQUETAS[d.label] || (d.label.length <= 16 ? d.label : ''), u:s.unidad, bold: r === 0,
                          color: r === 3 ? TEMA.texto_3 : col } };
    });
    charts[s.i] = new Chart(ctx, { type: s.barras ? 'bar' : 'line', data:{ labels:s.x, datasets:dss },
      options: overlayOpts(s), plugins: s.cruce ? [cruceOverlayPlugin(s.cruce)] : [] });
    ley = s.datasets.map((d, i) => { const r = nivel(i, n);
      return { label:d.label, color:NIVEL[r], linea:!s.barras, ancho:ANCHO[r], dash:TRAZO[r].length > 0 }; }).reverse();
    if (s.barras && s.datasets.some(d => tieneNeg(d.full_y || d.y))) extra = NEG_TXT;
    if (s.cruce) extra = (extra ? extra + ' ' : '') + '◆ marca el cambio de liderazgo.';
  } else if (s.kind === 'incidencia') {
    const dss = s.datasets.map((d, i) => {
      const r = d.label.startsWith('Resto') ? 3 : Math.min(i, 2);
      return { label:d.label, data:d.y, backgroundColor: colorSigno(NIVEL[r], TEMA.negativo), stack:'incidencia' };
    });
    charts[s.i] = new Chart(ctx, { type:'bar', data:{ labels:s.x, datasets:dss },
      options: incidenciaOpts(s.unidad, s.y_max, s.y_min), plugins:[atipicosIncidenciaPlugin] });
    charts[s.i].$atipicos = s.atipicos;
    charts[s.i].$restoDetalle = s.resto_detalle;
    ley = s.datasets.map((d, i) => ({ label:d.label, color: NIVEL[d.label.startsWith('Resto') ? 3 : Math.min(i, 2)] }));
    extra = 'Aportes negativos en arena.';
  } else if (s.kind === 'espejo') {
    charts[s.i] = new Chart(ctx, { data:{ labels:s.x, datasets:[
        { type:'bar', label:'Exportaciones', data:s.expo, backgroundColor:TEMA.azul_3, stack:'comercio', order:2 },
        { type:'bar', label:'Importaciones', data:s.impo, backgroundColor:TEMA.azul_contexto, stack:'comercio', order:2 },
        { type:'line', label:'Saldo comercial', data:s.saldo, borderColor:TEMA.azul_1, backgroundColor:TEMA.azul_1, borderWidth:2.25, order:1,
          segment:{ borderColor: g => (g.p0.parsed.y < 0 || g.p1.parsed.y < 0) ? TEMA.negativo : undefined },
          etiqueta:{ texto:'Saldo', u:s.unidad, bold:true } },
      ]}, options: espejoOpts(s.unidad) });
    ley = [{ label:'Exportaciones (arriba)', color:TEMA.azul_3 }, { label:'importaciones (abajo)', color:TEMA.azul_contexto },
           { label:'saldo', color:TEMA.azul_1, linea:true }];
    if (tieneNeg(s.full_saldo || s.saldo)) extra = 'Saldo negativo en arena.';
  } else if (s.kind === 'bar') {
    const dest = s.destacar;
    const bg = (c) => {
      const k = (dest !== undefined && dest !== null) ? dest : ultimoIdx(c.chart.data.datasets[0].data);
      const ult = c.dataIndex === k;
      if (c.raw != null && c.raw < 0) return ult ? TEMA.negativo : alfa(TEMA.negativo, .45);
      return ult ? TEMA.azul_1 : TEMA.azul_contexto;
    };
    charts[s.i] = new Chart(ctx, { type:'bar',
      data:{ labels:s.x, datasets:[{ label:'', data:s.y, backgroundColor:bg, categoryPercentage:.85, barPercentage:.9,
                                     etiqueta:{ barra:true, idx:dest, u:s.unidad } }] },
      options: baseOpts(s) });
    extra = (dest !== undefined && dest !== null) ? 'En azul oscuro, el contrato más cercano.' : 'En azul oscuro, el último dato.';
    if (tieneNeg(s.full_y || s.y)) extra += ' ' + NEG_TXT;
  } else if (s.kind === 'bar_sectores') {
    charts[s.i] = new Chart(ctx, { type:'bar',
      data:{ labels:s.x, datasets:[{ label:'', data:s.y, backgroundColor: colorSigno(TEMA.azul_3, TEMA.negativo) }] },
      options: sectorBarOpts(s.empleo_pct), plugins:[burbujaSectorPlugin(s.empleo_pct)] });
    extra = 'Barras: variación interanual de la actividad (caídas en arena). Burbujas: peso de cada sector en el empleo.';
  } else if (s.kind === 'combo_bl') {
    const nb = s.barras.length;
    const datasets = s.barras.map((b, i) => ({ type:'bar', label:b.label, data:b.y, yAxisID:'y', order:1,
        backgroundColor: nb === 1 ? colorSigno(TEMA.azul_3, TEMA.negativo) : (i === 0 ? TEMA.azul_3 : TEMA.azul_contexto) }));
    datasets.push({ type:'line', label:s.linea_label, data:s.linea, borderColor:TEMA.azul_1, backgroundColor:TEMA.azul_1,
        yAxisID:'y1', order:0, etiqueta:{ u:s.unidad_linea, arriba:-12, bold:true } });
    charts[s.i] = new Chart(ctx, { data:{ labels:s.x, datasets }, options: comboBLOpts(s.unidad_barras, s.unidad_linea) });
    ley = s.barras.map((b, i) => ({ label: b.label + (i === nb - 1 ? ' (eje izquierdo)' : ''), color: nb === 1 || i === 0 ? TEMA.azul_3 : TEMA.azul_contexto }))
          .concat([{ label: s.linea_label + ' (eje derecho)', color:TEMA.azul_1, linea:true }]);
    if (nb === 1 && tieneNeg(s.barras[0].full_y || s.barras[0].y)) extra = NEG_TXT;
  } else if (s.kind === 'combo_2lineas' || s.kind === 'combo_rezago') {
    const v0 = s.kind === 'combo_rezago' ? s.variantes[String(s.rezago_default)] : s;
    charts[s.i] = new Chart(ctx, { data:{ labels:v0.x, datasets:[
        { type:'line', label:s.label_izq, data:v0.izq, borderColor:TEMA.azul_1, backgroundColor:TEMA.azul_1, borderWidth:2.5, yAxisID:'y',
          etiqueta:{ u:s.unidad_izq, arriba:-12, bold:true } },
        { type:'line', label:s.label_der, data:v0.der, borderColor:TEMA.azul_3, backgroundColor:TEMA.azul_3, borderWidth:1.75, borderDash:[5, 3], yAxisID:'y1',
          etiqueta:{ u:s.unidad_der, arriba:13 } },
      ]}, options: combo2LOpts(s.unidad_izq, s.unidad_der) });
    ley = [{ label: s.label_izq + ' (eje izquierdo)', color:TEMA.azul_1, linea:true, ancho:2.5 },
           { label: s.label_der + ' (eje derecho)', color:TEMA.azul_3, linea:true, dash:true }];
  } else if (s.kind === 'combo_evento') {
    charts[s.i] = new Chart(ctx, { data:{ labels:s.x, datasets:[
        { type:'bar', label:s.label_barra, data:s.barra, backgroundColor: colorSigno(TEMA.azul_3, TEMA.negativo), yAxisID:'y', order:1 },
        { type:'line', label:s.label_evento, data:s.evento, showLine:false, pointRadius:6, pointHoverRadius:8,
          pointBackgroundColor:TEMA.azul_1, pointBorderColor:'#fff', pointBorderWidth:1.5, yAxisID:'y1', order:0 },
      ]}, options: comboEventoOpts(s.unidad_barra, s.unidad_evento) });
    ley = [{ label: s.label_barra + ' (barras, eje izquierdo)', color:TEMA.azul_3 }, { label: s.label_evento + ' (puntos, eje derecho)', color:TEMA.azul_1 }];
    if (tieneNeg(s.full_barra || s.barra)) extra = NEG_TXT;
  } else if (s.kind === 'muro') {
    charts[s.i] = new Chart(ctx, { type:'bar', data:{ labels:s.x, datasets: s.datasets.map((d, i) => (
        { label:d.label, data:d.y, backgroundColor: NIVEL[Math.min(i, 3)] }
      )) }, options: muroOpts(s.unidad) });
    ley = s.datasets.map((d, i) => ({ label:d.label, color: NIVEL[Math.min(i, 3)] }));
  } else {
    charts[s.i] = new Chart(ctx, { type:'line',
      data:{ labels:s.x, datasets:[{ label:'', data:s.y, borderColor:TEMA.azul_1, backgroundColor:TEMA.azul_1, fill:false,
                                     etiqueta:{ u:s.unidad, bold:true } }] },
      options: baseOpts(s), plugins: s.eventos ? [eventosPlugin(s.eventos)] : [] });
    if (s.eventos && s.eventos.length) extra = '▾ marca eventos (detalle en el tooltip).';
  }
  if (s.frenada) extra = (extra ? extra + ' ' : '') + 'El tramo sombreado no tiene datos de la fuente.';
  escribirLeyenda(s.i, ley, extra);
});

// Redibuja un chart ya creado con los datos ya filtrados (por un botón de rango fijo o por
// el rango "Personalizado"). Los colores son funciones del valor (tema), no hace falta recolorear.
function aplicarFiltro(idx, serie, rango, datFiltrados) {
  charts[idx].data.labels = datFiltrados.x;
  if (serie.kind === 'combo') {
    charts[idx].data.datasets[0].data = datFiltrados.flujo;
    charts[idx].data.datasets[1].data = datFiltrados.y;
  } else if (serie.kind === 'overlay' || serie.kind === 'incidencia') {
    datFiltrados.datasets.forEach((d, i) => { charts[idx].data.datasets[i].data = d.y; });
    if (serie.kind === 'incidencia') {
      // Rangos fijos usan el eje precalculado en Python (serie.ejes); "Personalizado" trae el
      // suyo ya calculado en JS (ver calcularEjeIncidencia) dentro de datFiltrados.eje.
      const eje = (serie.ejes && serie.ejes[rango]) || datFiltrados.eje;
      if (eje) {
        charts[idx].options.scales.y.max = eje.y_max ?? undefined;
        charts[idx].options.scales.y.min = eje.y_min ?? undefined;
        charts[idx].$atipicos = eje.atipicos;
      }
    }
  } else if (serie.kind === 'espejo') {
    charts[idx].data.datasets[0].data = datFiltrados.expo;
    charts[idx].data.datasets[1].data = datFiltrados.impo;
    charts[idx].data.datasets[2].data = datFiltrados.saldo;
  } else if (serie.kind === 'combo_bl') {
    datFiltrados.barras.forEach((b, i) => { charts[idx].data.datasets[i].data = b.y; });
    charts[idx].data.datasets[datFiltrados.barras.length].data = datFiltrados.linea;
  } else if (serie.kind === 'combo_2lineas' || serie.kind === 'combo_rezago') {
    charts[idx].data.datasets[0].data = datFiltrados.izq;
    charts[idx].data.datasets[1].data = datFiltrados.der;
  } else if (serie.kind === 'combo_evento') {
    charts[idx].data.datasets[0].data = datFiltrados.barra;
    charts[idx].data.datasets[1].data = datFiltrados.evento;
  } else {
    charts[idx].data.datasets[0].data = datFiltrados.y;
  }
  charts[idx].update('none');
}

// Event listeners para botones de filtro (rango de fecha). Selector acotado a
// '.filtro[data-rango]' (no todo '.filtro') por si en el futuro se reusa la misma
// clase visual con otro atributo data-* para un mecanismo distinto.
document.querySelectorAll('.filtro[data-rango]').forEach(btn => {
  btn.addEventListener('click', function() {
    const filtrosContainer = this.closest('.filtros');
    const idx = parseInt(filtrosContainer.dataset.idx);
    const rango = this.dataset.rango;
    const serie = SERIE_POR_I[idx];
    if (!serie || !charts[idx]) return;

    // Actualizar estado del botón
    filtrosContainer.querySelectorAll('.filtro').forEach(b => b.classList.remove('active'));
    this.classList.add('active');

    const customDiv = document.querySelector(`.rango-custom[data-idx='${idx}']`);
    if (rango === 'personalizado') {
      // Sólo despliega el selector de fechas; el filtrado real ocurre al tocar "Aplicar".
      if (customDiv) customDiv.style.display = 'flex';
      return;
    }
    if (customDiv) customDiv.style.display = 'none';

    aplicarFiltro(idx, serie, rango, filtrarDatos(serie, rango));
  });
});

// Selector de rezago (Punto 2.1 storytelling): swap de qué variante precalculada (0/3/6/12
// meses de desplazamiento) se muestra -- todo el cálculo ya vino hecho de Python, acá sólo
// se reemplazan labels/datasets del chart ya creado, mismo patrón liviano que aplicarFiltro.
document.querySelectorAll('.rezago-btn').forEach(btn => {
  btn.addEventListener('click', function() {
    const container = this.closest('.rezago-btns');
    const idx = parseInt(container.dataset.idx);
    const serie = SERIE_POR_I[idx];
    if (!serie || !charts[idx]) return;
    const variante = serie.variantes[this.dataset.rezago];
    if (!variante) return;
    container.querySelectorAll('.rezago-btn').forEach(b => b.classList.remove('active'));
    this.classList.add('active');
    // La variante elegida pasa a ser la "serie" que filtran los botones de fecha (mismos
    // campos x/izq/der/full_* que combo_2lineas), y se reaplica el rango de fecha activo
    // para que cambiar de rezago no resetee el período que el usuario estaba mirando.
    Object.assign(serie, variante);
    const rangoBtn = document.querySelector(`.filtros[data-idx='${idx}'] .filtro.active`);
    const rango = rangoBtn ? rangoBtn.dataset.rango : 'default';
    if (rango === 'personalizado') {
      const custom = document.querySelector(`.rango-custom[data-idx='${idx}']`);
      const desde = custom && custom.querySelector('.rango-desde').value;
      const hasta = custom && custom.querySelector('.rango-hasta').value;
      if (desde && hasta && desde <= hasta) {
        aplicarFiltro(idx, serie, 'personalizado', filtrarDatosPersonalizado(serie, desde, hasta));
        return;
      }
    }
    aplicarFiltro(idx, serie, rango === 'personalizado' ? 'default' : rango,
                  filtrarDatos(serie, rango === 'personalizado' ? 'default' : rango));
  });
});

// "Aplicar" del rango personalizado (Punto 6)
document.querySelectorAll('.rango-aplicar').forEach(btn => {
  btn.addEventListener('click', function() {
    const container = this.closest('.rango-custom');
    const idx = parseInt(container.dataset.idx);
    const serie = SERIE_POR_I[idx];
    if (!serie || !charts[idx]) return;
    const desde = container.querySelector('.rango-desde').value;
    const hasta = container.querySelector('.rango-hasta').value;
    if (!desde || !hasta || desde > hasta) return;
    aplicarFiltro(idx, serie, 'personalizado', filtrarDatosPersonalizado(serie, desde, hasta));
  });
});

// Ícono de pantalla completa (Punto 11): implementado UNA sola vez acá para las ~38
// tarjetas -- cada botón .fs-btn expande el .cell que lo contiene entero (no sólo el
// <canvas>) para que título/valor/filtros también se vean grandes. Usa la Fullscreen API
// nativa del navegador; si no existe (Safari iOS históricamente irregular), cae a un
// fallback con position:fixed (.fs-fallback en el CSS) controlado a mano.
function redimensionarChartDe(cell) {
  const canvas = cell.querySelector('canvas');
  if (!canvas) return;
  const idx = parseInt(canvas.id.replace('ch', ''));
  if (charts[idx]) charts[idx].resize();
}

const tieneFullscreenNativo = !!(document.documentElement.requestFullscreen);

document.querySelectorAll('.fs-btn').forEach(btn => {
  btn.addEventListener('click', function() {
    const cell = this.closest('.cell');
    if (!cell) return;
    if (tieneFullscreenNativo) {
      if (document.fullscreenElement === cell) {
        document.exitFullscreen();
      } else {
        cell.requestFullscreen().catch(() => {});
      }
    } else {
      // Fallback sin Fullscreen API: el mismo botón alterna la clase a mano.
      cell.classList.toggle('fs-fallback');
      redimensionarChartDe(cell);
    }
  });
});

if (tieneFullscreenNativo) {
  let cellFullscreenAnterior = null;
  document.addEventListener('fullscreenchange', () => {
    // Chart.js no redimensiona solo si el contenedor cambia de tamaño por la Fullscreen
    // API (no dispara resize del window) -- hay que llamarlo a mano, tanto al entrar como
    // al salir (document.fullscreenElement es null al salir, por eso se guarda la anterior).
    const actual = document.fullscreenElement;
    if (actual && actual.classList.contains('cell')) {
      redimensionarChartDe(actual);
      cellFullscreenAnterior = actual;
    } else if (cellFullscreenAnterior) {
      redimensionarChartDe(cellFullscreenAnterior);
      cellFullscreenAnterior = null;
    }
  });
}

// Barra de secciones: resalta la sección que se está leyendo.
const navLinks = [...document.querySelectorAll('nav.secciones a[href^="#"]')];
function marcarNav() {
  let activo = navLinks[0];
  navLinks.forEach(a => { const sec = document.querySelector(a.getAttribute('href')); if (sec && sec.getBoundingClientRect().top < 90) activo = a; });
  navLinks.forEach(a => a.classList.toggle('activo', a === activo));
}
window.addEventListener('scroll', marcarNav, { passive:true });
marcarNav();
</script>
</body></html>"""

    html = (plantilla.replace("__VARS__", css_vars).replace("__FUENTE__", fuente_css)
            .replace("__AHORA__", ahora).replace("__NAV__", nav)
            .replace("__FUENTES__", fuentes_pagina or FUENTES_HEADER_DEFAULT)
            .replace("__TITULO__", titulo_pagina)
            .replace("__SECCIONES__", secciones)
            .replace("__NOTAS__", notas_html)
            .replace("__TEMA__", json.dumps(tema_js, ensure_ascii=False))
            .replace("__ETIQUETAS__", json.dumps(etiquetas or {}, ensure_ascii=False))
            .replace("__DATA__", json.dumps(series_js, ensure_ascii=False)))
    OUT.mkdir(exist_ok=True)
    (OUT / archivo_salida).write_text(html, encoding="utf-8")

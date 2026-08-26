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

DESDE_GENERAL = "2024-01-01"
OUT = Path(__file__).resolve().parent / "docs"
MAX_PUNTOS_VIEJOS = 600  # tope de puntos para el tramo >2 años en series diarias largas
UMBRAL_DISCONTINUADA_DIAS = 90  # a partir de cuántos días sin datos se marca "sin datos nuevos desde..."

# Paleta institucional (Ministerio de Economía / argentina.gob.ar, sistema "Poncho"):
# tokens oficiales tomados de poncho.min.css (--arg-azul, --arg-enlace, --arg-rojo, etc.),
# elegidos para separarse bien entre sí incluso con daltonismo (protanopia/deuteranopia).
ACENTO = {"precios": "#C62828", "monetario_financiero": "#0767A7",
          "externo": "#EF6C00", "real": "#50B7B2", "social": "#6A1B99", "fiscal": "#8D2D04"}
AZUL_MARCA = "#232D4F"     # --arg-azul: navy institucional (header, footer, texto fuerte)
AZUL_ENLACE = "#0767A7"    # --arg-enlace: azul de interacción (links, botón activo)
TINTA = "#141414"; PAPEL = "#FFFFFF"; GRIS = "#555555"
ORDEN_BLOQUES = ["precios", "monetario_financiero", "externo", "real", "social", "fiscal"]
TITULO_BLOQUE = {"precios": "Precios", "monetario_financiero": "Monetario y financiero",
                 "real": "Actividad real", "externo": "Sector externo",
                 "social": "Social y empleo", "fiscal": "Fiscal"}
ORDEN_GRUPOS = ["Precios", "Dólar", "Brecha y TCR", "Riesgo país", "Reservas",
                "Agregados monetarios", "Tasas de interés", "Crédito",
                "Comercio exterior", "Exportaciones por rubro", "Importaciones por uso",
                "Actividad", "Social"]


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
    card = dict(i=idx, nombre=ind["nombre"], bloque=ind["bloque"], grupo=ind.get("grupo", "Otros"),
        color=ACENTO.get(ind["bloque"], AZUL_ENLACE), unidad=ind.get("unidad", ""),
        valor=_fmt_num(ult), pct=pct, marca_fecha=None,
        maxv=_fmt_num(g_linea["valor"].max()), minv=_fmt_num(g_linea["valor"].min()), nota_num=None,
        subtitulo=ind.get("subtitulo"),
        sube_es_bueno=ind.get("sube_es_bueno", False), neutral=ind.get("neutral", False))

    serie_js = dict(i=idx, color=ACENTO.get(ind["bloque"], AZUL_ENLACE), unidad=ind.get("unidad", ""), kind="combo",
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


COLORES_OVERLAY = ["#0767A7", "#C62828", "#2E7D33", "#8D2D04", "#6A1B99", "#EF6C00"]


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
        datasets.append(dict(label=nombre_serie, color=COLORES_OVERLAY[i % len(COLORES_OVERLAY)],
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


COLORES_INCIDENCIA = ["#C62828", "#0767A7", "#EF6C00", "#50B7B2", "#6A1B99", "#8D2D04",
                       "#2E7D33", "#EC407A", "#F79D00", "#3A3796", "#C2185B", "#6EA015"]


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
        datasets.append(dict(label=etiqueta, color=COLORES_INCIDENCIA[i % len(COLORES_INCIDENCIA)],
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
        datasets.append(dict(label=f"Resto ({len(resto)} divisiones)", color="#9E9E9E",
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


COLORES_BURBUJAS = COLORES_INCIDENCIA + ["#3B8681", "#9284BE", "#F48EAB"]


def _serie_bubble(idx, ind, historico):
    """
    Gráfico de burbujas: eje X = variación % interanual de empleo registrado
    (SIPA), eje Y = variación % interanual de actividad (EMAE por sector),
    tamaño = % del empleo total. El EMAE (mensual) se remuestrea a trimestres
    calendario (misma definición que usa la fuente de empleo, nativamente
    trimestral: ene-mar/abr-jun/jul-sep/oct-dic) antes de comparar, para que
    ambos ejes representen el mismo período exacto.
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
        var_empleo = (emp_q[fecha_comun] / emp_q[fecha_prev] - 1) * 100
        puntos.append(dict(nombre=nombre_sector, x=var_empleo, y=var_actividad, empleo=float(emp_q[fecha_comun])))
    if not puntos:
        return None

    total_empleo = sum(p["empleo"] for p in puntos)
    for i, p in enumerate(puntos):
        p["r"] = round(p["empleo"] / total_empleo * 100, 2)
        p["color"] = COLORES_BURBUJAS[i % len(COLORES_BURBUJAS)]
        p["x"] = round(p["x"], 2)
        p["y"] = round(p["y"], 2)

    trimestre = f"T{(fecha_comun.month - 1) // 3 + 1} {fecha_comun.year}"
    card = dict(i=idx, nombre=ind["nombre"], bloque=ind["bloque"], grupo=ind.get("grupo", "Otros"),
        color=ACENTO.get(ind["bloque"], AZUL_ENLACE), unidad="",
        valor=trimestre, pct=None, marca_fecha=None, maxv="s/d", minv="s/d", nota_num=None,
        sin_filtros=True, subtitulo=ind.get("subtitulo"), toggle_burbuja=True)

    # Cuadrante centrado en cero: límites simétricos (± el mayor valor absoluto de cada eje,
    # con margen) en vez de dejar que Chart.js autoescale cada eje por separado -- así el cero
    # queda en el centro del gráfico (un cuadrante de verdad: actividad/empleo que caen quedan
    # visualmente abajo/izquierda del cruce de ejes) en vez de pegado a un borde. Data-driven,
    # no un rango fijo: se recalcula solo según los sectores de cada corrida.
    #
    # Ronda 4 punto 12: con pocos sectores (~15), 1-2 outliers reales (ej. Pesca, Agricultura
    # en trimestres con datos volátiles) alejados del resto estiraban el eje tanto que el
    # cluster central (la mayoría de los sectores) quedaba amontonado en una franja angosta
    # cerca del cero, ilegible. Se usa la cerca de Tukey (Q3 + 1,5×RIC sobre el valor absoluto,
    # método estadístico estándar para detectar outliers, no un umbral fijo) para calcular el
    # límite del eje sobre el cluster central en vez del máximo absoluto; los sectores que
    # superan la cerca quedan clavados cerca del borde del gráfico (posición_real preservada en
    # 'x_real'/'y_real' para el tooltip) con un borde punteado que los distingue visualmente.
    MARGEN_EJE_BURBUJAS = 1.15

    def _limite_robusto(eje):
        valores_abs = sorted(abs(p[eje]) for p in puntos)
        n = len(valores_abs)
        if n < 4:
            return round(max(valores_abs) * MARGEN_EJE_BURBUJAS, 2)

        def _percentil(q):
            pos = q * (n - 1)
            lo, hi = int(pos), min(int(pos) + 1, n - 1)
            return valores_abs[lo] + (valores_abs[hi] - valores_abs[lo]) * (pos - lo)

        ric = _percentil(0.75) - _percentil(0.25)
        cerca = _percentil(0.75) + 1.5 * ric
        centrales = [v for v in valores_abs if v <= cerca]
        limite = round((max(centrales) if centrales else max(valores_abs)) * MARGEN_EJE_BURBUJAS, 2)
        for p in puntos:
            if abs(p[eje]) > cerca:
                p[f"{eje}_real"] = p[eje]
                p[eje] = round(max(-limite * 0.94, min(limite * 0.94, p[eje])), 2)
        return limite

    lim_x = _limite_robusto("x")
    lim_y = _limite_robusto("y")

    # Ronda 5 punto 1: aun con la cerca de Tukey, el cluster central (la mayoría real del
    # empleo del país) queda amontonado en una franja chica cerca del cero -- es estructural
    # a los datos (la mayoría de los sectores varía poco de un año a otro), no se arregla con
    # más margen de eje. Se arma un segundo set "zoom al cluster" que EXCLUYE del todo a los
    # sectores marcados como outlier (no sólo los recorta como en la vista completa) y
    # recalcula el límite de cada eje sólo sobre los que quedan, mismo margen ×1.15. El
    # usuario togglea entre las dos vistas con un botón (mismo lenguaje visual que .filtro).
    puntos_zoom = [p for p in puntos if "x_real" not in p and "y_real" not in p]
    lim_x_zoom = round(max((abs(p["x"]) for p in puntos_zoom), default=1) * MARGEN_EJE_BURBUJAS, 2)
    lim_y_zoom = round(max((abs(p["y"]) for p in puntos_zoom), default=1) * MARGEN_EJE_BURBUJAS, 2)

    serie_js = dict(i=idx, kind="bubble", fecha=fecha_comun.strftime("%m/%Y"), puntos=puntos,
        lim_x=round(lim_x, 2), lim_y=round(lim_y, 2),
        puntos_zoom=puntos_zoom, lim_x_zoom=lim_x_zoom, lim_y_zoom=lim_y_zoom)
    return card, serie_js


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


def generar(historico, config_indicadores):
    OUT.mkdir(parents=True, exist_ok=True)
    charts, series_js, semaforo, fecha_sem = [], [], [], ""
    tablas = defaultdict(list)
    notas_dict = {}  # {numero_nota: {"texto": ..., "indicadores": [...]}}
    indicadores_por_nombre = {i["nombre"]: i for i in config_indicadores}
    idx = 0
    for ind in config_indicadores:
        nombre = ind["nombre"]; bloque = ind["bloque"]; grupo = ind.get("grupo", "Otros")
        unidad = ind.get("unidad", ""); color = ACENTO.get(bloque, AZUL_ENLACE)
        nota = ind.get("nota")
        if ind.get("solo_componente"):
            continue  # sólo alimenta un 'vista' compuesta; no tiene tarjeta propia
        if ind.get("vista") in ("overlay", "incidencia_stack", "burbujas", "balance_cambiario", "comercio_espejo"):
            if ind["vista"] == "overlay":
                entrada = _serie_overlay(idx, ind, historico)
            elif ind["vista"] == "incidencia_stack":
                entrada = _serie_incidencia(idx, ind, historico, indicadores_por_nombre)
            elif ind["vista"] == "balance_cambiario":
                entrada = _serie_balance_cambiario(idx, ind, historico)
            elif ind["vista"] == "comercio_espejo":
                entrada = _serie_comercio_espejo(idx, ind, historico)
            else:
                entrada = _serie_bubble(idx, ind, historico)
            if entrada is None:
                continue
            card, serie_js_compuesta = entrada
            card["nota_num"] = _registrar_nota(nota, nombre, notas_dict)
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
        # Marca de "datos hasta MM/AAAA" para series que pueden discontinuarse (ej. tasa
        # de política monetaria). Se calcula de la última fecha REAL de la serie en cada
        # corrida: si la fuente retoma la publicación, la marca se actualiza o desaparece
        # sola (no queda un texto fijo desactualizado).
        marca_fecha = None
        if ind.get("marca_fecha"):
            dias_atraso = (pd.Timestamp.today().normalize() - serie["fecha"].max()).days
            if dias_atraso > UMBRAL_DISCONTINUADA_DIAS:
                marca_fecha = f"Sin datos nuevos desde {serie['fecha'].max().strftime('%m/%Y')}"
        charts.append(dict(i=idx, nombre=nombre, bloque=bloque, grupo=grupo, color=color,
            unidad=unidad, valor=_fmt_num(ult), pct=pct, marca_fecha=marca_fecha,
            maxv=_fmt_num(s["valor"].max()), minv=_fmt_num(s["valor"].min()), nota_num=nota_num,
            sube_es_bueno=ind.get("sube_es_bueno", False), neutral=ind.get("neutral", False),
            subtitulo=ind.get("subtitulo")))
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
            full_x = [d.strftime("%d/%m/%y") for d in full["fecha"]]
            full_y = [round(float(v), 2) for v in full["valor"]]
            full_dates = [d.isoformat() for d in full["fecha"]]  # ISO para comparación
            # Datos filtrados (para vista por defecto)
            s_x = [d.strftime("%d/%m/%y") for d in s["fecha"]]
            s_y = [round(float(v), 2) for v in s["valor"]]
            series_js.append(dict(i=idx, color=color, unidad=unidad,
                kind="bar" if ind.get("barras") else "line",
                x=s_x, y=s_y,  # Datos filtrados (default)
                full_x=full_x, full_y=full_y, full_dates=full_dates,  # Todos los datos
                min_date=serie["fecha"].min().isoformat(), max_date=serie["fecha"].max().isoformat()))
        idx += 1
    _escribir_html(charts, series_js, semaforo, fecha_sem, tablas, notas_dict)


def _color_semaforo(v):
    if v is None or pd.isna(v):
        return "#F0F0F0", TINTA
    if v > 1:  return "#DCEEDD", "#1E5C2E"
    if v < -1: return "#F6DCD8", "#8A2A1C"
    return "#FBF0D5", "#7A5A10"


def _tabla_semaforo(semaforo, fecha_sem):
    if not semaforo:
        return ""
    orden = sorted(semaforo, key=lambda x: (x["ia"] is None, -(x["ia"] or -999)))
    def celda(v):
        bg, fg = _color_semaforo(v)
        return f'<td style="background:{bg};color:{fg}">{(f"{v:+.1f}%" if v is not None else "s/d")}</td>'
    filas = "".join(f'<tr><td class="sec">{s["nombre"]}</td>{celda(s["ia"])}{celda(s["men"])}{celda(s["acum"])}</tr>' for s in orden)
    return (f'<h3 class="sub">EMAE por sector <span class="ref">({fecha_sem})</span></h3>'
            '<p class="nota">Interanual · mensual (serie original, con estacionalidad) · acumulado del año. '
            'Verde: +1% o más · Amarillo: entre -1% y +1% · Rojo: -1% o menos.</p>'
            '<table class="tabla"><thead><tr><th>Sector</th><th>Interanual</th><th>Mensual</th><th>Acum. año</th></tr></thead>'
            f'<tbody>{filas}</tbody></table>')


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


def _card_cell(c):
    if c["pct"] is None or abs(c["pct"]) <= 0.05:
        fl, cls = "•", "flat"
    else:
        sube = c["pct"] > 0.05
        fl = "▲" if sube else "▼"
        if c.get("neutral"):
            # El indicador declara 'neutral': subir no es ni buena ni mala noticia por sí
            # solo (ej. agregados monetarios, préstamos): se muestra la flecha sin pintarla.
            cls = "flat"
        else:
            # Genérico: subir = malo (rojo) salvo que el indicador declare 'sube_es_bueno'
            # (ej. EMAE: que la actividad suba es una buena noticia, no una mala).
            bueno = sube if c.get("sube_es_bueno") else not sube
            cls = "bueno" if bueno else "malo"
    chg = f'{fl} {abs(c["pct"]):.1f}%' if c["pct"] is not None else "—"
    # Asterisco numerado y clickeable: salta a su nota en el pie de página.
    nota_mark = ""
    if c.get("nota_num"):
        nota_mark = f'<div class="nota-ref"><a href="#nota-{c["nota_num"]}">*{c["nota_num"]}</a></div>'
    # Marca "sin datos nuevos desde MM/AAAA" (dinámica, ver generar())
    marca_html = f'<div class="marca-fecha">{c["marca_fecha"]}</div>' if c.get("marca_fecha") else ""
    # Botones de filtro (no aplican a gráficos de un solo período, ej. burbujas). "Personalizado"
    # despliega un selector de fechas (desde/hasta) en vez de filtrar al tocarlo directamente.
    # Rediseño de tarjetas: 4 botones visibles (Default/1A/5A/Todo, "Desde 2008" se saca por ser
    # el más redundante: "Todo" ya cubre el histórico completo y "5A" el mediano plazo) + un
    # ícono de calendario para el rango personalizado, en vez de 6 botones siempre visibles.
    # Mismos atributos (class="filtro" data-rango="...") que antes: el JS de filtrado
    # (calcFechaCorte/filtrarDatos/aplicarFiltro y el listener de .filtro[data-rango]) no cambia,
    # sólo el HTML/CSS que arma la fila de filtros.
    filtros = ""
    if not c.get("sin_filtros"):
        filtros = (
            f'<div class="filtros" data-idx="{c["i"]}">'
            '<div class="filtros-seg"><button class="filtro active" data-rango="default">Default</button>'
            '<button class="filtro" data-rango="1a">1A</button><button class="filtro" data-rango="5a">5A</button>'
            '<button class="filtro" data-rango="todo">Todo</button></div>'
            '<button class="filtro filtro-cal" data-rango="personalizado" title="Rango personalizado" aria-label="Rango personalizado">📅</button></div>'
            f'<div class="rango-custom" data-idx="{c["i"]}"><input type="date" class="rango-desde">'
            '<span>a</span><input type="date" class="rango-hasta"><button class="rango-aplicar">Aplicar</button></div>'
        )
    # Toggle "Vista completa" / "Zoom al cluster" (Ronda 5 punto 1, sólo burbujas): mismo
    # lenguaje visual que .filtro pero con data-vista en vez de data-rango, para no chocar
    # con el listener de los botones de rango de fecha (que no aplican acá, ver sin_filtros).
    toggle_burbuja = ""
    if c.get("toggle_burbuja"):
        toggle_burbuja = (
            f'<div class="filtros" data-idx="{c["i"]}"><button class="filtro active" data-vista="completa">Vista completa</button>'
            '<button class="filtro" data-vista="zoom">Zoom al cluster</button></div>'
        )
    grande = c.get("sin_filtros") or c.get("grande")
    cell_cls = "cell cell-ancha" if grande else "cell"
    cbox_cls = "cbox cbox-grande" if grande else "cbox"
    # Aclaración corta debajo del título (ej. grupo "Reservas", donde varios gráficos parecidos
    # se confundían entre sí leyendo sólo el nombre): visible sin tener que abrir la nota al pie.
    subtitulo_html = f'<div class="csub">{c["subtitulo"]}</div>' if c.get("subtitulo") else ""
    return (f'<div class="{cell_cls}"><div class="card" style="--acc:{c["color"]}">'
            f'<div class="cn">{c["nombre"]}</div>{subtitulo_html}<div class="cv">{c["valor"]}</div>'
            f'<div class="cm"><span class="chg {cls}">{chg}</span><span class="uni">{c["unidad"]}</span></div>'
            f'<div class="mm">máx {c["maxv"]} · mín {c["minv"]}</div>{marca_html}</div>'
            f'<div class="{cbox_cls}"><canvas id="ch{c["i"]}"></canvas></div>{filtros}{toggle_burbuja}{nota_mark}</div>')


def _escribir_html(charts, series_js, semaforo, fecha_sem, tablas, notas_dict):
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
        if not cb and not grupos_tabla and not tiene_sem:
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
                    cuerpo += f'<h3 class="sub">{g}</h3>'
                celdas = "".join(_card_cell(c) for c in cb if c["grupo"] == g)
                cuerpo += f'<div class="grid">{celdas}</div>'
        if tiene_sem:
            cuerpo += _tabla_semaforo(semaforo, fecha_sem)
        secciones += (f'<section class="bloque" id="{bloque}"><h2>'
                      f'<span class="dot" style="background:{ACENTO.get(bloque,AZUL_ENLACE)}"></span>'
                      f'{TITULO_BLOQUE.get(bloque, bloque)}</h2>{cuerpo}</section>')

    plantilla = """<!doctype html><html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monitor de coyuntura · Argentina</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Encode+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  /* Paleta institucional (argentina.gob.ar / Ministerio de Economía, sistema "Poncho") */
  :root {
    --papel:#FFFFFF; --fondo:#F4F6F8; --tinta:#141414; --gris:#555555; --gris-claro:#838383;
    --borde:#DEE2E6; --hover:#F0F0F0; --azul-marca:#232D4F; --azul-enlace:#0767A7; --azul-claro:#68C3EF;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--fondo); color:var(--tinta); font-family:"Encode Sans",system-ui,-apple-system,"Segoe UI",sans-serif; line-height:1.45; }
  .wrap { max-width:1180px; margin:0 auto; padding:0 22px 80px; }
  header.masthead { background:var(--azul-marca); color:#fff; margin-bottom:22px; }
  .masthead-inner { max-width:1180px; margin:0 auto; padding:26px 22px; }
  header h1 { font-size:26px; margin:0; font-weight:700; letter-spacing:-.01em; }
  header .sub { color:#C8D0DA; font-size:13px; margin-top:6px; }
  nav { display:flex; flex-wrap:wrap; gap:18px; margin:0 0 28px; padding-bottom:14px; border-bottom:1px solid var(--borde); font-size:13px; }
  nav a { color:var(--azul-enlace); text-decoration:none; font-weight:600; } nav a:hover { text-decoration:underline; }
  .bloque { margin:40px 0; scroll-margin-top:16px; }
  .bloque h2 { font-size:18px; font-weight:700; display:flex; align-items:center; gap:9px; border-bottom:2px solid var(--azul-marca); padding-bottom:8px; color:var(--azul-marca); }
  .sub { font-size:14px; font-weight:600; margin:24px 0 12px; color:var(--azul-marca); }
  .ref { color:var(--gris); font-weight:400; font-size:13px; }
  .nota { color:var(--gris); font-size:12px; margin:6px 0 14px; }
  .nota-ref { font-size:10px; margin-top:4px; text-align:center; }
  .nota-ref a { color:var(--azul-enlace); font-weight:600; text-decoration:none; }
  .nota-ref a:hover { text-decoration:underline; }
  .notas-list { margin:10px 0 14px 20px; font-size:12px; color:var(--gris); }
  .notas-list li { margin:6px 0; scroll-margin-top:16px; }
  .notas-list strong { color:var(--tinta); }
  .dot { width:11px; height:11px; border-radius:2px; display:inline-block; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,460px)); justify-content:start; gap:18px; margin-bottom:8px; }
  .cell { border:1px solid var(--borde); border-radius:10px; overflow:hidden; background:var(--papel); box-shadow:0 1px 2px rgba(20,20,20,.04); }
  .card { border-left:4px solid var(--acc); padding:12px 14px 8px; }
  .cn { font-size:11px; text-transform:uppercase; letter-spacing:.03em; color:var(--gris); min-height:28px; }
  .csub { font-size:11px; color:var(--tinta); opacity:0.75; margin-top:-4px; margin-bottom:4px; line-height:1.3; }
  .cv { font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:24px; font-weight:600; margin:2px 0; }
  .cm { display:flex; justify-content:space-between; align-items:baseline; font-size:11px; }
  .chg { font-family:ui-monospace,monospace; font-weight:600; }
  .chg.malo { color:#C62828; } .chg.bueno { color:#2E7D33; } .chg.flat { color:var(--gris); }
  .uni { color:var(--gris); }
  .mm { color:var(--gris); font-size:11px; margin-top:4px; font-family:ui-monospace,monospace; }
  .marca-fecha { color:#8D2D04; background:#F3DDB0; font-size:10px; font-weight:600; padding:3px 7px; border-radius:4px; margin-top:6px; display:inline-block; }
  .cbox { height:260px; padding:8px 10px 12px; }
  .cbox-grande { height:400px; }
  .cell-ancha { grid-column: span 2; }
  .tabla { width:100%; border-collapse:separate; border-spacing:3px; font-size:13px; margin-bottom:8px; }
  .tabla th { text-align:right; color:var(--gris); font-weight:600; font-size:11px; text-transform:uppercase; padding:4px 10px; }
  .tabla th:first-child { text-align:left; }
  .tabla td { padding:8px 10px; text-align:right; border-radius:5px; font-family:ui-monospace,monospace; font-weight:600; }
  .tabla td.sec { text-align:left; background:var(--papel); font-family:"Encode Sans",system-ui,sans-serif; font-weight:400; border:1px solid var(--borde); }
  .tabla td.num { background:var(--papel); color:#333; border:1px solid var(--borde); }
  .filtros { display:flex; align-items:center; gap:6px; flex-wrap:wrap; padding:8px 10px 0; font-size:11px; }
  .filtro { background:var(--fondo); border:1px solid var(--borde); color:var(--tinta); padding:4px 10px; border-radius:4px; cursor:pointer; font-size:11px; transition:all 0.15s; }
  .filtro:hover { background:var(--hover); border-color:var(--gris-claro); }
  .filtro.active { background:var(--azul-enlace); color:#fff; border-color:var(--azul-enlace); }
  /* Rediseño de tarjetas: segmented control para los 4 botones de rango + ícono de calendario
     aparte para "Personalizado" -- mismos elementos .filtro/data-rango de siempre, sólo cambia
     el envoltorio visual. */
  .filtros-seg { display:flex; background:var(--fondo); border:1px solid var(--borde); border-radius:6px; padding:2px; }
  .filtros-seg .filtro { border:none; background:transparent; }
  .filtros-seg .filtro.active { background:var(--azul-enlace); color:#fff; }
  .filtro-cal { width:26px; height:26px; padding:0; display:flex; align-items:center; justify-content:center; font-size:13px; line-height:1; }
  .rango-custom { display:none; align-items:center; gap:6px; padding:8px 10px 0; font-size:11px; color:var(--gris); }
  .rango-custom input[type=date] { font-size:11px; padding:3px 5px; border:1px solid var(--borde); border-radius:4px; background:var(--fondo); color:var(--tinta); font-family:inherit; }
  .rango-aplicar { background:var(--azul-enlace); color:#fff; border:none; padding:4px 10px; border-radius:4px; cursor:pointer; font-size:11px; }
  .rango-aplicar:hover { opacity:0.85; }
  footer { color:var(--gris); font-size:12px; border-top:1px solid var(--borde); padding-top:14px; margin-top:20px; }
</style></head>
<body>
<header class="masthead"><div class="masthead-inner">
  <h1>Monitor de coyuntura · Argentina</h1>
  <div class="sub">Actualizado __AHORA__ · fuentes: apis.datos.gob.ar · ArgentinaDatos · BCRA</div>
</div></header>
<div class="wrap">
  <nav>__NAV__</nav>
  __SECCIONES__
  __NOTAS__
  <footer>Pasá el cursor sobre cualquier gráfico para ver el valor. Editá indicadores en indicadores.yaml.</footer>
</div>
<script>
const SERIES = __DATA__;
const charts = {};
const baseOpts = (unidad) => ({
  responsive:true, maintainAspectRatio:false, animation:false,
  interaction:{ mode:'index', intersect:false },
  plugins:{ legend:{display:false}, tooltip:{
    callbacks:{ label:(c)=> c.parsed.y.toLocaleString('es-AR') + (unidad? ' '+unidad:'') } } },
  scales:{ x:{ ticks:{ maxTicksLimit:6, autoSkip:true, maxRotation:0, color:'#838383', font:{size:10} }, grid:{display:false} },
           y:{ ticks:{ color:'#838383', font:{size:10} }, grid:{color:'#EFEFEF'} } },
  elements:{ point:{radius:0, hitRadius:8}, line:{borderWidth:1.9, tension:0.12} }
});

function calcFechaCorte(rango) {
  const hoy = new Date();
  const hace1a = new Date(hoy.getFullYear()-1, hoy.getMonth(), hoy.getDate());
  const hace5a = new Date(hoy.getFullYear()-5, hoy.getMonth(), hoy.getDate());
  const desde2008 = new Date(2008, 0, 1);
  
  switch(rango) {
    case '1a': return hace1a.toISOString().split('T')[0];
    case '5a': return hace5a.toISOString().split('T')[0];
    case '2008': return '2008-01-01';
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
  return {
    x: indices.map(i => s.full_x[i]),
    y: indices.map(i => s.full_y[i]),
    flujo: s.full_flujo ? indices.map(i => s.full_flujo[i]) : undefined
  };
}

const espejoOpts = (unidad) => ({
  responsive:true, maintainAspectRatio:false, animation:false,
  interaction:{ mode:'index', intersect:false },
  plugins:{ legend:{display:true, position:'top', labels:{boxWidth:11, font:{size:10}, color:'#555555'}},
    tooltip:{ callbacks:{ label:(c)=> {
        const v = c.dataset.type === 'line' ? c.parsed.y : Math.abs(c.parsed.y);
        return `${c.dataset.label}: ${v == null ? 's/d' : v.toLocaleString('es-AR')} ${unidad}`;
      } } } },
  scales:{ x:{ stacked:true, ticks:{ maxTicksLimit:6, autoSkip:true, maxRotation:0, color:'#838383', font:{size:10} }, grid:{display:false} },
           y:{ stacked:true, ticks:{ color:'#838383', font:{size:10}, callback:(v)=> Math.abs(v).toLocaleString('es-AR') },
               grid:{color:(c)=> c.tick.value===0 ? '#B5B5B5' : '#EFEFEF'} } },
});

const overlayOpts = (unidad, radioPunto, cruce, escalaLog) => ({
  responsive:true, maintainAspectRatio:false, animation:false,
  interaction:{ mode:'index', intersect:false },
  plugins:{ legend:{display:true, position:'top', labels:{boxWidth:11, font:{size:10}, color:'#555555'}},
    tooltip:{ callbacks:{
      label:(c)=> `${c.dataset.label}: ${c.parsed.y == null ? 's/d' : c.parsed.y.toLocaleString('es-AR')} ${unidad}`,
      afterBody:(items)=> (cruce && items.length && items[0].label === cruce.fecha) ? [`◆ ${cruce.texto}`] : []
    } } },
  scales:{ x:{ ticks:{ maxTicksLimit:6, autoSkip:true, maxRotation:0, color:'#838383', font:{size:10} }, grid:{display:false} },
           y:{ type: escalaLog ? 'logarithmic' : 'linear',
               ticks:{ color:'#838383', font:{size:10}, callback:(v)=> v.toLocaleString('es-AR') }, grid:{color:'#EFEFEF'} } },
  elements:{ point:{radius: radioPunto || 0, hitRadius:8}, line:{borderWidth:1.9, tension:0.12} }
});

// Marca vertical de "cambio de liderazgo" en un overlay (ver 'cruce' en _serie_overlay,
// dashboard.py): útil cuando dos líneas se cruzan en un ángulo demasiado cerrado para notarlo
// a simple vista, pero el momento del cruce es el dato más importante del gráfico.
function cruceOverlayPlugin(cruce) {
  return {
    id: 'cruceOverlay',
    afterDatasetsDraw(chart) {
      if (!cruce) return;
      const i = chart.data.labels.indexOf(cruce.fecha);
      if (i === -1) return;
      const { ctx, chartArea, scales } = chart;
      const x = scales.x.getPixelForValue(i);
      ctx.save();
      ctx.strokeStyle = '#8D2D04';
      ctx.setLineDash([4, 3]);
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(x, chartArea.top);
      ctx.lineTo(x, chartArea.bottom);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#8D2D04';
      ctx.font = 'bold 11px "Encode Sans", system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('◆', x, chartArea.top - 2);
      ctx.restore();
    }
  };
}

const comboOpts = (unidad) => ({
  responsive:true, maintainAspectRatio:false, animation:false,
  interaction:{ mode:'index', intersect:false },
  plugins:{ legend:{display:true, position:'top', labels:{boxWidth:11, font:{size:10}, color:'#555555'}},
    tooltip:{ callbacks:{ label:(c)=> `${c.dataset.label}: ${c.parsed.y == null ? 's/d' : c.parsed.y.toLocaleString('es-AR')} ${c.dataset.yAxisID==='y1' ? unidad : ''}` } } },
  scales:{ x:{ ticks:{ maxTicksLimit:6, autoSkip:true, maxRotation:0, color:'#838383', font:{size:10} }, grid:{display:false} },
           y:{ position:'left', ticks:{ color:'#838383', font:{size:9} }, grid:{color:'#EFEFEF'}, title:{display:true, text:'Var. mensual', font:{size:9}, color:'#838383'} },
           y1:{ position:'right', ticks:{ color:'#838383', font:{size:9} }, grid:{display:false}, title:{display:true, text:'Stock', font:{size:9}, color:'#838383'} } },
  elements:{ point:{radius:0, hitRadius:8}, line:{borderWidth:1.9, tension:0.12} }
});

const incidenciaOpts = (unidad, yMax, yMin) => ({
  responsive:true, maintainAspectRatio:false, animation:false,
  interaction:{ mode:'index', intersect:false },
  layout:{ padding:{ top:18, bottom:8 } },
  plugins:{ legend:{display:true, position:'top', labels:{boxWidth:11, font:{size:9}, color:'#555555'}},
    tooltip:{ callbacks:{
      label:(c)=> `${c.dataset.label}: ${c.parsed.y == null ? 's/d' : c.parsed.y.toLocaleString('es-AR')} ${unidad}`,
      afterBody:(items)=> {
        if (!items.length) return [];
        const lineas = [];
        const atipicos = items[0].chart.$atipicos;
        const total = atipicos ? atipicos[items[0].label] : undefined;
        if (total !== undefined) {
          lineas.push(`⚠ Valor atípico, fuera de escala del gráfico — total real: ${total > 0 ? '+' : ''}${total.toLocaleString('es-AR')} ${unidad}`);
        }
        // Detalle de "Resto" (Punto 11): qué divisiones lo componen y cuánto aportó cada una
        // ESE mes -- no una lista fija, se recalcula con el dato real de cada período.
        const restoDetalle = items[0].chart.$restoDetalle;
        const detalle = restoDetalle ? restoDetalle[items[0].label] : null;
        if (detalle && detalle.length) {
          lineas.push('Detalle de "Resto":');
          detalle.forEach(d => lineas.push(`  ${d.nombre}: ${d.valor > 0 ? '+' : ''}${d.valor.toLocaleString('es-AR')} ${unidad}`));
        }
        return lineas;
      } } } },
  scales:{ x:{ stacked:true, ticks:{ maxTicksLimit:6, autoSkip:true, maxRotation:0, color:'#838383', font:{size:10} }, grid:{display:false} },
           y:{ stacked:true, max:yMax ?? undefined, min:yMin ?? undefined, ticks:{ color:'#838383', font:{size:10} }, grid:{color:'#EFEFEF'} } },
});

// Marca los meses "atípicos" (fuera del rango normal del eje, ver y_max/y_min en Python) con
// un ⚠ arriba o abajo de la barra recortada, para no perder el dato aunque el eje ya no se
// estire para incluirlo. Lee 'chart.$atipicos' (asignado al crear el chart y reasignado en cada
// click de filtro, ver 'ejes' en Python y el handler de .filtro) en vez de un valor cerrado sobre
// la función, porque el diccionario fecha->valor cambia según la ventana de filtro activa.
const atipicosIncidenciaPlugin = {
  id: 'atipicosIncidencia',
  afterDatasetsDraw(chart) {
    const atipicos = chart.$atipicos;
    if (!atipicos || !Object.keys(atipicos).length) return;
    const { ctx, chartArea, scales } = chart;
    ctx.save();
    ctx.font = 'bold 12px "Encode Sans", system-ui, sans-serif';
    ctx.textAlign = 'center';
    chart.data.labels.forEach((label, i) => {
      if (atipicos[label] === undefined) return;
      const x = scales.x.getPixelForValue(i);
      const arriba = atipicos[label] >= 0;
      ctx.fillText('⚠', x, arriba ? chartArea.top - 2 : chartArea.bottom + 16);
    });
    ctx.restore();
  }
};

// Plugin liviano (sin librería externa) para poner el nombre corto del sector
// al lado de cada burbuja — con 15 puntos y sin serie temporal, una leyenda
// tradicional no alcanza para identificarlos; mejor una etiqueta directa.
const etiquetasBurbujaPlugin = {
  // Anti-colisión simple (sin librería externa): ordena las burbujas de mayor a
  // menor radio (más prominente visualmente = más prioridad) y sólo dibuja la
  // etiqueta si su caja de texto no se superpone con una ya colocada. Los
  // sectores que quedan sin etiqueta fija (el cluster apretado del centro)
  // siguen identificables con el tooltip al pasar el mouse.
  id: 'etiquetasBurbuja',
  afterDatasetsDraw(chart) {
    if (chart.config.type !== 'bubble') return;
    const { ctx } = chart;
    ctx.save();
    ctx.font = '11px "Encode Sans", system-ui, sans-serif';
    ctx.fillStyle = '#333333';
    ctx.textBaseline = 'middle';

    const items = chart.data.datasets.map((ds, i) => {
      const meta = chart.getDatasetMeta(i);
      const punto = meta.data[0];
      return punto ? { ds, punto } : null;
    }).filter(Boolean).sort((a, b) => b.punto.options.radius - a.punto.options.radius);

    const ocupadas = [];
    items.forEach(({ ds, punto }) => {
      const corto = ds.label.length > 16 ? ds.label.slice(0, 15) + '…' : ds.label;
      const x = punto.x + punto.options.radius + 5;
      const y = punto.y;
      const caja = { x, y: y - 7, w: ctx.measureText(corto).width + 3, h: 14 };
      const choca = ocupadas.some(o =>
        caja.x < o.x + o.w && caja.x + caja.w > o.x && caja.y < o.y + o.h && caja.y + caja.h > o.y);
      if (choca) return;
      ctx.fillText(corto, x, y);
      ocupadas.push(caja);
    });
    ctx.restore();
  }
};

// Construye los datasets de burbujas a partir de una lista de puntos (Ronda 5 punto 1:
// factorizado para que lo use tanto la creación inicial del chart como el toggle
// "Vista completa"/"Zoom al cluster", que reemplaza los datasets sin recrear el chart).
// Radio en px escalado desde el % de empleo (sin piso artificial: un sector con 0,1% del
// empleo se ve casi invisible a propósito, es la realidad del dato).
function construirDatasetsBurbuja(puntos) {
  return puntos.map(p => {
    const recortado = p.x_real !== undefined || p.y_real !== undefined;
    return { label:p.nombre,
      data:[{ x:p.x, y:p.y, r:p.r*1.6, r_pct:p.r, label:p.nombre, x_real:p.x_real, y_real:p.y_real }],
      backgroundColor:p.color+'B0', borderColor:p.color,
      borderWidth: recortado ? 2.5 : 1, borderDash: recortado ? [4, 3] : [] };
  });
}

const bubbleOpts = (limX, limY) => ({
  responsive:true, maintainAspectRatio:false, animation:false,
  layout:{ padding:{ right:95, top:14 } },
  plugins:{ legend:{display:false},
    tooltip:{ callbacks:{
      title:(items)=> items[0].raw.label,
      label:(c)=> {
        const x = c.raw.x_real ?? c.raw.x, y = c.raw.y_real ?? c.raw.y;
        const lineas = [`Empleo registrado (i.a.): ${x > 0 ? '+' : ''}${x.toFixed(1)}%`,
                        `Actividad (EMAE, i.a.): ${y > 0 ? '+' : ''}${y.toFixed(1)}%`,
                        `% del empleo total: ${c.raw.r_pct.toFixed(1)}%`];
        if (c.raw.x_real !== undefined || c.raw.y_real !== undefined) {
          lineas.push('⚠ Fuera de escala del gráfico, dibujado cerca del borde -- valores reales arriba');
        }
        return lineas;
      } } } },
  scales:{ x:{ min:-limX, max:limX, title:{display:true, text:'Variación % interanual de empleo', font:{size:10}, color:'#555555'},
               ticks:{ color:'#838383', font:{size:10} }, grid:{color:(c)=> c.tick.value===0 ? '#B5B5B5' : '#EFEFEF'} },
           y:{ min:-limY, max:limY, title:{display:true, text:'Variación % interanual de actividad', font:{size:10}, color:'#555555'},
               ticks:{ color:'#838383', font:{size:10} }, grid:{color:(c)=> c.tick.value===0 ? '#B5B5B5' : '#EFEFEF'} } },
});

SERIES.forEach(s => {
  const el = document.getElementById('ch'+s.i);
  if(!el) return;
  const ctx = el.getContext('2d');
  if (s.kind === 'combo') {
    const coloresBarras = s.flujo.map(v => (v||0) >= 0 ? '#2E7D33' : '#C62828');
    charts[s.i] = new Chart(ctx, { data:{ labels:s.x, datasets:[
        { type:'bar', label:'Variación mensual', data:s.flujo, backgroundColor:coloresBarras, yAxisID:'y' },
        { type:'line', label:'Stock', data:s.y, borderColor:s.color, backgroundColor:s.color+'14', yAxisID:'y1', fill:false }
      ]}, options: comboOpts(s.unidad) });
  } else if (s.kind === 'overlay') {
    charts[s.i] = new Chart(ctx, { type: s.barras ? 'bar' : 'line', data:{ labels:s.x, datasets: s.datasets.map(d => (
        s.barras
          ? { label:d.label, data:d.y, backgroundColor:d.color, borderRadius:2 }
          : { label:d.label, data:d.y, borderColor:d.color, backgroundColor:d.color+'10', fill:false }
      )) }, options: overlayOpts(s.unidad, s.radio_punto, s.cruce, s.escala_log),
      plugins: s.cruce ? [cruceOverlayPlugin(s.cruce)] : [] });
  } else if (s.kind === 'incidencia') {
    charts[s.i] = new Chart(ctx, { type:'bar', data:{ labels:s.x, datasets: s.datasets.map(d => (
        { label:d.label, data:d.y, backgroundColor:d.color, stack:'incidencia' }
      )) }, options: incidenciaOpts(s.unidad, s.y_max, s.y_min),
      plugins: [atipicosIncidenciaPlugin] });
    charts[s.i].$atipicos = s.atipicos;
    charts[s.i].$restoDetalle = s.resto_detalle;
  } else if (s.kind === 'espejo') {
    charts[s.i] = new Chart(ctx, { data:{ labels:s.x, datasets:[
        { type:'bar', label:'Exportaciones', data:s.expo, backgroundColor:'#0767A7', stack:'comercio' },
        { type:'bar', label:'Importaciones', data:s.impo, backgroundColor:'#EF6C00', stack:'comercio' },
        { type:'line', label:'Saldo comercial', data:s.saldo, borderColor:'#232D4F', backgroundColor:'#232D4F14', fill:false, tension:0.12, pointRadius:0, borderWidth:1.9 },
      ]}, options: espejoOpts(s.unidad) });
  } else if (s.kind === 'bar') {
    charts[s.i] = new Chart(ctx, { type:'bar',
      data:{ labels:s.x, datasets:[{ data:s.y, backgroundColor:s.color, borderRadius:2 }] },
      options: baseOpts(s.unidad) });
  } else if (s.kind === 'bubble') {
    charts[s.i] = new Chart(ctx, { type:'bubble', data:{ datasets: construirDatasetsBurbuja(s.puntos) },
      options: bubbleOpts(s.lim_x, s.lim_y), plugins:[etiquetasBurbujaPlugin] });
  } else {
    charts[s.i] = new Chart(ctx, { type:'line',
      data:{ labels:s.x, datasets:[{ data:s.y, borderColor:s.color, backgroundColor:s.color+'14', fill:true }] },
      options: baseOpts(s.unidad) });
  }
});

// Redibuja un chart ya creado con los datos ya filtrados (por un botón de rango fijo o por
// el rango "Personalizado"). Factorizado para que ambos caminos compartan la misma lógica.
function aplicarFiltro(idx, serie, rango, datFiltrados) {
  charts[idx].data.labels = datFiltrados.x;
  if (serie.kind === 'combo') {
    const coloresBarras = datFiltrados.flujo.map(v => (v||0) >= 0 ? '#2E7D33' : '#C62828');
    charts[idx].data.datasets[0].data = datFiltrados.flujo;
    charts[idx].data.datasets[0].backgroundColor = coloresBarras;
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
  } else {
    charts[idx].data.datasets[0].data = datFiltrados.y;
  }
  charts[idx].update('none');
}

// Event listeners para botones de filtro (rango de fecha). Selector acotado a
// '.filtro[data-rango]' (no todo '.filtro') para no chocar con el toggle de vista de
// burbujas de más abajo, que reusa la misma clase visual pero con data-vista.
document.querySelectorAll('.filtro[data-rango]').forEach(btn => {
  btn.addEventListener('click', function() {
    const filtrosContainer = this.closest('.filtros');
    const idx = parseInt(filtrosContainer.dataset.idx);
    const rango = this.dataset.rango;
    const serie = SERIES[idx];
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

// Toggle "Vista completa" / "Zoom al cluster" del gráfico de burbujas (Ronda 5 punto 1):
// reemplaza los datasets y los límites de eje sin recrear el chart, mismo patrón que
// aplicarFiltro (chart.data, chart.options.scales, chart.update('none')).
document.querySelectorAll('.filtro[data-vista]').forEach(btn => {
  btn.addEventListener('click', function() {
    const container = this.closest('.filtros');
    const idx = parseInt(container.dataset.idx);
    const vista = this.dataset.vista;
    const serie = SERIES[idx];
    const chart = charts[idx];
    if (!serie || !chart) return;

    container.querySelectorAll('.filtro').forEach(b => b.classList.remove('active'));
    this.classList.add('active');

    const puntos = vista === 'zoom' ? serie.puntos_zoom : serie.puntos;
    const limX = vista === 'zoom' ? serie.lim_x_zoom : serie.lim_x;
    const limY = vista === 'zoom' ? serie.lim_y_zoom : serie.lim_y;
    chart.data.datasets = construirDatasetsBurbuja(puntos);
    chart.options.scales.x.min = -limX; chart.options.scales.x.max = limX;
    chart.options.scales.y.min = -limY; chart.options.scales.y.max = limY;
    chart.update('none');
  });
});

// "Aplicar" del rango personalizado (Punto 6)
document.querySelectorAll('.rango-aplicar').forEach(btn => {
  btn.addEventListener('click', function() {
    const container = this.closest('.rango-custom');
    const idx = parseInt(container.dataset.idx);
    const serie = SERIES[idx];
    if (!serie || !charts[idx]) return;
    const desde = container.querySelector('.rango-desde').value;
    const hasta = container.querySelector('.rango-hasta').value;
    if (!desde || !hasta || desde > hasta) return;
    aplicarFiltro(idx, serie, 'personalizado', filtrarDatosPersonalizado(serie, desde, hasta));
  });
});
</script>
</body></html>"""

    html = (plantilla.replace("__AHORA__", ahora).replace("__NAV__", nav)
            .replace("__SECCIONES__", secciones)
            .replace("__NOTAS__", notas_html)
            .replace("__DATA__", json.dumps(series_js, ensure_ascii=False)))
    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(html, encoding="utf-8")

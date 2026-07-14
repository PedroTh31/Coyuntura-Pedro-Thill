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
from collections import defaultdict
import json
import pandas as pd

DESDE_GENERAL = "2024-01-01"
OUT = Path(__file__).resolve().parent / "docs"

ACENTO = {"precios": "#B4341F", "monetario_financiero": "#1D4E89",
          "real": "#256D5B", "externo": "#0E7C86", "social": "#B26B00", "fiscal": "#7A5195"}
TINTA = "#1A1A1A"; PAPEL = "#FBFAF7"; GRIS = "#9A968C"
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


def generar(historico, config_indicadores):
    OUT.mkdir(parents=True, exist_ok=True)
    charts, series_js, semaforo, fecha_sem = [], [], [], ""
    tablas = defaultdict(list)
    notas_dict = {}  # {numero_nota: {"texto": ..., "indicadores": [...]}}
    idx = 0
    for ind in config_indicadores:
        nombre = ind["nombre"]; bloque = ind["bloque"]; grupo = ind.get("grupo", "Otros")
        unidad = ind.get("unidad", ""); color = ACENTO.get(bloque, "#1D4E89")
        nota = ind.get("nota")
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
        # Registrar nota si existe
        nota_num = None
        if nota:
            nota_key = nota  # usar el texto de la nota como clave para deduplicar
            if nota_key not in notas_dict:
                nota_num = len(notas_dict) + 1
                notas_dict[nota_key] = {"numero": nota_num, "indicadores": [nombre]}
            else:
                nota_num = notas_dict[nota_key]["numero"]
                notas_dict[nota_key]["indicadores"].append(nombre)
        charts.append(dict(i=idx, nombre=nombre, bloque=bloque, grupo=grupo, color=color,
            unidad=unidad, valor=_fmt_num(ult), pct=pct,
            maxv=_fmt_num(s["valor"].max()), minv=_fmt_num(s["valor"].min()), nota_num=nota_num))
        series_js.append(dict(i=idx, color=color, unidad=unidad,
            x=[d.strftime("%d/%m/%y") for d in s["fecha"]],
            y=[round(float(v), 2) for v in s["valor"]]))
        idx += 1
    _escribir_html(charts, series_js, semaforo, fecha_sem, tablas, notas_dict)


def _color_semaforo(v):
    if v is None or pd.isna(v):
        return "#E7E3D8", TINTA
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
    if c["pct"] is None: fl, cls = "•", "flat"
    elif c["pct"] > 0.05: fl, cls = "▲", "up"
    elif c["pct"] < -0.05: fl, cls = "▼", "down"
    else: fl, cls = "•", "flat"
    chg = f'{fl} {abs(c["pct"]):.1f}%' if c["pct"] is not None else "—"
    # Renderizar asterisco si hay nota
    nota_mark = ""
    if c.get("nota_num"):
        nota_asterisco = "*" * c["nota_num"]
        nota_mark = f'<div class="nota-ref">{nota_asterisco}</div>'
    return (f'<div class="cell"><div class="card" style="--acc:{c["color"]}">'
            f'<div class="cn">{c["nombre"]}</div><div class="cv">{c["valor"]}</div>'
            f'<div class="cm"><span class="chg {cls}">{chg}</span><span class="uni">{c["unidad"]}</span></div>'
            f'<div class="mm">máx {c["maxv"]} · mín {c["minv"]}</div></div>'
            f'<div class="cbox"><canvas id="ch{c["i"]}"></canvas></div>{nota_mark}</div>')


def _escribir_html(charts, series_js, semaforo, fecha_sem, tablas, notas_dict):
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
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
            asterisco = "*" * num
            notas_items.append(f'<li><strong>{asterisco}</strong> {nota_texto}</li>')
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
                      f'<span class="dot" style="background:{ACENTO.get(bloque,"#1D4E89")}"></span>'
                      f'{TITULO_BLOQUE.get(bloque, bloque)}</h2>{cuerpo}</section>')

    plantilla = """<!doctype html><html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monitor de coyuntura · Argentina</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root { --papel:#FBFAF7; --tinta:#1A1A1A; --gris:#9A968C; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--papel); color:var(--tinta); font-family:system-ui,-apple-system,"Segoe UI",sans-serif; line-height:1.4; }
  .wrap { max-width:1180px; margin:0 auto; padding:32px 22px 80px; }
  header { border-bottom:2px solid var(--tinta); padding-bottom:14px; margin-bottom:18px; }
  header h1 { font-size:27px; margin:0; letter-spacing:-.02em; }
  header .sub { color:var(--gris); font-size:13px; margin-top:4px; }
  nav { display:flex; flex-wrap:wrap; gap:16px; margin-bottom:26px; font-size:13px; }
  nav a { color:#1D4E89; text-decoration:none; } nav a:hover { text-decoration:underline; }
  .bloque { margin:40px 0; scroll-margin-top:16px; }
  .bloque h2 { font-size:18px; display:flex; align-items:center; gap:9px; border-bottom:1px solid #E4E0D4; padding-bottom:8px; }
  .sub { font-size:14px; margin:24px 0 12px; color:#444; }
  .ref { color:var(--gris); font-weight:400; font-size:13px; }
  .nota { color:var(--gris); font-size:12px; margin:6px 0 14px; }
  .nota-ref { font-size:10px; color:#B4341F; font-weight:600; margin-top:4px; text-align:center; }
  .notas-list { margin:10px 0 14px 20px; font-size:12px; color:var(--gris); }
  .notas-list li { margin:6px 0; }
  .notas-list strong { color:#1A1A1A; }
  .dot { width:11px; height:11px; border-radius:2px; display:inline-block; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,460px)); justify-content:start; gap:18px; margin-bottom:8px; }
  .cell { border:1px solid #ECE8DC; border-radius:10px; overflow:hidden; background:#fff; }
  .card { border-left:3px solid var(--acc); padding:12px 14px 8px; }
  .cn { font-size:11px; text-transform:uppercase; letter-spacing:.03em; color:var(--gris); min-height:28px; }
  .cv { font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:24px; font-weight:600; margin:2px 0; }
  .cm { display:flex; justify-content:space-between; align-items:baseline; font-size:11px; }
  .chg { font-family:ui-monospace,monospace; font-weight:600; }
  .chg.up { color:#B4341F; } .chg.down { color:#256D5B; } .chg.flat { color:var(--gris); }
  .uni { color:var(--gris); }
  .mm { color:var(--gris); font-size:11px; margin-top:4px; font-family:ui-monospace,monospace; }
  .cbox { height:200px; padding:8px 10px 12px; }
  .tabla { width:100%; border-collapse:separate; border-spacing:3px; font-size:13px; margin-bottom:8px; }
  .tabla th { text-align:right; color:var(--gris); font-weight:600; font-size:11px; text-transform:uppercase; padding:4px 10px; }
  .tabla th:first-child { text-align:left; }
  .tabla td { padding:8px 10px; text-align:right; border-radius:5px; font-family:ui-monospace,monospace; font-weight:600; }
  .tabla td.sec { text-align:left; background:#fff; font-family:system-ui,sans-serif; font-weight:400; border:1px solid #ECE8DC; }
  .tabla td.num { background:#fff; color:#333; border:1px solid #ECE8DC; }
  footer { color:var(--gris); font-size:12px; border-top:1px solid #E4E0D4; padding-top:14px; margin-top:20px; }
</style></head>
<body><div class="wrap">
  <header><h1>Monitor de coyuntura · Argentina</h1>
  <div class="sub">Actualizado __AHORA__ · fuentes: apis.datos.gob.ar · ArgentinaDatos · BCRA</div></header>
  <nav>__NAV__</nav>
  __SECCIONES__
  __NOTAS__
  <footer>Pasá el cursor sobre cualquier gráfico para ver el valor. Editá indicadores en indicadores.yaml.</footer>
</div>
<script>
const SERIES = __DATA__;
const baseOpts = (unidad) => ({
  responsive:true, maintainAspectRatio:false, animation:false,
  interaction:{ mode:'index', intersect:false },
  plugins:{ legend:{display:false}, tooltip:{
    callbacks:{ label:(c)=> c.parsed.y.toLocaleString('es-AR') + (unidad? ' '+unidad:'') } } },
  scales:{ x:{ ticks:{ maxTicksLimit:6, autoSkip:true, maxRotation:0, color:'#9A968C', font:{size:10} }, grid:{display:false} },
           y:{ ticks:{ color:'#9A968C', font:{size:10} }, grid:{color:'#EDEAE0'} } },
  elements:{ point:{radius:0, hitRadius:8}, line:{borderWidth:1.9, tension:0.12} }
});
SERIES.forEach(s => {
  const el = document.getElementById('ch'+s.i);
  if(!el) return;
  new Chart(el, { type:'line',
    data:{ labels:s.x, datasets:[{ data:s.y, borderColor:s.color, backgroundColor:s.color+'14', fill:true }] },
    options: baseOpts(s.unidad) });
});
</script>
</body></html>"""

    html = (plantilla.replace("__AHORA__", ahora).replace("__NAV__", nav)
            .replace("__SECCIONES__", secciones)
            .replace("__NOTAS__", notas_html)
            .replace("__DATA__", json.dumps(series_js, ensure_ascii=False)))
    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(html, encoding="utf-8")

"""
dashboard.py  ·  genera docs/index.html + docs/img/*.png
Diseño: grupos con subtítulos, gráficos de tamaño uniforme, etiquetas máx/mín/último.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

DESDE_GENERAL = "2024-01-01"
OUT = Path(__file__).resolve().parent / "docs"
IMG = OUT / "img"

ACENTO = {"precios": "#B4341F", "monetario_financiero": "#1D4E89",
          "real": "#256D5B", "externo": "#0E7C86", "social": "#B26B00", "fiscal": "#7A5195"}
TINTA = "#1A1A1A"; PAPEL = "#FBFAF7"; GRIS = "#9A968C"
ORDEN_BLOQUES = ["precios", "monetario_financiero", "externo", "real", "social", "fiscal"]
TITULO_BLOQUE = {"precios": "Precios", "monetario_financiero": "Monetario y financiero",
                 "real": "Actividad real", "externo": "Sector externo", "social": "Social y empleo", "fiscal": "Fiscal"}
ORDEN_GRUPOS = ["Precios", "Dólar", "Riesgo país", "Reservas",
                "Agregados monetarios", "Tasas de interés", "Crédito",
                "Comercio exterior", "Exportaciones por rubro", "Importaciones por uso",
                "Actividad", "Social"]


def _estilo():
    plt.rcParams.update({
        "figure.facecolor": PAPEL, "axes.facecolor": PAPEL,
        "axes.edgecolor": "#D8D4C8", "axes.linewidth": 0.8,
        "axes.grid": True, "grid.color": "#E7E3D8", "grid.linewidth": 0.7,
        "axes.spines.top": False, "axes.spines.right": False,
        "text.color": TINTA, "axes.labelcolor": TINTA,
        "xtick.color": GRIS, "ytick.color": GRIS,
        "font.family": "DejaVu Sans", "font.size": 10})


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


FIGSIZE = (7.0, 3.5)   # tamaño único para TODOS los gráficos


def _grafico(serie, nombre, unidad, color, desde, path):
    _estilo()
    s = serie[serie["fecha"] >= pd.to_datetime(desde)].sort_values("fecha")
    if len(s) < 2:
        s = serie.sort_values("fecha")
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=130)
    ax.plot(s["fecha"], s["valor"], color=color, linewidth=1.9)
    ax.fill_between(s["fecha"], s["valor"], s["valor"].min(), color=color, alpha=0.06)

    imax, imin = s["valor"].idxmax(), s["valor"].idxmin()
    for i, etq, dy in [(imax, "máx", 10), (imin, "mín", -16)]:
        ax.scatter([s.loc[i, "fecha"]], [s.loc[i, "valor"]], s=16,
                   facecolor="white", edgecolor=GRIS, zorder=5)
        ax.annotate(f"{etq} {_fmt_num(s.loc[i,'valor'])}", (s.loc[i, "fecha"], s.loc[i, "valor"]),
                    textcoords="offset points", xytext=(0, dy), ha="center",
                    fontsize=8, color="#6B6B6B")
    ful, vul = s["fecha"].iloc[-1], s["valor"].iloc[-1]
    ax.scatter([ful], [vul], s=26, color=color, zorder=6)
    ax.annotate(_fmt_num(vul), (ful, vul), textcoords="offset points", xytext=(7, 6),
                fontsize=9.5, fontweight="bold", color=color)
    ax.set_title(nombre, fontsize=12, fontweight="bold", loc="left", pad=8)
    ax.set_ylabel(unidad, fontsize=8, color=GRIS)
    ax.margins(x=0.02)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%y"))
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor=PAPEL)
    plt.close(fig)


def _grafico_reservas(serie, nombre, unidad, color, desde, path):
    """Compra/venta (barras = variación mensual del stock) + stock (línea). Mismo tamaño."""
    _estilo()
    s = serie.sort_values("fecha")
    s = s[s["fecha"] >= pd.to_datetime(desde)]
    if len(s) < 2:
        s = serie.sort_values("fecha")
    sm = s.set_index("fecha")["valor"].resample("MS").last()
    flujo = sm.diff()
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=130)
    colores = ["#256D5B" if (x or 0) >= 0 else "#B4341F" for x in flujo]
    ax.bar(flujo.index, flujo.values, width=22, color=colores, alpha=0.55)
    ax.axhline(0, color=GRIS, linewidth=0.6)
    ax.set_ylabel("Compra/venta mensual", fontsize=8, color=GRIS)
    ax2 = ax.twinx()
    ax2.plot(sm.index, sm.values, color=color, linewidth=1.9)
    ax2.set_ylabel("Stock", fontsize=8, color=color)
    ax2.grid(False)
    u = sm.dropna()
    if len(u):
        ax2.annotate(_fmt_num(u.iloc[-1]), (u.index[-1], u.iloc[-1]),
                     textcoords="offset points", xytext=(6, 6),
                     fontsize=9.5, fontweight="bold", color=color)
    ax.set_title(nombre, fontsize=12, fontweight="bold", loc="left", pad=8)
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    ax.legend(handles=[Patch(color="#256D5B", alpha=0.55, label="Compra (sube stock)"),
                       Patch(color="#B4341F", alpha=0.55, label="Venta (baja stock)"),
                       Line2D([0], [0], color=color, lw=2, label="Stock de reservas")],
              fontsize=7, loc="upper left", framealpha=0.9)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor=PAPEL)
    plt.close(fig)


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
    IMG.mkdir(parents=True, exist_ok=True)
    items, semaforo, fecha_sem = [], [], ""
    tablas = defaultdict(list)   # nombre_tabla -> filas (comercio exterior desagregado)
    for ind in config_indicadores:
        nombre = ind["nombre"]; bloque = ind["bloque"]; grupo = ind.get("grupo", "Otros")
        unidad = ind.get("unidad", ""); color = ACENTO.get(bloque, "#1D4E89")
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
            tablas[ind["tabla"]].append(dict(
                nombre=nombre, bloque=bloque, grupo=grupo,
                valor=serie["valor"].iloc[-1],
                yoy=(ia["valor"].iloc[-1] if not ia.empty else None),
                fecha=serie["fecha"].iloc[-1].strftime("%m/%Y")))
            continue
        desde = ind.get("desde", DESDE_GENERAL)
        p = IMG / f"{_slug(nombre)}.png"
        if ind.get("vista") == "reservas_combo":
            _grafico_reservas(serie, nombre, unidad, color, desde, p)
        else:
            _grafico(serie, nombre, unidad, color, desde, p)
        ult, pct = _variacion(serie)
        items.append(dict(nombre=nombre, bloque=bloque, grupo=grupo, color=color,
                          img=p.name, valor=_fmt_num(ult), unidad=unidad, pct=pct))
    _escribir_html(items, semaforo, fecha_sem, tablas)


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
    return f"""
      <h3 class="sub">EMAE por sector <span class="ref">({fecha_sem})</span></h3>
      <p class="nota">Interanual · mensual (serie original, con estacionalidad) · acumulado del año.
      Verde: +1% o más · Amarillo: entre -1% y +1% · Rojo: -1% o menos.</p>
      <table class="sem-tabla"><thead><tr><th>Sector</th><th>Interanual</th><th>Mensual</th><th>Acum. año</th></tr></thead>
      <tbody>{filas}</tbody></table>"""


def _tabla_valores(titulo, filas):
    """Tabla: rubro | último valor | var. interanual (coloreada). Para comercio exterior."""
    if not filas:
        return ""
    fecha = filas[0].get("fecha", "")
    def celda_yoy(v):
        bg, fg = _color_semaforo(v)
        return f'<td style="background:{bg};color:{fg}">{(f"{v:+.1f}%" if v is not None else "s/d")}</td>'
    cuerpo = "".join(
        f'<tr><td class="sec">{f["nombre"]}</td>'
        f'<td class="num">{_fmt_num(f["valor"])}</td>{celda_yoy(f["yoy"])}</tr>'
        for f in filas)
    return f"""
      <h3 class="sub">{titulo} <span class="ref">({fecha})</span></h3>
      <table class="sem-tabla"><thead><tr><th>Rubro</th><th>Último (USD M)</th><th>Interanual</th></tr></thead>
      <tbody>{cuerpo}</tbody></table>"""


def _escribir_html(items, semaforo, fecha_sem, tablas=None):
    tablas = tablas or {}
    # mapa grupo -> (titulo_tabla, filas)  para insertar tablas en su grupo
    grupo_tabla = {}
    for titulo, filas in tablas.items():
        if filas:
            grupo_tabla[filas[0]["grupo"]] = (titulo, filas)
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")

    def card(t):
        if t["pct"] is None: fl, cls = "•", "flat"
        elif t["pct"] > 0.05: fl, cls = "▲", "up"
        elif t["pct"] < -0.05: fl, cls = "▼", "down"
        else: fl, cls = "•", "flat"
        chg = f'{fl} {abs(t["pct"]):.1f}%' if t["pct"] is not None else "—"
        return f"""<div class="card" style="--acc:{t['color']}"><div class="cn">{t['nombre']}</div>
          <div class="cv">{t['valor']}</div><div class="cm"><span class="chg {cls}">{chg}</span><span class="uni">{t['unidad']}</span></div></div>"""

    # ---- TABLERO agrupado con subtítulos ----
    by_grupo = defaultdict(list)
    for it in items:
        by_grupo[it["grupo"]].append(it)
    tablero = ""
    for g in ORDEN_GRUPOS:
        if g in by_grupo:
            cards = "".join(card(t) for t in by_grupo[g])
            tablero += f'<div class="gwrap"><h4 class="gt">{g}</h4><div class="tablero">{cards}</div></div>'

    # ---- SECCIONES de gráficos por bloque -> subtítulos por grupo ----
    nav, secciones = "", ""
    for bloque in ORDEN_BLOQUES:
        its = [it for it in items if it["bloque"] == bloque]
        grupos_chart = {it["grupo"] for it in its}
        grupos_tabla = {g for g, (t, fs) in grupo_tabla.items() if fs[0]["bloque"] == bloque}
        tiene_sem = (bloque == "real" and semaforo)
        if not its and not grupos_tabla and not tiene_sem:
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
                gi = [it for it in its if it["grupo"] == g]
                if multi:
                    cuerpo += f'<h3 class="sub">{g}</h3>'
                figs = "".join(f'<figure><img src="img/{it["img"]}" alt="{it["nombre"]}" loading="lazy"></figure>' for it in gi)
                cuerpo += f'<div class="grid">{figs}</div>'
        if tiene_sem:
            cuerpo += _tabla_semaforo(semaforo, fecha_sem)
        secciones += f"""<section class="bloque" id="{bloque}">
          <h2><span class="dot" style="background:{ACENTO.get(bloque,'#1D4E89')}"></span>{TITULO_BLOQUE.get(bloque, bloque)}</h2>
          {cuerpo}</section>"""

    html = f"""<!doctype html><html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monitor de coyuntura · Argentina</title>
<style>
  :root {{ --papel:{PAPEL}; --tinta:{TINTA}; --gris:{GRIS}; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--papel); color:var(--tinta); font-family:system-ui,-apple-system,"Segoe UI",sans-serif; line-height:1.4; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:32px 22px 80px; }}
  header {{ border-bottom:2px solid var(--tinta); padding-bottom:14px; margin-bottom:18px; }}
  header h1 {{ font-size:27px; margin:0; letter-spacing:-.02em; }}
  header .sub {{ color:var(--gris); font-size:13px; margin-top:4px; }}
  nav {{ display:flex; flex-wrap:wrap; gap:16px; margin-bottom:26px; font-size:13px; }}
  nav a {{ color:#1D4E89; text-decoration:none; }} nav a:hover {{ text-decoration:underline; }}
  .gwrap {{ margin-bottom:20px; }}
  .gt {{ font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--gris);
    margin:0 0 8px; border-bottom:1px solid #E4E0D4; padding-bottom:4px; }}
  .tablero {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:10px; margin-bottom:8px; }}
  .card {{ border:1px solid #E4E0D4; border-left:3px solid var(--acc); border-radius:6px; padding:10px 12px; background:#fff; }}
  .cn {{ font-size:11px; text-transform:uppercase; letter-spacing:.03em; color:var(--gris); min-height:28px; }}
  .cv {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:21px; font-weight:600; margin:2px 0; }}
  .cm {{ display:flex; justify-content:space-between; align-items:baseline; font-size:11px; }}
  .chg {{ font-family:ui-monospace,monospace; font-weight:600; }}
  .chg.up {{ color:#B4341F; }} .chg.down {{ color:#256D5B; }} .chg.flat {{ color:var(--gris); }}
  .uni {{ color:var(--gris); }}
  .bloque {{ margin:40px 0; scroll-margin-top:16px; }}
  .bloque h2 {{ font-size:18px; display:flex; align-items:center; gap:9px; border-bottom:1px solid #E4E0D4; padding-bottom:8px; }}
  .sub {{ font-size:14px; margin:22px 0 10px; color:#444; }}
  .ref {{ color:var(--gris); font-weight:400; font-size:13px; }}
  .nota {{ color:var(--gris); font-size:12px; margin:6px 0 14px; }}
  .dot {{ width:11px; height:11px; border-radius:2px; display:inline-block; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(360px,440px)); justify-content:start; gap:18px; margin-bottom:8px; }}
  figure {{ margin:0; border:1px solid #ECE8DC; border-radius:8px; overflow:hidden; background:#fff; }}
  figure img {{ width:100%; display:block; }}
  .sem-tabla {{ width:100%; border-collapse:separate; border-spacing:3px; font-size:13px; margin-top:8px; }}
  .sem-tabla th {{ text-align:right; color:var(--gris); font-weight:600; font-size:11px; text-transform:uppercase; padding:4px 10px; }}
  .sem-tabla th:first-child {{ text-align:left; }}
  .sem-tabla td {{ padding:8px 10px; text-align:right; border-radius:5px; font-family:ui-monospace,monospace; font-weight:600; }}
  .sem-tabla td.sec {{ text-align:left; background:#fff; font-family:system-ui,sans-serif; font-weight:400; border:1px solid #ECE8DC; }}
  .sem-tabla td.num {{ background:#fff; color:#333; border:1px solid #ECE8DC; }}
  footer {{ color:var(--gris); font-size:12px; border-top:1px solid #E4E0D4; padding-top:14px; margin-top:20px; }}
  footer code {{ background:#F0EDE3; padding:1px 5px; border-radius:3px; }}
</style></head>
<body><div class="wrap">
  <header><h1>Monitor de coyuntura · Argentina</h1>
  <div class="sub">Actualizado {ahora} · fuentes: apis.datos.gob.ar · ArgentinaDatos · BCRA</div></header>
  <nav>{nav}</nav>
  {tablero}
  {secciones}
  <footer>Cada gráfico marca máximo, mínimo y último valor. Editá indicadores, grupos y ventanas en <code>indicadores.yaml</code>.</footer>
</div></body></html>"""
    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(html, encoding="utf-8")

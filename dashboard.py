"""
dashboard.py
------------
Genera docs/index.html + docs/img/*.png

Criterios de diseño:
  - UN gráfico por indicador (no paneles partidos), todos del MISMO tamaño.
  - Cada gráfico anota máximo, mínimo y último valor.
  - Orden fijo de secciones: Precios · Monetario y financiero · Actividad real · Social.
  - "Actividad real" agrupa el EMAE general + el SEMÁFORO por sector.
  - Ventana temporal por defecto desde 2024; cada indicador puede pedir otra con 'desde'.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

DESDE_GENERAL = "2024-01-01"          # arranque por defecto de los gráficos
OUT = Path(__file__).resolve().parent / "docs"
IMG = OUT / "img"

ACENTO = {
    "precios": "#B4341F", "monetario_financiero": "#1D4E89",
    "real": "#256D5B", "actividad_sectorial": "#256D5B",
    "fiscal": "#7A5195", "social": "#B26B00",
}
TINTA = "#1A1A1A"; PAPEL = "#FBFAF7"; GRIS = "#9A968C"
ORDEN_BLOQUES = ["precios", "monetario_financiero", "real", "social", "fiscal"]
TITULO_BLOQUE = {
    "precios": "Precios", "monetario_financiero": "Monetario y financiero",
    "real": "Actividad real", "social": "Social y empleo", "fiscal": "Fiscal",
}


def _estilo():
    plt.rcParams.update({
        "figure.facecolor": PAPEL, "axes.facecolor": PAPEL,
        "axes.edgecolor": "#D8D4C8", "axes.linewidth": 0.8,
        "axes.grid": True, "grid.color": "#E7E3D8", "grid.linewidth": 0.7,
        "axes.spines.top": False, "axes.spines.right": False,
        "text.color": TINTA, "axes.labelcolor": TINTA,
        "xtick.color": GRIS, "ytick.color": GRIS,
        "font.family": "DejaVu Sans", "font.size": 10,
    })


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


def _grafico(serie, nombre, unidad, color, desde, path):
    """Un solo gráfico, tamaño uniforme, con etiquetas de máx / mín / último."""
    _estilo()
    s = serie[serie["fecha"] >= pd.to_datetime(desde)].sort_values("fecha")
    if len(s) < 2:
        s = serie.sort_values("fecha")

    fig, ax = plt.subplots(figsize=(7.4, 3.6), dpi=130)
    ax.plot(s["fecha"], s["valor"], color=color, linewidth=1.9)
    ax.fill_between(s["fecha"], s["valor"], s["valor"].min(), color=color, alpha=0.06)

    imax = s["valor"].idxmax(); imin = s["valor"].idxmin()
    fmax, vmax = s.loc[imax, "fecha"], s.loc[imax, "valor"]
    fmin, vmin = s.loc[imin, "fecha"], s.loc[imin, "valor"]
    ful, vul = s["fecha"].iloc[-1], s["valor"].iloc[-1]

    # máximo y mínimo (gris, discretos)
    for f, v, etq, dy in [(fmax, vmax, f"máx {_fmt_num(vmax)}", 10),
                          (fmin, vmin, f"mín {_fmt_num(vmin)}", -16)]:
        ax.scatter([f], [v], s=16, facecolor="white", edgecolor=GRIS, zorder=5)
        ax.annotate(etq, (f, v), textcoords="offset points", xytext=(0, dy),
                    ha="center", fontsize=8, color="#6B6B6B")
    # último (color, destacado)
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


def _interanual(serie: pd.DataFrame) -> pd.DataFrame:
    s = serie.sort_values("fecha").copy()
    prev = s.rename(columns={"valor": "valor_prev"})[["fecha", "valor_prev"]].copy()
    prev["fecha"] = prev["fecha"] + pd.DateOffset(years=1)
    m = pd.merge_asof(s, prev, on="fecha", direction="nearest",
                      tolerance=pd.Timedelta(days=20))
    m = m.dropna(subset=["valor_prev"]); m = m[m["valor_prev"] != 0]
    m["valor"] = (m["valor"] / m["valor_prev"] - 1) * 100
    return m[["fecha", "valor"]].dropna().reset_index(drop=True)


def _metricas_sector(serie: pd.DataFrame):
    s = serie.sort_values("fecha").reset_index(drop=True)
    ia = _interanual(s)
    v_ia = ia["valor"].iloc[-1] if not ia.empty else None
    v_men = None
    if len(s) >= 2 and s["valor"].iloc[-2] != 0:
        v_men = (s["valor"].iloc[-1] / s["valor"].iloc[-2] - 1) * 100
    v_acum = None
    ult = s["fecha"].iloc[-1]
    este = s[(s["fecha"].dt.year == ult.year) & (s["fecha"].dt.month <= ult.month)]
    prev = s[(s["fecha"].dt.year == ult.year - 1) & (s["fecha"].dt.month <= ult.month)]
    if len(este) and len(prev) and prev["valor"].mean() != 0:
        v_acum = (este["valor"].mean() / prev["valor"].mean() - 1) * 100
    return v_ia, v_men, v_acum


def _variacion(serie):
    if len(serie) < 2:
        return (serie["valor"].iloc[-1] if len(serie) else None), None
    ult, prev = serie["valor"].iloc[-1], serie["valor"].iloc[-2]
    pct = ((ult - prev) / prev * 100) if prev else None
    return ult, pct


def generar(historico: pd.DataFrame, config_indicadores: list[dict]):
    IMG.mkdir(parents=True, exist_ok=True)
    tarjetas, secciones, semaforo = [], {}, []
    fecha_sem = ""

    for ind in config_indicadores:
        nombre = ind["nombre"]; bloque = ind["bloque"]
        unidad = ind.get("unidad", ""); color = ACENTO.get(bloque, "#1D4E89")
        serie = (historico[historico["indicador"] == nombre]
                 .sort_values("fecha").reset_index(drop=True))
        if serie.empty:
            continue

        if ind.get("semaforo"):
            ia, men, acum = _metricas_sector(serie)
            fecha_sem = serie["fecha"].iloc[-1].strftime("%m/%Y")
            semaforo.append(dict(nombre=nombre.replace("EMAE · ", ""),
                                 ia=ia, men=men, acum=acum))
            continue

        desde = ind.get("desde", DESDE_GENERAL)
        p = IMG / f"{_slug(nombre)}.png"
        _grafico(serie, nombre, unidad, color, desde, p)

        ult, pct = _variacion(serie)
        tarjetas.append(dict(nombre=nombre, color=color, valor=_fmt_num(ult),
                             unidad=unidad, pct=pct,
                             fecha=serie["fecha"].iloc[-1].strftime("%d/%m/%Y")))
        secciones.setdefault(bloque, []).append(dict(nombre=nombre, img=p.name))

    _escribir_html(tarjetas, secciones, semaforo, fecha_sem)


def _color_semaforo(v):
    if v is None or pd.isna(v):
        return "#E7E3D8", TINTA
    if v > 1:   return "#DCEEDD", "#1E5C2E"
    if v < -1:  return "#F6DCD8", "#8A2A1C"
    return "#FBF0D5", "#7A5A10"


def _tabla_semaforo(semaforo, fecha_sem):
    if not semaforo:
        return ""
    orden = sorted(semaforo, key=lambda x: (x["ia"] is None, -(x["ia"] or -999)))

    def celda(v):
        bg, fg = _color_semaforo(v)
        t = f"{v:+.1f}%" if v is not None else "s/d"
        return f'<td style="background:{bg};color:{fg}">{t}</td>'

    filas = "".join(
        f'<tr><td class="sec">{s["nombre"]}</td>{celda(s["ia"])}{celda(s["men"])}{celda(s["acum"])}</tr>'
        for s in orden)
    return f"""
      <h3 class="sub">EMAE por sector <span class="ref">({fecha_sem})</span></h3>
      <p class="nota">Variación interanual (i.a.), mensual (serie original, con estacionalidad) y acumulada del año.
      Verde: sube +1% o más · Amarillo: entre -1% y +1% · Rojo: baja -1% o más.</p>
      <table class="sem-tabla">
        <thead><tr><th>Sector</th><th>Interanual</th><th>Mensual</th><th>Acum. año</th></tr></thead>
        <tbody>{filas}</tbody>
      </table>"""


def _escribir_html(tarjetas, secciones, semaforo, fecha_sem):
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")

    def card(t):
        if t["pct"] is None: fl, cls = "•", "flat"
        elif t["pct"] > 0.05: fl, cls = "▲", "up"
        elif t["pct"] < -0.05: fl, cls = "▼", "down"
        else: fl, cls = "•", "flat"
        chg = f'{fl} {abs(t["pct"]):.1f}%' if t["pct"] is not None else "—"
        return f"""<div class="card" style="--acc:{t['color']}">
          <div class="cn">{t['nombre']}</div><div class="cv">{t['valor']}</div>
          <div class="cm"><span class="chg {cls}">{chg}</span><span class="uni">{t['unidad']}</span></div>
        </div>"""

    tablero = "\n".join(card(t) for t in tarjetas)

    nav, bloques_html = "", ""
    for bloque in ORDEN_BLOQUES:
        items = secciones.get(bloque)
        tiene_sem = (bloque == "real" and semaforo)
        if not items and not tiene_sem:
            continue
        nav += f'<a href="#{bloque}">{TITULO_BLOQUE.get(bloque, bloque)}</a>'
        figs = "".join(
            f'<figure><img src="img/{it["img"]}" alt="{it["nombre"]}" loading="lazy"></figure>\n'
            for it in (items or []))
        extra = _tabla_semaforo(semaforo, fecha_sem) if tiene_sem else ""
        bloques_html += f"""
        <section class="bloque" id="{bloque}">
          <h2><span class="dot" style="background:{ACENTO.get(bloque,'#1D4E89')}"></span>{TITULO_BLOQUE.get(bloque, bloque)}</h2>
          <div class="grid">{figs}</div>
          {extra}
        </section>"""

    html = f"""<!doctype html><html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monitor de coyuntura · Argentina</title>
<style>
  :root {{ --papel:{PAPEL}; --tinta:{TINTA}; --gris:{GRIS}; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--papel); color:var(--tinta);
    font-family: system-ui,-apple-system,"Segoe UI",sans-serif; line-height:1.4; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:32px 22px 80px; }}
  header {{ border-bottom:2px solid var(--tinta); padding-bottom:14px; margin-bottom:18px; }}
  header h1 {{ font-size:27px; margin:0; letter-spacing:-.02em; }}
  header .sub {{ color:var(--gris); font-size:13px; margin-top:4px; font-variant-numeric:tabular-nums; }}
  nav {{ display:flex; flex-wrap:wrap; gap:16px; margin-bottom:30px; font-size:13px; }}
  nav a {{ color:#1D4E89; text-decoration:none; border-bottom:1px solid transparent; }}
  nav a:hover {{ border-bottom-color:#1D4E89; }}
  .tablero {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:12px; margin-bottom:44px; }}
  .card {{ border:1px solid #E4E0D4; border-left:3px solid var(--acc); border-radius:6px; padding:11px 13px; background:#fff; }}
  .cn {{ font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:var(--gris); min-height:30px; }}
  .cv {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:22px; font-weight:600; margin:2px 0; }}
  .cm {{ display:flex; justify-content:space-between; align-items:baseline; font-size:11px; }}
  .chg {{ font-family:ui-monospace,monospace; font-weight:600; }}
  .chg.up {{ color:#B4341F; }} .chg.down {{ color:#256D5B; }} .chg.flat {{ color:var(--gris); }}
  .uni {{ color:var(--gris); }}
  .bloque {{ margin-bottom:46px; scroll-margin-top:16px; }}
  .bloque h2 {{ font-size:18px; display:flex; align-items:center; gap:9px; border-bottom:1px solid #E4E0D4; padding-bottom:8px; }}
  .sub {{ font-size:15px; margin:26px 0 2px; }}
  .ref {{ color:var(--gris); font-weight:400; font-size:13px; }}
  .nota {{ color:var(--gris); font-size:12px; margin:6px 0 14px; }}
  .dot {{ width:11px; height:11px; border-radius:2px; display:inline-block; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(430px,1fr)); gap:18px; }}
  figure {{ margin:0; border:1px solid #ECE8DC; border-radius:8px; overflow:hidden; background:#fff; }}
  figure img {{ width:100%; display:block; }}
  .sem-tabla {{ width:100%; border-collapse:separate; border-spacing:3px; font-size:13px; }}
  .sem-tabla th {{ text-align:right; color:var(--gris); font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:.03em; padding:4px 10px; }}
  .sem-tabla th:first-child {{ text-align:left; }}
  .sem-tabla td {{ padding:8px 10px; text-align:right; border-radius:5px; font-family:ui-monospace,monospace; font-weight:600; font-variant-numeric:tabular-nums; }}
  .sem-tabla td.sec {{ text-align:left; background:#fff; font-family:system-ui,sans-serif; font-weight:400; border:1px solid #ECE8DC; }}
  footer {{ color:var(--gris); font-size:12px; border-top:1px solid #E4E0D4; padding-top:14px; margin-top:20px; }}
  footer code {{ background:#F0EDE3; padding:1px 5px; border-radius:3px; }}
</style></head>
<body><div class="wrap">
  <header><h1>Monitor de coyuntura · Argentina</h1>
  <div class="sub">Actualizado {ahora} · fuentes: apis.datos.gob.ar · ArgentinaDatos · BCRA</div></header>
  <nav>{nav}</nav>
  <div class="tablero">{tablero}</div>
  {bloques_html}
  <footer>Cada gráfico marca máximo, mínimo y último valor. Para editar indicadores o su ventana temporal,
  cambiá <code>indicadores.yaml</code>.</footer>
</div></body></html>"""

    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(html, encoding="utf-8")

"""
dashboard.py
------------
Genera en docs/:
  - docs/img/*.png   : por cada indicador, un panel con "serie completa" + "ultimo anio"
  - docs/index.html  : tablero reorganizado con:
        * fila de titulares (valor ultimo + variacion)
        * SEMAFORO sectorial del EMAE (tabla verde/amarillo/rojo por variacion i.a.)
        * secciones por bloque con los graficos

Sin dependencias de red: solo lee el CSV historico ya guardado.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

OUT = Path(__file__).resolve().parent / "docs"
IMG = OUT / "img"

ACENTO = {
    "precios":               "#B4341F",
    "monetario_financiero":  "#1D4E89",
    "real":                  "#256D5B",
    "actividad_sectorial":   "#256D5B",
    "fiscal":                "#7A5195",
    "social":                "#B26B00",
}
TINTA = "#1A1A1A"; PAPEL = "#FBFAF7"; GRIS = "#9A968C"

TITULO_BLOQUE = {
    "precios": "Precios",
    "monetario_financiero": "Monetario y financiero",
    "real": "Actividad real",
    "fiscal": "Fiscal",
    "social": "Social y empleo",
}


def _estilo():
    plt.rcParams.update({
        "figure.facecolor": PAPEL, "axes.facecolor": PAPEL,
        "axes.edgecolor": "#D8D4C8", "axes.linewidth": 0.8,
        "axes.grid": True, "grid.color": "#E7E3D8", "grid.linewidth": 0.7,
        "axes.spines.top": False, "axes.spines.right": False,
        "text.color": TINTA, "axes.labelcolor": TINTA,
        "xtick.color": GRIS, "ytick.color": GRIS,
        "font.family": "DejaVu Sans", "font.size": 9,
    })


def _fmt_num(v) -> str:
    if v is None or pd.isna(v):
        return "s/d"
    if abs(v) >= 1000:
        return f"{v:,.0f}".replace(",", ".")
    s = f"{v:,.1f}" if abs(v) >= 10 else f"{v:,.2f}"
    return s.replace(",", "@").replace(".", ",").replace("@", ".")


def _panel(ax, serie, color, titulo):
    ax.plot(serie["fecha"], serie["valor"], color=color, linewidth=1.6)
    ax.fill_between(serie["fecha"], serie["valor"], serie["valor"].min(),
                    color=color, alpha=0.06)
    ult = serie.iloc[-1]
    ax.scatter([ult["fecha"]], [ult["valor"]], color=color, s=18, zorder=5)
    ax.annotate(_fmt_num(ult["valor"]), (ult["fecha"], ult["valor"]),
                textcoords="offset points", xytext=(5, 5),
                fontsize=8, fontweight="bold", color=color)
    ax.set_title(titulo, fontsize=9, color=GRIS, loc="left", pad=6)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%y"))


def _grafico_doble(serie, nombre, unidad, color, path):
    """Un PNG con dos paneles: serie completa (izq) y ultimo anio (der)."""
    _estilo()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.2, 3.0), dpi=130)
    _panel(a1, serie, color, "Serie completa")
    corte = serie["fecha"].max() - pd.Timedelta(days=380)
    ult_anio = serie[serie["fecha"] >= corte]
    if len(ult_anio) >= 2:
        _panel(a2, ult_anio, color, "Ultimo anio")
    else:
        a2.axis("off")
    fig.suptitle(f"{nombre}   ·   {unidad}", fontsize=11, fontweight="bold",
                 x=0.01, ha="left")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(path, bbox_inches="tight", facecolor=PAPEL)
    plt.close(fig)


def _grafico_simple(serie, titulo, unidad, color, path):
    _estilo()
    fig, ax = plt.subplots(figsize=(6.2, 3.0), dpi=130)
    _panel(ax, serie, color, "")
    ax.set_title(titulo, fontsize=11, fontweight="bold", loc="left", pad=8)
    ax.set_ylabel(unidad, fontsize=8, color=GRIS)
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


def _variacion(serie):
    if len(serie) < 2:
        return (serie["valor"].iloc[-1] if len(serie) else None), None
    ult, prev = serie["valor"].iloc[-1], serie["valor"].iloc[-2]
    pct = ((ult - prev) / prev * 100) if prev else None
    return ult, pct


def _slug(s: str) -> str:
    import re
    s = s.lower()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


# ---------------------------------------------------------------------------
def generar(historico: pd.DataFrame, config_indicadores: list[dict]):
    IMG.mkdir(parents=True, exist_ok=True)
    tarjetas, secciones, semaforo = [], {}, []

    for ind in config_indicadores:
        nombre = ind["nombre"]; bloque = ind["bloque"]
        unidad = ind.get("unidad", ""); color = ACENTO.get(bloque, "#1D4E89")
        serie = (historico[historico["indicador"] == nombre]
                 .sort_values("fecha").reset_index(drop=True))
        if serie.empty:
            continue

        # --- sectores del EMAE -> van a la tabla semaforo, no a graficos ---
        if ind.get("semaforo"):
            ia = _interanual(serie)
            yoy = ia["valor"].iloc[-1] if not ia.empty else None
            fecha = serie["fecha"].iloc[-1].strftime("%m/%Y")
            semaforo.append(dict(nombre=nombre.replace("EMAE · ", ""),
                                 yoy=yoy, fecha=fecha))
            continue

        graficos = ind.get("graficos", ["nivel"])
        imgs = []
        if "nivel" in graficos:
            p = IMG / f"{_slug(nombre)}.png"
            _grafico_doble(serie, nombre, unidad, color, p)
            imgs.append(p.name)
        if "interanual" in graficos:
            ia = _interanual(serie)
            if not ia.empty:
                p = IMG / f"{_slug(nombre)}_ia.png"
                _grafico_simple(ia, f"{nombre} — var. % interanual", "% i.a.", color, p)
                imgs.append(p.name)

        ult, pct = _variacion(serie)
        tarjetas.append(dict(nombre=nombre, color=color, valor=_fmt_num(ult),
                             unidad=unidad, pct=pct,
                             fecha=serie["fecha"].iloc[-1].strftime("%d/%m/%Y")))
        secciones.setdefault(bloque, []).append(dict(nombre=nombre, imgs=imgs))

    _escribir_html(tarjetas, secciones, semaforo)


def _color_semaforo(yoy):
    if yoy is None or pd.isna(yoy):
        return "#E7E3D8", TINTA
    if yoy > 1:   return "#DCEEDD", "#1E5C2E"    # verde
    if yoy < -1:  return "#F6DCD8", "#8A2A1C"    # rojo
    return "#FBF0D5", "#7A5A10"                  # amarillo


def _escribir_html(tarjetas, secciones, semaforo):
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")

    def card(t):
        if t["pct"] is None: fl, cls = "•", "flat"
        elif t["pct"] > 0.05: fl, cls = "▲", "up"
        elif t["pct"] < -0.05: fl, cls = "▼", "down"
        else: fl, cls = "•", "flat"
        chg = f'{fl} {abs(t["pct"]):.1f}%' if t["pct"] is not None else "—"
        return f"""<div class="card" style="--acc:{t['color']}">
          <div class="cn">{t['nombre']}</div>
          <div class="cv">{t['valor']}</div>
          <div class="cm"><span class="chg {cls}">{chg}</span><span class="uni">{t['unidad']} · {t['fecha']}</span></div>
        </div>"""

    tablero = "\n".join(card(t) for t in tarjetas)

    # --- semaforo sectorial ---
    semaforo_html = ""
    if semaforo:
        orden = sorted(semaforo, key=lambda x: (x["yoy"] is None, -(x["yoy"] or -999)))
        celdas = ""
        for s in orden:
            bg, fg = _color_semaforo(s["yoy"])
            val = f'{s["yoy"]:+.1f}%' if s["yoy"] is not None else "s/d"
            celdas += f"""<div class="sem" style="background:{bg};color:{fg}">
              <div class="sem-n">{s['nombre']}</div>
              <div class="sem-v">{val}</div></div>"""
        fecha_ref = orden[0]["fecha"] if orden else ""
        semaforo_html = f"""
        <section class="bloque" id="semaforo">
          <h2><span class="dot" style="background:{ACENTO['real']}"></span>EMAE por sector — variación interanual <span class="ref">({fecha_ref})</span></h2>
          <p class="nota">Verde: crece más de 1% i.a. · Amarillo: entre -1% y +1% · Rojo: cae más de 1% i.a. Ordenado de mayor a menor.</p>
          <div class="sem-grid">{celdas}</div>
        </section>"""

    # --- secciones por bloque ---
    nav = '<a href="#semaforo">Semáforo sectorial</a>' if semaforo else ""
    bloques_html = ""
    for bloque, items in secciones.items():
        nav += f'<a href="#{bloque}">{TITULO_BLOQUE.get(bloque, bloque)}</a>'
        graf = ""
        for it in items:
            for img in it["imgs"]:
                graf += f'<figure><img src="img/{img}" alt="{it["nombre"]}" loading="lazy"></figure>\n'
        bloques_html += f"""
        <section class="bloque" id="{bloque}">
          <h2><span class="dot" style="background:{ACENTO.get(bloque,'#1D4E89')}"></span>{TITULO_BLOQUE.get(bloque, bloque)}</h2>
          <div class="grid">{graf}</div>
        </section>"""

    html = f"""<!doctype html><html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monitor de coyuntura · Argentina</title>
<style>
  :root {{ --papel:{PAPEL}; --tinta:{TINTA}; --gris:{GRIS}; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--papel); color:var(--tinta);
    font-family: system-ui,-apple-system,"Segoe UI",sans-serif; line-height:1.4; }}
  .wrap {{ max-width:1120px; margin:0 auto; padding:32px 20px 80px; }}
  header {{ border-bottom:2px solid var(--tinta); padding-bottom:14px; margin-bottom:18px; }}
  header h1 {{ font-size:26px; margin:0; letter-spacing:-.02em; }}
  header .sub {{ color:var(--gris); font-size:13px; margin-top:4px; font-variant-numeric:tabular-nums; }}
  nav {{ display:flex; flex-wrap:wrap; gap:14px; margin-bottom:28px; font-size:13px; }}
  nav a {{ color:#1D4E89; text-decoration:none; border-bottom:1px solid transparent; }}
  nav a:hover {{ border-bottom-color:#1D4E89; }}
  .tablero {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(185px,1fr)); gap:12px; margin-bottom:40px; }}
  .card {{ border:1px solid #E4E0D4; border-left:3px solid var(--acc); border-radius:6px; padding:11px 13px; background:#fff; }}
  .cn {{ font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:var(--gris); min-height:26px; }}
  .cv {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:23px; font-weight:600; margin:2px 0; }}
  .cm {{ display:flex; justify-content:space-between; align-items:baseline; font-size:11px; }}
  .chg {{ font-family:ui-monospace,monospace; font-weight:600; }}
  .chg.up {{ color:#B4341F; }} .chg.down {{ color:#256D5B; }} .chg.flat {{ color:var(--gris); }}
  .uni {{ color:var(--gris); }}
  .bloque {{ margin-bottom:42px; scroll-margin-top:16px; }}
  .bloque h2 {{ font-size:17px; display:flex; align-items:center; gap:9px; border-bottom:1px solid #E4E0D4; padding-bottom:8px; }}
  .ref {{ color:var(--gris); font-weight:400; font-size:13px; }}
  .nota {{ color:var(--gris); font-size:12px; margin:6px 0 16px; }}
  .dot {{ width:11px; height:11px; border-radius:2px; display:inline-block; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(420px,1fr)); gap:16px; }}
  figure {{ margin:0; border:1px solid #ECE8DC; border-radius:8px; overflow:hidden; background:#fff; }}
  figure img {{ width:100%; display:block; }}
  .sem-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:8px; }}
  .sem {{ border-radius:6px; padding:11px 13px; }}
  .sem-n {{ font-size:12px; line-height:1.25; min-height:44px; }}
  .sem-v {{ font-family:ui-monospace,monospace; font-size:20px; font-weight:700; margin-top:4px; }}
  footer {{ color:var(--gris); font-size:12px; border-top:1px solid #E4E0D4; padding-top:14px; margin-top:20px; }}
  footer code {{ background:#F0EDE3; padding:1px 5px; border-radius:3px; }}
</style></head>
<body><div class="wrap">
  <header><h1>Monitor de coyuntura · Argentina</h1>
  <div class="sub">Actualizado {ahora} · fuentes: apis.datos.gob.ar · ArgentinaDatos · BCRA</div></header>
  <nav>{nav}</nav>
  <div class="tablero">{tablero}</div>
  {semaforo_html}
  {bloques_html}
  <footer>En las tarjetas, la variación es respecto de la observación anterior de cada serie.
  Para agregar indicadores, editá <code>indicadores.yaml</code>.</footer>
</div></body></html>"""

    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(html, encoding="utf-8")

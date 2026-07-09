"""
dashboard.py
------------
Genera:
  - output/img/*.png : un gráfico por indicador (nivel y/o interanual)
  - output/index.html : tablero que agrupa todo por bloque, con una fila
                        de "titulares" arriba (valor último + variación).

Diseño: papel claro, tinta oscura, números en monoespaciada (estética de
terminal financiera), un único color de acento por bloque. Sin dependencias
de red: sólo lee el CSV histórico ya guardado.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

OUT = Path(__file__).resolve().parent / "output"
IMG = OUT / "img"

# --- paleta por bloque (un acento por sección, resto en gris tinta) ----------
ACENTO = {
    "precios":               "#B4341F",   # rojo ladrillo
    "monetario_financiero":  "#1D4E89",   # azul
    "real":                  "#256D5B",   # verde profundo
    "fiscal":                "#7A5195",   # violeta
    "social":                "#B26B00",   # ámbar
}
TINTA = "#1A1A1A"
PAPEL = "#FBFAF7"
GRIS = "#9A968C"

TITULO_BLOQUE = {
    "precios": "Precios",
    "monetario_financiero": "Monetario y financiero",
    "real": "Actividad real",
    "fiscal": "Fiscal",
    "social": "Social y empleo",
}


def _estilo():
    plt.rcParams.update({
        "figure.facecolor": PAPEL,
        "axes.facecolor": PAPEL,
        "axes.edgecolor": "#D8D4C8",
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "grid.color": "#E7E3D8",
        "grid.linewidth": 0.7,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "text.color": TINTA,
        "axes.labelcolor": TINTA,
        "xtick.color": GRIS,
        "ytick.color": GRIS,
        "font.family": "DejaVu Sans",
        "font.size": 10,
    })


def _fmt_num(v: float) -> str:
    if v is None or pd.isna(v):
        return "s/d"
    if abs(v) >= 1000:
        return f"{v:,.0f}".replace(",", ".")
    if abs(v) >= 10:
        return f"{v:,.1f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"{v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _grafico(serie: pd.DataFrame, titulo: str, unidad: str, color: str, path: Path):
    _estilo()
    fig, ax = plt.subplots(figsize=(6.4, 3.2), dpi=130)
    ax.plot(serie["fecha"], serie["valor"], color=color, linewidth=1.8)
    ax.fill_between(serie["fecha"], serie["valor"], serie["valor"].min(),
                    color=color, alpha=0.06)
    # marcar último punto
    ult = serie.iloc[-1]
    ax.scatter([ult["fecha"]], [ult["valor"]], color=color, s=22, zorder=5)
    ax.annotate(_fmt_num(ult["valor"]), (ult["fecha"], ult["valor"]),
                textcoords="offset points", xytext=(6, 6),
                fontsize=9, fontweight="bold", color=color)
    ax.set_title(titulo, fontsize=11, fontweight="bold", loc="left", pad=8)
    ax.set_ylabel(unidad, fontsize=8, color=GRIS)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor=PAPEL)
    plt.close(fig)


def _interanual(serie: pd.DataFrame) -> pd.DataFrame:
    """
    Variación % interanual robusta a la frecuencia: para cada fecha busca el
    valor de ~1 año calendario antes (con tolerancia de 20 días) y calcula el
    cambio %. Funciona igual para series diarias, mensuales o trimestrales.
    """
    s = serie.sort_values("fecha").copy()
    prev = s.rename(columns={"valor": "valor_prev"})[["fecha", "valor_prev"]].copy()
    prev["fecha"] = prev["fecha"] + pd.DateOffset(years=1)  # "correr" 1 año adelante
    m = pd.merge_asof(s, prev, on="fecha", direction="nearest",
                      tolerance=pd.Timedelta(days=20))
    m = m.dropna(subset=["valor_prev"])
    m = m[m["valor_prev"] != 0]
    m["valor"] = (m["valor"] / m["valor_prev"] - 1) * 100
    return m[["fecha", "valor"]].dropna().reset_index(drop=True)


def _variacion(serie: pd.DataFrame):
    """Devuelve (ultimo_valor, delta_abs, delta_pct) vs observación anterior."""
    if len(serie) < 2:
        return serie["valor"].iloc[-1] if len(serie) else None, None, None
    ult, prev = serie["valor"].iloc[-1], serie["valor"].iloc[-2]
    delta = ult - prev
    pct = (delta / prev * 100) if prev else None
    return ult, delta, pct


def generar(historico: pd.DataFrame, config_indicadores: list[dict]):
    """
    historico: DataFrame largo [fecha, indicador, bloque, unidad, valor]
    config_indicadores: lista del yaml (para respetar orden y qué gráficos hacer)
    """
    IMG.mkdir(parents=True, exist_ok=True)
    tarjetas = []      # titulares
    secciones: dict[str, list] = {}

    for ind in config_indicadores:
        nombre = ind["nombre"]
        bloque = ind["bloque"]
        unidad = ind.get("unidad", "")
        color = ACENTO.get(bloque, "#1D4E89")
        serie = (historico[historico["indicador"] == nombre]
                 .sort_values("fecha").reset_index(drop=True))
        if serie.empty:
            continue

        graficos = ind.get("graficos", ["nivel"])
        imgs = []
        if "nivel" in graficos:
            p = IMG / f"{_slug(nombre)}_nivel.png"
            _grafico(serie, nombre, unidad, color, p)
            imgs.append(p.name)
        if "interanual" in graficos:
            ia = _interanual(serie)   # variación vs ~1 año calendario antes
            if not ia.empty:
                p = IMG / f"{_slug(nombre)}_ia.png"
                _grafico(ia, f"{nombre} — var. % interanual", "% i.a.", color, p)
                imgs.append(p.name)

        ult, delta, pct = _variacion(serie)
        fecha_ult = serie["fecha"].iloc[-1].strftime("%d/%m/%Y")
        tarjetas.append(dict(nombre=nombre, bloque=bloque, color=color,
                             valor=_fmt_num(ult), unidad=unidad,
                             pct=pct, delta=delta, fecha=fecha_ult))
        secciones.setdefault(bloque, []).append(dict(nombre=nombre, imgs=imgs))

    _escribir_html(tarjetas, secciones)


def _slug(s: str) -> str:
    import re
    s = s.lower()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _escribir_html(tarjetas, secciones):
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")

    def card(t):
        if t["pct"] is None:
            flecha, cls = "", "flat"
        elif t["pct"] > 0.05:
            flecha, cls = "▲", "up"
        elif t["pct"] < -0.05:
            flecha, cls = "▼", "down"
        else:
            flecha, cls = "•", "flat"
        chg = f'{flecha} {abs(t["pct"]):.1f}%' if t["pct"] is not None else "—"
        return f"""
        <div class="card" style="--acc:{t['color']}">
          <div class="card-nombre">{t['nombre']}</div>
          <div class="card-valor">{t['valor']}</div>
          <div class="card-meta">
            <span class="chg {cls}">{chg}</span>
            <span class="uni">{t['unidad']} · {t['fecha']}</span>
          </div>
        </div>"""

    tablero = "\n".join(card(t) for t in tarjetas)

    bloques_html = ""
    for bloque, items in secciones.items():
        graf = ""
        for it in items:
            for img in it["imgs"]:
                graf += f'<figure><img src="img/{img}" alt="{it["nombre"]}" loading="lazy"></figure>\n'
        bloques_html += f"""
        <section class="bloque">
          <h2><span class="dot" style="background:{ACENTO.get(bloque,'#1D4E89')}"></span>{TITULO_BLOQUE.get(bloque, bloque)}</h2>
          <div class="grid">{graf}</div>
        </section>"""

    html = f"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monitor de coyuntura · Argentina</title>
<style>
  :root {{ --papel:{PAPEL}; --tinta:{TINTA}; --gris:{GRIS}; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--papel); color:var(--tinta);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif; line-height:1.4; }}
  .wrap {{ max-width:1100px; margin:0 auto; padding:32px 20px 80px; }}
  header {{ border-bottom:2px solid var(--tinta); padding-bottom:14px; margin-bottom:26px; }}
  header h1 {{ font-size:26px; margin:0; letter-spacing:-.02em; }}
  header .sub {{ color:var(--gris); font-size:13px; margin-top:4px;
    font-variant-numeric:tabular-nums; }}
  .tablero {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(190px,1fr));
    gap:12px; margin-bottom:40px; }}
  .card {{ border:1px solid #E4E0D4; border-left:3px solid var(--acc);
    border-radius:6px; padding:12px 14px; background:#fff; }}
  .card-nombre {{ font-size:11px; text-transform:uppercase; letter-spacing:.04em;
    color:var(--gris); min-height:28px; }}
  .card-valor {{ font-family: ui-monospace, "SF Mono", "Cascadia Code", Menlo, monospace;
    font-size:24px; font-weight:600; margin:2px 0; }}
  .card-meta {{ display:flex; justify-content:space-between; align-items:baseline;
    font-size:11px; }}
  .chg {{ font-family: ui-monospace, monospace; font-weight:600; }}
  .chg.up {{ color:#B4341F; }} .chg.down {{ color:#256D5B; }} .chg.flat {{ color:var(--gris); }}
  .uni {{ color:var(--gris); }}
  .bloque {{ margin-bottom:40px; }}
  .bloque h2 {{ font-size:17px; display:flex; align-items:center; gap:9px;
    border-bottom:1px solid #E4E0D4; padding-bottom:8px; }}
  .dot {{ width:11px; height:11px; border-radius:2px; display:inline-block; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:16px; }}
  figure {{ margin:0; border:1px solid #ECE8DC; border-radius:8px; overflow:hidden; background:#fff; }}
  figure img {{ width:100%; display:block; }}
  footer {{ color:var(--gris); font-size:12px; border-top:1px solid #E4E0D4;
    padding-top:14px; margin-top:20px; }}
  footer code {{ background:#F0EDE3; padding:1px 5px; border-radius:3px; }}
</style></head>
<body><div class="wrap">
  <header>
    <h1>Monitor de coyuntura · Argentina</h1>
    <div class="sub">Actualizado {ahora} · fuentes: apis.datos.gob.ar · ArgentinaDatos · BCRA</div>
  </header>

  <div class="tablero">{tablero}</div>

  {bloques_html}

  <footer>
    En las tarjetas, la variación es respecto de la observación anterior de cada serie
    (rojo = suba, verde = baja; los colores están pensados para inflación/dólar, no implican
    juicio de valor). Para agregar indicadores, editá <code>config/indicadores.yaml</code>.
  </footer>
</div></body></html>"""

    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(html, encoding="utf-8")

"""Home del sitio (Bloque E2, diseño aprobado por Pedro el 07/11/2026): docs/index.html, más la página
"Acerca" (docs/acerca/index.html).

Nada se recalcula: los datos clave toman valor y variación de la MISMA card que muestra su tema (las
cards que devuelve dashboard.generar); la línea de frescura y el mini gráfico son los de la serie que
resume esa card (dashboard._serie_resumen), sin las otras series de una card combinada. El EMAE general (decisión D3) no tiene card: se le aplica la misma
función de la card (dashboard._completar_card / _linea_frescura) sin registrarlo en la agenda del mail.
La franja Hoy / Esta semana y los datos demorados salen de la agenda (agenda.armar), igual que el mail
y el calendario.

Las anclas del dashboard viejo (index.html#precios, ..., las de los mails ya enviados) se redirigen a la
página de tema que corresponde (sitio.REDIRECCION_ANCLAS); #nota-N queda en la home.
"""
from __future__ import annotations

import dataclasses
import json
from html import escape
from pathlib import Path

import pandas as pd

import dashboard
import frescura as F
import sitio
import titulares
from tema import TEMA

DOCS = Path(__file__).resolve().parent / "docs"
CHART_JS = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"
TITULO_SITIO = "Monitor de coyuntura · Argentina"

CSS = """
  .franja { background:var(--franja-fondo); margin-top:0; }
  .franja .wrap { display:flex; align-items:center; flex-wrap:wrap; gap:8px 26px; padding-top:10px; padding-bottom:10px; font-size:13px; }
  .f-lbl { font-size:10px; text-transform:uppercase; letter-spacing:.08em; color:var(--texto-3); margin-right:8px; }
  .f-sem { display:flex; flex-wrap:wrap; gap:6px 18px; align-items:center; }
  .f-pub b { color:var(--principal-1); } .f-pub span { color:var(--texto-3); }
  .f-sem .f-pub { display:inline-flex; align-items:center; gap:8px; }
  .f-tt { display:flex; flex-direction:column; line-height:1.25; } .f-tt b { color:var(--texto); font-weight:600; }
  .f-tt span { font-size:11px; }
  .f-cal { margin-left:auto; font-weight:600; }
  .h-sec { margin-top:30px; }
  .h-tit { display:flex; align-items:baseline; flex-wrap:wrap; gap:4px 12px; border-top:1px solid var(--texto); padding-top:8px; }
  .h-tit h2 { font-size:22px; margin:0; }
  .h-sub { font-size:12px; color:var(--texto-3); }
  .dkgrid { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); column-gap:40px; }
  a.dk { display:block; color:inherit; border-top:1px solid var(--linea); padding:14px 0 16px; min-width:0; }
  a.dk:hover { text-decoration:none; } a.dk:hover .dk-n { color:var(--principal-2); }
  .dk-n { font-size:13px; font-weight:700; }
  .dk-v { display:flex; align-items:baseline; gap:6px; margin-top:4px; flex-wrap:wrap; }
  .dk-v .cv { font-size:26px; font-weight:700; color:var(--principal-1); font-variant-numeric:tabular-nums; letter-spacing:-.01em; }
  .dk-v .uni { font-size:12px; color:var(--texto-2); }
  .chg { font-size:12px; color:var(--texto-2); font-variant-numeric:tabular-nums; } .chg .tri { font-size:10px; margin-right:3px; }
  .mbox { position:relative; height:64px; margin:8px 0 6px; }
  .tmgrid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); column-gap:30px; }
  a.tm { display:block; color:inherit; border-top:1px solid var(--linea); padding:12px 0 18px; min-width:0; }
  a.tm:hover { text-decoration:none; } a.tm:hover b { color:var(--principal-2); }
  .tm-h { display:flex; justify-content:space-between; align-items:baseline; gap:8px; }
  .tm-h b { font-size:18px; } .tm-h span { font-size:11px; color:var(--texto-3); white-space:nowrap; }
  a.tm p { font-size:13px; color:var(--texto-2); margin:6px 0 0; line-height:1.4; }
  .ver { display:inline-block; font-size:13px; color:var(--principal-2); font-weight:600; margin-top:8px; }
  .avisos { list-style:none; padding:0; margin:8px 0; font-size:13px; color:var(--atrasado); }
  .avisos li { border-top:1px solid var(--linea); padding:6px 0; }
  .h-nada { font-size:13px; color:var(--texto-2); margin:8px 0; }
  @media (max-width:980px) { .tmgrid { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
  @media (max-width:760px) {
    .dkgrid { grid-template-columns:repeat(2, minmax(0, 1fr)); column-gap:18px; }
    .dk-v .cv { font-size:22px; }
    .f-cal { margin-left:0; }
    .h-tit h2 { font-size:19px; }
  }
  @media (max-width:420px) { .tmgrid { grid-template-columns:minmax(0, 1fr); } }
"""

JS_MINIS = """
const T = __TEMA__, MINIS = __MINIS__;
const esPP = u => u === 'p.p.' || u === 'pp';
const esPct = u => !!u && (u.includes('%') || esPP(u));
function decDe(u, v) {
  if (esPct(u)) return esPP(u) ? 2 : 1;
  if (u && /millones|miles|puntos/.test(u)) return 0;
  const a = Math.abs(v || 0); return a >= 1000 ? 0 : a >= 10 ? 1 : 2;
}
const fmt = (v, u) => v == null ? 's/d' : v.toLocaleString('es-AR', {minimumFractionDigits:decDe(u, v), maximumFractionDigits:decDe(u, v)}).replace('-', '−');
document.querySelectorAll('canvas[data-mini]').forEach(cv => {
  const m = MINIS[cv.dataset.mini]; if (!m) return;
  const n = m.y.length;
  const ds = m.bar
    ? { data:m.y, backgroundColor:m.y.map(v => v != null && v < 0 ? T.negativo : T.principal_1), borderRadius:1, barPercentage:.8, categoryPercentage:.9 }
    : { data:m.y, borderColor:T.principal_1, borderWidth:1.75, tension:0, spanGaps:false,
        pointRadius:m.y.map((v, k) => k === n - 1 ? 2.5 : 0), pointBackgroundColor:T.principal_1, pointHoverRadius:3 };
  new Chart(cv, { type:m.bar ? 'bar' : 'line', data:{ labels:m.x, datasets:[ds] },
    options:{ responsive:true, maintainAspectRatio:false, animation:false,
      interaction:{ mode:'index', intersect:false },
      layout:{ padding:{ top:3, right:4, bottom:1, left:1 } },
      scales:{ x:{ display:false }, y:{ display:false, grace:'4%' } },
      plugins:{ legend:{ display:false }, tooltip:{ displayColors:false, backgroundColor:'#FFFFFF', borderColor:T.principal_contexto,
        borderWidth:1, titleColor:T.texto, bodyColor:T.texto_2, padding:6, cornerRadius:2,
        callbacks:{ label:c => fmt(c.raw, m.u) + ' ' + m.u } } } } });
});
"""


def js_redireccion() -> str:
    """Anclas del dashboard viejo -> página de tema (mails ya enviados); #nota-N queda en la home."""
    return sitio.js_anclas(sitio.REDIRECCION_ANCLAS)


# ------------------------------------------------------------------------------------------------
# Datos
# ------------------------------------------------------------------------------------------------
def _mini(historico: pd.DataFrame, nombre: str, unidad: str, barras: bool) -> dict | None:
    """Últimos 12 meses de una serie diaria, 24 datos de una mensual, 12 de una trimestral."""
    g = historico[historico["indicador"] == nombre].sort_values("fecha")
    s = pd.Series(g["valor"].values, index=pd.to_datetime(g["fecha"].values)).dropna()
    if len(s) < 2:
        return None
    freq = titulares.frecuencia(s.index)
    if freq == "diaria":
        s = s[s.index >= s.index[-1] - pd.DateOffset(years=1)]
        x = [d.strftime("%d/%m/%y") for d in s.index]
    else:
        s = s.tail(24 if freq == "mensual" else 12)
        x = ([f"{F.MESES_CORTOS[d.month - 1]}-{str(d.year)[2:]}" for d in s.index] if freq == "mensual"
             else [f"{(d.month - 1) // 3 + 1}T-{str(d.year)[2:]}" for d in s.index])
    return {"x": x, "y": [round(float(v), 2) for v in s.values], "u": unidad, "bar": bool(barras)}


def _frescura_resumen(historico: pd.DataFrame, nombre: str, cfg: dict, ctx: F.Contexto | None) -> str:
    """Línea de frescura SÓLO de la serie que resume la card (decisión de Pedro: en la home no van las
    líneas de las otras series de una card combinada; quedan en la página del tema). No se registra en la
    agenda del mail."""
    if ctx is None:
        return ""
    fechas = historico.loc[historico["indicador"] == nombre, "fecha"]
    return F.html_card([(nombre, F.calcular(cfg, nombre, fechas, ctx))], nombre)


def armar_datos_clave(datos_clave: list[dict], cards: dict[str, dict], tema_de: dict[str, str],
                      historico: pd.DataFrame, indicadores: list[dict], ctx: F.Contexto | None) -> list[dict]:
    """Un dict por dato clave: etiqueta, valor, unidad, cambio, frescura (HTML), href, mini.
    `cards`: {nombre: card} de todas las páginas de tema; `tema_de`: {ítem: slug del tema}."""
    por_nombre = {i["nombre"]: i for i in indicadores}
    out = []
    for d in datos_clave:
        if d.get("card"):
            c = cards.get(d["card"])
            ind = por_nombre.get(d["card"])
            if c is None or ind is None:
                print(f"::warning title=Home::el dato clave '{d['card']}' no tiene card en esta corrida")
                continue
            resumen = dashboard._serie_resumen(ind)
            unidad = por_nombre.get(resumen, ind).get("unidad", c.get("unidad", ""))
            href = f'serie/{c.get("slug", "")}/'
            item = dict(etiqueta=d.get("etiqueta", d["card"]), valor=c.get("valor"), unidad=unidad,
                        cambio=c.get("cambio"), frescura=_frescura_resumen(historico, resumen, por_nombre.get(resumen, ind), ctx),
                        href=href)
            barras = ind.get("barras") or por_nombre.get(resumen, {}).get("barras")
        else:
            ind = por_nombre.get(d["serie"])
            if ind is None or historico[historico["indicador"] == d["serie"]].empty:
                print(f"::warning title=Home::el dato clave '{d['serie']}' no tiene datos en esta corrida")
                continue
            # Misma función que una card, sin registrarlo en la agenda del mail (registro descartable).
            ctx_local = dataclasses.replace(ctx, registro={}) if ctx is not None else None
            fr, grave = dashboard._linea_frescura(ind, historico, ctx_local, por_nombre)
            card = {"unidad": ind.get("unidad", "")}
            anio = ctx.ahora.year if ctx is not None else pd.Timestamp.now(tz="America/Argentina/Buenos_Aires").year
            dashboard._completar_card(card, ind, historico, por_nombre, grave, True, anio)
            resumen, unidad = d["serie"], ind.get("unidad", "")
            item = dict(etiqueta=d.get("etiqueta", d["serie"]), valor=card.get("valor"), unidad=unidad,
                        cambio=card.get("cambio"), frescura=fr, href=f'{d.get("tema", "")}/')
            barras = ind.get("barras")
        item["mini"] = _mini(historico, resumen, unidad, barras)
        out.append(item)
    return out


def resumen_temas(temas: list[dict], cards: dict[str, dict]) -> list[dict]:
    """Por tema: slug, titulo, cantidad de cards y hasta 2 titulares por reglas (o nombres, si no hay)."""
    out = []
    for t in temas:
        cs = [cards[it] for s in t["secciones"] for it in s["items"] if it in cards]
        tits = [c["titular"] for c in cs if c.get("titular") and c["titular"] != c["nombre"]][:2]
        out.append(dict(slug=t["slug"], titulo=t["titulo"], n=len(cs), titulares=tits or [c["nombre"] for c in cs][:2]))
    return out


# ------------------------------------------------------------------------------------------------
# HTML
# ------------------------------------------------------------------------------------------------
def _chg(c: dict | None) -> str:
    if not c:
        return ""
    tri = {1: "▲", -1: "▼"}.get(c["signo"], "•")
    return f'<span class="chg"><span class="tri">{tri}</span>{escape(c["texto"])} vs. {escape(c["ref"])}</span>'


def _tile_dia(dia: str) -> str:
    """"jue 12/11" (agenda, sin tocar su formato) -> estampilla de fecha (E5, variante C)."""
    try:
        sem, ddmm = dia.split()
        d, m = (int(x) for x in ddmm.split("/"))
        return sitio.tile(sem, d, dashboard._MESES_ABREV_C[m])
    except (ValueError, IndexError):
        return f"<span>{escape(dia)}</span>"


def _franja(agenda: dict | None) -> str:
    cal = (agenda or {}).get("calendario") or {}
    if not agenda or cal.get("estado") == "no_disponible":
        cont = '<span>Calendario del INDEC no disponible hoy.</span>'
    else:
        if cal.get("hoy"):
            hoy = " · ".join(f'<span class="f-pub"><b>{escape(i["titulo"])}</b> <span>{escape(i["hora"])}</span></span>'
                             for i in cal["hoy"])
        elif cal.get("feriado_hoy"):
            hoy = f'feriado ({escape(cal["feriado_hoy"])})'
        else:
            hoy = "no se publica nada de lo que usa el monitor"
        sem = "".join(f'<span class="f-pub">{_tile_dia(d["dia"])}<span class="f-tt"><b>{escape(", ".join(d["titulos"]))}</b>'
                      f'<span>INDEC · {escape(d["hora"])}</span></span></span>' for d in cal.get("semana", []))
        cont = (f'<span><span class="f-lbl">Hoy</span>{hoy}</span>'
                f'<span class="f-sem"><span class="f-lbl">Esta semana</span>{sem or "sin publicaciones del INDEC que use el monitor"}</span>')
    return f'<div class="franja"><div class="wrap">{cont}<a class="f-cal" href="calendario/">Calendario →</a></div></div>'


def html(datos: list[dict], temas_res: list[dict], agenda: dict | None, ahora_txt: str, temas_nav=None) -> str:
    minis, tiles = {}, ""
    for k, d in enumerate(datos):
        if d.get("mini"):
            minis[str(k)] = d["mini"]
        canvas = f'<div class="mbox"><canvas data-mini="{k}" aria-label="{escape(d["etiqueta"])}"></canvas></div>' if d.get("mini") else ""
        tiles += (f'<a class="dk" href="{escape(d["href"])}"><div class="dk-n">{escape(d["etiqueta"])}</div>'
                  f'<div class="dk-v"><span class="cv">{escape(str(d["valor"]))}</span><span class="uni">{escape(d["unidad"])}</span></div>'
                  f'<div>{_chg(d.get("cambio"))}</div>{canvas}{d.get("frescura", "")}</a>')
    tms = "".join(f'<a class="tm" href="{t["slug"]}/"><div class="tm-h"><b>{escape(t["titulo"])}</b>'
                  f'<span>{t["n"]} {"serie" if t["n"] == 1 else "series"}</span></div>'
                  + "".join(f"<p>{escape(x)}</p>" for x in t["titulares"]) + '<span class="ver">Ver tema →</span></a>'
                  for t in temas_res)
    atr = (agenda or {}).get("atrasados", [])
    graves = (agenda or {}).get("graves", [])
    items_atr = "".join(f"<li>{escape(a['texto'])}</li>" for a in atr)
    demorados = f'<ul class="avisos">{items_atr}</ul>' if atr else ""
    if graves:
        n = len(graves)
        demorados += (f'<p class="h-nada">{"Una serie" if n == 1 else f"{n} series"} sin datos nuevos de la fuente hace más de '
                      f'3 meses. <a href="calendario/#demorados">Ver {"cuál" if n == 1 else "cuáles"} →</a></p>')
    if not demorados:
        demorados = '<p class="h-nada">No hay datos demorados.</p>'
    cuerpo = f"""
<section class="h-sec"><div class="h-tit"><h2>Datos clave</h2><span class="h-sub">el último dato de cada uno, con su período y cuándo llega el próximo</span></div>
<div class="dkgrid">{tiles}</div></section>
<section class="h-sec"><div class="h-tit"><h2>Temas</h2></div><div class="tmgrid">{tms}</div></section>
<section class="h-sec"><div class="h-tit"><h2>Datos demorados</h2><span class="h-sub">los mismos avisos que el calendario</span></div>
{demorados}</section>"""
    js = (JS_MINIS.replace("__TEMA__", json.dumps(TEMA, ensure_ascii=False))
          .replace("__MINIS__", json.dumps(minis, ensure_ascii=False)))
    pagina = sitio.pagina(TITULO_SITIO, TITULO_SITIO,
                          f"Actualizado {escape(ahora_txt)} · datos públicos, actualizados cada día hábil",
                          sitio.nav_sitio("", "Inicio", temas_nav), cuerpo, css=CSS, js=js,
                          pie=sitio.pie_sitio("", "Gráficos interactivos: pasá el cursor (o tocá) para ver cada valor."),
                          inicio="./", head=js_redireccion() + f'\n<script src="{CHART_JS}"></script>')
    # la franja Hoy / Esta semana va pegada debajo del nav, a todo el ancho
    return pagina.replace("</nav>\n<main", f"</nav>\n{_franja(agenda)}\n<main", 1)


def generar(datos, temas_res, agenda, ahora_txt, temas_nav=None, ruta: Path = DOCS / "index.html") -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(html(datos, temas_res, agenda, ahora_txt, temas_nav), encoding="utf-8")
    return ruta


# ------------------------------------------------------------------------------------------------
# Acerca
# ------------------------------------------------------------------------------------------------
CSS_ACERCA = """
  article.acerca { max-width:760px; }
  article.acerca h2 { font-size:19px; margin:26px 0 6px; padding-top:8px; border-top:1px solid var(--texto); }
  article.acerca p { font-size:15px; margin:6px 0; }
  ul.lee { list-style:none; padding:0; margin:8px 0; }
  ul.lee li { display:grid; grid-template-columns:minmax(0, 3fr) minmax(0, 2fr); gap:18px; border-top:1px solid var(--linea); padding:8px 0; font-size:14px; }
  ul.lee li > span:last-child { color:var(--texto-2); font-size:13px; }
  .sw-p, .sw-n { display:inline-block; width:10px; height:10px; margin-right:4px; vertical-align:-1px; }
  .sw-p { background:var(--principal-1); } .sw-n { background:var(--negativo); }
  @media (max-width:760px) { ul.lee li { grid-template-columns:minmax(0, 1fr); gap:4px; } }
"""


def html_acerca(ahora_txt: str, temas_nav=None) -> str:
    cuerpo = f"""<article class="acerca">
<h2 style="border:0;font-size:26px">Acerca del monitor</h2>
<p>Un monitor de la coyuntura económica argentina hecho con datos públicos. Se actualiza solo cada día hábil.
Proyecto iniciado el <a href="{sitio.URL_REPO}/commit/{sitio.PRIMER_COMMIT}">9 de julio de 2026</a>.</p>
<h2>Qué es</h2>
<p>Reúne en un solo lugar los indicadores que se publican por separado: precios, actividad, empleo y salarios, dólar y
reservas, dinero y crédito, sector externo, fiscal y deuda, y mercados. Cada gráfico lleva su nota metodológica y el link a la fuente.</p>
<h2>De dónde salen los datos</h2>
<p>De fuentes oficiales y públicas, consultadas directamente: la API del INDEC (con datos.gob.ar o ArgentinaDatos como
respaldo), apis.datos.gob.ar, la API del BCRA y sus planillas, el Ministerio de Economía (deuda pública), BYMA, el Mercado
Abierto Electrónico y FRED (Reserva Federal). Cuando un dato se calcula o se aproxima (por ejemplo, el spread soberano o las
reservas ajustadas), el gráfico lo dice en el rótulo y en su nota con asterisco.</p>
<h2 id="leer">Cómo leer cada dato</h2>
<ul class="lee">
 <li><span><b>El titular</b> lo arma una regla fija a partir del dato. No lo escribe una persona ni una IA.</span><span>“La inflación mensual sube a 1,9% en septiembre”</span></li>
 <li><span><b>La variación</b> compara contra el mismo período del año anterior, salvo las series diarias, la inflación mensual y las series que ya son interanuales, que comparan contra el dato anterior.</span><span>▲ +0,2 pp vs. ago-26</span></li>
 <li><span><b>Al día</b>: el monitor ya tiene el último dato que publicó la fuente.</span><span><span class="cf"><span class="per">sep-26</span> · <span class="ok">✓ al día</span> · próximo 12/11, 16 h</span></span></li>
 <li><span><b>Publicado, todavía no incorporado</b>: la fuente lo publicó y entra en la próxima actualización.</span><span><span class="cf"><span class="per">sep-26</span> · oct-26 publicado el 12/11, entra en la próxima actualización</span></span></li>
 <li><span><b>Atrasado</b>: pasó más de un día hábil desde la publicación y el monitor todavía no lo muestra.</span><span><span class="cf"><span class="per">ago-26</span> · <span class="atr">⚠ atrasado</span> · sep-26 se publicó el 19/10</span></span></li>
 <li><span><b>Sin datos nuevos</b>: la fuente no publica hace más de tres meses.</span><span><span class="cf grave">⏸ may-26 · sin datos nuevos hace 5 meses</span></span></li>
 <li><span><b>Sin calendario oficial</b>: la fuente no anuncia fechas, y el monitor no las inventa. En las series diarias, “estimado” es el próximo día hábil.</span><span><span class="cf"><span class="per">ago-26</span> · próximo: sin calendario oficial</span></span></li>
 <li><span><b>Colores</b>: no juzgan si un dato es bueno o malo. El color fuerte es la serie principal. El arena marca sólo los valores negativos.</span><span><span class="sw-p"></span>serie principal &nbsp; <span class="sw-n"></span>valor negativo</span></li>
</ul>
<h2>Notas metodológicas</h2>
<p>Cada gráfico lleva un asterisco numerado que remite a su nota, al pie de su página: cómo se calcula, qué fuente usa,
desde cuándo y qué cambios de metodología tiene la serie.</p>
<h2>Calendario</h2>
<p>Las fechas de las publicaciones del INDEC salen de su <a href="../calendario/">calendario oficial</a> y se actualizan todos
los días. Son días no hábiles aquellos en que no operan el INDEC, el BCRA y BYMA.</p>
<h2>Quién lo hace</h2>
<p>Lo hace Pedro Thill. Es un proyecto personal, gratuito y automatizado. No es asesoramiento financiero ni una publicación
oficial. El <a href="{sitio.URL_REPO}">código es público en GitHub</a>.</p>
<p><b>Contacto:</b> <a href="#" class="mail">por mail</a> · <a href="{sitio.LINKEDIN}" rel="noopener">LinkedIn</a></p>
</article>"""
    return sitio.pagina(f"Acerca · {TITULO_SITIO}", TITULO_SITIO, f"Actualizado {escape(ahora_txt)}",
                        sitio.nav_sitio("../", "", temas_nav), cuerpo, css=CSS_ACERCA, pie=sitio.pie_sitio("../"))


def html_redireccion(destino: str) -> str:
    """Página mínima que manda a `destino` (relativo a docs/): meta refresh + location.replace, con link
    visible por si el navegador no redirige."""
    return (f'<!doctype html><html lang="es"><head><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0; url={destino}"><title>{TITULO_SITIO}</title>'
            f'<script>location.replace("{destino}");</script></head>'
            f'<body><p>Esta página se mudó: <a href="{destino}">{destino}</a></p></body></html>')


def generar_redireccion(archivo: str, destino: str) -> Path:
    ruta = DOCS / archivo
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(html_redireccion(destino), encoding="utf-8")
    return ruta


def generar_acerca(ahora_txt: str, temas_nav=None, ruta: Path = DOCS / "acerca" / "index.html") -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(html_acerca(ahora_txt, temas_nav), encoding="utf-8")
    return ruta

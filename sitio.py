"""Armazón común de las páginas nuevas del sitio (Bloque E de organización): cabecera, navegación, pie
y estilos base, todo con los colores y la tipografía de tema.py.

Lo usan el calendario (E1), la home y la página "Acerca" (E2); las páginas de tema (dashboard.py) toman de
acá la navegación y el pie. La identidad (E5: serif + ciruela + sello) está
en CSS_IDENTIDAD, con las variables de tema.py: acá no hay colores fijos.
"""
from __future__ import annotations

import re
from html import escape

from tema import TEMA


def css_variables() -> str:
    """Las mismas variables CSS que el template de dashboard.py (--principal-1, --texto-2, ...)."""
    return "\n".join(f"    --{k.replace('_', '-')}: {v};" for k, v in TEMA.items() if k != "fuente")


CSS_BASE = """
  * { box-sizing:border-box; }
  html { scroll-behavior:smooth; }
  body { margin:0; background:var(--fondo); color:var(--texto); font-family:__FUENTE__; line-height:1.45; -webkit-font-smoothing:antialiased; }
  a { color:var(--principal-2); text-decoration:none; } a:hover { text-decoration:underline; }
  .wrap { max-width:1180px; margin:0 auto; padding:0 32px; }
  main.wrap { padding-bottom:60px; }
  header.masthead { border-top:4px solid var(--principal-1); padding:26px 0 16px; }
  header h1 { font-size:30px; line-height:1.15; margin:0; font-weight:700; letter-spacing:-.01em; }
  header h1 a { color:inherit; }
  header .sub { font-size:14px; color:var(--texto-2); margin-top:6px; }
  nav.secciones { position:sticky; top:0; z-index:20; background:var(--fondo); border-bottom:1px solid var(--linea); }
  nav.secciones .wrap { display:flex; align-items:center; gap:22px; overflow-x:auto; scrollbar-width:none; }
  nav.secciones .wrap::-webkit-scrollbar { display:none; }
  nav.secciones a { flex:none; font-size:14px; color:var(--texto-2); padding:12px 0 10px; border-bottom:3px solid transparent; }
  nav.secciones a.activo { color:var(--texto); font-weight:700; border-bottom-color:var(--principal-1); }
  nav.secciones a:hover { color:var(--texto); text-decoration:none; }
  h3.grupo { font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--texto-3); font-weight:700;
    margin:30px 0 4px; padding-top:8px; border-top:1px solid var(--texto); }
  .bajada { font-size:14px; color:var(--texto-2); margin:6px 0 0; max-width:820px; }
  .tabla { width:100%; border-collapse:collapse; font-size:13px; font-variant-numeric:tabular-nums; }
  .tabla th { text-align:left; color:var(--texto-3); font-weight:600; font-size:11px; text-transform:uppercase;
    letter-spacing:.04em; padding:6px 8px; border-bottom:1px solid var(--texto); }
  .tabla td { padding:7px 8px; border-bottom:1px solid var(--linea); vertical-align:top; }
  /* Línea de frescura (Bloque B2): mismas reglas que en dashboard.py. */
  .cf { font-size:11px; color:var(--texto-3); line-height:1.35; }
  .cf .per { color:var(--texto-2); font-weight:600; }
  .cf .ok { color:var(--principal-2); font-weight:600; }
  .cf .atr { color:var(--atrasado); font-weight:700; }
  .cf.grave { color:var(--atrasado); background:var(--franja-fondo); border-left:3px solid var(--franja-borde);
    padding:4px 8px; border-radius:0 4px 4px 0; }
  footer.pie { margin-top:40px; padding-top:12px; border-top:1px solid var(--texto); font-size:11px; color:var(--texto-3); }
  @media (max-width:760px) {
    .wrap { padding:0 16px; }
    header.masthead { padding:18px 0 12px; }
    header h1 { font-size:23px; }
    header .sub { font-size:13px; }
    nav.secciones a { font-size:13px; }
  }
"""


# Identidad del sitio (Bloque E5, variante A+B+C aprobada por Pedro): A = cabecera, títulos y titulares en
# serif (`fuente_titulares` de tema.py); B = banda ciruela (`principal_1`) en la cabecera y el pie; C = la
# frescura y el calendario como sello (estampilla de la card, frescura.html_sello, y estampillas de fecha,
# tile()). Va al final del <style> de TODAS las páginas (sitio.pagina y la plantilla de dashboard.py), así
# que pisa lo anterior. Los colores salen de las variables de tema.py: acá no hay ningún hex de la paleta.
CSS_IDENTIDAD = """
  /* --- E5 · A+B: cabecera ciruela con título en serif y filete doble --- */
  header.masthead { background:var(--principal-1); color:#fff; border-top:0; padding:22px 0 14px; text-align:center; }
  header.masthead .wrap { padding-bottom:12px; border-bottom:3px double rgba(255,255,255,.65); }
  header.masthead h1 { font-family:var(--fuente-titulares); font-size:38px; letter-spacing:-.005em; color:#fff; }
  header.masthead h1 a { color:#fff; } header.masthead h1 a:hover { text-decoration:none; }
  header.masthead .sub { color:rgba(255,255,255,.82); }
  header.masthead .sub a { color:#fff; }
  @media (min-width:1100px) { nav.secciones .wrap { justify-content:center; } }
  /* --- E5 · A: titulares y títulos de página en serif; kickers, valores y datos siguen en sans --- */
  .ct, .s-tit, section.bloque > h2, .h-tit h2, .tm-h b, .cal-h2, .acerca h2, .acerca h3 {
    font-family:var(--fuente-titulares); letter-spacing:0; }
  .ct { font-weight:700; }
  /* --- E5 · B: pie ciruela a todo el ancho (sin scroll horizontal: box-shadow + clip-path) --- */
  main.wrap { padding-bottom:0; }
  footer, footer.pie { background:var(--principal-1); color:rgba(255,255,255,.85); border-top:0; margin-top:48px;
    padding:18px 0 22px; box-shadow:0 0 0 100vmax var(--principal-1); clip-path:inset(0 -100vmax); font-size:12px; }
  footer a, footer.pie a { color:#fff; text-decoration:underline; text-decoration-color:rgba(255,255,255,.45); }
  /* --- E5 · C: estampillas de fecha (franja Hoy/Esta semana de la home y calendario) --- */
  .tile { display:inline-flex; flex-direction:column; align-items:center; justify-content:center; width:40px; flex:none;
    border:1px solid var(--principal-1); background:var(--fondo); color:var(--principal-1); line-height:1; padding:3px 0 4px; }
  .tile-d { font-size:9px; text-transform:uppercase; letter-spacing:.06em; }
  .tile-n { font-size:16px; font-weight:700; margin:2px 0 1px; }
  .tile-m { font-size:9px; text-transform:uppercase; color:var(--texto-3); }
  /* --- E5 · C: sello de frescura en la card del tema (mismo código que la línea del B2: borde lleno = al
     día, punteado = atrasado, gris con fondo = sin datos nuevos, gris claro = sin calendario) --- */
  .cc-cab { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
  .cc-tx { min-width:0; }
  a.cc.con-sello > .cf:not(.grave) { display:none; }   /* la línea completa sigue en la página de la serie */
  .sello { flex:none; display:flex; flex-direction:column; align-items:flex-end; width:max-content; max-width:118px;
    border:1px solid var(--principal-1); background:var(--fondo); padding:3px 6px 4px; font-size:10px; line-height:1.25; text-align:right; }
  .sello .se-per { font-size:13px; font-weight:700; color:var(--principal-1); letter-spacing:.02em; }
  .sello .se-est { color:var(--principal-2); font-weight:700; text-transform:uppercase; letter-spacing:.05em; font-size:9px; }
  .sello .se-det { color:var(--texto-3); }
  .sello-atr { border-style:dashed; border-color:var(--atrasado); } .sello-atr .se-est { color:var(--atrasado); }
  .sello-grave { border-color:var(--franja-borde); background:var(--franja-fondo); }
  .sello-grave .se-per, .sello-grave .se-est { color:var(--atrasado); }
  .sello-neutro { border-color:var(--linea); } .sello-neutro .se-per { color:var(--texto-2); }
  .s-prox { background:var(--fondo); border:1px solid var(--principal-1); }
  @media (max-width:760px) {
    header.masthead { padding:16px 0 10px; }
    header.masthead h1 { font-size:27px; }
  }
"""


def tile(dia: str, numero: int | str, mes: str) -> str:
    """Estampilla de fecha (E5, variante C): día de la semana / número / mes."""
    return (f'<span class="tile"><span class="tile-d">{escape(dia)}</span><span class="tile-n">{numero}</span>'
            f'<span class="tile-m">{escape(mes)}</span></span>')


URL_REPO = "https://github.com/PedroTh31/Coyuntura-Pedro-Thill"
PRIMER_COMMIT = "730dd39"           # 9 de julio de 2026 (git log --reverse)
LINKEDIN = "https://www.linkedin.com/in/pedro-thill-286076218/"
# Mail de contacto OFUSCADO (pedido de Pedro: nunca completo en el HTML). Va en dos partes invertidas;
# el JS lo arma recién al hacer click. Ver JS_MAIL.
_MAIL_U, _MAIL_D = "pedrothill31"[::-1], "gmail.com"[::-1]

# (título, carpeta) de las 8 páginas de tema, en el orden del nav. Lo completa run.py desde el bloque
# `temas:` de indicadores.yaml (temas.py); este default es el mismo orden, para tests y para el calendario.
TEMAS_NAV = [("Precios", "precios"), ("Actividad", "actividad"), ("Empleo y salarios", "empleo-y-salarios"),
             ("Dólar y reservas", "dolar-y-reservas"), ("Dinero y crédito", "dinero-y-credito"),
             ("Sector externo", "sector-externo"), ("Fiscal y deuda", "fiscal-y-deuda"), ("Mercados", "mercados")]

# Anclas del dashboard viejo (index.html#<bloque>, las usan los mails ya enviados) -> página de tema.
REDIRECCION_ANCLAS = {"precios": "precios/", "monetario_financiero": "dolar-y-reservas/", "externo": "sector-externo/",
                      "real": "actividad/", "social": "empleo-y-salarios/", "fiscal": "fiscal-y-deuda/",
                      "mercados": "mercados/"}


def slug(nombre: str, ind: dict | None = None) -> str:
    """Slug de URL/ancla de una card (D7): sale del nombre, sin lo que va entre paréntesis; `slug:` en el
    yaml lo congela si un día se renombra la card."""
    if ind and ind.get("slug"):
        return ind["slug"]
    s = nombre.lower()
    for a, b in zip("áéíóúñü", "aeiounu"):
        s = s.replace(a, b)
    s = re.sub(r"\(.*?\)", "", s)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60]


def nav_sitio(raiz: str, activo: str, temas_nav=None) -> str:
    """Inicio · Calendario · los 8 temas. `raiz`: ruta relativa a docs/ desde la página ("" o "../")."""
    items = [("Inicio", raiz or "./"), ("Calendario", f"{raiz}calendario/")]
    items += [(t, f"{raiz}{c}/") for t, c in (temas_nav or TEMAS_NAV)]
    return nav(items, activo)


JS_MAIL = (f"document.querySelectorAll('a.mail').forEach(a=>a.addEventListener('click',e=>{{e.preventDefault();"
           f"const r=x=>x.split('').reverse().join('');location.href='mailto:'+r('{_MAIL_U}')+'@'+r('{_MAIL_D}');}}));")


def pie_sitio(raiz: str, extra: str = "") -> str:
    """Pie común: fecha de inicio del proyecto con link al primer commit, contacto (mail ofuscado y
    LinkedIn) y Acerca. `extra`: texto propio de la página, antes."""
    return (f'{extra}{"<br>" if extra else ""}'
            f'Monitor de coyuntura · Argentina. Proyecto iniciado el '
            f'<a href="{URL_REPO}/commit/{PRIMER_COMMIT}">9 de julio de 2026</a>. '
            f'<a href="{raiz}acerca/">Acerca del monitor</a> · Contacto: '
            f'<a href="#" class="mail">mail</a> · <a href="{LINKEDIN}" rel="noopener">LinkedIn</a>'
            f'<script>{JS_MAIL}</script>')


def nav(items: list[tuple[str, str]], activo: str) -> str:
    """items: [(texto, href)]."""
    activa = ' class="activo"'
    return "".join(f'<a href="{escape(h)}"{activa if t == activo else ""}>{escape(t)}</a>' for t, h in items)


def pagina(titulo: str, titulo_sitio: str, sub: str, nav_html: str, cuerpo: str, css: str = "", js: str = "",
           pie: str = "", inicio: str = "../", head: str = "") -> str:
    fuente_css = '"Helvetica Neue", ' + TEMA["fuente"]
    return f"""<!doctype html><html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titulo)}</title>{head}
<style>
  :root {{
{css_variables()}
    --linea:#E3E8ED;
  }}
{CSS_BASE.replace("__FUENTE__", fuente_css)}
{css}
{CSS_IDENTIDAD}
</style></head>
<body>
<header class="masthead"><div class="wrap">
  <h1><a href="{inicio}">{escape(titulo_sitio)}</a></h1>
  <div class="sub">{sub}</div>
</div></header>
<nav class="secciones"><div class="wrap">{nav_html}</div></nav>
<main class="wrap">
{cuerpo}
<footer class="pie">{pie}</footer>
</main>
{f"<script>{js}</script>" if js else ""}
</body></html>
"""

"""Armazón común de las páginas nuevas del sitio (Bloque E de organización): cabecera, navegación, pie
y estilos base, todo con los colores y la tipografía de tema.py.

E1 lo usa sólo la página del calendario (docs/calendario/index.html). En E2-E4 lo van a usar también la
home, las páginas de tema y las de serie, y el CSS/JS compartido pasa a docs/assets/. La identidad
aprobada (serif + ciruela + sello) se aplica recién en E5, cambiando tema.py: acá no hay colores fijos.
"""
from __future__ import annotations

from html import escape

from tema import TEMA


def css_variables() -> str:
    """Las mismas variables CSS que el template de dashboard.py (--azul-1, --texto-2, ...)."""
    return "\n".join(f"    --{k.replace('_', '-')}: {v};" for k, v in TEMA.items() if k != "fuente")


CSS_BASE = """
  * { box-sizing:border-box; }
  html { scroll-behavior:smooth; }
  body { margin:0; background:var(--fondo); color:var(--texto); font-family:__FUENTE__; line-height:1.45; -webkit-font-smoothing:antialiased; }
  a { color:var(--azul-2); text-decoration:none; } a:hover { text-decoration:underline; }
  .wrap { max-width:1180px; margin:0 auto; padding:0 32px; }
  main.wrap { padding-bottom:60px; }
  header.masthead { border-top:4px solid var(--azul-1); padding:26px 0 16px; }
  header h1 { font-size:30px; line-height:1.15; margin:0; font-weight:700; letter-spacing:-.01em; }
  header h1 a { color:inherit; }
  header .sub { font-size:14px; color:var(--texto-2); margin-top:6px; }
  nav.secciones { position:sticky; top:0; z-index:20; background:var(--fondo); border-bottom:1px solid var(--linea); }
  nav.secciones .wrap { display:flex; align-items:center; gap:22px; overflow-x:auto; scrollbar-width:none; }
  nav.secciones .wrap::-webkit-scrollbar { display:none; }
  nav.secciones a { flex:none; font-size:14px; color:var(--texto-2); padding:12px 0 10px; border-bottom:3px solid transparent; }
  nav.secciones a.activo { color:var(--texto); font-weight:700; border-bottom-color:var(--azul-1); }
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
  .cf .ok { color:var(--azul-2); font-weight:600; }
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


def nav(items: list[tuple[str, str]], activo: str) -> str:
    """items: [(texto, href)]."""
    activa = ' class="activo"'
    return "".join(f'<a href="{escape(h)}"{activa if t == activo else ""}>{escape(t)}</a>' for t, h in items)


def pagina(titulo: str, titulo_sitio: str, sub: str, nav_html: str, cuerpo: str, css: str = "", js: str = "",
           pie: str = "", inicio: str = "../") -> str:
    fuente_css = '"Helvetica Neue", ' + TEMA["fuente"]
    return f"""<!doctype html><html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titulo)}</title>
<style>
  :root {{
{css_variables()}
    --linea:#E3E8ED;
  }}
{CSS_BASE.replace("__FUENTE__", fuente_css)}
{css}
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

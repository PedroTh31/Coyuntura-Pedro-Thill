"""
enviar_mail.py  ·  Arma y envía por Gmail un resumen diario (lun-vie):
  - indicadores clave con su variación de la semana
  - titulares económicos más relevantes (RSS público, gratis)

Necesita 3 variables de entorno (se cargan desde GitHub Secrets):
  GMAIL_USER           -> tu dirección de Gmail
  GMAIL_APP_PASSWORD   -> "contraseña de aplicación" de Google (no la común)
  MAIL_TO              -> a quién enviar (opcional; por defecto, a vos mismo)
"""
import os
import re
import ssl
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd
import yaml

RAIZ = Path(__file__).resolve().parent
CSV = RAIZ / "data" / "series_largo.csv"
CONFIG = RAIZ / "indicadores.yaml"
DASHBOARD_URL = "https://pedroth31.github.io/Coyuntura-Pedro-Thill/"   # editable
ZONA_AR = ZoneInfo("America/Argentina/Buenos_Aires")

# indicadores que van en el mail (deben coincidir con los nombres del config)
INDICADORES_MAIL = [
    "Dólar oficial", "Dólar blue", "Brecha cambiaria (CCL/oficial)",
    "Riesgo país (EMBI)", "Reservas internacionales (BCRA)",
    "Inflación mensual (IPC)", "Base monetaria", "Tasa BADLAR (mayorista)",
    "EMAE (actividad económica)", "Saldo comercial",
]

# feeds de medios argentinos que SÍ traen bajada (verificados con feedparser antes de sumarlos;
# si alguno cambia su URL más adelante, se ignora sin romper -- ver _recolectar)
FEEDS_MEDIOS = [
    "https://www.pagina12.com.ar/rss/secciones/economia/notas",
    "https://www.ambito.com/rss/economia.xml",
    "https://www.cronista.com/files/rss/economia.xml",
    "https://www.iprofesional.com/rss/economia.xml",
    "https://www.perfil.com/feed/economia",
    "https://www.infobae.com/arc/outboundfeeds/rss/category/economia/",
    "https://www.lanacion.com.ar/arc/outboundfeeds/rss/category/economia/",
    "https://www.clarin.com/rss/economia/",
    "https://www.bloomberglinea.com/arc/outboundfeeds/rss/category/economia/?outputType=xml",
]

# feeds internacionales ya acotados a economía/finanzas o geopolítica por su propia sección
# editorial -- no necesitan el filtro adicional de KW_INTERNACIONAL de más abajo
FEEDS_INTERNACIONAL = [
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://www.economist.com/finance-and-economics/rss.xml",
    "https://foreignpolicy.com/feed/",
    "https://www.foreignaffairs.com/rss.xml",
    "https://www.ft.com/global-economy?format=rss",
    "https://www.project-syndicate.org/rss",
    "https://www.france24.com/es/econom%C3%ADa/rss",
]

# feeds internacionales generalistas (traen de todo, no sólo economía/geopolítica): se
# incluyen igual porque tienen buena cobertura en español, pero cada nota debe matchear
# KW_INTERNACIONAL antes de entrar al mail (ver obtener_noticias)
FEEDS_INTERNACIONAL_GENERALISTA = [
    "http://feeds.bbci.co.uk/mundo/rss.xml",
    "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/economia/portada",
]

# si el título/copete contiene alguna de estas, se considera internacional/geopolítico:
# (a) saca una nota Argentina del bloque argentino si igual menciona esto, y
# (b) es el filtro de relevancia para las fuentes generalistas de arriba
KW_INTERNACIONAL = ["trump", "china", "ee.uu", "eeuu", "estados unidos", "wall street",
    "reserva federal", " fed ", "europa", "alemania", "japón", "brasil", "lula",
    "nvidia", "apple", "petróleo brent", "unión europea", "rusia", "israel", "bitcoin",
    "otan", "sanciones", "guerra comercial", "geopolític", "conflicto", "cumbre",
    "aranceles"]

# notas tipo "consejo/listicle" que no son noticia económica real (ej. "cómo pagar
# reservas de hotel en dólares"): filtro heurístico, ajustar según lo que se cuele
KW_EXCLUIR_TIPS = [
    "la mejor forma de", "cómo pagar", "cómo ahorrar", "consejos para",
    "trucos para", "paso a paso para", "todo lo que tenés que saber para",
    "todo lo que necesitás saber para", "cuidar tu bolsillo",
]
_RE_LISTICLE = re.compile(r"^\d+\s+(formas?|tips?|claves?|trucos?|maneras?)\s+", re.I)


def _limpiar(texto):
    """Saca etiquetas HTML y espacios sobrantes de una bajada, y la recorta."""
    import html as _html
    if not texto:
        return ""
    t = re.sub(r"<[^>]+>", " ", texto)
    t = _html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > 220:
        t = t[:220].rsplit(" ", 1)[0] + "…"
    return t


def _es_internacional(texto):
    t = " " + texto.lower() + " "
    return any(k in t for k in KW_INTERNACIONAL)


def _es_tip(titulo):
    """Filtra notas tipo consejo/listicle que no son noticia económica real."""
    t = titulo.lower().strip()
    if _RE_LISTICLE.match(t):
        return True
    return any(k in t for k in KW_EXCLUIR_TIPS)


def _limite(es_argentina):
    """Ventana de tiempo por categoría: Argentina 1-2 días (lunes cubre el fin de
    semana), internacional hasta 7 días (menos volumen de fuentes, más colchón)."""
    hoy_ar = datetime.now(ZONA_AR)
    if es_argentina:
        dias = 3 if hoy_ar.weekday() == 0 else 1   # lunes=0
    else:
        dias = 7
    return hoy_ar.replace(tzinfo=None) - timedelta(days=dias)


def _recolectar(feeds, es_argentina):
    """Junta notas de una lista de feeds RSS directos, con bajada y fecha."""
    import feedparser
    limite = _limite(es_argentina)
    vistos, items = set(), []

    def procesar(feed):
        for e in getattr(feed, "entries", []):
            t = getattr(e, "title", "").strip()
            if not t or t in vistos:
                continue
            try:
                pub = datetime(*e.published_parsed[:6])
            except Exception:
                pub = datetime.now()
            if pub < limite:
                continue
            bajada = _limpiar(getattr(e, "summary", "") or getattr(e, "description", ""))
            if bajada.lower().startswith(t.lower()[:25]) or len(bajada) < 40:
                bajada = ""
            fuente = ""
            src = getattr(e, "source", None)
            if src is not None:
                fuente = getattr(src, "title", "") or (src.get("title", "") if isinstance(src, dict) else "")
            vistos.add(t)
            items.append(dict(titulo=t, link=getattr(e, "link", "#"),
                              fuente=fuente, bajada=bajada, pub=pub))

    for url in feeds:
        try:
            procesar(feedparser.parse(url))
        except Exception:
            continue

    items.sort(key=lambda x: (x["bajada"] == "", -x["pub"].timestamp()))
    return items


def obtener_noticias(n=6):
    """Devuelve (argentinas, internacionales), n de cada una."""
    try:
        import feedparser  # noqa: F401
    except Exception:
        return [], []
    arg = [x for x in _recolectar(FEEDS_MEDIOS, es_argentina=True)
           if not _es_internacional(x["titulo"]) and not _es_tip(x["titulo"])]
    arg = arg[:n]
    titulos_arg = {x["titulo"] for x in arg}

    crudo_intl = _recolectar(FEEDS_INTERNACIONAL, es_argentina=False)
    crudo_generalista = [x for x in _recolectar(FEEDS_INTERNACIONAL_GENERALISTA, es_argentina=False)
                         if _es_internacional(x["titulo"] + " " + x["bajada"])]
    intl = [x for x in crudo_intl + crudo_generalista
            if x["titulo"] not in titulos_arg and not _es_tip(x["titulo"])]
    intl.sort(key=lambda x: (x["bajada"] == "", -x["pub"].timestamp()))
    intl = intl[:n]
    return arg, intl


def _fmt(v):
    if v is None or pd.isna(v):
        return "s/d"
    if abs(v) >= 1000:
        return f"{v:,.0f}".replace(",", ".")
    s = f"{v:,.1f}" if abs(v) >= 10 else f"{v:,.2f}"
    return s.replace(",", "@").replace(".", ",").replace("@", ".")


def _cargar_sube_es_bueno():
    """Mismo criterio que dashboard.py: por defecto subir = malo (rojo), salvo que el
    indicador declare 'sube_es_bueno' en indicadores.yaml (ej. EMAE). Se lee del yaml
    (única fuente de verdad) para que dashboard y mail nunca queden desincronizados."""
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    return {i["nombre"]: bool(i.get("sube_es_bueno")) for i in cfg["indicadores"]}


def resumen_indicadores(df):
    sube_es_bueno = _cargar_sube_es_bueno()
    filas = []
    for n in INDICADORES_MAIL:
        s = df[df["indicador"] == n].sort_values("fecha")
        if s.empty:
            continue
        ult = s.iloc[-1]
        prev = s[s["fecha"] <= ult["fecha"] - pd.Timedelta(days=7)]
        chg = None
        if not prev.empty and prev.iloc[-1]["valor"]:
            chg = (ult["valor"] / prev.iloc[-1]["valor"] - 1) * 100
        filas.append(dict(nombre=n, valor=_fmt(ult["valor"]), unidad=ult.get("unidad", ""),
                          chg=chg, fecha=ult["fecha"].strftime("%d/%m/%Y"),
                          sube_es_bueno=sube_es_bueno.get(n, False)))
    return filas


# artículo + forma corta de cada indicador de INDICADORES_MAIL, sólo para armar el
# briefing en una frase natural (lista fija, igual que INDICADORES_MAIL)
_ARTICULO_BRIEFING = {
    "Dólar oficial": "el dólar oficial",
    "Dólar blue": "el dólar blue",
    "Brecha cambiaria (CCL/oficial)": "la brecha cambiaria",
    "Riesgo país (EMBI)": "el riesgo país",
    "Reservas internacionales (BCRA)": "las reservas internacionales",
    "Inflación mensual (IPC)": "la inflación mensual",
    "Base monetaria": "la base monetaria",
    "Tasa BADLAR (mayorista)": "la tasa BADLAR",
    "EMAE (actividad económica)": "el EMAE",
    "Saldo comercial": "el saldo comercial",
}


def _generar_briefing(indicadores, umbral=1.0, max_items=3):
    """Frase corta con los indicadores que más se movieron, por regla fija (sin LLM)."""
    movidos = [f for f in indicadores if f["chg"] is not None and abs(f["chg"]) > umbral]
    movidos.sort(key=lambda f: abs(f["chg"]), reverse=True)
    top = movidos[:max_items]
    if not top:
        return "Jornada sin grandes movimientos en los indicadores clave."
    partes = []
    for f in top:
        verbo = "subió" if f["chg"] > 0 else "bajó"
        nombre = _ARTICULO_BRIEFING.get(f["nombre"], f["nombre"])
        pct = f'{abs(f["chg"]):.1f}'.replace(".", ",")
        unidad = f' {f["unidad"]}' if f.get("unidad") else ""
        partes.append(f'{nombre}, que {verbo} {pct}% a {f["valor"]}{unidad}')
    cuerpo = partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]
    return f"Hoy se destaca {cuerpo}."


def _render_noticias(lista):
    if not lista:
        return '<p style="color:#999">Sin novedades hoy.</p>'
    bloques = []
    for x in lista:
        bajada = f'<div style="color:#444;font-size:13px;margin:2px 0 3px">{x["bajada"]}</div>' if x.get("bajada") else ""
        fuente = f'<span style="color:#999;font-size:11px">{x["fuente"]}</span> · ' if x.get("fuente") else ""
        bloques.append(
            f'<div style="margin-bottom:14px">'
            f'<div style="font-weight:600;font-size:14px">{x["titulo"]}</div>'
            f'{bajada}'
            f'<div>{fuente}<a href="{x["link"]}" style="color:#1D4E89;text-decoration:none;font-size:13px">Leer nota →</a></div>'
            f'</div>')
    return "".join(bloques)


def armar_html(indicadores, argentinas, internacionales, briefing=""):
    hoy = datetime.now(ZONA_AR).strftime("%d/%m/%Y")
    filas_ind = ""
    for f in indicadores:
        if f["chg"] is None or abs(f["chg"]) <= 0.05:
            flecha, color = "•", "#9A968C"
        else:
            sube = f["chg"] > 0.05
            flecha = "▲" if sube else "▼"
            bueno = sube if f.get("sube_es_bueno") else not sube
            color = "#256D5B" if bueno else "#B4341F"
        chg = f'{flecha} {abs(f["chg"]):.1f}%' if f["chg"] is not None else "—"
        filas_ind += (f'<tr><td style="padding:6px 10px;border-bottom:1px solid #eee">{f["nombre"]}</td>'
                      f'<td style="padding:6px 10px;border-bottom:1px solid #eee;font-family:monospace;text-align:right"><b>{f["valor"]}</b> <span style="color:#999;font-size:11px">{f["unidad"]}</span></td>'
                      f'<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;color:{color};font-family:monospace">{chg}</td></tr>')

    briefing_html = f'<p style="font-size:15px;margin-top:14px">{briefing}</p>' if briefing else ""
    return f"""<div style="font-family:system-ui,Arial,sans-serif;max-width:640px;margin:0 auto;color:#1A1A1A">
      <h2 style="border-bottom:2px solid #1A1A1A;padding-bottom:8px">Coyuntura Argentina · {hoy}</h2>
      {briefing_html}
      <h3 style="margin-top:22px">Indicadores clave <span style="color:#999;font-weight:400;font-size:13px">(variación vs. 7 días atrás)</span></h3>
      <table style="width:100%;border-collapse:collapse;font-size:14px">{filas_ind}</table>
      <h3 style="margin-top:26px">🇦🇷 Noticias argentinas</h3>
      {_render_noticias(argentinas)}
      <h3 style="margin-top:26px">🌎 Noticias internacionales</h3>
      {_render_noticias(internacionales)}
      <p style="margin-top:26px"><a href="{DASHBOARD_URL}" style="background:#1D4E89;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none">Ver el dashboard completo →</a></p>
      <p style="color:#999;font-size:12px;margin-top:20px">Generado automáticamente. Fuentes: apis.datos.gob.ar · ArgentinaDatos · BCRA · medios citados en cada nota.</p>
    </div>"""


def enviar(html):
    user = os.environ["GMAIL_USER"]
    pw = os.environ["GMAIL_APP_PASSWORD"]
    to = os.environ.get("MAIL_TO", user)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Coyuntura Argentina · {datetime.now(ZONA_AR):%d/%m}"
    msg["From"] = user
    msg["To"] = to
    msg.attach(MIMEText(html, "html", "utf-8"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as srv:
        srv.login(user, pw)
        srv.sendmail(user, [x.strip() for x in to.split(",")], msg.as_string())
    print(f"Mail enviado a {to}")


def main():
    df = pd.read_csv(CSV, parse_dates=["fecha"])
    indicadores = resumen_indicadores(df)
    briefing = _generar_briefing(indicadores)
    argentinas, internacionales = obtener_noticias()
    html = armar_html(indicadores, argentinas, internacionales, briefing)
    enviar(html)


if __name__ == "__main__":
    main()

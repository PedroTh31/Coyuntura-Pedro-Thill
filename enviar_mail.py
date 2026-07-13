"""
enviar_mail.py  ·  Arma y envía por Gmail un resumen semanal:
  - indicadores clave con su variación de la semana
  - titulares económicos más relevantes (RSS público, gratis)

Necesita 3 variables de entorno (se cargan desde GitHub Secrets):
  GMAIL_USER           -> tu dirección de Gmail
  GMAIL_APP_PASSWORD   -> "contraseña de aplicación" de Google (no la común)
  MAIL_TO              -> a quién enviar (opcional; por defecto, a vos mismo)
"""
import os
import ssl
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from urllib.parse import quote
from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parent
CSV = RAIZ / "data" / "series_largo.csv"
DASHBOARD_URL = "https://pedroth31.github.io/Coyuntura-Pedro-Thill/"   # editable

# indicadores que van en el mail (deben coincidir con los nombres del config)
INDICADORES_MAIL = [
    "Dólar oficial", "Dólar blue", "Brecha cambiaria (CCL/oficial)",
    "Riesgo país (EMBI)", "Reservas internacionales (BCRA)",
    "Inflación mensual (IPC)", "Base monetaria", "Tasa BADLAR (mayorista)",
    "EMAE (actividad económica)", "Saldo comercial",
]

CONSULTAS_NOTICIAS = ["economía argentina", "dólar inflación argentina", "BCRA reservas tasas"]

# feeds de medios que SÍ traen bajada (si alguno cambia su URL, se ignora sin romper)
FEEDS_MEDIOS = [
    "https://www.pagina12.com.ar/rss/secciones/economia/notas",
    "https://www.ambito.com/rss/economia.xml",
    "https://www.cronista.com/files/rss/economia.xml",
    "https://www.iprofesional.com/rss/economia.xml",
]


def _limpiar(texto):
    """Saca etiquetas HTML y espacios sobrantes de una bajada, y la recorta."""
    import re
    import html as _html
    if not texto:
        return ""
    t = re.sub(r"<[^>]+>", " ", texto)          # sacar etiquetas
    t = _html.unescape(t)                        # decodificar &amp; etc.
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > 220:
        t = t[:220].rsplit(" ", 1)[0] + "…"
    return t


def obtener_noticias(n=6):
    try:
        import feedparser
    except Exception:
        return []
    limite = datetime.now() - timedelta(days=7)
    vistos, items = set(), []

    def procesar(feed, fuente_default=""):
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
            # en Google News la "bajada" suele ser sólo la fuente: la descartamos
            if bajada.lower().startswith(t.lower()[:25]) or len(bajada) < 40:
                bajada = ""
            fuente = fuente_default
            src = getattr(e, "source", None)
            if src is not None:
                fuente = getattr(src, "title", "") or (src.get("title", "") if isinstance(src, dict) else "") or fuente
            vistos.add(t)
            items.append(dict(titulo=t, link=getattr(e, "link", "#"),
                              fuente=fuente, bajada=bajada, pub=pub))

    # 1) medios (traen bajada real)
    for url in FEEDS_MEDIOS:
        try:
            procesar(feedparser.parse(url))
        except Exception:
            continue
    # 2) Google News como respaldo (garantiza que no quede vacío)
    for q in CONSULTAS_NOTICIAS:
        url = f"https://news.google.com/rss/search?q={quote(q)}&hl=es-419&gl=AR&ceid=AR:es"
        try:
            procesar(feedparser.parse(url))
        except Exception:
            continue

    # priorizar las que tienen bajada, y ordenar por fecha
    items.sort(key=lambda x: (x["bajada"] == "", -x["pub"].timestamp()))
    return items[:n]


def _fmt(v):
    if v is None or pd.isna(v):
        return "s/d"
    if abs(v) >= 1000:
        return f"{v:,.0f}".replace(",", ".")
    s = f"{v:,.1f}" if abs(v) >= 10 else f"{v:,.2f}"
    return s.replace(",", "@").replace(".", ",").replace("@", ".")


def resumen_indicadores(df):
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
                          chg=chg, fecha=ult["fecha"].strftime("%d/%m/%Y")))
    return filas


def armar_html(indicadores, noticias):
    hoy = datetime.now().strftime("%d/%m/%Y")
    filas_ind = ""
    for f in indicadores:
        if f["chg"] is None:
            flecha, color = "•", "#9A968C"
        elif f["chg"] > 0.05:
            flecha, color = "▲", "#B4341F"
        elif f["chg"] < -0.05:
            flecha, color = "▼", "#256D5B"
        else:
            flecha, color = "•", "#9A968C"
        chg = f'{flecha} {abs(f["chg"]):.1f}%' if f["chg"] is not None else "—"
        filas_ind += (f'<tr><td style="padding:6px 10px;border-bottom:1px solid #eee">{f["nombre"]}</td>'
                      f'<td style="padding:6px 10px;border-bottom:1px solid #eee;font-family:monospace;text-align:right"><b>{f["valor"]}</b> <span style="color:#999;font-size:11px">{f["unidad"]}</span></td>'
                      f'<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;color:{color};font-family:monospace">{chg}</td></tr>')

    if noticias:
        bloques = []
        for x in noticias:
            bajada = f'<div style="color:#444;font-size:13px;margin:2px 0 3px">{x["bajada"]}</div>' if x.get("bajada") else ""
            fuente = f'<span style="color:#999;font-size:11px">{x["fuente"]}</span> · ' if x.get("fuente") else ""
            bloques.append(
                f'<div style="margin-bottom:14px">'
                f'<div style="font-weight:600;font-size:14px">{x["titulo"]}</div>'
                f'{bajada}'
                f'<div>{fuente}<a href="{x["link"]}" style="color:#1D4E89;text-decoration:none;font-size:13px">Leer nota →</a></div>'
                f'</div>')
        bloque_news = "".join(bloques)
    else:
        bloque_news = '<p style="color:#999">No se pudieron recuperar titulares esta semana.</p>'

    return f"""<div style="font-family:system-ui,Arial,sans-serif;max-width:640px;margin:0 auto;color:#1A1A1A">
      <h2 style="border-bottom:2px solid #1A1A1A;padding-bottom:8px">Coyuntura Argentina · semana del {hoy}</h2>
      <h3 style="margin-top:22px">Indicadores clave <span style="color:#999;font-weight:400;font-size:13px">(variación vs. 7 días atrás)</span></h3>
      <table style="width:100%;border-collapse:collapse;font-size:14px">{filas_ind}</table>
      <h3 style="margin-top:26px">Noticias de la semana</h3>
      {bloque_news}
      <p style="margin-top:26px"><a href="{DASHBOARD_URL}" style="background:#1D4E89;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none">Ver el dashboard completo →</a></p>
      <p style="color:#999;font-size:12px;margin-top:20px">Generado automáticamente. Fuentes: apis.datos.gob.ar · ArgentinaDatos · BCRA · Google News.</p>
    </div>"""


def enviar(html):
    user = os.environ["GMAIL_USER"]
    pw = os.environ["GMAIL_APP_PASSWORD"]
    to = os.environ.get("MAIL_TO", user)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Coyuntura Argentina · semana {datetime.now():%d/%m}"
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
    noticias = obtener_noticias()
    html = armar_html(indicadores, noticias)
    enviar(html)


if __name__ == "__main__":
    main()

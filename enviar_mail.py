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
import unicodedata
from difflib import SequenceMatcher
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
    "Inflación mensual (IPC)", "Base monetaria", "Tasa TAMAR (total bancos)",
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

# feeds internacionales: la sección editorial NO alcanza como filtro por sí sola (verificado
# con el primer mail real: hasta BBC Business/The Economist traen notas de consumo/lifestyle
# sin relación con macro/geopolítica, ej. "Ironing board seats to be replaced on Thameslink") --
# todas, sin excepción, pasan por el filtro KW_INTERNACIONAL de más abajo (ver obtener_noticias)
FEEDS_INTERNACIONAL = [
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://www.economist.com/finance-and-economics/rss.xml",
    "https://foreignpolicy.com/feed/",
    "https://www.foreignaffairs.com/rss.xml",
    "https://www.ft.com/global-economy?format=rss",
    "https://www.project-syndicate.org/rss",
    "https://www.france24.com/es/econom%C3%ADa/rss",
    "http://feeds.bbci.co.uk/mundo/rss.xml",
    "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/economia/portada",
]

# si el título/copete contiene alguna de estas, se considera internacional/geopolítico:
# (a) saca una nota Argentina del bloque argentino si igual menciona esto, y
# (b) es el filtro de relevancia obligatorio para TODAS las fuentes internacionales de arriba
KW_INTERNACIONAL = ["trump", "china", "ee.uu", "eeuu", "estados unidos", "wall street",
    "reserva federal", " fed ", "europa", "alemania", "japón", "brasil", "lula",
    "nvidia", "apple", "petróleo brent", "unión europea", "rusia", "israel", "bitcoin",
    "otan", "sanciones", "guerra comercial", "geopolític", "conflicto", "cumbre",
    "aranceles"]

# palabras que, si aparecen en título o bajada de una nota ARGENTINA, confirman que es
# noticia económica real: filtro POSITIVO (además del negativo de KW_EXCLUIR_TIPS más abajo)
# -- un feriado o un calendario de pagos de ANSES no matchea ningún patrón "tips", pero
# tampoco es economía, así que el filtro negativo solo nunca alcanza para excluirlo
KW_ECONOMICO_AR = [
    "inflación", "dólar", "bcra", "banco central", "riesgo país", "pbi",
    "producto bruto", "actividad económica", "emae", "reservas", "deuda", "fmi",
    "superávit", "déficit", "tasa de interés", "tasas de interés", "desempleo",
    "pobreza", "canasta básica", "comercio exterior", "exportaciones",
    "importaciones", "balanza comercial", "merval", "bolsa", "acciones", "bonos",
    "salario", "paritaria", "recesión", "tarifa", "impuesto", "recaudación",
    "fiscal", "presupuesto", "milei",
]
# "inversión", "consumo", "industria", "producción" se sacaron de la lista de arriba
# (Ronda 2 del mail): son demasiado genéricos -- aparecen tal cual en notas de
# management/franquicias sin nada de macro (ej. "Radiografía de un negocio"), dejaban
# pasar contenido fuera de tema aunque el resto del filtro funcionara bien.

# Además del tema económico, una nota ARGENTINA tiene que mencionar Argentina en algún
# lado (Ronda 2): "deuda" o "desempleo" solos no alcanzan si la nota es sobre Colombia,
# México, etc. -- caso real que se coló: "Deuda de las EPS en Colombia llegó a...".
# "Milei"/"Caputo" ya están acá, pero sólo cuentan junto con un match de
# KW_ECONOMICO_AR (las dos listas se exigen en conjunto, ver _es_economico_ar).
KW_ARGENTINA_CONTEXTO = [
    "argentina", "argentino", "argentina", "bcra", "banco central", "indec",
    "ministerio de economía", "peso argentino", "gobierno nacional", "milei", "caputo",
    "buenos aires", "córdoba", "santa fe", "mendoza", "tucumán", "salta",
    "entre ríos", "chaco", "corrientes", "misiones", "san juan", "jujuy",
    "río negro", "neuquén", "formosa", "chubut", "san luis", "catamarca",
    "la rioja", "santa cruz", "santiago del estero", "la pampa", "tierra del fuego",
]

# notas tipo "consejo/listicle" o de relleno que no son noticia económica real (ej. "cómo
# pagar reservas de hotel en dólares", "Dólar EN VIVO minuto a minuto", "qué significa esto
# para tu factura"): filtro heurístico, ajustar según lo que se cuele
KW_EXCLUIR_TIPS = [
    "la mejor forma de", "cómo pagar", "cómo ahorrar", "consejos para",
    "trucos para", "paso a paso para", "todo lo que tenés que saber para",
    "todo lo que necesitás saber para", "cuidar tu bolsillo",
    "cuánto cobra", "cuánto se cobra", "a cuánto llega", "de cuánto es",
    "a cuánto cotiza", "aumento confirmado", "en vivo", "minuto a minuto", "hora a hora",
    "cronograma de pagos", "calendario de pagos", "esquema de cobros",
    "quiénes cobran", "quiénes perciben",
    "what does this mean for", "what will this mean for", "mean for my bills",
    "mean for your",
    "denuncia periodística", "investigación periodística", "ronda de investigación",
]
_RE_LISTICLE = re.compile(r"^\d+\s+(formas?|tips?|claves?|trucos?|maneras?)\s+", re.I)
# Acrónimos cortos (ej. "CIA") con \b: si se buscaran como substring suelto ("cia")
# matchean falsos positivos adentro de palabras comunes ("diferencia", "resistencia").
# Caso real que se coló (Ronda 2): nota sobre Peter Thiel/Palantir/CIA con referencias
# a la AMIA -- investigación periodística/política, no una noticia económica.
_RE_EXCLUIR_ACRONIMOS = re.compile(r"\b(cia|amia|espionaje|inteligencia)\b", re.I)

# Ronda 2 del mail: priorizar (no excluir del todo) noticias internacionales con
# contenido económico/de mercados por sobre las puramente geopolíticas (guerra,
# elecciones, diplomacia) que no tengan ningún término de esta lista.
KW_ECONOMICO_INTL = [
    "fed", "reserva federal", "fomc", "tasa de interés", "tasas de interés",
    "banco central", "bce", "banco de inglaterra", "banco de japón", "pboc",
    "futuros", "bonos", "rendimientos", "wall street", "nasdaq", "s&p 500",
    "nikkei", "yuan", "yen", "euro",
    "inflación", "pib", "desempleo", "manufactura", "exportaciones",
]


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
    """Filtra notas tipo consejo/listicle/relleno, y (Ronda 2) notas de investigación
    política/periodística que no son noticia económica real aunque mencionen de
    pasada algún término económico (ej. una nota sobre la CIA y la AMIA)."""
    t = titulo.lower().strip()
    if _RE_LISTICLE.match(t):
        return True
    if t.startswith("firstft:"):
        return True  # boletín embolsado de FT, agrupa varias notas sin relación
    if _RE_EXCLUIR_ACRONIMOS.search(t):
        return True
    return any(k in t for k in KW_EXCLUIR_TIPS)


def _es_economico_ar(texto):
    """Filtro positivo para notas argentinas: título o bajada tienen que mencionar algo
    de economía real (un feriado o un calendario de pagos no matchea 'tips', pero
    tampoco es economía -- el filtro negativo solo no alcanza para esos casos)."""
    t = " " + texto.lower() + " "
    return any(k in t for k in KW_ECONOMICO_AR)


def _es_argentina_contexto(texto):
    """Filtro positivo adicional (Ronda 2): la nota tiene que mencionar Argentina en
    algún lado -- 'deuda' o 'desempleo' solos no alcanzan si la nota es sobre otro
    país (caso real: una nota sobre deuda de obras sociales en Colombia)."""
    t = " " + texto.lower() + " "
    return any(k in t for k in KW_ARGENTINA_CONTEXTO)


def _es_economico_intl(texto):
    """Para priorizar (no excluir) noticias internacionales con contenido económico/
    de mercados por sobre las puramente geopolíticas (Ronda 2)."""
    t = " " + texto.lower() + " "
    return any(k in t for k in KW_ECONOMICO_INTL)


def _normalizar_titulo(texto):
    """Normaliza un título para comparar similitud entre notas (Ronda 2, dedup):
    minúsculas, sin tildes, sin puntuación."""
    t = texto.lower().strip()
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _deduplicar(items, umbral=0.6):
    """Colapsa notas que son la misma noticia contada por distintas fuentes (Ronda 2;
    ej. dos notas de la cotización del dólar, una con foco en Córdoba y otra en Buenos
    Aires). Compara títulos normalizados con SequenceMatcher; ante un grupo de
    duplicados se queda con el de fuente de mayor jerarquía (el orden en que aparece
    la fuente en FEEDS_MEDIOS/FEEDS_INTERNACIONAL, guardado en 'rank' por
    _recolectar) y, si empatan, con el más reciente. Preserva el orden relativo
    original de los sobrevivientes (ya viene pre-ordenado por _recolectar)."""
    normalizados = [_normalizar_titulo(x["titulo"]) for x in items]
    usados = [False] * len(items)
    resultado = []
    for i in range(len(items)):
        if usados[i]:
            continue
        grupo = [i]
        usados[i] = True
        for j in range(i + 1, len(items)):
            if usados[j]:
                continue
            if SequenceMatcher(None, normalizados[i], normalizados[j]).ratio() > umbral:
                grupo.append(j)
                usados[j] = True
        if len(grupo) == 1:
            resultado.append(items[i])
        else:
            ganador = min(grupo, key=lambda k: (items[k].get("rank", 0), -items[k]["pub"].timestamp()))
            resultado.append(items[ganador])
    return resultado


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
    """Junta notas de una lista de feeds RSS directos, con bajada y fecha. 'rank' guarda
    la posición del feed en la lista (jerarquía de fuente, usada por _deduplicar)."""
    import feedparser
    limite = _limite(es_argentina)
    vistos, items = set(), []

    def procesar(feed, rank):
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
                              fuente=fuente, bajada=bajada, pub=pub, rank=rank))

    for rank, url in enumerate(feeds):
        try:
            procesar(feedparser.parse(url), rank)
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
    arg_crudo = [x for x in _recolectar(FEEDS_MEDIOS, es_argentina=True)
           if not _es_internacional(x["titulo"]) and not _es_tip(x["titulo"])
           and _es_economico_ar(x["titulo"] + " " + x["bajada"])
           and _es_argentina_contexto(x["titulo"] + " " + x["bajada"])]
    arg_crudo = _deduplicar(arg_crudo)
    arg = arg_crudo[:n]
    titulos_arg = {x["titulo"] for x in arg}

    crudo_intl = _recolectar(FEEDS_INTERNACIONAL, es_argentina=False)
    intl_crudo = [x for x in crudo_intl
            if x["titulo"] not in titulos_arg and not _es_tip(x["titulo"])
            and _es_internacional(x["titulo"] + " " + x["bajada"])]
    intl_crudo = _deduplicar(intl_crudo)
    # Prioriza (no excluye) notas con contenido económico/de mercados por sobre las
    # puramente geopolíticas -- sort estable, mantiene el orden bajada/recencia dentro
    # de cada grupo de prioridad (ver _recolectar).
    intl_crudo.sort(key=lambda x: 0 if _es_economico_intl(x["titulo"] + " " + x["bajada"]) else 1)
    intl = intl_crudo[:n]
    return arg, intl


def _fmt(v):
    if v is None or pd.isna(v):
        return "s/d"
    if abs(v) >= 1000:
        return f"{v:,.0f}".replace(",", ".")
    s = f"{v:,.1f}" if abs(v) >= 10 else f"{v:,.2f}"
    return s.replace(",", "@").replace(".", ",").replace("@", ".")


def _cargar_flags_color():
    """Mismo criterio que dashboard.py: por defecto subir = malo (rojo), salvo que el
    indicador declare 'sube_es_bueno' (ej. EMAE) o 'neutral' (sin juicio de valor, ej.
    agregados monetarios) en indicadores.yaml. Se lee del yaml (única fuente de verdad)
    para que dashboard y mail nunca queden desincronizados."""
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    sube_es_bueno = {i["nombre"]: bool(i.get("sube_es_bueno")) for i in cfg["indicadores"]}
    neutral = {i["nombre"]: bool(i.get("neutral")) for i in cfg["indicadores"]}
    return sube_es_bueno, neutral


def resumen_indicadores(df):
    sube_es_bueno, neutral = _cargar_flags_color()
    filas = []
    for n in INDICADORES_MAIL:
        s = df[df["indicador"] == n].sort_values("fecha")
        if s.empty:
            continue
        ult = s.iloc[-1]
        unidad = ult.get("unidad", "")
        prev = s[s["fecha"] <= ult["fecha"] - pd.Timedelta(days=7)]
        chg = None
        # Ronda 2: para indicadores que ya son tasas/porcentajes (TAMAR, inflación,
        # brecha cambiaria...), la variación a 7 días se muestra como diferencia
        # simple en puntos porcentuales (ej. "de 3,0% a 3,5% = +0,5 p.p."), no como
        # variación % del valor (que para una tasa da un número confuso, ej. "+16,7%"
        # para ese mismo movimiento). El resto (dólar, reservas, montos en pesos)
        # sigue en % de variación como siempre -- "%" en la unidad ya declarada en
        # indicadores.yaml decide cuál criterio aplica, sin lista hardcodeada aparte.
        es_pp = "%" in str(unidad)
        if not prev.empty and prev.iloc[-1]["valor"] is not None:
            valor_prev = prev.iloc[-1]["valor"]
            if es_pp:
                chg = ult["valor"] - valor_prev
            elif valor_prev:
                chg = (ult["valor"] / valor_prev - 1) * 100
        filas.append(dict(nombre=n, valor=_fmt(ult["valor"]), unidad=unidad,
                          chg=chg, es_pp=es_pp, fecha=ult["fecha"].strftime("%d/%m/%Y"),
                          sube_es_bueno=sube_es_bueno.get(n, False), neutral=neutral.get(n, False)))
    return filas


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


def armar_html(indicadores, argentinas, internacionales):
    hoy = datetime.now(ZONA_AR).strftime("%d/%m/%Y")
    filas_ind = ""
    for f in indicadores:
        if f["chg"] is None or abs(f["chg"]) <= 0.05:
            flecha, color = "•", "#9A968C"
        else:
            sube = f["chg"] > 0.05
            flecha = "▲" if sube else "▼"
            if f.get("neutral"):
                color = "#9A968C"
            else:
                bueno = sube if f.get("sube_es_bueno") else not sube
                color = "#256D5B" if bueno else "#B4341F"
        unidad_chg = " p.p." if f.get("es_pp") else "%"
        chg = f'{flecha} {abs(f["chg"]):.1f}{unidad_chg}' if f["chg"] is not None else "—"
        filas_ind += (f'<tr><td style="padding:6px 10px;border-bottom:1px solid #eee">{f["nombre"]}</td>'
                      f'<td style="padding:6px 10px;border-bottom:1px solid #eee;font-family:monospace;text-align:right"><b>{f["valor"]}</b> <span style="color:#999;font-size:11px">{f["unidad"]}</span></td>'
                      f'<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;color:{color};font-family:monospace">{chg}</td></tr>')

    return f"""<div style="font-family:system-ui,Arial,sans-serif;max-width:640px;margin:0 auto;color:#1A1A1A">
      <h2 style="border-bottom:2px solid #1A1A1A;padding-bottom:8px">Coyuntura Argentina · {hoy}</h2>
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
    to_raw = os.environ.get("MAIL_TO", user)
    # Sanitizado: un secret MAIL_TO cargado con una dirección por renglón (en vez de
    # separadas por coma) mete un '\n' en el header "To", y la librería estándar de
    # email rechaza cualquier header con salto de línea adentro (HeaderWriteError) --
    # el envío entero corta con exit code 1. Acepta coma Y salto de línea como
    # separador, y usa la misma lista ya limpia para el header y el envío real.
    destinatarios = [x.strip() for x in re.split(r"[,\n\r]+", to_raw) if x.strip()]
    to = ", ".join(destinatarios)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Coyuntura Argentina · {datetime.now(ZONA_AR):%d/%m}"
    msg["From"] = user
    msg["To"] = to
    msg.attach(MIMEText(html, "html", "utf-8"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as srv:
        srv.login(user, pw)
        srv.sendmail(user, destinatarios, msg.as_string())
    print(f"Mail enviado a {to}")


def main():
    df = pd.read_csv(CSV, parse_dates=["fecha"])
    indicadores = resumen_indicadores(df)
    argentinas, internacionales = obtener_noticias()
    html = armar_html(indicadores, argentinas, internacionales)
    enviar(html)


if __name__ == "__main__":
    main()

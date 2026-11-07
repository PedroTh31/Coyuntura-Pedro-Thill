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
import sys
import json
import smtplib
import unicodedata
from difflib import SequenceMatcher
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlparse
import pandas as pd
import yaml

import mail_agenda

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

# "banco central" es contexto argentino DÉBIL (Bloque 3 de PROMPT_mail_v3.md): sólo cuenta si
# la nota no menciona otro país de esta lista. Caso real (2026-11-05): notas sobre el Banco
# Central de Paraguay (Ueno Bank) y Banxico entraban al bloque Argentina porque "banco
# central" cumplía a la vez el filtro económico y el de contexto. No se borra de
# KW_ARGENTINA_CONTEXTO: muchas notas argentinas dicen sólo "el Banco Central" (ej. "Tras dos
# días sin sumar divisas, el Banco Central volvió a comprar dólares"). Lista de Pedro; se
# compara SIN tildes (para que "mexic" reconozca "México"). Se aplica SOLO en evaluar_ar: el
# filtro internacional no la usa, una nota sobre estos países puede seguir en Internacional.
# Tests: tests/test_noticias.py.
KW_OTRO_PAIS_BANCO_CENTRAL = ["paragua", "urugua", "chile", "brasil", "bolivia", "mexic", "banxico"]

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


def _motivo_tip(titulo):
    """Qué regla de 'tip/relleno' excluye el título (None si ninguna). Filtra notas tipo
    consejo/listicle/relleno, y (Ronda 2) notas de investigación política/periodística
    que no son noticia económica real aunque mencionen de pasada algún término
    económico (ej. una nota sobre la CIA y la AMIA)."""
    t = titulo.lower().strip()
    if _RE_LISTICLE.match(t):
        return "listicle"
    if t.startswith("firstft:"):
        return "firstft"  # boletín embolsado de FT, agrupa varias notas sin relación
    if _RE_EXCLUIR_ACRONIMOS.search(t):
        return "acronimos"
    if any(k in t for k in KW_EXCLUIR_TIPS):
        return "KW_EXCLUIR_TIPS"
    return None


def _es_tip(titulo):
    return _motivo_tip(titulo) is not None


def _coincidencias(lista, texto):
    t = " " + texto.lower() + " "
    return [k for k in lista if k in t]


def evaluar_ar(titulo, bajada):
    """Decide si una nota de un medio argentino entra al bloque Argentina. Devuelve
    (entra, regla, detalle): 'regla' es la que decidió (para el log de noticias y los
    tests de regresión), 'detalle' las palabras que coincidieron. Mismo orden de reglas
    que el filtro histórico: internacional (sólo título) -> tip -> tema económico (un
    feriado o un calendario de pagos no matchea 'tips', pero tampoco es economía) ->
    contexto argentino ('deuda' o 'desempleo' solos no alcanzan si la nota es de otro
    país, caso real: deuda de obras sociales en Colombia)."""
    texto = titulo + " " + bajada
    intl = _coincidencias(KW_INTERNACIONAL, titulo)
    if intl:
        return False, "KW_INTERNACIONAL", intl
    motivo = _motivo_tip(titulo)
    if motivo:
        return False, motivo, None
    econ = _coincidencias(KW_ECONOMICO_AR, texto)
    if not econ:
        return False, "sin_KW_ECONOMICO_AR", None
    contexto = _coincidencias(KW_ARGENTINA_CONTEXTO, texto)
    if not contexto:
        return False, "sin_KW_ARGENTINA_CONTEXTO", {"economico": econ}
    if contexto == ["banco central"]:
        # Único contexto = "banco central" (débil): no alcanza si la nota es de otro país.
        sin_tildes = _normalizar_titulo(texto)
        otros = [p for p in KW_OTRO_PAIS_BANCO_CENTRAL if p in sin_tildes]
        if otros:
            return False, "banco_central_otro_pais", {"economico": econ, "otro_pais": otros}
    return True, "entra", {"economico": econ, "contexto": contexto}


def evaluar_intl(titulo, bajada):
    """Decide si una nota de un feed internacional pasa el filtro de relevancia (antes de
    dedup/prioridad/corte). Mismo contrato que evaluar_ar."""
    motivo = _motivo_tip(titulo)
    if motivo:
        return False, motivo, None
    intl = _coincidencias(KW_INTERNACIONAL, titulo + " " + bajada)
    if not intl:
        return False, "sin_KW_INTERNACIONAL", None
    return True, "entra", {"internacional": intl}


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


def _deduplicar(items, umbral=0.6, descartes=None):
    """Colapsa notas que son la misma noticia contada por distintas fuentes (Ronda 2;
    ej. dos notas de la cotización del dólar, una con foco en Córdoba y otra en Buenos
    Aires). Compara títulos normalizados con SequenceMatcher; ante un grupo de
    duplicados se queda con el de fuente de mayor jerarquía (el orden en que aparece
    la fuente en FEEDS_MEDIOS/FEEDS_INTERNACIONAL, guardado en 'rank' por
    _recolectar) y, si empatan, con el más reciente. Preserva el orden relativo
    original de los sobrevivientes (ya viene pre-ordenado por _recolectar).
    'descartes' (lista opcional): se le agregan (descartada, ganadora) para el log."""
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
            if descartes is not None:
                descartes.extend((items[k], items[ganador]) for k in grupo if k != ganador)
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
                              fuente=fuente, bajada=bajada, pub=pub, rank=rank,
                              feed=urlparse(feeds[rank]).netloc))

    for rank, url in enumerate(feeds):
        try:
            procesar(feedparser.parse(url), rank)
        except Exception:
            continue

    items.sort(key=lambda x: (x["bajada"] == "", -x["pub"].timestamp()))
    return items


def obtener_noticias(n=6, registro=None):
    """Devuelve (argentinas, internacionales), n de cada una. 'registro' (lista opcional):
    se le agrega una entrada por CADA nota evaluada con la regla que decidió (ver
    escribir_log_noticias) -- sale de las mismas decisiones que arman el mail, no de un
    cálculo paralelo."""
    try:
        import feedparser  # noqa: F401
    except Exception:
        return [], []

    def _reg(x, bloque, entro, regla, detalle=None):
        if registro is not None:
            registro.append(dict(bloque=bloque, titulo=x["titulo"], fuente=x.get("feed", ""),
                                 link=x["link"], entro=entro, regla=regla, detalle=detalle))

    arg_crudo = []
    for x in _recolectar(FEEDS_MEDIOS, es_argentina=True):
        entra, regla, detalle = evaluar_ar(x["titulo"], x["bajada"])
        if entra:
            x["_detalle"] = detalle
            arg_crudo.append(x)
        else:
            _reg(x, "ar", False, regla, detalle)
    descartes = []
    arg_crudo = _deduplicar(arg_crudo, descartes=descartes)
    for x, ganador in descartes:
        _reg(x, "ar", False, "dedup", {"duplicado_de": ganador["titulo"]})
    arg = arg_crudo[:n]
    for k, x in enumerate(arg_crudo):
        _reg(x, "ar", k < n, "entra" if k < n else f"corte_top_{n}", x.pop("_detalle", None))
    titulos_arg = {x["titulo"] for x in arg}

    intl_crudo = []
    for x in _recolectar(FEEDS_INTERNACIONAL, es_argentina=False):
        if x["titulo"] in titulos_arg:
            _reg(x, "intl", False, "ya_en_AR")
            continue
        entra, regla, detalle = evaluar_intl(x["titulo"], x["bajada"])
        if entra:
            x["_detalle"] = detalle
            intl_crudo.append(x)
        else:
            _reg(x, "intl", False, regla, detalle)
    descartes = []
    intl_crudo = _deduplicar(intl_crudo, descartes=descartes)
    for x, ganador in descartes:
        _reg(x, "intl", False, "dedup", {"duplicado_de": ganador["titulo"]})
    # Prioriza (no excluye) notas con contenido económico/de mercados por sobre las
    # puramente geopolíticas -- sort estable, mantiene el orden bajada/recencia dentro
    # de cada grupo de prioridad (ver _recolectar).
    intl_crudo.sort(key=lambda x: 0 if _es_economico_intl(x["titulo"] + " " + x["bajada"]) else 1)
    intl = intl_crudo[:n]
    for k, x in enumerate(intl_crudo):
        _reg(x, "intl", k < n, "entra" if k < n else f"corte_top_{n}", x.pop("_detalle", None))
    return arg, intl


# Bloque 3 de PROMPT_mail_v3.md: log de decisiones del filtro de noticias, una línea JSON por
# nota evaluada y por corrida. Se conservan sólo los últimos DIAS_LOG_NOTICIAS días (decisión
# de Pedro: ~370 notas/día, ~110 KB/día) para que el repo no crezca sin límite.
LOG_NOTICIAS = RAIZ / "data" / "noticias_log.jsonl"
DIAS_LOG_NOTICIAS = 14


def escribir_log_noticias(registro):
    ahora = datetime.now(ZONA_AR)
    corte = (ahora - timedelta(days=DIAS_LOG_NOTICIAS - 1)).date().isoformat()
    previas = []
    if LOG_NOTICIAS.exists():
        for linea in LOG_NOTICIAS.read_text(encoding="utf-8").splitlines():
            try:
                if json.loads(linea).get("corrida", "")[:10] >= corte:
                    previas.append(linea)
            except json.JSONDecodeError:
                continue  # una línea corrupta no tira abajo el log entero
    corrida = ahora.isoformat(timespec="seconds")
    nuevas = [json.dumps({"corrida": corrida, **r}, ensure_ascii=False) for r in registro]
    LOG_NOTICIAS.write_text("\n".join(previas + nuevas) + "\n", encoding="utf-8")
    entraron = sum(r["entro"] for r in registro)
    print(f"Log de noticias -> data/{LOG_NOTICIAS.name} ({len(registro)} notas evaluadas, "
          f"{entraron} entraron; {len(previas)} líneas previas conservadas)")


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


def armar_html(indicadores, argentinas, internacionales, datos_al_envio=False, agenda=None):
    hoy = datetime.now(ZONA_AR).strftime("%d/%m/%Y")
    # Bloque 1.2: si el pipeline de las 7 no dejó datos de hoy y el mail tuvo que correr
    # run.py por su cuenta, se avisa con una línea chica (no es un error para el lector).
    aviso = ('<p style="color:#999;font-size:12px;margin:4px 0 0">Datos actualizados al momento del envío.</p>'
             if datos_al_envio else "")
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

    # Bloque B3 (mail_agenda.py): Dato nuevo, Hoy se publica y Esta semana arriba; Datos demorados
    # después de los indicadores. Sin agenda (None) el mail queda como antes.
    if agenda is None:
        feriado = apertura = calendario = avisos = ""
    else:
        feriado = mail_agenda.html_feriado(agenda)
        apertura = mail_agenda.html_apertura(agenda, DASHBOARD_URL)
        calendario = mail_agenda.html_calendario(agenda)
        avisos = mail_agenda.html_avisos(agenda, DASHBOARD_URL)
    return f"""<div style="font-family:system-ui,Arial,sans-serif;max-width:640px;margin:0 auto;color:#1A1A1A">
      <h2 style="border-bottom:2px solid #1A1A1A;padding-bottom:8px">Coyuntura Argentina · {hoy}</h2>{aviso}{feriado}
      {apertura}{calendario}
      <h3 style="margin-top:22px">Indicadores clave <span style="color:#999;font-weight:400;font-size:13px">(variación vs. 7 días atrás)</span></h3>
      <table style="width:100%;border-collapse:collapse;font-size:14px">{filas_ind}</table>
      {avisos}
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


# --- Bloque 1 de PROMPT_mail_v3.md: frescura de datos + guardia anti-duplicado ---------------
# El workflow del mail ya no corre run.py siempre: lee lo que dejó commiteado coyuntura.yml
# (06:30 AR) y sólo corre run.py como fallback si data/ultima_corrida.json no es de hoy.
# data/mail_enviado.json registra el último envío: si ya es de hoy, no se manda otro (cubre
# el disparo externo + el schedule de respaldo + disparos manuales).
ULTIMA_CORRIDA = RAIZ / "data" / "ultima_corrida.json"
MAIL_ENVIADO = RAIZ / "data" / "mail_enviado.json"


def _hoy_ar():
    return datetime.now(ZONA_AR).date().isoformat()


def _leer_json(ruta):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[aviso] no se pudo leer {ruta.relative_to(RAIZ)}: {e}")
        return {}


def ya_enviado_hoy():
    return _leer_json(MAIL_ENVIADO).get("fecha") == _hoy_ar()


def datos_frescos():
    """(bool, motivo): True si la última corrida completa de run.py es de hoy y trajo datos."""
    uc = _leer_json(ULTIMA_CORRIDA)
    if not uc:
        return False, "no hay data/ultima_corrida.json"
    if uc.get("fecha") != _hoy_ar():
        return False, f"última corrida del {uc.get('fecha')} {uc.get('hora')}, no de hoy"
    if uc.get("estado") == "sin_datos":
        return False, "la corrida de hoy no trajo ningún dato"
    return True, f"corrida de hoy {uc.get('hora')} (estado: {uc.get('estado')})"


def registrar_envio(datos_al_envio, estado_agenda=None):
    """Se llama sólo después de un envío exitoso. `estado_agenda` (Bloque B3, mail_agenda.seleccionar):
    periodos_anunciados / graves_vistos. Se mergea con lo anterior para no perderlo los días en que la
    agenda no está disponible."""
    ahora = datetime.now(ZONA_AR)
    previo = _leer_json(MAIL_ENVIADO)
    datos = {k: previo[k] for k in ("periodos_anunciados", "graves_vistos") if k in previo}
    datos.update(estado_agenda or {})
    datos.update({
        "fecha": ahora.date().isoformat(),
        "hora_envio": ahora.strftime("%H:%M:%S"),
        "zona": "America/Argentina/Buenos_Aires",
        "disparo": os.environ.get("GITHUB_EVENT_NAME", "local"),
        "datos_al_momento_del_envio": datos_al_envio,
    })
    MAIL_ENVIADO.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def estado():
    """Para el workflow: imprime y exporta a $GITHUB_OUTPUT si ya se mandó hoy y si los datos
    commiteados están frescos. No manda nada."""
    enviado = ya_enviado_hoy()
    frescos, motivo = datos_frescos()
    print(f"Disparo: {os.environ.get('GITHUB_EVENT_NAME', 'local')} · "
          f"hora real: {datetime.now(ZONA_AR):%Y-%m-%d %H:%M:%S} AR")
    if enviado:
        print(f"Ya se envió el mail de hoy ({_leer_json(MAIL_ENVIADO).get('hora_envio')}): no se reenvía.")
    print(f"Datos: {'frescos' if frescos else 'VIEJOS'} -- {motivo}")
    if not enviado and not frescos:
        # Sin fallback silencioso: queda como warning visible en el resumen del run.
        print(f"::warning::Datos commiteados viejos ({motivo}): se corre run.py como fallback antes de mandar.")
    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a", encoding="utf-8") as f:
            f.write(f"ya_enviado={'true' if enviado else 'false'}\n")
            f.write(f"datos_frescos={'true' if frescos else 'false'}\n")


def main(dry_run=False):
    print(f"Disparo: {os.environ.get('GITHUB_EVENT_NAME', 'local')} · "
          f"inicio: {datetime.now(ZONA_AR):%Y-%m-%d %H:%M:%S} AR")
    if ya_enviado_hoy() and not dry_run:
        print("Ya se envió el mail de hoy (data/mail_enviado.json): salgo sin enviar.")
        return
    datos_al_envio = os.environ.get("DATOS_AL_ENVIO") == "1"
    df = pd.read_csv(CSV, parse_dates=["fecha"])
    indicadores = resumen_indicadores(df)
    registro = []
    argentinas, internacionales = obtener_noticias(registro=registro)
    vista, estado_agenda = mail_agenda.seleccionar(_leer_json(ULTIMA_CORRIDA), _hoy_ar(), _leer_json(MAIL_ENVIADO))
    html = armar_html(indicadores, argentinas, internacionales, datos_al_envio=datos_al_envio, agenda=vista)
    if dry_run:
        destino = Path(os.environ.get("MAIL_DRY_RUN_HTML", RAIZ / "_mail_preview.html"))
        destino.write_text(html, encoding="utf-8")
        print(f"[dry-run] no se envió ni se registró nada; HTML en {destino} "
              f"({len(registro)} notas evaluadas, log de noticias sin escribir)")
        return
    enviar(html)
    registrar_envio(datos_al_envio, estado_agenda)
    escribir_log_noticias(registro)
    print(f"Hora real de envío: {datetime.now(ZONA_AR):%Y-%m-%d %H:%M:%S} AR")


if __name__ == "__main__":
    if "--estado" in sys.argv:
        estado()
    else:
        main(dry_run="--dry-run" in sys.argv)

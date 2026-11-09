"""FED (Bloque F1): decisiones del FOMC anunciadas y statements/minutas publicados.

Fuentes oficiales (verificadas el 09/11/2026):
  - https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm: un panel por año ("2026 FOMC Meetings")
    con una fila por reunión: mes ("January", "Apr/May") y días ("27-28", "16-17*" con SEP, "30-1" que cruza
    de mes). La decisión es el ÚLTIMO día. Sin hora. Las filas con paréntesis ("22 (notation vote)",
    "(unscheduled)") no son reuniones anunciadas y se saltean.
  - Hora de la decisión: la página del mes (índice https://www.federalreserve.gov/newsevents/calendar.htm;
    los slugs NO siguen un patrón: "2026-november.htm", "2026-04.htm", "2025-11.htm", así que se toma el link
    del índice). Sección "FOMC Meetings", fila "FOMC Meeting": hora ("2:00 p.m.") y día de publicación. Sólo
    existe para el mes actual y el siguiente. Zona: hora del Este de EE.UU. (decisión de Pedro, la página no
    la escribe).
  - Publicados: RSS https://www.federalreserve.gov/feeds/press_monetary.xml (pubDate en GMT, se pasa a ET).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import calendario_externo as X

_RE_ANIO = re.compile(r'<h4>\s*<a id="\d+">\s*(\d{4}) FOMC Meetings\s*</a>\s*</h4>')
_RE_REUNION = re.compile(r'fomc-meeting__month[^>]*>\s*<strong>(.*?)</strong>\s*</div>\s*'
                         r'<div class="fomc-meeting__date[^>]*>(.*?)</div>', re.S)
_RE_DIAS = re.compile(r"(\d{1,2})(?:-(\d{1,2}))?(\*)?(?:\s*\((.+)\))?")
_RE_TITULO_MES = re.compile(r'<div class="row-title[^"]*">\s*<h4[^>]*>\s*([A-Za-z]+) (\d{4})\s*</h4>')
_RE_FILA_MES = re.compile(r'<div class="col-xs-2">\s*<p>(.*?)</p>\s*</div>\s*<div class="col-xs-7">(.*?)</div>\s*'
                          r'<div class="col-xs-3">\s*<p>(.*?)</p>', re.S)
MESES_LARGOS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
                "October", "November", "December"]


def parsear_reuniones(contenido: str, desde_anio: int) -> list[dict]:
    """Decisiones (último día de cada reunión) de los años >= desde_anio."""
    cortes = list(_RE_ANIO.finditer(contenido))
    if not cortes:
        raise X.ExternoFormatoError("FOMC: no se encontraron los paneles '<año> FOMC Meetings'")
    eventos = []
    for k, m in enumerate(cortes):
        anio = int(m.group(1))
        if anio < desde_anio:
            continue
        bloque = contenido[m.end(): cortes[k + 1].start() if k + 1 < len(cortes) else len(contenido)]
        reuniones = _RE_REUNION.findall(bloque)
        if not reuniones:
            raise X.ExternoFormatoError(f"FOMC {anio}: el panel no tiene reuniones (fomc-meeting__month/__date)")
        for mes_txt, dias_txt in reuniones:
            mes_txt, dias_txt = X.texto(mes_txt), X.texto(dias_txt)
            fm = _RE_DIAS.fullmatch(dias_txt)
            if not fm:
                raise X.ExternoFormatoError(f"FOMC {anio}: fecha no reconocida {mes_txt!r} {dias_txt!r}")
            if fm.group(4):
                continue   # "(notation vote)", "(unscheduled)": no es una reunión anunciada
            meses = [X.mes_en(x) for x in mes_txt.split("/")]
            dia = int(fm.group(2) or fm.group(1))
            mes = meses[-1]
            anio_dec = anio + 1 if len(meses) == 2 and meses[1] < meses[0] else anio
            eventos.append({"tipo": "decision", "fecha": date(anio_dec, mes, dia).isoformat(), "hora": None})
    return eventos


def _hora_24(txt: str) -> str:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})\s*([ap])\.?m\.?", X.texto(txt).lower())
    if not m:
        raise X.ExternoFormatoError(f"FED: hora no reconocida {txt!r}")
    h = int(m.group(1)) % 12 + (12 if m.group(3) == "p" else 0)
    return f"{h:02d}:{m.group(2)}"


def parsear_mes(contenido: str, anio: int, mes: int) -> list[dict]:
    """Filas de la sección "FOMC Meetings" de la página del mes: [{evento, hora, fechas}]. Un mes sin esa
    sección devuelve []; un título de mes distinto del pedido es un error."""
    t = _RE_TITULO_MES.search(contenido)
    if not t or (X.mes_en(t.group(1)), int(t.group(2))) != (mes, anio):
        raise X.ExternoFormatoError(f"FED, página de {MESES_LARGOS[mes - 1]} {anio}: título del mes ausente o distinto "
                                    f"({t.group(0) if t else '-'})")
    ini = contenido.find("FOMC Meetings", t.end())
    if ini < 0:
        return []
    fin = contenido.find("cal-nojs__rowTitle", ini)
    seccion = contenido[ini: fin if fin > 0 else len(contenido)]
    filas = []
    for hora, desc, dias in _RE_FILA_MES.findall(seccion):
        ps = [X.texto(p) for p in re.findall(r"<p>(.*?)</p>", desc, re.S)]
        nums = re.findall(r"\d{1,2}", X.texto(dias))
        if not ps or not nums:
            raise X.ExternoFormatoError(f"FED, {MESES_LARGOS[mes - 1]} {anio}: fila de FOMC ilegible ({X.texto(desc)!r})")
        filas.append({"evento": ps[0], "hora": _hora_24(hora),
                      "fechas": [date(anio, mes, int(n)).isoformat() for n in nums]})
    return filas


def link_mes(indice: str, anio: int, mes: int) -> str | None:
    m = re.search(rf'href="([^"]+\.htm)">\s*{MESES_LARGOS[mes - 1]} {anio}\s*</a>', indice)
    return m.group(1) if m else None


def aplicar_horas(eventos: list[dict], filas: list[dict]) -> list[str]:
    """Pone la hora de la fila "FOMC Meeting" en la decisión de ese día. Devuelve avisos si la página del mes
    tiene una reunión en un día que el calendario del FOMC no lista (posible reprogramación)."""
    avisos = []
    por_fecha = {e["fecha"]: e for e in eventos}
    for f in filas:
        if f["evento"] != "FOMC Meeting":
            continue
        fecha = max(f["fechas"])
        if fecha in por_fecha:
            por_fecha[fecha]["hora"] = f["hora"]
        else:
            avisos.append(f"la página del mes de la FED tiene una reunión del FOMC el {fecha} que no figura en "
                          "fomccalendars.htm (¿reprogramada?)")
    return avisos


def bajar_anunciados(org: dict, hoy: date, bajar=X.bajar) -> tuple[list[dict], list[str]]:
    eventos = parsear_reuniones(bajar(org["url"]), hoy.year - 1)
    avisos = []
    try:
        indice = bajar(org["url_indice_mes"])
        for n in (0, 1):
            a, m = X._sumar_meses(hoy, n)
            link = link_mes(indice, a, m)
            if not link:
                if n == 0:
                    avisos.append(f"el índice {org['url_indice_mes']} no tiene link a {MESES_LARGOS[m - 1]} {a}: "
                                  "las decisiones van sin hora")
                continue
            avisos += aplicar_horas(eventos, parsear_mes(bajar(urljoin(org["url_indice_mes"], link)), a, m))
    except Exception as e:   # sin hora no es grave: la fecha sigue siendo la oficial
        avisos.append(f"no se pudo leer la hora de las decisiones ({type(e).__name__}: {e}): van sin hora")
    return eventos, avisos


def parsear_rss(contenido: str, org: dict) -> list[dict]:
    try:
        raiz = ET.fromstring(contenido)
    except ET.ParseError as e:
        raise X.ExternoFormatoError(f"FED: el RSS no es XML válido ({e})")
    items = raiz.findall("./channel/item")
    if not items:
        raise X.ExternoFormatoError("FED: el RSS no tiene ítems")
    zona = ZoneInfo(org["zona"])
    salida = []
    for it in items:
        titulo, link, fecha = (it.findtext("title") or "").strip(), (it.findtext("link") or "").strip(), it.findtext("pubDate")
        if not titulo or not link or not fecha:
            raise X.ExternoFormatoError(f"FED: ítem del RSS incompleto ({titulo!r})")
        for t in org["publicados"]["tipos"]:
            if t["_re"].search(titulo):
                local = parsedate_to_datetime(fecha).astimezone(zona)
                salida.append({"tipo": t["tipo"], "fecha": local.date().isoformat(), "hora": local.strftime("%H:%M"),
                               "url": link, "titulo_fuente": titulo})
                break
    return salida


def bajar_publicados(org: dict, bajar=X.bajar) -> list[dict]:
    return parsear_rss(bajar(org["publicados"]["url"]), org)

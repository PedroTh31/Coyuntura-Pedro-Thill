"""Licitaciones del Tesoro (Secretaría de Finanzas): llamado, licitación y liquidación (pedido de Pedro del
11/11/2026, calendario ampliado del Bloque F1).

Fuentes oficiales (verificadas el 11/11/2026):
  - Anunciados: el "Cronograma de Licitaciones <año>" (PDF anual exportado de Excel). Se llega desde
    https://www.argentina.gob.ar/economia/licitaciones -> página "cronograma-<año>" -> botón "Descargar
    cronograma" (el nombre del PDF no tiene patrón: hoy calendario_prensa_0.pdf). El PDF es un calendario
    PINTADO: el texto sólo trae los números de los días; el tipo de evento sale del color de relleno de la
    celda, según la leyenda del propio PDF (Llamado / Licitación / Liquidación / Feriados). Los colores se
    leen de la leyenda, no se tipean. Sin hora (la fuente no la da).
  - Publicados: https://www.argentina.gob.ar/economia/finanzas/noticias (últimos ~5 ciclos; el listado trae fecha
    y título de cada nota). El llamado dice la fecha de la licitación ("... 14 de octubre de 2026 (T)", la clave
    del ciclo) y la de la liquidación ("(T+2)"), que mandan sobre el cronograma; el resultado de la licitación
    por efectivo se publica el mismo día de la licitación (verificado con los 4 resultados del listado del
    11/11/2026). Las conversiones y demás notas no entran.

Cada evento lleva `ciclo` = fecha de la licitación: calendario_externo une el publicado con el anunciado del
mismo ciclo (no de la misma fecha) y, por decisión A de Pedro (11/11/2026), muestra la fecha REAL de
publicación: el llamado del 11/11/2026 salió el 05/11, el cronograma lo tenía el 09/11 (feriados del 9 y el 10
decretados después del PDF).

Falla ruidosamente (ExternoFormatoError) si el PDF no tiene la leyenda, si una celda pintada no cae en
exactamente un día, si un evento cae en fin de semana, si las cantidades de llamados/licitaciones/
liquidaciones no coinciden o si un ciclo no va en orden llamado < licitación < liquidación.
"""
from __future__ import annotations

import io
import re
from datetime import date

import requests

import calendario_externo as X
from fetchers import HEADERS

BASE = "https://www.argentina.gob.ar"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]
LEYENDA = {"Llamado": "llamado", "Licitación": "licitacion", "Liquidación": "liquidacion"}
ORDEN = ("llamado", "licitacion", "liquidacion")


def _abs(href: str) -> str:
    return href if href.startswith("http") else BASE + href


def _bajar_pdf(url: str, timeout: int = 30) -> bytes:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        raise X.ExternoFormatoError(f"Tesoro: el cronograma {url} no es un PDF (HTTP {r.status_code})")
    return r.content


# ---------------------------------------------------------------------------------------------
# Anunciados: el PDF del cronograma
# ---------------------------------------------------------------------------------------------
def _color(r: dict):
    c = r.get("non_stroking_color")
    return tuple(round(float(x), 3) for x in c) if isinstance(c, (list, tuple)) and len(c) == 3 else None


def parsear_pdf(contenido: bytes, anio: int) -> list[dict]:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        if len(pdf.pages) != 1:
            raise X.ExternoFormatoError(f"Tesoro: el cronograma tiene {len(pdf.pages)} páginas (se esperaba 1)")
        pg = pdf.pages[0]
        palabras = pg.extract_words()
        texto = " ".join(w["text"] for w in palabras)
        if f"Cronograma de Licitaciones {anio}" not in texto:
            raise X.ExternoFormatoError(f"Tesoro: el PDF no dice 'Cronograma de Licitaciones {anio}'")
        rellenos = [r for r in pg.rects if r.get("fill") and _color(r)]
        # Leyenda: el rectángulo de color pegado a la izquierda de cada rótulo, en la misma fila.
        colores = {}
        for w in palabras:
            if w["text"] not in LEYENDA:
                continue
            cerca = [r for r in rellenos if abs(r["top"] - w["top"]) < 15 and 0 <= w["x0"] - r["x1"] < 40
                     and _color(r) != (1.0, 1.0, 1.0)]
            if len(cerca) != 1:
                raise X.ExternoFormatoError(f"Tesoro: no se reconoce el color de '{w['text']}' en la leyenda")
            colores[_color(cerca[0])] = LEYENDA[w["text"]]
        if len(colores) != 3:
            raise X.ExternoFormatoError(f"Tesoro: la leyenda no tiene los 3 colores esperados ({sorted(colores.values())})")
        tope_leyenda = max(w["bottom"] for w in palabras if w["text"] in LEYENDA)
        # encabezados de mes = los que tienen la fila "Do. Lu. ..." justo debajo (un nombre de mes también
        # aparece en los feriados: "Día de la Revolución de Mayo")
        encabezado = [w for w in palabras if w["text"] == "Do."]
        meses = [(w, MESES.index(w["text"].lower()) + 1) for w in palabras if w["text"].lower() in MESES
                 and any(0 < d["top"] - w["top"] < 25 and abs(d["x0"] - w["x0"]) < 120 for d in encabezado)]
        if len(meses) != 12:
            raise X.ExternoFormatoError(f"Tesoro: el cronograma tiene {len(meses)} meses (se esperaban 12)")
        eventos = []
        for r in rellenos:
            tipo = colores.get(_color(r))
            if not tipo or r["top"] <= tope_leyenda:
                continue
            dias = [w for w in palabras if w["text"].isdigit() and w["x0"] >= r["x0"] - 1 and w["x1"] <= r["x1"] + 1
                    and w["top"] >= r["top"] - 1 and w["bottom"] <= r["bottom"] + 1]
            cx, cy = (r["x0"] + r["x1"]) / 2, (r["top"] + r["bottom"]) / 2
            # el mes es el encabezado más cercano por encima, en la misma columna del calendario
            arriba = [(w, m) for w, m in meses if w["top"] < cy and abs((w["x0"] + w["x1"]) / 2 - cx) < 115]
            if len(dias) != 1 or not arriba:
                raise X.ExternoFormatoError(f"Tesoro: una celda de '{tipo}' no cae en exactamente un día "
                                            f"({[w['text'] for w in dias]}, x={cx:.0f}, y={cy:.0f})")
            mes = max(arriba, key=lambda t: t[0]["top"])[1]
            try:
                d = date(anio, mes, int(dias[0]["text"]))
            except ValueError as e:
                raise X.ExternoFormatoError(f"Tesoro: fecha inválida en el cronograma ({e})") from e
            if d.weekday() >= 5:
                raise X.ExternoFormatoError(f"Tesoro: {tipo} el {d:%d/%m/%Y}, un fin de semana")
            eventos.append((d, tipo))
    return armar_ciclos(eventos, anio)


def armar_ciclos(eventos: list[tuple[date, str]], anio: int) -> list[dict]:
    """[(fecha, tipo)] -> eventos con `ciclo` (fecha de la licitación), validando el orden de cada ciclo."""
    por_tipo = {t: sorted(d for d, tt in eventos if tt == t) for t in ORDEN}
    cantidades = {t: len(v) for t, v in por_tipo.items()}
    if len(set(cantidades.values())) != 1 or not cantidades["licitacion"]:
        raise X.ExternoFormatoError(f"Tesoro: el cronograma {anio} no cierra en ciclos completos ({cantidades})")
    salida = []
    for i, (ll, li, lq) in enumerate(zip(*(por_tipo[t] for t in ORDEN))):
        if not ll < li < lq:
            raise X.ExternoFormatoError(f"Tesoro: el ciclo {i + 1} del cronograma {anio} no va en orden "
                                        f"llamado < licitación < liquidación ({ll}, {li}, {lq})")
        if i and ll <= por_tipo["licitacion"][i - 1]:
            raise X.ExternoFormatoError(f"Tesoro: el llamado del {ll:%d/%m} es anterior a la licitación previa "
                                        f"({por_tipo['licitacion'][i - 1]:%d/%m}) en el cronograma {anio}")
        ciclo = li.isoformat()
        salida += [{"tipo": t, "fecha": d.isoformat(), "hora": None, "ciclo": ciclo}
                   for t, d in zip(ORDEN, (ll, li, lq))]
    return salida


def cronogramas(landing: str, hoy: date) -> dict[int, str]:
    """{año: URL de la página 'cronograma-<año>'} de los años >= el actual que linkea la página general."""
    anios = {int(a): _abs(h) for h, a in re.findall(r'href="([^"]*/cronograma-(\d{4}))"', landing)}
    if hoy.year not in anios:
        raise X.ExternoFormatoError(f"Tesoro: la página de licitaciones no linkea el cronograma {hoy.year}")
    return {a: u for a, u in sorted(anios.items()) if a >= hoy.year}


def url_pdf(pagina: str) -> str:
    links = re.findall(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>\s*Descargar cronograma', pagina)
    if len(links) != 1:
        raise X.ExternoFormatoError(f"Tesoro: la página del cronograma no tiene un único 'Descargar cronograma' ({links})")
    return _abs(links[0])


def bajar_anunciados(org: dict, hoy: date, bajar=X.bajar, bajar_pdf=_bajar_pdf) -> tuple[list[dict], list[str]]:
    eventos = []
    for anio, url in cronogramas(bajar(org["url"]), hoy).items():
        eventos += parsear_pdf(bajar_pdf(url_pdf(bajar(url))), anio)
    return eventos, []


# ---------------------------------------------------------------------------------------------
# Publicados: llamados y resultados en las noticias de Finanzas
# ---------------------------------------------------------------------------------------------
def _fecha_es(txt: str) -> date:
    m = re.fullmatch(r"(\d{1,2}) de ([a-záéíóú]+) de (\d{4})", txt.strip().lower())
    if not m or m.group(2) not in MESES:
        raise X.ExternoFormatoError(f"Tesoro: fecha no reconocida en el listado de noticias {txt!r}")
    return date(int(m.group(3)), MESES.index(m.group(2)) + 1, int(m.group(1)))


def listado(contenido: str) -> list[dict]:
    """[{url, fecha, titulo}] de las notas del listado de noticias de Finanzas."""
    notas = []
    for href, cuerpo in re.findall(r'<a href="(/noticias/[^"]+)" class="panel panel-default">(.*?)</a>', contenido, re.S):
        t = X.texto(cuerpo)
        m = re.match(r"(\d{1,2} de [a-záéíóú]+ de \d{4})\s+(.+)", t, re.I)
        if not m:
            raise X.ExternoFormatoError(f"Tesoro: nota del listado sin fecha y título ({t[:80]!r})")
        notas.append({"url": _abs(href), "fecha": _fecha_es(m.group(1)), "titulo": m.group(2)})
    if not notas:
        raise X.ExternoFormatoError("Tesoro: el listado de noticias de Finanzas no trae notas")
    return notas


def fechas_llamado(contenido: str) -> tuple[date, date]:
    """(licitación, liquidación) que anuncia un llamado. El texto de los 5 llamados del listado del 11/11/2026
    dice "... del día miércoles 14 de octubre de 2026 (T)" y "Fecha de liquidación 16 de octubre de 2026 (T+2)".
    Si la página trae además la fecha de la licitación en el adjunto ("comunicado_llamado_20261111_1.pdf") o en
    su rótulo ("Llamado a licitación 11/11/2026"), tienen que coincidir."""
    t = X.texto(re.sub(r"<(script|style).*?</\1>", "", contenido, flags=re.S))
    lic = {_fecha_es(f) for f in re.findall(r"(\d{1,2} de [a-záéíóú]+ de \d{4}) \(T\)", t, re.I)}
    liq = {_fecha_es(f) for f in re.findall(r"(\d{1,2} de [a-záéíóú]+ de \d{4}) \(T\+\d\)", t, re.I)}
    if len(lic) != 1 or len(liq) != 1:
        raise X.ExternoFormatoError(f"Tesoro: el llamado no dice una única fecha de licitación (T) y de liquidación "
                                    f"(T+n) ({sorted(lic)}, {sorted(liq)})")
    lic, liq = lic.pop(), liq.pop()
    otras = {date(int(a), int(m), int(d)) for a, m, d in re.findall(r"comunicado_llamado_(\d{4})(\d{2})(\d{2})", contenido)}
    otras |= {date(int(a), int(m), int(d)) for d, m, a in re.findall(r"Llamado a licitaci(?:ó|&oacute;)n (\d{2})/(\d{2})/(\d{4})", t)}
    if otras - {lic} or not lic < liq:
        raise X.ExternoFormatoError(f"Tesoro: fechas del llamado que no coinciden (licitación {lic}, liquidación {liq}, "
                                    f"adjunto/rótulo {sorted(otras)})")
    return lic, liq


def bajar_publicados(org: dict, bajar=X.bajar) -> list[dict]:
    pub = org["publicados"]
    items = []
    for nota in listado(bajar(pub["url"])):
        tipo = next((t["tipo"] for t in pub["tipos"] if t["_re"].search(nota["titulo"])), None)
        if not tipo:
            continue
        item = {"tipo": tipo, "fecha": nota["fecha"].isoformat(), "hora": None, "url": nota["url"],
                "titulo_fuente": nota["titulo"]}
        if tipo == "llamado":
            lic, liq = fechas_llamado(bajar(nota["url"]))
            # decisión A de Pedro: lo que dice el llamado manda sobre el cronograma para su ciclo
            item.update(ciclo=lic.isoformat(), fechas_ciclo={"licitacion": lic.isoformat(), "liquidacion": liq.isoformat()})
        else:
            item["ciclo"] = nota["fecha"].isoformat()   # el resultado sale el mismo día de la licitación
        items.append(item)
    if not items:
        raise X.ExternoFormatoError("Tesoro: el listado de noticias no trae ningún llamado ni resultado de licitación")
    return items

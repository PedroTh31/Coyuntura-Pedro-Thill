"""BCE (Bloque F1): decisiones de política monetaria anunciadas.

Fuente oficial (verificada el 09/11/2026): https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html,
lista <dt>dd/mm/aaaa</dt><dd>descripción</dd> con TODAS las reuniones (también no monetarias y del General
Council) hasta fines de 2028. Entra sólo lo que matchea la regex del yaml: el día 2 de la reunión de política
monetaria ("... monetary policy meeting in Frankfurt (Day 2), followed by press conference"). Sin hora.
"""
from __future__ import annotations

import re
from datetime import date, datetime

import calendario_externo as X

_RE_PAR = re.compile(r"<dt>\s*(.*?)\s*</dt>\s*<dd>(.*?)</dd>", re.S)


def parsear(contenido: str, org: dict) -> list[dict]:
    pares = _RE_PAR.findall(contenido)
    if not pares:
        raise X.ExternoFormatoError("BCE: la página no tiene la lista de reuniones (<dt>/<dd>)")
    eventos = []
    for fecha_txt, desc in pares:
        fecha_txt, desc = X.texto(fecha_txt), X.texto(desc)
        try:
            fecha = datetime.strptime(fecha_txt, "%d/%m/%Y").date()
        except ValueError:
            raise X.ExternoFormatoError(f"BCE: fecha no reconocida {fecha_txt!r} ({desc!r})")
        for ev in org["eventos"]:
            if ev["_re"].search(desc):
                eventos.append({"tipo": ev["tipo"], "fecha": fecha.isoformat(), "hora": None})
                break
    if not eventos:
        raise X.ExternoFormatoError("BCE: ninguna fila matchea las reuniones de política monetaria (¿cambió el texto?)")
    return eventos


def bajar_anunciados(org: dict, hoy: date, bajar=X.bajar) -> tuple[list[dict], list[str]]:
    return parsear(bajar(org["url"]), org), []

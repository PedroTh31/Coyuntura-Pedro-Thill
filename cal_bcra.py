"""BCRA (Bloque F1): fechas anunciadas del IPOM y del REM.

Fuente oficial (verificada el 09/11/2026): https://www.bcra.gob.ar/calendario-de-informes/, una tabla
"Publicaciones | Fecha" ("Relevamiento de Expectativas de Mercado (REM)" | "07 ene 2026"). Sin hora (la nota
al pie "Se publica al cierre del día hábil" no dice a qué filas aplica). El IPOM figura con dos nombres
("Informe de Política Monetaria (IPOM)" e "Informe de Política Monetaria"): la regex del yaml toma los dos.
Al 09/11/2026 la tabla llega sólo hasta dic-2026 (sin el REM de diciembre ni 2027): lo avisa
verificar_calendario.py (sin fechas futuras), nunca se estima.
"""
from __future__ import annotations

import re
from datetime import date

import calendario_externo as X

MESES_ES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "set": 9,
            "oct": 10, "nov": 11, "dic": 12}


def _fecha(txt: str) -> date:
    m = re.fullmatch(r"(\d{1,2}) ([a-z]{3})[a-z]*\.? (\d{4})", txt.lower())
    if not m or m.group(2) not in MESES_ES:
        raise X.ExternoFormatoError(f"BCRA: fecha no reconocida {txt!r}")
    return date(int(m.group(3)), MESES_ES[m.group(2)], int(m.group(1)))


def parsear(contenido: str, org: dict) -> list[dict]:
    t = re.search(r"<table[^>]*>(.*?)</table>", contenido, re.S)
    if not t:
        raise X.ExternoFormatoError("BCRA: la página no tiene la tabla del calendario de informes")
    filas = [[X.texto(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", f, re.S)]
             for f in re.findall(r"<tr[^>]*>(.*?)</tr>", t.group(1), re.S)]
    if not filas or filas[0][:2] != ["Publicaciones", "Fecha"]:
        raise X.ExternoFormatoError(f"BCRA: encabezado de la tabla distinto de 'Publicaciones | Fecha' ({filas[:1]})")
    eventos = []
    for fila in filas[1:]:
        if len(fila) < 2:
            raise X.ExternoFormatoError(f"BCRA: fila incompleta {fila!r}")
        nombre, fecha = fila[0], _fecha(fila[1])
        for ev in org["eventos"]:
            if ev["_re"].search(nombre):
                eventos.append({"tipo": ev["tipo"], "fecha": fecha.isoformat(), "hora": None})
                break
    if not eventos:
        raise X.ExternoFormatoError("BCRA: ninguna fila es del REM ni del IPOM (¿cambiaron los nombres?)")
    return eventos


def bajar_anunciados(org: dict, hoy: date, bajar=X.bajar) -> tuple[list[dict], list[str]]:
    return parsear(bajar(org["url"]), org), []

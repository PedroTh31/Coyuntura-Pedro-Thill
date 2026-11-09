"""BoE (Bloque F1): anuncios de Bank Rate.

Fuente oficial (verificada el 09/11/2026): https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates,
un <h2>"<año> confirmed dates"</h2> + tabla por año; cada fila es un anuncio de Bank Rate ("Thursday 5
February" | "February MPC Summary and minutes ..."). El año sale del encabezado; el día de la semana escrito se
controla contra la fecha armada (si no coincide, el año o el formato cambiaron). Sin hora.
"""
from __future__ import annotations

import re
from datetime import date

import calendario_externo as X

_RE_ANIO = re.compile(r"<h2>\s*(\d{4}) confirmed dates\s*</h2>\s*<table>(.*?)</table>", re.S)
DIAS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def parsear(contenido: str, org: dict) -> list[dict]:
    bloques = _RE_ANIO.findall(contenido)
    if not bloques:
        raise X.ExternoFormatoError("BoE: no se encontraron las tablas '<año> confirmed dates'")
    tipo = org["eventos"][0]["tipo"]
    eventos = []
    for anio, tabla in bloques:
        n = 0
        for fila in re.findall(r"<tr>(.*?)</tr>", tabla, re.S):
            celdas = [X.texto(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", fila, re.S)]
            if len(celdas) < 2 or "MPC" not in celdas[1]:
                continue
            m = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2})\s+([A-Za-z]+)", celdas[0])
            if not m:
                raise X.ExternoFormatoError(f"BoE {anio}: fecha no reconocida {celdas[0]!r}")
            fecha = date(int(anio), X.mes_en(m.group(3)), int(m.group(2)))
            if DIAS[fecha.weekday()] != m.group(1).lower():
                raise X.ExternoFormatoError(f"BoE {anio}: '{celdas[0]}' no cae {m.group(1)} ({fecha})")
            eventos.append({"tipo": tipo, "fecha": fecha.isoformat(), "hora": None})
            n += 1
        if not n:
            raise X.ExternoFormatoError(f"BoE {anio}: la tabla no tiene anuncios del MPC")
    return eventos


def bajar_anunciados(org: dict, hoy: date, bajar=X.bajar) -> tuple[list[dict], list[str]]:
    return parsear(bajar(org["url"]), org), []

"""BoJ (Bloque F1): decisiones de política monetaria anunciadas.

Fuente oficial (verificada el 09/11/2026): https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm, una tabla por
año ("Table : 2026") cuya primera columna, "Date of MPM", trae los días de la reunión: "Jan. 22 (Thurs.), 23
(Fri.) [PDF 171KB]". La decisión es el ÚLTIMO día ("released immediately after", sin hora: va sin hora). El
mes se arrastra entre días ("Apr. 30 (Thu.), May 1 (Fri.)" también se lee bien).
"""
from __future__ import annotations

import re
from datetime import date

import calendario_externo as X

_RE_TABLA = re.compile(r"<caption[^>]*>\s*Table\s*:\s*(\d{4})\s*</caption>(.*?)</table>", re.S)
_RE_DIA = re.compile(r"(?:([A-Z][a-z]{2,4})\.?\s+)?(\d{1,2})\s*\(")


def parsear(contenido: str, org: dict) -> list[dict]:
    tablas = _RE_TABLA.findall(contenido)
    if not tablas:
        raise X.ExternoFormatoError("BoJ: no se encontraron las tablas 'Table : <año>'")
    tipo = org["eventos"][0]["tipo"]
    eventos = []
    for anio, tabla in tablas:
        cuerpo = tabla.split("<tbody>", 1)[-1]
        filas = 0
        for fila in re.findall(r"<tr>(.*?)</tr>", cuerpo, re.S):
            celdas = re.findall(r"<td[^>]*>(.*?)</td>", fila, re.S)
            if not celdas:
                continue
            txt = re.sub(r"\[PDF[^\]]*\]", "", X.texto(celdas[0]))
            mes, dia = None, None
            for m, d in _RE_DIA.findall(txt):
                if m:
                    mes = X.mes_en(m)
                dia = int(d)
            if mes is None or dia is None:
                raise X.ExternoFormatoError(f"BoJ {anio}: fecha de reunión no reconocida {txt!r}")
            eventos.append({"tipo": tipo, "fecha": date(int(anio), mes, dia).isoformat(), "hora": None})
            filas += 1
        if not filas:
            raise X.ExternoFormatoError(f"BoJ {anio}: la tabla no tiene reuniones")
    return eventos


def bajar_anunciados(org: dict, hoy: date, bajar=X.bajar) -> tuple[list[dict], list[str]]:
    return parsear(bajar(org["url"]), org), []

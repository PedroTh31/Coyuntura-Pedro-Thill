"""Calendario de difusión del INDEC (Bloque B de PROMPT_ronda_macro_indec.md).

Fuente: la página oficial del calendario, https://www.indec.gob.ar/indec/web/Calendario-Fecha-0,
arma la grilla de cada mes pidiendo un fragmento HTML a
    https://www.indec.gob.ar/Calendario/FiltrosCalendario/mes/{Mes}-{AAAA}/0
(Scripts/CalendarioFull.js, función MesSelect: `{Mes}` con mayúscula inicial, ej. "Noviembre-2026";
el 0 final es el idioma, español). NO es una API documentada: devuelve HTML. Por eso este parser
falla RUIDOSAMENTE (CalendarioFormatoError) ante cualquier cosa que no reconozca, en vez de
devolver una lista vacía que se confundiría con "ese mes no hay publicaciones":
  - HTTP distinto de 200, o el encabezado del mes ("mes-ano") ausente o de otro mes;
  - un bloque de día sin número/nombre de día válido;
  - títulos y horarios desparejos dentro de un día, o un horario que no es "HH:MMhs";
  - 0 publicaciones en un mes que debería tenerlas (`exigir_publicaciones=True`).
El servidor del INDEC rechaza navegadores headless (HTTP 500 de su firewall) pero acepta
pedidos simples con requests.
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yaml

from fetchers import HEADERS

ZONA_AR = ZoneInfo("America/Argentina/Buenos_Aires")

URL_PAGINA = "https://www.indec.gob.ar/indec/web/Calendario-Fecha-0"
URL_MES = "https://www.indec.gob.ar/Calendario/FiltrosCalendario/mes/{mes}-{anio}/0"
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
         "Septiembre", "Octubre", "Noviembre", "Diciembre"]
DIAS = {"LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"}
SIN_PUBLICACIONES = "No hay publicaciones en la fecha seleccionada"

_RE_MES_ANO = re.compile(r'<div class="mes-ano">\s*(.*?)\s*</div>', re.S)
_RE_NRO_DIA = re.compile(r'<div class="nro-dia">\s*(.*?)\s*</div>\s*<div class="dia">\s*(.*?)\s*</div>', re.S)
_RE_TITULO = re.compile(r'<div class="cal-content text-calendario">\s*(.*?)\s*</div>', re.S)
_RE_HORA = re.compile(r'<div class="cal-content text-calendario text-center">\s*(.*?)\s*</div>', re.S)


class CalendarioFormatoError(RuntimeError):
    """El HTML del calendario no tiene el formato esperado (o vino vacío cuando no debía)."""


@dataclass(frozen=True)
class Publicacion:
    fecha: date
    hora: str      # "16:00"
    titulo: str    # tal como lo publica el INDEC, ej. "Índice de precios al consumidor (IPC). ... Octubre de 2026"


def _texto(fragmento: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragmento))).strip()


def parsear_mes(contenido: str, anio: int, mes: int, exigir_publicaciones: bool = False) -> list[Publicacion]:
    """Parsea el fragmento HTML de un mes. Ver el docstring del módulo para las validaciones."""
    esperado = f"{MESES[mes - 1]} {anio}"
    if SIN_PUBLICACIONES in contenido and "nro-dia" not in contenido:
        if exigir_publicaciones:
            raise CalendarioFormatoError(f"{esperado}: el calendario del INDEC no tiene publicaciones cargadas")
        return []
    encabezado = _RE_MES_ANO.search(contenido)
    if not encabezado:
        raise CalendarioFormatoError(f"{esperado}: no se encontró el encabezado del mes (div.mes-ano); "
                                     "¿cambió el formato del calendario?")
    if _texto(encabezado.group(1)).lower() != esperado.lower():
        raise CalendarioFormatoError(f"se pidió {esperado} y el calendario devolvió '{_texto(encabezado.group(1))}'")

    cortes = [m.start() for m in re.finditer(r'<div class="nro-dia">', contenido)]
    if not cortes:
        raise CalendarioFormatoError(f"{esperado}: hay encabezado de mes pero ningún bloque de día (div.nro-dia)")
    publicaciones = []
    for k, ini in enumerate(cortes):
        bloque = contenido[ini: cortes[k + 1] if k + 1 < len(cortes) else len(contenido)]
        m = _RE_NRO_DIA.match(bloque)
        if not m or not m.group(1).isdigit() or _texto(m.group(2)).upper() not in DIAS:
            raise CalendarioFormatoError(f"{esperado}: bloque de día ilegible: {_texto(bloque)[:80]!r}")
        dia = date(anio, mes, int(m.group(1)))   # ValueError si el día no existe en el mes
        titulos = [_texto(t) for t in _RE_TITULO.findall(bloque)]
        horas = [_texto(h) for h in _RE_HORA.findall(bloque)]
        if not titulos or len(titulos) != len(horas):
            raise CalendarioFormatoError(f"{esperado}, día {dia.day}: {len(titulos)} títulos y {len(horas)} horarios")
        for titulo, hora in zip(titulos, horas):
            mh = re.fullmatch(r"(\d{1,2}):(\d{2})\s*hs", hora)
            if not mh or not titulo:
                raise CalendarioFormatoError(f"{esperado}, día {dia.day}: horario o título inválido ({hora!r}, {titulo!r})")
            publicaciones.append(Publicacion(dia, f"{int(mh.group(1)):02d}:{mh.group(2)}", titulo))
    if exigir_publicaciones and not publicaciones:
        raise CalendarioFormatoError(f"{esperado}: 0 publicaciones")
    return publicaciones


def bajar_mes(anio: int, mes: int, exigir_publicaciones: bool = False, timeout: int = 30) -> list[Publicacion]:
    url = URL_MES.format(mes=MESES[mes - 1], anio=anio)
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    if r.status_code != 200:
        raise CalendarioFormatoError(f"{MESES[mes - 1]} {anio}: HTTP {r.status_code} desde {url}")
    r.encoding = r.encoding or "utf-8"
    return parsear_mes(r.text, anio, mes, exigir_publicaciones)


def _sumar_meses(anio: int, mes: int, n: int) -> tuple[int, int]:
    k = anio * 12 + (mes - 1) + n
    return k // 12, k % 12 + 1


# ---------------------------------------------------------------------------------------------
# Configuración (calendario.yaml) + caché con fallback (data/calendario_indec.json)
# ---------------------------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent
CONFIG = RAIZ / "calendario.yaml"
CACHE = RAIZ / "data" / "calendario_indec.json"
# Meses en los que el INDEC SIEMPRE tiene publicaciones cargadas (carga ~10 meses por adelantado):
# el actual y los 2 siguientes. Si alguno viene vacío, es un error (no "ese mes no hay nada").
MESES_EXIGIDOS = 3


def cargar_config(ruta: Path = CONFIG) -> dict:
    cfg = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    for p in cfg["publicaciones"]:
        p["_re"] = re.compile(p["titulo_regex"])
        if "periodo" not in p["_re"].groupindex:
            raise ValueError(f"calendario.yaml: el titulo_regex de '{p['id']}' no tiene el grupo (?P<periodo>...)")
    return cfg


def _clave_mes(anio: int, mes: int) -> str:
    return f"{anio}-{mes:02d}"


def _a_dict(p: Publicacion) -> dict:
    return {"fecha": p.fecha.isoformat(), "hora": p.hora, "titulo": p.titulo}


def _de_dict(d: dict) -> Publicacion:
    return Publicacion(date.fromisoformat(d["fecha"]), d["hora"], d["titulo"])


def cargar_cache(ruta: Path = CACHE) -> dict:
    if ruta.exists():
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"meses": {}}


def obtener_publicaciones(hoy: date, meses_a_bajar: int, cache: dict | None = None,
                          bajar=bajar_mes) -> tuple[list[Publicacion], dict, list[str]]:
    """Baja el mes actual y los siguientes. Si un mes falla, usa el último caché válido de ese mes
    (marcado como tal en `estado`). Devuelve (publicaciones, estado por mes, errores) y actualiza
    `cache` en el lugar (sólo con descargas exitosas: un mes fallido nunca pisa uno válido)."""
    cache = cache if cache is not None else cargar_cache()
    pubs, estado, errores = [], {}, []
    ahora = datetime.now(ZONA_AR).isoformat(timespec="seconds")
    for n in range(meses_a_bajar):
        a, m = _sumar_meses(hoy.year, hoy.month, n)
        k = _clave_mes(a, m)
        try:
            del_mes = bajar(a, m, exigir_publicaciones=n < MESES_EXIGIDOS)
            cache["meses"][k] = {"bajado": ahora, "publicaciones": [_a_dict(p) for p in del_mes]}
            estado[k] = {"fuente": "endpoint", "bajado": ahora}
        except Exception as e:
            errores.append(f"{MESES[m - 1]} {a}: {type(e).__name__}: {e}")
            previo = cache["meses"].get(k)
            if previo is None:
                estado[k] = {"fuente": "sin_datos"}
                continue
            del_mes = [_de_dict(d) for d in previo["publicaciones"]]
            estado[k] = {"fuente": "cache", "bajado": previo["bajado"]}
        pubs.extend(del_mes)
    return pubs, estado, errores


def guardar_cache(cache: dict, ruta: Path = CACHE):
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def asignar(pubs: list[Publicacion], cfg: dict) -> tuple[dict[str, list[dict]], list[str]]:
    """{id de publicación: [{fecha, hora, periodo, titulo}, ...]} ordenado por fecha. Un título que
    matchea dos patrones es un error de configuración (se reporta, no se asigna a ninguno)."""
    por_id = {p["id"]: [] for p in cfg["publicaciones"]}
    errores = []
    for pub in pubs:
        hits = [(p["id"], m) for p in cfg["publicaciones"] if (m := p["_re"].match(pub.titulo))]
        if len(hits) > 1:
            errores.append(f"'{pub.titulo}' matchea varios patrones: {[h[0] for h in hits]}")
        elif hits:
            pid, m = hits[0]
            por_id[pid].append({"fecha": pub.fecha.isoformat(), "hora": pub.hora,
                                "periodo": m.group("periodo"), "titulo": pub.titulo})
    for lista in por_id.values():
        lista.sort(key=lambda d: (d["fecha"], d["hora"]))
    return por_id, errores


def faltantes_en_ventana(asignadas: dict, cfg: dict, hoy: date) -> list[str]:
    """Publicaciones sin ninguna fecha en el mes actual ni en sus `meses_siguientes_alerta`
    siguientes (posible cambio de título en el calendario del INDEC)."""
    faltan = []
    for p in cfg["publicaciones"]:
        fin_a, fin_m = _sumar_meses(hoy.year, hoy.month, p["meses_siguientes_alerta"])
        desde, hasta = _clave_mes(hoy.year, hoy.month), _clave_mes(fin_a, fin_m)
        if not any(desde <= d["fecha"][:7] <= hasta for d in asignadas.get(p["id"], [])):
            faltan.append(p["id"])
    return faltan


# ---------------------------------------------------------------------------------------------
# Días hábiles (feriados de calendario.yaml: los días en que no operan INDEC, BCRA y BYMA)
# ---------------------------------------------------------------------------------------------
def feriados(cfg: dict) -> set[date]:
    return {date.fromisoformat(f["fecha"]) for anio in cfg["feriados"].values() for f in anio["fechas"]}


def es_habil(d: date, no_habiles: set[date]) -> bool:
    return d.weekday() < 5 and d not in no_habiles


def sumar_dias_habiles(d: date, n: int, no_habiles: set[date]) -> date:
    """El n-ésimo día hábil posterior a `d` (n >= 1)."""
    while n > 0:
        d += timedelta(days=1)
        if es_habil(d, no_habiles):
            n -= 1
    return d


if __name__ == "__main__":
    # Prueba de conectividad y formato (la usa el workflow temporal de prueba). Exige
    # publicaciones en el mes actual y los 2 siguientes: el INDEC carga ~10 meses por adelantado.
    import sys
    hoy = date.today()
    errores = 0
    for n in range(3):
        a, m = _sumar_meses(hoy.year, hoy.month, n)
        try:
            pubs = bajar_mes(a, m, exigir_publicaciones=True)
            print(f"OK  {MESES[m - 1]} {a}: {len(pubs)} publicaciones")
            for p in pubs[:3]:
                print(f"      {p.fecha} {p.hora}  {p.titulo}")
        except Exception as e:
            errores += 1
            print(f"::error title=Calendario INDEC::{type(e).__name__}: {e}")
    sys.exit(1 if errores else 0)

"""Calendario ampliado (Bloque F1, decisiones de Pedro del 09/11/2026): eventos de otros organismos que no
alimentan series del dashboard (decisiones de tasa de la FED, el BCE, el BoJ y el BoE; IPOM y REM del BCRA).

Configuración en el bloque `externos:` de calendario.yaml. Un parser por organismo (cal_fed.py, cal_bce.py,
cal_boj.py, cal_boe.py, cal_bcra.py), cada uno con `bajar_anunciados(org, hoy) -> (eventos, avisos)`; la FED
además `bajar_publicados(org)` (RSS oficial). Igual que calendario_indec.py, los parsers fallan RUIDOSAMENTE
(ExternoFormatoError) ante un formato que no reconocen: nunca devuelven una lista vacía en silencio.

Modelo:
  - anunciado: {tipo, fecha, hora|None} en hora LOCAL del organismo (`zona` del yaml);
  - publicado: {tipo, fecha, hora, url, titulo_fuente}, también en hora local;
  - un publicado se une con el anunciado del mismo organismo, tipo y fecha local (ej. el statement del FOMC
    con la decisión de ese día) y queda un solo evento `publicado` con link. Un anunciado pasado sin
    publicación queda `anunciado` (decisión B4 de Pedro: sin link y sin afirmar que pasó).
  - `ciclo` (opcional, hoy sólo el Tesoro): si los eventos lo traen, el publicado se une con el anunciado del
    mismo tipo y CICLO (no de la misma fecha) y queda la fecha real de publicación (decisión A de Pedro,
    11/11/2026: el llamado del 11/11 salió el 05/11 y el cronograma decía 09/11). El título puede llevar
    "{ciclo}" (DD/MM del ciclo) y cada evento tiene `link`: su propia página si se publicó; si no, la página
    publicada más reciente de su ciclo; si no, `url_general` del yaml (None si el organismo no la declara).
  - la hora se muestra en AR con la local entre paréntesis, "16:00 AR (14:00 ET)" (zoneinfo, con horario de
    verano). Sin hora en la fuente, sin hora: nunca estimada.

Caché: data/calendario_externo.json. Una descarga fallida nunca pisa lo guardado; los anunciados pasados
se conservan aunque la fuente ya no los liste (el BCE sólo muestra fechas futuras) y los publicados se
acumulan (el RSS de la FED es una ventana móvil de 15 ítems).
"""
from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

import calendario_indec as C
from fetchers import HEADERS

CACHE = C.RAIZ / "data" / "calendario_externo.json"
MESES_EN = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


class ExternoFormatoError(RuntimeError):
    """La página de un organismo no tiene el formato esperado (o no trajo lo que debía)."""


# ---------------------------------------------------------------------------------------------
# Utilidades de los parsers
# ---------------------------------------------------------------------------------------------
def texto(fragmento: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragmento))).strip()


def mes_en(nombre: str) -> int:
    """'Jan.', 'January', 'Sept.' -> número de mes. ExternoFormatoError si no es un mes en inglés."""
    k = nombre.strip().rstrip(".").lower()[:3]
    if k not in MESES_EN:
        raise ExternoFormatoError(f"mes no reconocido: {nombre!r}")
    return MESES_EN.index(k) + 1


def bajar(url: str, timeout: int = 30) -> str:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    if r.status_code != 200:
        raise ExternoFormatoError(f"HTTP {r.status_code} desde {url}")
    if "charset" not in r.headers.get("Content-Type", "").lower():
        return r.content.decode("utf-8", errors="replace")   # requests asumiría ISO-8859-1
    return r.text


def _sumar_meses(d: date, n: int) -> tuple[int, int]:
    return C._sumar_meses(d.year, d.month, n)


# ---------------------------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------------------------
def organismos(cfg: dict) -> list[dict]:
    """El bloque `externos:` de calendario.yaml con las regex compiladas (`_re`)."""
    orgs = []
    for org in cfg.get("externos") or []:
        org = dict(org)
        org["eventos"] = [dict(e, _re=re.compile(e["regex"]) if e.get("regex") else None) for e in org["eventos"]]
        if org.get("publicados"):
            pub = dict(org["publicados"])
            pub["tipos"] = [dict(t, _re=re.compile(t["regex"])) for t in pub["tipos"]]
            org["publicados"] = pub
        orgs.append(org)
    return orgs


def _modulos() -> dict:
    import cal_bce
    import cal_bcra
    import cal_boe
    import cal_boj
    import cal_fed
    import cal_tesoro
    return {"fed": cal_fed, "bce": cal_bce, "boj": cal_boj, "boe": cal_boe, "bcra": cal_bcra, "tesoro": cal_tesoro}


# ---------------------------------------------------------------------------------------------
# Caché
# ---------------------------------------------------------------------------------------------
def cargar_cache(ruta: Path = CACHE) -> dict:
    if ruta.exists():
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"anunciados": {}, "publicados": {}}


def guardar_cache(cache: dict, ruta: Path = CACHE):
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _orden(e: dict):
    return (e["fecha"], e.get("hora") or "99:99", e["tipo"])


def fusionar_anunciados(previos: list[dict], nuevos: list[dict], hoy: date) -> list[dict]:
    """Lo nuevo manda. Se conservan los anunciados PASADOS que la fuente ya no lista (y la hora que se
    conocía de un evento si la descarga nueva no la trae: la página del mes de la FED sólo existe para el
    mes actual y el siguiente). Un evento futuro que desapareció de la fuente (reprogramado) se va."""
    previo = {(e["tipo"], e["fecha"]): e for e in previos}
    salida = []
    for e in nuevos:
        v = previo.get((e["tipo"], e["fecha"]))
        salida.append(dict(e, hora=v["hora"]) if not e.get("hora") and v and v.get("hora") else dict(e))
    claves = {(e["tipo"], e["fecha"]) for e in nuevos}
    salida += [e for e in previos if e["fecha"] < hoy.isoformat() and (e["tipo"], e["fecha"]) not in claves]
    return sorted(salida, key=_orden)


def fusionar_publicados(previos: list[dict], nuevos: list[dict]) -> list[dict]:
    """Se acumulan por link: el RSS es una ventana móvil."""
    por_url = {p["url"]: p for p in previos}
    por_url.update({p["url"]: p for p in nuevos})
    return sorted(por_url.values(), key=_orden)


def actualizar(cache: dict, cfg: dict, hoy: date, modulos: dict | None = None) -> tuple[list, list, dict]:
    """Baja cada organismo y actualiza `cache` en el lugar (sólo con descargas exitosas). Devuelve
    (ítems diarios, ítems semanales, estado por organismo) para verificar_calendario.py."""
    modulos = modulos or _modulos()
    diarios, semanales, estado = [], [], {}
    ahora = datetime.now(C.ZONA_AR).isoformat(timespec="seconds")
    cache.setdefault("anunciados", {})
    cache.setdefault("publicados", {})
    for org in organismos(cfg):
        oid, nombre, mod = org["id"], org["organismo"], modulos[org["id"]]
        est = estado.setdefault(oid, {})
        try:
            nuevos, avisos = mod.bajar_anunciados(org, hoy)
            previo = cache["anunciados"].get(oid, {})
            cache["anunciados"][oid] = {"bajado": ahora,
                                        "eventos": fusionar_anunciados(previo.get("eventos", []), nuevos, hoy)}
            est["anunciados"] = {"fuente": "pagina", "bajado": ahora, "eventos": len(nuevos)}
            for k, a in enumerate(avisos):
                diarios.append((f"externo:{oid}:aviso:{k}", f"Calendario de {nombre}: {a}"))
        except Exception as e:
            previo = cache["anunciados"].get(oid)
            est["anunciados"] = {"fuente": "cache", "bajado": previo["bajado"]} if previo else {"fuente": "sin_datos"}
            diarios.append((f"externo:{oid}:descarga",
                            f"Calendario de {nombre}: {type(e).__name__}: {e} ({org['url']}). "
                            + ("Se usa la caché." if previo else "Sin caché: no se muestran sus fechas.")))
        if org.get("publicados"):
            try:
                pubs = mod.bajar_publicados(org)
                previo = cache["publicados"].get(oid, {})
                cache["publicados"][oid] = {"bajado": ahora,
                                            "items": fusionar_publicados(previo.get("items", []), pubs)}
                est["publicados"] = {"fuente": "feed", "bajado": ahora, "items": len(pubs)}
            except Exception as e:
                est["publicados"] = {"fuente": "cache" if cache["publicados"].get(oid) else "sin_datos"}
                diarios.append((f"externo:{oid}:publicados",
                                f"Publicaciones de {nombre}: {type(e).__name__}: {e} ({org['publicados']['url']})."))
        # Un publicado con `ciclo` que no está en el cronograma (ej. una licitación movida de día): se muestra
        # igual, pero se avisa para revisar (semanal, por ciclo).
        ciclos = {e.get("ciclo") for e in cache["anunciados"].get(oid, {}).get("eventos", [])} - {None}
        if ciclos:
            for p in cache["publicados"].get(oid, {}).get("items", []):
                if p.get("ciclo") and p["ciclo"] not in ciclos and p["ciclo"] >= min(ciclos):
                    semanales.append((f"externo:{oid}:ciclo:{p['ciclo']}",
                                      f"{nombre}: '{p.get('titulo_fuente') or p['tipo']}' ({p['url']}) es del "
                                      f"{p['ciclo']}, que no figura en el cronograma ({org['url']})."))
        # Ventana: el mes actual y los `meses_alerta` - 1 siguientes, completos.
        ult_a, ult_m = _sumar_meses(hoy, org.get("meses_alerta", 3) - 1)
        lim_a, lim_m = _sumar_meses(hoy, org.get("meses_alerta", 3))
        limite = date(lim_a, lim_m, 1).isoformat()
        futuros = [e for e in cache["anunciados"].get(oid, {}).get("eventos", []) if hoy.isoformat() <= e["fecha"] < limite]
        if not futuros:
            semanales.append((f"externo:{oid}:sin_futuros",
                              f"El calendario de {nombre} no tiene fechas anunciadas entre hoy y fin de {ult_m:02d}/{ult_a} "
                              f"({org['url']}): ¿no las publicó todavía o cambió el formato?"))
    return diarios, semanales, estado


# ---------------------------------------------------------------------------------------------
# Eventos listos para mostrar
# ---------------------------------------------------------------------------------------------
def a_ar(fecha: str, hora: str | None, zona: str) -> tuple[str, str | None]:
    """(fecha AR, hora AR) de un momento en hora local de `zona`. Sin hora, la fecha queda como está."""
    if not hora:
        return fecha, None
    dt = datetime.combine(date.fromisoformat(fecha), time.fromisoformat(hora), ZoneInfo(zona)).astimezone(C.ZONA_AR)
    return dt.date().isoformat(), dt.strftime("%H:%M")


def texto_hora(hora_ar: str | None, hora_local: str | None, org: dict) -> str:
    """"16:00 AR (14:00 ET)"; sin hora, ""."""
    if not hora_ar:
        return ""
    if org["zona"] == str(C.ZONA_AR) or not org.get("zona_abrev"):
        return f"{hora_ar} AR"
    return f"{hora_ar} AR ({hora_local} {org['zona_abrev']})"


def eventos(cache: dict, cfg: dict, hoy: date) -> list[dict]:
    """Todos los eventos de la caché, ya unidos (anunciado + publicado) y con fecha/hora en AR, ordenados.
    Estado: 'publicado' (con `url`) o 'anunciado'. Sólo los tipos configurados en el yaml."""
    salida = []
    for org in organismos(cfg):
        oid = org["id"]
        titulos = {e["tipo"]: e["titulo"] for e in org["eventos"]}
        tipos_pub = {}
        if org.get("publicados"):
            tipos_pub = {t["tipo"]: t["titulo"] for t in org["publicados"]["tipos"]}
        anunciados = {(e["tipo"], e["fecha"]): dict(e) for e in cache.get("anunciados", {}).get(oid, {}).get("eventos", [])
                      if e["tipo"] in titulos}
        publicados = [p for p in cache.get("publicados", {}).get(oid, {}).get("items", []) if p["tipo"] in tipos_pub]
        # con `ciclo`, un solo publicado por tipo y ciclo: el más reciente
        con_ciclo = {}
        for p in sorted((p for p in publicados if p.get("ciclo")), key=_orden):
            con_ciclo[(p["tipo"], p["ciclo"])] = p
        publicados = [p for p in publicados if not p.get("ciclo")] + list(con_ciclo.values())
        # clave de unión: (tipo, ciclo) si el evento lo trae, si no (tipo, fecha)
        anunciados = {(e["tipo"], e.get("ciclo") or e["fecha"]): e for e in anunciados.values()}
        unidos = []
        for p in publicados:
            a = anunciados.pop((p["tipo"], p.get("ciclo") or p["fecha"]), None)
            unidos.append({"tipo": p["tipo"], "fecha": p["fecha"], "hora": p.get("hora") or (a or {}).get("hora"),
                           "titulo": titulos.get(p["tipo"]) or tipos_pub[p["tipo"]], "estado": "publicado",
                           "url": p["url"], "ciclo": p.get("ciclo")})
        unidos += [{"tipo": a["tipo"], "fecha": a["fecha"], "hora": a.get("hora"), "titulo": titulos[a["tipo"]],
                    "estado": "anunciado", "url": None, "ciclo": a.get("ciclo")} for a in anunciados.values()]
        # link: la propia página; si no, la publicada más reciente del mismo ciclo; si no, la general del yaml
        # y un publicado con `fechas_ciclo` (el llamado del Tesoro dice la licitación y la liquidación reales)
        # corrige la fecha de los eventos todavía anunciados de su ciclo (decisión A)
        por_ciclo, fechas_ciclo = {}, {}
        for p in sorted(publicados, key=_orden):
            if p.get("ciclo"):
                por_ciclo[p["ciclo"]] = p["url"]
                fechas_ciclo.setdefault(p["ciclo"], {}).update(p.get("fechas_ciclo") or {})
        for e in unidos:
            if e["estado"] == "anunciado" and e["ciclo"]:
                e["fecha"] = fechas_ciclo.get(e["ciclo"], {}).get(e["tipo"], e["fecha"])
            e["link"] = e["url"] or por_ciclo.get(e["ciclo"]) or org.get("url_general")
            if e["ciclo"]:
                c = date.fromisoformat(e["ciclo"])
                e["titulo"] = e["titulo"].replace("{ciclo}", f"{c:%d/%m}")
        for e in unidos:
            fecha_ar, hora_ar = a_ar(e["fecha"], e["hora"], org["zona"])
            salida.append(dict(e, org=oid, organismo=org["organismo"], zona=org["zona"], fecha_ar=fecha_ar,
                               hora_ar=hora_ar, hora_txt=texto_hora(hora_ar, e["hora"], org), url_fuente=org["url"]))
    return sorted(salida, key=lambda e: (e["fecha_ar"], e["hora_ar"] or "99:99", e["organismo"]))

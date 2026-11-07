"""Verificación diaria del calendario (Bloque B1 de PROMPT_ronda_macro_indec.md). Corre en el cron
de datos (coyuntura.yml), después de run.py.

1. Baja el calendario del INDEC (`meses_atras` meses anteriores, mes actual + `meses_a_bajar` - 1) y actualiza la caché
   data/calendario_indec.json. Un mes que falla usa su último caché válido (marcado como tal).
2. Avisa a Pedro (un solo mail por corrida, mismo mecanismo que las alertas del INDEC) si:
   - la descarga o el formato fallan (el parser no devuelve silencio: ver calendario_indec.py);
   - un título matchea más de un patrón de calendario.yaml;
   - una publicación esperada no aparece en su ventana (mes actual + `meses_siguientes_alerta`):
     posible cambio de título;
   - los feriados de calendario.yaml no coinciden con los oficiales (JSON que usa
     https://www.argentina.gob.ar/feriados: /sites/default/files/holidays-{AAAA}-es.json), aparece
     un feriado "especial" que todavía no se evaluó, o ya salieron los oficiales de un año que el
     yaml tiene como provisorio;
   - estamos en diciembre y el yaml no tiene los feriados del año siguiente.
Nunca corta la corrida: cualquier error inesperado también se avisa y sale con 0.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

import requests

import calendario_indec as C
from fetchers import HEADERS
from fuentes_indec import enviar_alerta, _toca_aviso

ESTADO = C.RAIZ / "data" / "calendario_estado.json"
URL_FERIADOS = "https://www.argentina.gob.ar/sites/default/files/holidays-{anio}-es.json"
TIPOS_NACIONALES = {"inamovible", "trasladable", "turistico"}
REPETIR_DIAS = 7


def feriados_oficiales(anio: int) -> dict | None:
    """{"nacionales": {fecha: nombre}, "especiales": {fecha: nombre}} o None si el año todavía no
    está publicado (404). Cualquier otro problema es un error (se avisa)."""
    r = requests.get(URL_FERIADOS.format(anio=anio), headers=HEADERS, timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    nac, esp = {}, {}
    for x in r.json()["mainEntity"]["itemListElement"]:
        it = x["item"]
        tipo = it["additionalProperty"]["value"]
        if not it["startDate"].startswith(f"{anio}-"):
            continue   # el JSON de un año trae también el 1/1 del siguiente
        if tipo in TIPOS_NACIONALES:
            nac[it["startDate"]] = it["name"]
        elif tipo == "especial":
            esp[it["startDate"]] = it["name"]
    if not nac:
        raise C.CalendarioFormatoError(f"feriados {anio}: el JSON oficial no trae feriados nacionales")
    return {"nacionales": nac, "especiales": esp}


def chequear_feriados(cfg: dict, hoy: date, oficiales=feriados_oficiales) -> list[tuple[str, str]]:
    """Ítems de alerta (clave, texto) sobre los feriados de calendario.yaml."""
    items = []
    for anio_s, bloque in sorted(cfg["feriados"].items()):
        anio = int(anio_s)
        if anio < hoy.year:
            continue
        of = oficiales(anio)
        if of is None:
            continue   # el año todavía no está publicado: el yaml queda como está (provisorio)
        yaml_nac = {f["fecha"] for f in bloque["fechas"] if f["tipo"] != "especial"}
        yaml_esp = {f["fecha"] for f in bloque["fechas"] if f["tipo"] == "especial"}
        descartados = {d["fecha"] for d in bloque.get("especiales_descartados", [])}
        solo_of = sorted(set(of["nacionales"]) - yaml_nac)
        solo_yaml = sorted(yaml_nac - set(of["nacionales"]))
        if not bloque.get("verificado"):
            items.append((f"feriados:{anio}:publicados",
                          f"Ya están publicados los feriados oficiales de {anio} y calendario.yaml los tiene como "
                          f"provisorios. Revisar y marcar verificado: true. Diferencias: oficiales que faltan en el "
                          f"yaml {solo_of or '-'}; en el yaml y no oficiales {solo_yaml or '-'}."))
        elif solo_of or solo_yaml:
            items.append((f"feriados:{anio}:difieren",
                          f"Los feriados nacionales {anio} de calendario.yaml no coinciden con los oficiales. "
                          f"Faltan en el yaml: {solo_of or '-'}. Sobran en el yaml: {solo_yaml or '-'}."))
        nuevos = sorted(set(of["especiales"]) - yaml_esp - descartados)
        if nuevos:
            items.append((f"feriados:{anio}:especiales",
                          "Feriado(s) especial(es) sin evaluar en calendario.yaml: "
                          + "; ".join(f"{d} ({of['especiales'][d]})" for d in nuevos)
                          + ". Decidir si cuentan (criterio: si ese día no operan el INDEC, el BCRA y BYMA)."))
    if hoy.month == 12 and str(hoy.year + 1) not in cfg["feriados"]:
        items.append((f"feriados:{hoy.year + 1}:faltan",
                      f"calendario.yaml no tiene los feriados de {hoy.year + 1}."))
    return items


def verificar(hoy: date, cfg: dict, cache: dict, bajar=C.bajar_mes, oficiales=feriados_oficiales):
    """Núcleo sin efectos de disco ni mail (testeable). Devuelve (items_diarios, items_semanales,
    asignadas, estado_meses)."""
    diarios, semanales = [], []
    pubs, estado_meses, errores = C.obtener_publicaciones(hoy, cfg["fuente"]["meses_a_bajar"], cache, bajar,
                                                        cfg["fuente"].get("meses_atras", 0))
    for e in errores:
        diarios.append((f"descarga:{e.split(':')[0]}", f"Calendario del INDEC: {e}"))
    asignadas, err_asig = C.asignar(pubs, cfg)
    for e in err_asig:
        diarios.append(("asignacion", f"calendario.yaml: {e}"))
    for pid in C.faltantes_en_ventana(asignadas, cfg, hoy):
        p = next(p for p in cfg["publicaciones"] if p["id"] == pid)
        semanales.append((f"falta:{pid}",
                          f"No aparece '{p['nombre']}' en el calendario del INDEC entre este mes y los "
                          f"{p['meses_siguientes_alerta']} siguientes: posible cambio de título "
                          f"(patrón: {p['titulo_regex']})."))
    try:
        semanales += chequear_feriados(cfg, hoy, oficiales)
    except Exception as e:
        diarios.append(("feriados:error", f"No se pudieron verificar los feriados oficiales: {type(e).__name__}: {e}"))
    return diarios, semanales, asignadas, estado_meses


def main() -> int:
    hoy = datetime.now(C.ZONA_AR).date()
    estado = json.loads(ESTADO.read_text(encoding="utf-8")) if ESTADO.exists() else {}
    avisos = estado.setdefault("avisos", {})
    try:
        cfg = C.cargar_config()
        cache = C.cargar_cache()
        diarios, semanales, asignadas, estado_meses = verificar(hoy, cfg, cache)
        C.guardar_cache(cache)
    except Exception as e:   # bug o yaml roto: se avisa igual, nunca se corta la corrida
        diarios, semanales, asignadas, estado_meses = [("crash", f"verificar_calendario.py falló: {type(e).__name__}: {e}")], [], {}, {}

    hoy_s = hoy.isoformat()
    items = [(k, t) for k, t in diarios if _toca_aviso(avisos, k, hoy_s, None)]
    items += [(k, t) for k, t in semanales if _toca_aviso(avisos, k, hoy_s, REPETIR_DIAS)]
    for k, t in diarios + semanales:
        print(f"::warning title=Calendario::{t}")
    if items:
        cuerpo = "Alertas del calendario de publicaciones (coyuntura):\n\n" + "\n\n".join(f"- {t}" for _, t in items)
        if enviar_alerta(f"[Coyuntura] {len(items)} alerta(s) del calendario", cuerpo):
            for k, _ in items:
                avisos[k] = hoy_s
    estado.update({"ultima_verificacion": datetime.now(C.ZONA_AR).isoformat(timespec="seconds"),
                   "meses": estado_meses, "alertas_hoy": [t for _, t in diarios + semanales]})
    ESTADO.parent.mkdir(exist_ok=True)
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Calendario: {sum(1 for v in estado_meses.values() if v['fuente'] == 'endpoint')} meses del endpoint, "
          f"{sum(1 for v in estado_meses.values() if v['fuente'] == 'cache')} de caché, "
          f"{len(diarios) + len(semanales)} alerta(s).")
    for pid, fechas in asignadas.items():
        prox = next((f for f in fechas if f["fecha"] >= hoy_s), None)
        print(f"  {pid:16} próxima: " + (f"{prox['fecha']} {prox['hora']} ({prox['periodo']})" if prox else "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

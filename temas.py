"""Temas del sitio (Bloque E2, decisión de Pedro D5): qué card va en qué página de tema.

El mapeo vive en el bloque `temas:` de indicadores.yaml (lista de temas, cada uno con `secciones` de
`items`). Funciones puras: run.py arma con ellas la lista de indicadores de cada página de tema y
tests/test_temas.py verifica que cada card esté en UN solo tema.

Un ítem es lo que produce una card o una tabla en el dashboard:
  - el `nombre` de un indicador con card propia (no `solo_componente` ni `solo_referencia`);
  - el `tabla:` de las tablas de comercio exterior (varios indicadores, una tabla);
  - SEMAFORO para los sectores del EMAE (`semaforo: true`, una tabla);
  - las cards/tablas que arma run.py aparte (EXTRAS).
"""
from __future__ import annotations

SEMAFORO = "Semáforo del EMAE"
MURO = "Muro de vencimientos (AL30/GD30/GD35)"
DDF = "Dólar futuro (DDF)"
ACCIONES = "Acciones y CEDEARs más operados"
EXTRAS = (MURO, DDF, ACCIONES)
SIN_TEMA = "Sin tema asignado"
# Tema de respaldo para un ítem que no figura en `temas:` (nunca desaparece callado: va ahí con warning).
TEMA_DE_BLOQUE = {"precios": "precios", "real": "actividad", "social": "empleo-y-salarios",
                  "externo": "sector-externo", "fiscal": "fiscal-y-deuda",
                  "monetario_financiero": "dinero-y-credito", "mercados": "mercados"}


def item_de(ind: dict) -> str | None:
    """El ítem que produce un indicador en una página (None si no tiene card ni tabla propia)."""
    if ind.get("solo_componente") or ind.get("solo_referencia"):
        return None
    if ind.get("semaforo"):
        return SEMAFORO
    if ind.get("tabla"):
        return ind["tabla"]
    return ind["nombre"]


def items_esperados(indicadores: list[dict]) -> dict[str, str]:
    """{ítem: bloque} de todos los ítems que tienen que estar en algún tema (más los EXTRAS)."""
    out = {}
    for ind in indicadores:
        it = item_de(ind)
        if it is not None:
            out.setdefault(it, ind["bloque"])
    for it in EXTRAS:
        out.setdefault(it, "mercados")
    return out


def repetidos(temas: list[dict]) -> list[str]:
    vistos, rep = set(), []
    for t in temas:
        for s in t["secciones"]:
            for it in s["items"]:
                if it in vistos:
                    rep.append(it)
                vistos.add(it)
    return rep


def completar(temas: list[dict], indicadores: list[dict], extras_presentes=EXTRAS) -> tuple[list[dict], list[str], list[str]]:
    """(temas con los ítems sin tema agregados en "Sin tema asignado" del tema de su bloque,
    ítems sin tema, ítems del yaml que no existen). No modifica la lista original."""
    esperados = items_esperados(indicadores)
    temas = [dict(t, secciones=[dict(s, items=list(s["items"])) for s in t["secciones"]]) for t in temas]
    asignados = {it for t in temas for s in t["secciones"] for it in s["items"]}
    sin_tema = [it for it in esperados if it not in asignados and (it not in EXTRAS or it in extras_presentes)]
    for it in sin_tema:
        slug = TEMA_DE_BLOQUE.get(esperados[it], temas[-1]["slug"])
        t = next((x for x in temas if x["slug"] == slug), temas[-1])
        sec = next((s for s in t["secciones"] if s["titulo"] == SIN_TEMA), None)
        if sec is None:
            sec = {"titulo": SIN_TEMA, "items": []}
            t["secciones"].append(sec)
        sec["items"].append(it)
    inexistentes = [it for it in asignados if it not in esperados]
    return temas, sin_tema, inexistentes


def items(tema: dict) -> list[str]:
    return [it for s in tema["secciones"] for it in s["items"]]


def indicadores_de(tema: dict, indicadores: list[dict]) -> list[dict]:
    """Indicadores que van a la página del tema: los que producen uno de sus ítems, en el orden del yaml,
    más todos los `solo_componente` (alimentan las vistas compuestas, no hacen card)."""
    its = set(items(tema))
    return [i for i in indicadores if i.get("solo_componente") or (item_de(i) in its)]


def tema_de_item(temas: list[dict]) -> dict[str, str]:
    return {it: t["slug"] for t in temas for s in t["secciones"] for it in s["items"]}

"""
fuentes_datos_gob.py
--------------------
Fallback de la API de series de datos.gob.ar al CSV de distribución del mismo catálogo (decisión de
Pedro del 08/11/2026, diagnóstico del #21 de PENDIENTES).

La API puede tener la metadata al día y aun así devolver 0 filas, historia cortada (ej. 74.3_IICL_0_M_42:
sólo 1992-01 a 2003-06) o filas completas con valores erróneos (ej. base monetaria desde jun-2026, con la
metadata repitiendo el error). Por eso el CSV se usa en vez de la API cuando:
  1. la API devuelve 0 filas;
  2. la API devuelve menos filas que el `time_index_size` de su propia metadata (historia cortada);
  3. los últimos 12 períodos que tienen las dos fuentes difieren más que la tolerancia: la mayor
     diferencia absoluta, dividida por el promedio del valor absoluto del CSV en esos 12 períodos, supera
     TOLERANCIA (1%). Relativa a la escala de la serie (no período a período) para que las series que
     cruzan el cero (ej. resultado fiscal) no disparen por un dato chico;
  4. el CSV tiene períodos más nuevos que la API (la API suele indexar un mes después).
Guarda anti-RIPTE: si el período más nuevo del CSV repite EXACTAMENTE el valor del anterior (el CSV del RIPTE
traía ago-2026 con el valor de jun-2026), ese período no se usa: se vuelve a decidir sin él (si el único
motivo era el disparador 4, queda la API) y sale una alerta. No salta si la API publica ese mismo período
con el mismo valor (dos fuentes que coinciden: el valor repetido es real, ej. tasa de informalidad 2T-2026).
Alertas a Pedro: sólo por los disparadores 1-3 (0 filas, historia cortada, diferencia > tolerancia) y por la
guarda. El 4 (y la coherencia, que sigue a otro id) queda en ultima_corrida.json, en la racha y en la nota.
Coherencia por card: si un id de una distribución cae al CSV, todos los ids de esa misma distribución que
se usan en la misma card (combos, espejos, overlays, tablas, componentes de `calculo:`) también usan el
CSV, para no mezclar API y CSV dentro de un gráfico (`grupos_por_card` + `ResolverDatosGob.preparar`).
Los ids de `fallback_csv_excluir` (indicadores.yaml) nunca usan el CSV (hoy: el RIPTE, cuyo CSV trae
agosto-2026 con el valor de junio).

Cada uso queda en data/ultima_corrida.json (clave `datos_gob_csv`), en data/datos_gob_estado.json (racha
de corridas seguidas por serie) y dispara una alerta a Pedro (como las del INDEC, máx. 1 mail por
corrida): el día en que una serie empieza a usar el CSV y después una vez por semana mientras siga.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

import fetchers
from fuentes_indec import ZONA_AR, _hoy, _toca_aviso, enviar_alerta, DIAS_REPETICION

RAIZ = Path(__file__).resolve().parent
ESTADO = RAIZ / "data" / "datos_gob_estado.json"
TOLERANCIA = 0.01          # 1% de la escala de la serie en la ventana comparada
PERIODOS_COMPARADOS = 12


def diferencia_relativa(api: pd.DataFrame, csv: pd.DataFrame, n: int = PERIODOS_COMPARADOS) -> float | None:
    """Mayor |API − CSV| en los últimos `n` períodos comunes, dividida por el promedio de |CSV| en esos
    períodos. None si no hay períodos comunes (no se puede comparar)."""
    a = api.set_index("fecha")["valor"]
    c = csv.set_index("fecha")["valor"]
    comunes = a.index.intersection(c.index).sort_values()[-n:]
    if len(comunes) == 0:
        return None
    escala = c.loc[comunes].abs().mean()
    dif = (a.loc[comunes] - c.loc[comunes]).abs().max()
    if escala == 0:
        return 0.0 if dif == 0 else float("inf")
    return float(dif / escala)


def decidir(api: pd.DataFrame, filas_api_total: int, size_meta: int | None, csv: pd.DataFrame | None,
            tolerancia: float = TOLERANCIA) -> str | None:
    """Motivo para usar el CSV en vez de la API, o None si la API está bien (función pura).
    `filas_api_total`: filas que devolvió la API sin filtrar por fecha (para compararlas con la metadata)."""
    if filas_api_total == 0:
        return "la API devolvió 0 filas"
    if size_meta and filas_api_total < size_meta:
        return f"la API devolvió {filas_api_total} de {size_meta} filas (historia cortada)"
    if csv is not None and not csv.empty:
        d = diferencia_relativa(api, csv)
        if d is not None and d > tolerancia:
            return (f"los últimos {PERIODOS_COMPARADOS} períodos difieren del CSV un {d * 100:.1f}% "
                    f"(tolerancia {tolerancia * 100:.0f}%)")
        fin_api, fin_csv = api["fecha"].max(), csv["fecha"].max()
        if fin_csv > fin_api:
            return f"{MOTIVO_MAS_NUEVO} (CSV hasta {fin_csv:%Y-%m}, API hasta {fin_api:%Y-%m})"
    return None


def ultimo_repetido(csv: pd.DataFrame | None, api: pd.DataFrame | None = None) -> bool:
    """¿El período más nuevo del CSV repite exactamente el valor del anterior? (guarda anti-RIPTE). No cuenta
    si la API publica ese mismo período con ese mismo valor: dos fuentes coinciden, el valor repetido es real."""
    if csv is None or len(csv) < 2 or csv["valor"].iloc[-1] != csv["valor"].iloc[-2]:
        return False
    if api is not None and not api.empty:
        en_api = api.loc[api["fecha"] == csv["fecha"].iloc[-1], "valor"]
        if len(en_api) and (en_api == csv["valor"].iloc[-1]).any():
            return False
    return True


MOTIVO_MAS_NUEVO = "el CSV tiene períodos más nuevos que la API"
MOTIVO_COHERENCIA = "coherencia:"


def motivo_alerta(motivo: str) -> bool:
    """¿El motivo amerita alerta a Pedro? Sí: 0 filas, historia cortada, diferencia > tolerancia. No: el CSV
    sólo va un período adelante (disparador 4) o el id sigue a otro de su card (coherencia)."""
    return not (motivo.startswith(MOTIVO_MAS_NUEVO) or motivo.startswith(MOTIVO_COHERENCIA))


# Claves del yaml que nombran un id de datos.gob.ar (directo o componente de un `calculo:`) y claves que
# referencian otros indicadores por nombre (vistas compuestas), para armar los grupos de coherencia.
CLAVES_ID = ("id", "minuendo_id", "sustraendo_id", "numerador_id", "denominador_id", "base_id", "nominal_id",
             "deflactor_id", "pbi_id", "ipc_base_id")
CLAVES_REFERENCIA = ("series", "sectores", "barras", "linea", "linea_izq", "linea_der", "barra", "evento")


def _ids_de(ind: dict) -> set:
    if "calculo" not in ind and ind.get("fuente") != "datos_gob":
        return set()   # bcra, fred, mae, INDEC directo...: no son ids de datos.gob.ar
    ids = {ind[k] for k in CLAVES_ID if isinstance(ind.get(k), str)}
    for c in ind.get("componentes") or []:
        ids.add(c if isinstance(c, str) else c.get("id"))
    return {i for i in ids if i}


def grupos_por_card(indicadores: list, equivalencias: dict | None = None) -> list:
    """[(card, ids de datos.gob.ar que dibuja)] con 2 ids o más. Una card = un indicador más los que
    referencia por nombre, o todos los de una misma `tabla:`. Los ids con equivalencia en la API del INDEC
    quedan afuera (su primaria es el INDEC, no datos.gob.ar)."""
    por_nombre = {i["nombre"]: i for i in indicadores}
    excluir = set(equivalencias or {})
    grupos = []
    for ind in indicadores:
        nombres = [ind["nombre"]]
        for k in CLAVES_REFERENCIA:
            v = ind.get(k)
            for x in (v if isinstance(v, list) else [v]):
                if isinstance(x, str):
                    nombres.append(x)
                elif isinstance(x, dict):
                    nombres.extend(y for y in x.values() if isinstance(y, str))
        ids = set().union(*(_ids_de(por_nombre[n]) for n in nombres if n in por_nombre)) - excluir
        if len(ids) > 1:
            grupos.append((ind["nombre"], ids))
    tablas = {}
    for ind in indicadores:
        if ind.get("tabla"):
            tablas.setdefault(ind["tabla"], set()).update(_ids_de(ind) - excluir)
    grupos += [(f"tabla {n}", ids) for n, ids in tablas.items() if len(ids) > 1]
    return grupos


class ResolverDatosGob:
    def __init__(self, excluidos=None, fetch_api=None, fetch_meta=None, fetch_csv=None):
        self.excluidos = set(excluidos or [])
        self._api = fetch_api or fetchers.fetch_datos_gob
        self._meta = fetch_meta or fetchers.datos_gob_meta
        self._csv = fetch_csv or fetchers.fetch_datos_gob_csv
        self._eval: dict = {}            # id -> evaluación de esta corrida (API, CSV, decisión)
        self.por_id: dict = {}           # id -> uso del CSV en esta corrida
        self.descartados: dict = {}      # id -> último período del CSV descartado (guarda anti-RIPTE)
        self.por_indicador: dict = {}    # indicador -> ids que salieron del CSV
        self._actual = None
        self._nombre = None

    # --- contexto: qué indicador se está calculando (mismo esquema que ResolverIndec) --------------
    def empezar(self, nombre: str):
        self._actual, self._nombre = [], nombre

    def terminar(self, ok: bool):
        if ok and self._actual:
            self.por_indicador[self._nombre] = list(self._actual)
        self._actual = None

    def _anotar(self, registro: dict, serie_id: str, uso: dict):
        uso = registro.setdefault(serie_id, uso)
        if self._nombre and self._nombre not in uso["indicadores"]:
            uso["indicadores"].append(self._nombre)

    # --- núcleo -----------------------------------------------------------------------------------
    def _evaluar(self, serie_id: str) -> dict:
        """API y CSV completos (sin filtro de fecha) y la decisión, una sola vez por corrida y por id."""
        if serie_id in self._eval:
            return self._eval[serie_id]
        if serie_id in self.excluidos:
            ev = {"api": self._api(serie_id, None), "usa_csv": False}
            self._eval[serie_id] = ev
            return ev
        api = self._api(serie_id, None)   # sin filtro de fecha: para comparar con time_index_size
        try:
            meta = self._meta(serie_id)
            csv = self._csv(meta["url"], meta["columna"], None) if meta.get("url") and meta.get("columna") else None
        except Exception as e:
            print(f"  [datos.gob] {serie_id}: no se pudo bajar el CSV de distribución para verificar la API "
                  f"({type(e).__name__}: {e}); se usa la API sin verificar")
            meta, csv = {}, None
        motivo = decidir(api, len(api), meta.get("size"), csv)
        descarte = None
        if motivo and ultimo_repetido(csv, api):
            ult = csv.iloc[-1]
            descarte = (f"el período más nuevo del CSV ({ult['fecha']:%Y-%m}) repite exactamente el valor del "
                        f"anterior ({ult['valor']:g}): no se usa ese período")
            csv = csv.iloc[:-1].reset_index(drop=True)
            motivo = decidir(api, len(api), meta.get("size"), csv)
            print(f"  [datos.gob] {serie_id}: {descarte}" + ("" if motivo else "; queda la API"))
        usa = bool(motivo) and csv is not None and not csv.empty
        if motivo and not usa:
            print(f"  [datos.gob] {serie_id}: {motivo}, pero el CSV de distribución no está disponible")
        ev = {"api": api, "csv": csv, "url": meta.get("url"), "columna": meta.get("columna"),
              "motivo": motivo, "usa_csv": usa, "descarte": descarte}
        self._eval[serie_id] = ev
        return ev

    def preparar(self, grupos: list):
        """Evalúa todos los ids de las cards con varios ids y fuerza el CSV en los de la misma distribución
        que otro id de la card que ya cae al CSV (coherencia por card; se repite hasta que no cambia nada,
        porque un id puede estar en varias cards)."""
        for _, ids in grupos:
            for sid in sorted(ids):
                try:
                    self._evaluar(sid)
                except Exception as e:   # se reintenta (y se reporta) al traer el indicador
                    print(f"  [datos.gob] {sid}: no se pudo evaluar antes de la corrida ({type(e).__name__}: {e})")
        cambio = True
        while cambio:
            cambio = False
            for card, ids in grupos:
                evs = {s: self._eval[s] for s in sorted(ids) if s in self._eval}
                for sid, ev in evs.items():
                    if ev["usa_csv"] or sid in self.excluidos or ev.get("csv") is None or ev["csv"].empty:
                        continue
                    otro = next((o for o, x in evs.items() if x["usa_csv"] and x.get("url") == ev.get("url")), None)
                    if otro:
                        ev["usa_csv"] = True
                        ev["motivo"] = (f"{MOTIVO_COHERENCIA} {otro}, de la misma distribución, sale del CSV en la card "
                                        f"'{card}'")
                        cambio = True

    def serie(self, serie_id: str, start: str | None = None) -> pd.DataFrame:
        """Reemplazo de fetch_datos_gob(id, start) con el fallback al CSV de distribución."""
        ev = self._evaluar(serie_id)
        df = ev["csv"] if ev["usa_csv"] else ev["api"]
        if ev.get("descarte"):
            self._anotar(self.descartados, serie_id, {"motivo": ev["descarte"], "url": ev["url"], "indicadores": []})
        if ev["usa_csv"]:
            if serie_id not in self.por_id:
                print(f"  [datos.gob] {serie_id}: {ev['motivo']}; se usa el CSV de distribución ({ev['url']})")
                print(f"::warning title=Fallback datos.gob (CSV)::{serie_id} — {ev['motivo']}; se usó el CSV de distribución")
            self._anotar(self.por_id, serie_id, {"motivo": ev["motivo"], "url": ev["url"], "columna": ev["columna"],
                                                 "indicadores": []})
            if self._actual is not None and serie_id not in self._actual:
                self._actual.append(serie_id)
        if start:
            df = df[df["fecha"] >= pd.to_datetime(start)]
        return df.reset_index(drop=True).copy()


# ---------------------------------------------------------------------------------------------
# Estado entre corridas + alertas
# ---------------------------------------------------------------------------------------------
def cargar_estado() -> dict:
    if ESTADO.exists():
        try:
            return json.loads(ESTADO.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def _guardar_estado(estado: dict):
    ESTADO.parent.mkdir(exist_ok=True)
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def actualizar_estado(estado: dict, usos: dict, hoy: str, descartados: dict | None = None) -> list[tuple[str, str]]:
    """Rachas por serie y alertas a mandar (función pura sobre `estado`, que modifica). Una serie que deja
    de usar el CSV vuelve a racha 0. Alerta (sólo si `motivo_alerta`): el día en que empieza a usarlo y
    después una vez por semana. La racha cuenta igual para todos los motivos."""
    rachas = estado.setdefault("rachas", {})
    avisos = estado.setdefault("avisos", {})
    for sid in list(rachas):
        if sid not in usos:
            rachas[sid] = 0
    items = []
    for sid, uso in sorted(usos.items()):
        rachas[sid] = rachas.get(sid, 0) + 1
        uso["racha"] = rachas[sid]
        clave = f"csv:{sid}"
        if not motivo_alerta(uso["motivo"]):
            continue
        if rachas[sid] == 1 or _toca_aviso(avisos, clave, hoy, DIAS_REPETICION):
            items.append((clave, f"{sid} ({', '.join(uso['indicadores']) or 'sin indicador'}): {uso['motivo']}. "
                                 f"Se usó el CSV de distribución ({uso['url']}, columna {uso['columna']}). "
                                 f"Corridas seguidas usando el CSV: {rachas[sid]}."))
    for sid, d in sorted((descartados or {}).items()):
        clave = f"repetido:{sid}"
        if _toca_aviso(avisos, clave, hoy, DIAS_REPETICION):
            items.append((clave, f"{sid} ({', '.join(d['indicadores']) or 'sin indicador'}): {d['motivo']} "
                                 f"(CSV {d['url']}). Revisar contra la fuente primaria."))
    estado["corridas"] = (estado.get("corridas", []) + [{
        "fecha": hoy, "hora": datetime.now(ZONA_AR).strftime("%H:%M:%S"),
        "disparo": os.environ.get("GITHUB_EVENT_NAME", "local"), "csv": sorted(usos)}])[-30:]
    return items


def cerrar_corrida(resolver: ResolverDatosGob) -> tuple[dict, dict]:
    """Guarda el estado, manda (como mucho) un mail a Pedro y devuelve el resumen para ultima_corrida.json:
    (series que salieron del CSV, períodos del CSV descartados por la guarda anti-RIPTE)."""
    estado = cargar_estado()
    hoy = _hoy()
    items = actualizar_estado(estado, resolver.por_id, hoy, resolver.descartados)
    if items:
        cuerpo = ("Fallback de la API de series de datos.gob.ar al CSV de distribución del mismo catálogo (series "
                  "que salieron del CSV y períodos del CSV descartados por repetir el valor anterior):\n\n" + "\n\n".join(f"- {t}" for _, t in items)
                  + "\n\nEstado completo: data/datos_gob_estado.json en el repo.")
        if enviar_alerta(f"[Coyuntura] {len(items)} serie(s) de datos.gob.ar desde el CSV de distribución",
                         cuerpo, titulo="Fallback datos.gob (CSV)"):
            for clave, _ in items:
                estado["avisos"][clave] = hoy
    _guardar_estado(estado)
    return ({sid: {k: uso[k] for k in ("motivo", "indicadores", "racha")} for sid, uso in sorted(resolver.por_id.items())},
            {sid: {k: d[k] for k in ("motivo", "indicadores")} for sid, d in sorted(resolver.descartados.items())})


def describir_csv(ids: list[str]) -> str | None:
    """Texto para la nota de la serie mientras se use el CSV."""
    if not ids:
        return None
    return ("Datos vía CSV de distribución de datos.gob.ar (en esta corrida la API de series no los devolvió "
            f"completos o coincidentes): {', '.join(sorted(ids))}.")

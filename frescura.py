"""Línea de frescura de cada card (Bloque B2 de PROMPT_ronda_macro_indec.md).

Debajo del valor de cada card: de qué período es el último dato, si está al día y cuándo sale el
próximo. Diseño aprobado por Pedro el 07/11/2026:

  al día              sep-26 · ✓ al día · próximo 12/11, 16 h        (o "próximo hoy, 16 h")
  publicado, sin      sep-26 · oct-26 publicado el 12/11, entra en la próxima actualización
    incorporar          (dentro del margen: fecha de publicación + 1 día hábil)
  atrasado            ago-26 · ⚠ atrasado · sep-26 se publicó el 19/10
  sin calendario      ago-26 · próximo: sin calendario oficial
  serie diaria        04/11 · próximo 11/11 (estimado)               (próximo día hábil)
  rezago grave        ⏸ may-26 · sin datos nuevos hace 5 meses · <resto de la línea>   (al 07/11: 160 días desde el 31/05)

- Calendario: las publicaciones del INDEC asignadas a cada indicador en calendario.yaml, con las
  fechas de la caché data/calendario_indec.json (la actualiza verificar_calendario.py en cada
  corrida). Un indicador que no está en calendario.yaml no tiene "atrasado": sólo puede pasar a
  rezago grave.
- Rezago grave: días entre el FIN del período del último dato y hoy por encima de
  UMBRAL_DISCONTINUADA_DIAS (90), con piso en `rezago_normal_dias` del indicador. Las trimestrales
  suman un trimestre de tolerancia (90 + 92): el dato de un trimestre sigue siendo el último
  publicado hasta ~170 días después de su cierre (ej. EPH del 2T, vigente hasta el 18/12).
- Días hábiles: feriados de calendario.yaml (días en que no operan INDEC, BCRA y BYMA).
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time

import pandas as pd

import calendario_indec as C

UMBRAL_DISCONTINUADA_DIAS = 90
TOLERANCIA_TRIMESTRAL_DIAS = 92
MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_LARGOS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                "septiembre", "octubre", "noviembre", "diciembre"]
ORDINALES_TRIMESTRE = {"primer": 1, "segundo": 2, "tercer": 3, "cuarto": 4}


# ---------------------------------------------------------------------------------------------
# Períodos
# ---------------------------------------------------------------------------------------------
def frecuencia(fechas: pd.Series) -> str:
    """'diaria' / 'mensual' / 'trimestral' según la separación típica de los últimos 2 años."""
    f = pd.Series(sorted(pd.to_datetime(fechas).unique()))
    f = f[f >= f.max() - pd.DateOffset(years=2)]
    gaps = f.diff().dt.days.dropna()
    if gaps.empty:
        return "mensual"
    g = gaps.median()
    if g <= 10:
        return "diaria"
    if g >= 60:
        return "trimestral"
    return "mensual"


def periodo_de(fecha: pd.Timestamp, frec: str) -> pd.Period:
    return pd.Period(fecha, freq={"diaria": "D", "mensual": "M", "trimestral": "Q"}[frec])


def texto_periodo(p: pd.Period) -> str:
    if p.freqstr.startswith("Q"):
        return f"{p.quarter}T-{p.year % 100:02d}"
    if p.freqstr.startswith("M"):
        return f"{MESES_CORTOS[p.month - 1]}-{p.year % 100:02d}"
    return p.strftime("%d/%m")


def parsear_periodo_indec(texto: str) -> pd.Period:
    """'Octubre de 2026' -> 2026-10; 'Tercer trimestre de 2026' -> 2026Q3."""
    t = texto.strip().lower()
    if m := re.fullmatch(r"(\w+) de (\d{4})", t):
        if m.group(1) in MESES_LARGOS:
            return pd.Period(year=int(m.group(2)), month=MESES_LARGOS.index(m.group(1)) + 1, freq="M")
    if m := re.fullmatch(r"(\w+) trimestre de (\d{4})", t):
        if m.group(1) in ORDINALES_TRIMESTRE:
            return pd.Period(year=int(m.group(2)), quarter=ORDINALES_TRIMESTRE[m.group(1)], freq="Q")
    raise ValueError(f"período del calendario del INDEC no reconocido: {texto!r}")


def _misma_frecuencia(p: pd.Period, frec_dato: str) -> pd.Period:
    """Lleva un período del calendario a la frecuencia del dato (para comparar)."""
    return p.asfreq({"mensual": "M", "trimestral": "Q", "diaria": "D"}[frec_dato], how="end")


def _ddmm(d: date) -> str:
    return d.strftime("%d/%m")


def _hora(h: str) -> str:
    hh, mm = h.split(":")
    return f"{int(hh)} h" if mm == "00" else f"{int(hh)}:{mm} h"


# ---------------------------------------------------------------------------------------------
# Contexto de la corrida
# ---------------------------------------------------------------------------------------------
@dataclass
class Contexto:
    ahora: datetime                                # hora argentina, naive
    no_habiles: set = field(default_factory=set)
    pub_de_indicador: dict = field(default_factory=dict)   # nombre -> id de publicación
    fechas: dict | None = None                      # id -> [{fecha, hora, periodo(Period)}]; None = sin caché
    meses_bajado: dict = field(default_factory=dict)       # "AAAA-MM" -> ISO de la última descarga válida (caché)
    nombres_feriados: dict = field(default_factory=dict)   # date -> nombre del feriado (calendario.yaml)
    # Bloque B3: dashboard.generar registra acá las series de cada card (nombre de la card ->
    # (estados, serie resumen)) para que el mail use exactamente las mismas líneas que el dashboard.
    registro: dict = field(default_factory=dict)

    @property
    def hoy(self) -> date:
        return self.ahora.date()


def cargar_contexto(ahora: datetime | None = None) -> Contexto:
    """Lee calendario.yaml + la caché del calendario. Si la caché no se puede leer, las series con
    calendario muestran sólo el período (nunca una fecha inventada)."""
    ahora = ahora or datetime.now(C.ZONA_AR).replace(tzinfo=None)
    cfg = C.cargar_config()
    ctx = Contexto(ahora=ahora, no_habiles=C.feriados(cfg),
                   pub_de_indicador={n: p["id"] for p in cfg["publicaciones"] for n in p["indicadores"]},
                   nombres_feriados=C.nombres_feriados(cfg))
    try:
        cache = C.cargar_cache()
        ctx.meses_bajado = {k: v["bajado"] for k, v in cache["meses"].items()}
        pubs = [C._de_dict(d) for mes in cache["meses"].values() for d in mes["publicaciones"]]
        asignadas, _ = C.asignar(pubs, cfg)
        fechas = {}
        for pid, lista in asignadas.items():
            fechas[pid] = []
            for d in lista:
                try:
                    fechas[pid].append(dict(d, periodo=parsear_periodo_indec(d["periodo"])))
                except ValueError as e:
                    print(f"::warning title=Frescura::{e}")
        ctx.fechas = fechas
    except Exception as e:   # caché ilegible: se muestra sólo el período
        print(f"::warning title=Frescura::no se pudo leer el calendario: {type(e).__name__}: {e}")
    return ctx


# ---------------------------------------------------------------------------------------------
# Estado de una serie
# ---------------------------------------------------------------------------------------------
@dataclass
class Frescura:
    periodo: str            # "sep-26", "2T-26", "06/11"
    estado: str             # al_dia | publicado | atrasado | sin_calendario | diaria | sin_fecha
    detalle: str            # resto de la línea (HTML ya armado, sin el período ni el estado)
    tooltip: str
    grave: str | None = None   # "sin datos nuevos hace 5 meses" si hay rezago grave
    dias_rezago: int | None = None   # días desde el cierre del período (para ordenar los avisos del mail)


def calcular(ind: dict, nombre_serie: str, fechas: pd.Series, ctx: Contexto) -> Frescura | None:
    if fechas is None or len(fechas) == 0:
        return None
    ultima = pd.to_datetime(fechas).max()
    frec = frecuencia(fechas)
    per = periodo_de(ultima, frec)
    per_txt = texto_periodo(per)

    # Rezago grave: días desde el FIN del período del último dato.
    fin = per.end_time.normalize().date()
    dias = (ctx.hoy - fin).days
    umbral = max(UMBRAL_DISCONTINUADA_DIAS + (TOLERANCIA_TRIMESTRAL_DIAS if frec == "trimestral" else 0),
                 ind.get("rezago_normal_dias", 0))
    grave = None
    if dias > umbral:
        # Meses COMPLETOS desde el cierre del período (misma base que `dias`): may-26 cierra el 31/05,
        # al 07/11 van 160 días = 5 meses completos (no 6, que sería contar desde el 01/05).
        meses = (ctx.hoy.year * 12 + ctx.hoy.month) - (fin.year * 12 + fin.month) - (ctx.hoy.day < fin.day)
        grave = f"sin datos nuevos hace {meses} meses" if meses >= 2 else f"sin datos nuevos hace {dias} días"

    if grave and frec == "diaria":
        per_txt = ultima.strftime("%d/%m/%y")   # frenada hace meses: sin el año, "28/01" se lee mal
    pid = ctx.pub_de_indicador.get(nombre_serie) or ctx.pub_de_indicador.get(ind.get("nombre"))
    if pid is not None:
        f = _con_calendario(per, frec, per_txt, ctx, pid)
    elif frec == "diaria":
        prox = C.sumar_dias_habiles(ctx.hoy, 1, ctx.no_habiles)
        f = Frescura(per_txt, "diaria", f"próximo {_ddmm(prox)} (estimado)",
                     "Sin calendario oficial: se estima el próximo dato para el próximo día hábil "
                     "(feriados nacionales y los especiales en que no operan INDEC, BCRA y BYMA).")
    else:
        f = Frescura(per_txt, "sin_calendario", "próximo: sin calendario oficial",
                     "Esta serie no tiene un calendario oficial de publicación.")
    f.grave = grave
    f.dias_rezago = dias
    if grave:
        f.tooltip = (f"Último dato: {per_txt}. La fuente no publica datos nuevos desde hace "
                     f"{dias} días contados desde el cierre de ese período. " + f.tooltip)
    return f


def _con_calendario(per, frec, per_txt, ctx, pid) -> Frescura:
    if ctx.fechas is None:
        return Frescura(per_txt, "sin_fecha", "", "No se pudo leer el calendario del INDEC en esta corrida.")
    pubs = []
    for d in ctx.fechas.get(pid, []):
        momento = datetime.combine(date.fromisoformat(d["fecha"]), time.fromisoformat(d["hora"]))
        pubs.append((momento, _misma_frecuencia(d["periodo"], frec), d))
    nuevas_publicadas = [x for x in pubs if x[0] <= ctx.ahora and x[1] > per]
    if nuevas_publicadas:
        momento, p_nuevo, d = max(nuevas_publicadas, key=lambda x: x[1])
        nuevo_txt = texto_periodo(p_nuevo)
        limite = C.sumar_dias_habiles(momento.date(), 1, ctx.no_habiles)
        if ctx.hoy <= limite:
            return Frescura(per_txt, "publicado",
                            f"{nuevo_txt} publicado el {_ddmm(momento.date())}, entra en la próxima actualización",
                            f"El INDEC publicó {nuevo_txt} el {_ddmm(momento.date())}; se incorpora en la "
                            f"próxima corrida (margen: hasta el {_ddmm(limite)}, 1 día hábil).")
        return Frescura(per_txt, "atrasado", f"{nuevo_txt} se publicó el {_ddmm(momento.date())}",
                        f"El INDEC publicó {nuevo_txt} el {_ddmm(momento.date())} y ya pasó el margen de "
                        f"1 día hábil ({_ddmm(limite)}): el dashboard sigue mostrando {per_txt}. Puede ser "
                        "una demora de la fuente intermedia o una falla de la descarga.")
    futuras = sorted(x for x in pubs if x[0] > ctx.ahora and x[1] > per)
    if not futuras:
        return Frescura(per_txt, "al_dia", "", "Al día. La próxima fecha todavía no figura en el calendario del INDEC.")
    momento, p_prox, d = futuras[0]
    cuando = "hoy" if momento.date() == ctx.hoy else _ddmm(momento.date())
    return Frescura(per_txt, "al_dia", f"próximo {cuando}, {_hora(d['hora'])}",
                    f"Próxima publicación ({texto_periodo(p_prox)}) según el calendario del INDEC: "
                    f"{momento.strftime('%d/%m/%Y')} a las {d['hora']} h.")


# ---------------------------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------------------------
ESTADO_HTML = {"al_dia": '<span class="ok">✓ al día</span>',
               "atrasado": '<span class="atr">⚠ atrasado</span>'}
ESTADO_TEXTO = {"al_dia": "✓ al día", "atrasado": "⚠ atrasado"}


def _partes(f: Frescura, series: str | None, como_html: bool) -> list[str]:
    """Las partes de la línea, en el orden del B2. Única fuente de la redacción: la usan la línea del
    dashboard (HTML) y los avisos del mail (texto plano, Bloque B3)."""
    esc = html.escape if como_html else (lambda x: x)
    per = f'<span class="per">{f.periodo}</span>' if como_html else f.periodo
    partes = [per]
    if f.grave:
        quien = f"{esc(series)}: " if series else ""
        partes = [f"⏸ {quien}{per}", f.grave]
    if f.estado in ESTADO_HTML:
        partes.append((ESTADO_HTML if como_html else ESTADO_TEXTO)[f.estado])
    if f.grave and f.estado in ("sin_calendario", "diaria"):
        partes.append("sin calendario oficial")   # una fecha "estimada" no tiene sentido si la serie está frenada
    elif f.detalle:
        partes.append(f.detalle)
    return partes


def html_linea(f: Frescura | None, series: str | None = None) -> str:
    """`series`: nombre(s) de la(s) serie(s) frenada(s), sólo en cards mixtas (ver html_card)."""
    if f is None:
        return ""
    clase = "cf grave" if f.grave else "cf"
    return f'<div class="{clase}" title="{html.escape(f.tooltip)}">{" · ".join(_partes(f, series, True))}</div>'


def html_sello(f: Frescura | None) -> str:
    """Sello de la card del tema (Bloque E5, variante C): la misma línea del B2 partida en sus partes
    (período / estado / resto), sin redactar nada nuevo. Clase por estado: al día o publicado = borde lleno,
    atrasado = punteado, rezago grave = gris con fondo, sin calendario o diaria = gris claro."""
    if f is None:
        return ""
    if f.grave:
        clase, est = "sello-grave", "⏸ " + f.grave.split(" hace ")[0]   # "sin datos nuevos" (los meses, en la franja)
    elif f.estado == "atrasado":
        clase, est = "sello-atr", ESTADO_TEXTO["atrasado"]
    elif f.estado in ("al_dia", "publicado"):
        clase, est = "sello-ok", ESTADO_TEXTO.get(f.estado, "")
    else:
        clase, est = "sello-neutro", ""
    det = "sin calendario oficial" if f.grave and f.estado in ("sin_calendario", "diaria") else f.detalle
    partes = [f'<span class="se-per">{f.periodo}</span>']
    partes += [f'<span class="se-est">{est}</span>'] if est else []
    partes += [f'<span class="se-det">{det}</span>'] if det else []
    return f'<span class="sello {clase}" title="{html.escape(f.tooltip)}">{"".join(partes)}</span>'


def sello_card(estados: list[tuple[str, Frescura | None]], resumen: str) -> str:
    """El sello de una card: el de su línea principal (la primera de lineas_card)."""
    lineas = lineas_card(estados, resumen)
    return html_sello(lineas[0][1]) if lineas else ""


def texto_linea(f: Frescura, series: str | None = None) -> str:
    """La misma línea que html_linea, en texto plano (avisos del mail diario, Bloque B3)."""
    return " · ".join(_partes(f, series, False))


def lineas_card(estados: list[tuple[str, Frescura | None]], resumen: str) -> list[tuple[str, Frescura, str | None]]:
    """Qué líneas lleva una card: [(serie, Frescura, nombres a mostrar o None)]. `estados`: [(nombre de
    la serie, Frescura)] de todas sus series; `resumen`: la que da el valor de la card. Una sola serie,
    o todas frenadas: una sola línea, sin nombres. Card mixta (alguna frenada y alguna no; decisión de
    Pedro 07/11/2026): la línea normal de la serie resumen (o de la primera no frenada, si la resumen
    es la frenada) y una franja por cada grupo de series frenadas con el mismo período, que dice
    cuáles son."""
    validos = [(n, f) for n, f in estados if f is not None]
    if not validos:
        return []
    graves = [(n, f) for n, f in validos if f.grave]
    if not graves or len(graves) == len(validos):
        n = resumen if resumen in dict(validos) else validos[0][0]
        return [(n, dict(validos)[n], None)]
    no_graves = dict((n, f) for n, f in validos if not f.grave)
    n_princ = resumen if resumen in no_graves else next(iter(no_graves))
    salida = [(n_princ, no_graves[n_princ], None)]
    grupos: dict[tuple, list] = {}
    for n, f in graves:
        grupos.setdefault((f.periodo, f.grave, f.estado, f.detalle), []).append((n, f))
    for miembros in grupos.values():
        nombres = [n for n, _ in miembros]
        quien = nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]
        salida.append((miembros[0][0], miembros[0][1], quien))
    return salida


def html_card(estados: list[tuple[str, Frescura | None]], resumen: str) -> str:
    """Línea(s) de una card (ver lineas_card)."""
    return "".join(html_linea(f, series=quien) for _, f, quien in lineas_card(estados, resumen))

"""Titulares por reglas y variación de la card (Bloque C3 de PROMPT_ronda_macro_indec.md, diseño
aprobado por Pedro el 07/11/2026). Funciones puras, sin LLM: describen el dato, nunca atribuyen causas.

Configuración por card en indicadores.yaml (sobre la serie que resume la card, la misma de la línea de
frescura del B2):
  - titular_regla: direccion | signo | saldo | aporte (sin el campo: el titular es el nombre de la card).
  - titular_sujeto: "La inflación mensual" (el artículo define género y número: El/La/Los/Las).
  - titular_formato: cómo se escribe un nivel, con {} para el número (ej. "USD {} M"). Por defecto, el
    número solo; en series en % se agrega "%".
  - titular: override manual (se usa tal cual).
  - comparar: anterior | interanual. Por defecto, las series diarias comparan contra el dato anterior y
    las mensuales y trimestrales contra el mismo período del año anterior: ninguna serie mensual o
    trimestral del dashboard está desestacionalizada (verificado en el metadato oficial de cada serie de
    datos.gob.ar; el INDEC no publica el IPC desestacionalizado). Las excepciones van explícitas en el
    yaml con `comparar: anterior`: el IPC (decisión de Pedro: se comunica contra el mes anterior) y las
    series que ya son interanuales o sumas de 12 meses (inflación interanual, tasa real).
La variación que se muestra debajo del valor de la card compara contra lo mismo que el titular (D13).

Reglas:
  - direccion, contra el anterior: "{sujeto} sube a {x} en {período}"; "· {n}.º mes seguido de suba"
    desde 3; "· Máximo desde {mes} de {año}" si el período anterior con un valor igual o mayor está a 12
    meses o más (un empate no cuenta). En índices se usa la variación % ("sube 1,1% en agosto").
  - direccion, interanual: "{sujeto} de {período} fue {x}%, 0,2 pp menos que un año antes" (series en %)
    o "está 1,6% por encima del de un año antes" (niveles); racha: "· {n}.º mes seguido por encima del
    año anterior". Sin "máximo/mínimo desde" (D12: el máximo de una serie estacional está sesgado).
  - signo: "{sujeto} sigue negativa: −9,7% en septiembre (11.º mes seguido)".
  - saldo: "Superávit {sujeto} de USD 2.187 M en agosto: 33.º mes seguido".
  - aporte: "{división} aportó 0,54 pp de la inflación de septiembre" (incidencia).
Rachas: desde 3 períodos. Las de dirección se omiten si pasan de 24 períodos y en series nominales en
pesos (`nominal_pesos: true`); las de signo/saldo van siempre, sin tope. Decisiones de Pedro.
Nunca se presenta un dato viejo como nuevo: todo titular nombra su período, y si la serie está en rezago
grave (franja ⏸ del B2) o no hay con qué comparar, el titular vuelve al nombre de la card.
Período: los trimestrales llevan siempre el año ("el 2.º trimestre de 2026"); los mensuales, sólo si no
es el año en curso.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

import pandas as pd

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
MESES_ABREV = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MENOS = "−"
MIN_MESES_EXTREMO = 12
MIN_RACHA = 3
MAX_RACHA = 24   # decisión de Pedro (Bloque C): una racha de DIRECCIÓN de más de 24 períodos se omite


def _mostrar_racha(cfg: dict, n: int, direccion: bool = True) -> bool:
    """La racha va en el titular desde MIN_RACHA períodos. Las de DIRECCIÓN (suba/baja, por encima/debajo
    del año anterior) se omiten si pasan de MAX_RACHA y en series nominales en pesos (`nominal_pesos:
    true` en el yaml: crecen por la inflación). Las de SIGNO (superávit, déficit, tasa negativa;
    direccion=False) van siempre, sin tope y también en pesos. Decisiones de Pedro."""
    if not direccion:
        return n >= MIN_RACHA
    return MIN_RACHA <= n <= MAX_RACHA and not cfg.get("nominal_pesos")


# ---------------------------------------------------------------------------------------------
# Números
# ---------------------------------------------------------------------------------------------
def redondear(x: float, dec: int) -> float:
    return float(Decimal(str(float(x))).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP))


def fmt(x: float, dec: int, signo: bool = False) -> str:
    v = redondear(x, dec)
    t = f"{abs(v):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if v < 0:
        return MENOS + t
    return ("+" + t) if signo and v > 0 else t


def es_porcentaje(unidad: str) -> bool:
    """Tasas y variaciones: se comparan en puntos porcentuales y se muestran con 1 decimal (D4)."""
    u = (unidad or "").lower()
    return "%" in u or u.strip() in ("p.p.", "pp")


def es_indice(unidad: str) -> bool:
    return "índice" in (unidad or "").lower()


def decimales(unidad: str, valor: float | None = None) -> int:
    if es_porcentaje(unidad):
        return 2 if (unidad or "").strip() in ("p.p.", "pp") else 1
    u = (unidad or "").lower()
    if any(k in u for k in ("millones", "miles", "puntos")):
        return 0   # montos y puntos básicos: sin decimales
    if valor is None:
        return 1
    a = abs(valor)
    return 0 if a >= 1000 else (1 if a >= 10 else 2)


def fmt_valor(valor, unidad: str) -> str:
    """Valor grande de la card (D4: decimales según la unidad)."""
    if valor is None or pd.isna(valor):
        return "s/d"
    return fmt(valor, decimales(unidad, valor))


# ---------------------------------------------------------------------------------------------
# Frecuencia y períodos
# ---------------------------------------------------------------------------------------------
def frecuencia(fechas) -> str:
    f = pd.Series(pd.to_datetime(list(fechas))).sort_values().drop_duplicates()
    if len(f) < 2:
        return "mensual"
    paso = f.diff().dropna().tail(12).median().days
    return "diaria" if paso <= 7 else ("mensual" if paso <= 45 else "trimestral")


def comparar_de(cfg: dict, freq: str) -> str:
    if cfg.get("comparar") in ("anterior", "interanual"):
        return cfg["comparar"]
    return "anterior" if freq == "diaria" else "interanual"


def _trim(ts) -> int:
    return (ts.month - 1) // 3 + 1


def periodo(ts, freq: str, anio_actual: int) -> str:
    if freq == "diaria":
        return "el " + ts.strftime("%d/%m") + ("" if ts.year == anio_actual else ts.strftime("/%y"))
    if freq == "trimestral":
        return f"el {_trim(ts)}.º trimestre de {ts.year}"
    return MESES[ts.month - 1] + ("" if ts.year == anio_actual else f" de {ts.year}")


def de_periodo(ts, freq: str, anio_actual: int) -> str:
    p = periodo(ts, freq, anio_actual)
    return ("del " + p[3:]) if p.startswith("el ") else "de " + p


def ref_corta(ts, freq: str) -> str:
    """Referencia de la variación de la card: "vs. ago", "vs. sep-25", "vs. 1T-26", "vs. 06/11"."""
    if freq == "diaria":
        return ts.strftime("%d/%m")
    if freq == "trimestral":
        return f"{_trim(ts)}T-{str(ts.year)[2:]}"
    return f"{MESES_ABREV[ts.month - 1]}-{str(ts.year)[2:]}"


# ---------------------------------------------------------------------------------------------
# Gramática (por el artículo del sujeto)
# ---------------------------------------------------------------------------------------------
def _genero_numero(sujeto: str) -> tuple[str, str]:
    art = (sujeto or "").split(" ", 1)[0].lower()
    return {"el": ("m", "s"), "la": ("f", "s"), "los": ("m", "p"), "las": ("f", "p")}.get(art, ("m", "s"))


def _v(sujeto: str, singular: str, plural: str) -> str:
    return plural if _genero_numero(sujeto)[1] == "p" else singular


def _adj(sujeto: str, raiz: str) -> str:   # "negativ" -> negativo/a/os/as
    g, n = _genero_numero(sujeto)
    return raiz + ("o" if g == "m" else "a") + ("s" if n == "p" else "")


def _del_de(sujeto: str) -> str:
    g, n = _genero_numero(sujeto)
    return {("m", "s"): "del", ("f", "s"): "de la", ("m", "p"): "de los", ("f", "p"): "de las"}[(g, n)] + " de"


# ---------------------------------------------------------------------------------------------
# Comparaciones
# ---------------------------------------------------------------------------------------------
def _limpia(serie: pd.Series) -> pd.Series:
    s = serie.dropna().sort_index()
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")]


def _anio_antes(s: pd.Series) -> dict:
    return {(d.year, d.month): v for d, v in s.items()}


def _racha(difs: list[float]) -> tuple[int, int]:
    if not difs or difs[-1] == 0:
        return 0, 0
    sg = 1 if difs[-1] > 0 else -1
    n = 0
    for x in reversed(difs):
        if x * sg > 0:
            n += 1
        else:
            break
    return n, sg


def _difs_interanuales(s: pd.Series, pp: bool, dec: int) -> list[float]:
    base = _anio_antes(s)
    difs = []
    for d, v in s.items():
        b = base.get((d.year - 1, d.month))
        if b is None:
            continue
        if pp:
            difs.append(redondear(v - b, dec))
        elif b > 0 and v > 0:
            difs.append(redondear((v / b - 1) * 100, 1))
    return difs


def cambio(serie: pd.Series, unidad: str, comparar: str, freq: str) -> dict | None:
    """Variación de la card contra lo mismo que el titular. {"signo": 1|-1|0, "texto", "ref"} o None."""
    s = _limpia(serie)
    if len(s) < 2:
        return None
    ult_f, ult = s.index[-1], s.iloc[-1]
    if comparar == "interanual" and freq != "diaria":
        prev = _anio_antes(s).get((ult_f.year - 1, ult_f.month))
        if prev is None:
            return None
        prev_f = ult_f - pd.DateOffset(years=1)
    else:
        prev_f, prev = s.index[-2], s.iloc[-2]
    if es_porcentaje(unidad):
        d = redondear(ult - prev, decimales(unidad))
        texto = f"{fmt(d, decimales(unidad), signo=True)} pp"
    elif prev > 0 and ult > 0:
        d = redondear((ult / prev - 1) * 100, 1)
        texto = f"{fmt(d, 1, signo=True)}%"
    else:
        dec = decimales(unidad, max(abs(ult), abs(prev)))
        d = redondear(ult - prev, dec)
        texto = fmt(d, dec, signo=True)
    return {"signo": (d > 0) - (d < 0), "texto": texto, "ref": ref_corta(prev_f, freq)}


def _extremo_desde(s: pd.Series, freq: str) -> str | None:
    ult_f, ult = s.index[-1], s.iloc[-1]
    for tipo, cmp in (("Máximo", lambda a: a >= ult), ("Mínimo", lambda a: a <= ult)):
        previos = [i for i in range(len(s) - 1) if cmp(s.iloc[i])]
        if not previos:
            continue   # nunca antes: con poca historia no se anuncia "de la serie"
        i = previos[-1]
        if s.iloc[i] == ult:
            continue   # empate con un máximo anterior: no se anuncia
        f = s.index[i]
        meses = (ult_f.year - f.year) * 12 + ult_f.month - f.month
        if meses >= MIN_MESES_EXTREMO:
            return f"{tipo} desde {MESES[f.month - 1]} de {f.year}"
    return None


def _unidad_periodo(freq: str) -> str:
    return {"diaria": "día", "trimestral": "trimestre"}.get(freq, "mes")


def _nivel(cfg: dict, x: float, unidad: str, absoluto: bool = False) -> str:
    v = abs(x) if absoluto else x
    if es_porcentaje(unidad):
        return fmt(v, decimales(unidad)) + "%"
    return (cfg.get("titular_formato") or "{}").replace("{}", fmt(v, decimales(unidad, v)))


# ---------------------------------------------------------------------------------------------
# Titular
# ---------------------------------------------------------------------------------------------
def titular(cfg: dict, serie: pd.Series, unidad: str, anio_actual: int, grave: bool = False,
            freq: str | None = None) -> str | None:
    """Texto del titular, o None (= usar el nombre de la card)."""
    if cfg.get("titular"):
        return cfg["titular"]
    regla, sujeto = cfg.get("titular_regla"), cfg.get("titular_sujeto", "")
    s = _limpia(serie)
    if not regla or regla == "aporte" or grave or len(s) < 2:
        return None
    freq = freq or frecuencia(s.index)
    comp = comparar_de(cfg, freq)
    ult_f, ult = s.index[-1], s.iloc[-1]
    per, up = periodo(ult_f, freq, anio_actual), _unidad_periodo(freq)

    if regla in ("signo", "saldo"):
        signos = [(v > 0) - (v < 0) for v in s]
        n, sg = _racha(signos)
        if sg == 0:
            return None
        if regla == "saldo":
            base = f"{'Superávit' if sg > 0 else 'Déficit'} {sujeto} de {_nivel(cfg, ult, unidad, True)} {_en(per)}"
            return base + (f": {n}.º {up} seguido" if _mostrar_racha(cfg, n, direccion=False) else "")
        verbo = _v(sujeto, "sigue", "siguen") if n > 1 else _v(sujeto, "pasa a ser", "pasan a ser")
        base = f"{sujeto} {verbo} {_adj(sujeto, 'negativ' if sg < 0 else 'positiv')}: {_nivel(cfg, ult, unidad)} {_en(per)}"
        return base + (f" ({n}.º {up} seguido)" if _mostrar_racha(cfg, n, direccion=False) else "")

    if regla != "direccion":
        return None
    pp = es_porcentaje(unidad)
    dec = decimales(unidad, ult)

    if comp == "interanual" and freq != "diaria":
        prev = _anio_antes(s).get((ult_f.year - 1, ult_f.month))
        if prev is None:
            return None
        difs = _difs_interanuales(s, pp, decimales(unidad))
        n, sg = _racha(difs)
        cola = (f" · {n}.º {up} seguido por {'encima' if sg > 0 else 'debajo'} del año anterior"
                if _mostrar_racha(cfg, n) else "")
        dp = de_periodo(ult_f, freq, anio_actual)
        if pp:
            d = redondear(ult - prev, decimales(unidad))
            fue = _v(sujeto, "fue", "fueron")
            if d == 0:
                return f"{sujeto} {dp} {fue} {_nivel(cfg, ult, unidad)}, igual que un año antes"
            return (f"{sujeto} {dp} {fue} {_nivel(cfg, ult, unidad)}, {fmt(abs(d), decimales(unidad))} pp "
                    f"{'más' if d > 0 else 'menos'} que un año antes" + cola)
        if not (prev > 0 and ult > 0):
            return None
        var = redondear((ult / prev - 1) * 100, 1)
        if var == 0:
            return f"{sujeto} {dp} {_v(sujeto, 'queda', 'quedan')} igual que un año antes"
        return (f"{sujeto} {dp} {_v(sujeto, 'está', 'están')} {fmt(abs(var), 1)}% por "
                f"{'encima' if var > 0 else 'debajo'} {_del_de(sujeto)} un año antes" + cola)

    # contra el período anterior
    r = [redondear(v, dec) for v in s]
    difs = [round(b - a, 9) for a, b in zip(r[:-1], r[1:])]
    n, sg = _racha(difs)
    sube, baja = _v(sujeto, "sube", "suben"), _v(sujeto, "baja", "bajan")
    if es_indice(unidad):
        var = redondear((ult / s.iloc[-2] - 1) * 100, 1) if s.iloc[-2] else 0
        if var == 0:
            base = f"{sujeto} {_v(sujeto, 'se mantiene', 'se mantienen')} {_en(per)}"
        else:
            base = f"{sujeto} {sube if var > 0 else baja} {fmt(abs(var), 1)}% {_en(per)}"
    elif difs[-1] == 0:
        base = f"{sujeto} {_v(sujeto, 'se mantiene', 'se mantienen')} en {_nivel(cfg, ult, unidad)} {_en(per)}"
    else:
        base = f"{sujeto} {sube if difs[-1] > 0 else baja} a {_nivel(cfg, ult, unidad)} {_en(per)}"
    extra = _extremo_desde(pd.Series(r, index=s.index), freq)
    if not extra and _mostrar_racha(cfg, n):
        extra = f"{n}.º {up} seguido de {'suba' if sg > 0 else 'baja'}"
    return base + (f" · {extra}" if extra else "")


def _en(per: str) -> str:
    return per if per.startswith("el ") else "en " + per


def titular_aporte(cfg: dict, nombre: str, valor: float, fecha, anio_actual: int, freq: str = "mensual") -> str | None:
    """Incidencia: "{división} aportó 0,54 pp de la inflación de septiembre"."""
    if cfg.get("titular"):
        return cfg["titular"]
    if valor is None or pd.isna(valor):
        return None
    sujeto = cfg.get("titular_sujeto", "del total")
    return f"{nombre} aportó {fmt(valor, 2)} pp {sujeto} {de_periodo(pd.Timestamp(fecha), freq, anio_actual)}"

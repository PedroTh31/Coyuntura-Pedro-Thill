"""Agenda de publicaciones y avisos de frescura para el mail diario (Bloque B3 de
PROMPT_ronda_macro_indec.md, diseño aprobado por Pedro el 07/11/2026).

run.py llama a `armar()` después de generar el dashboard y guarda el resultado en
data/ultima_corrida.json (clave "agenda"). El mail (enviar_mail.py + mail_agenda.py) NO recalcula
nada: sólo elige qué mostrar y arma el HTML. Todo sale de:
  - el calendario del INDEC ya cacheado (frescura.Contexto: fechas, meses bajados, feriados);
  - el histórico (períodos y valores de las series que el dashboard ya calcula);
  - las líneas de frescura del B2 que registró dashboard.generar (ctx.registro), con su misma
    redacción (frescura.texto_linea).

Funciones puras (sin red ni disco), salvo `avisar_atrasados`, que manda el aviso semanal a Pedro.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd

import calendario_indec as C
import frescura as F

DIAS_SEMANA = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
ORDINALES = {1: "primer", 2: "segundo", 3: "tercer", 4: "cuarto"}
CACHE_VIEJA_DIAS = 7          # un mes de la ventana bajado hace más que esto: "caché vieja"
VENTANA_DIAS_HABILES = 5      # "Esta semana": hoy + los 4 días hábiles siguientes
UMBRAL_SIN_CAMBIO = 0.05
ESTADO_AVISOS = C.RAIZ / "data" / "frescura_estado.json"
REPETIR_AVISO_DIAS = 7


# ---------------------------------------------------------------------------------------------
# Textos
# ---------------------------------------------------------------------------------------------
def dia_corto(d: date) -> str:
    return f"{DIAS_SEMANA[d.weekday()]} {d:%d/%m}"


def nombre_periodo(p: pd.Period, anio_ref: int) -> str:
    """"octubre" / "octubre de 2025" / "tercer trimestre" (el año sólo si no es `anio_ref`)."""
    t = f"{ORDINALES[p.quarter]} trimestre" if p.freqstr.startswith("Q") else F.MESES_LARGOS[p.month - 1]
    return t if p.year == anio_ref else f"{t} de {p.year}"


def titulo_publicacion(pub: dict, periodo: pd.Period, anio_ref: int) -> str:
    """"IPC de octubre", "Mercado de trabajo (EPH) del tercer trimestre"."""
    conector = "del" if periodo.freqstr.startswith("Q") else "de"
    return f"{pub['nombre_corto']} {conector} {nombre_periodo(periodo, anio_ref)}"


def _num(v: float, dec: int) -> str:
    return f"{v:,.{dec}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def fmt_valor(v: float, unidad: str) -> str:
    if unidad == "%":
        return f"{_num(v, 1)}%"
    if unidad == "USD M":
        return f"USD {_num(v, 0)} M"
    return _num(v, 1)


def fmt_variacion(var: float, tipo: str, unidad: str) -> str:
    """"▲ 0,2 pp", "▼ 1,1%", "▲ USD 88 M", "= sin cambios"."""
    if abs(var) < UMBRAL_SIN_CAMBIO:
        return "= sin cambios"
    flecha = "▲" if var > 0 else "▼"
    if tipo == "pp":
        return f"{flecha} {_num(abs(var), 1)} pp"
    if tipo == "pct":
        return f"{flecha} {_num(abs(var), 1)}%"
    return f"{flecha} {fmt_valor(abs(var), unidad)}"


def _con_signo(var: float, tipo: str, unidad: str) -> str:
    """Para el titular: "+1,1%", "−2,2%", "+0,2 pp"."""
    if abs(var) < UMBRAL_SIN_CAMBIO:
        return "sin cambios"
    signo = "+" if var > 0 else "−"
    if tipo == "pp":
        return f"{signo}{_num(abs(var), 1)} pp"
    if tipo == "pct":
        return f"{signo}{_num(abs(var), 1)}%"
    return f"{signo}{fmt_valor(abs(var), unidad)}"


# ---------------------------------------------------------------------------------------------
# Calendario: hoy, esta semana, próxima
# ---------------------------------------------------------------------------------------------
def _momento(d: dict) -> datetime:
    return datetime.combine(date.fromisoformat(d["fecha"]), time.fromisoformat(d["hora"]))


def primer_habil_de_la_semana(hoy: date, no_habiles: set) -> bool:
    return C.es_habil(hoy, no_habiles) and not any(
        C.es_habil(hoy - timedelta(days=k), no_habiles) for k in range(1, hoy.weekday() + 1))


def fin_ventana(ctx: F.Contexto) -> date:
    """Último día de "Esta semana": hoy + los 4 días hábiles siguientes (si hoy no es hábil, los 5
    siguientes). La usan el mail y la página del calendario (Bloque E1)."""
    habil = C.es_habil(ctx.hoy, ctx.no_habiles)
    return C.sumar_dias_habiles(ctx.hoy, VENTANA_DIAS_HABILES - 1 if habil else VENTANA_DIAS_HABILES, ctx.no_habiles)


def armar_calendario(ctx: F.Contexto, cfg: dict) -> dict:
    """Ventana = hoy + los 4 días hábiles siguientes (si hoy no es hábil, los 5 siguientes). Las
    publicaciones se muestran en la fecha del calendario del INDEC aunque caigan en un día que
    calendario.yaml marca como no hábil (los feriados sólo definen la ventana)."""
    hoy = ctx.hoy
    habil = C.es_habil(hoy, ctx.no_habiles)
    fin = fin_ventana(ctx)
    out = {"fecha": hoy.isoformat(), "estado": "ok", "bajado": None,
           "feriado_hoy": None if habil else ctx.nombres_feriados.get(hoy),
           "primer_habil_semana": primer_habil_de_la_semana(hoy, ctx.no_habiles),
           "hoy": [], "semana": [], "hasta": dia_corto(fin), "proxima": None}
    if ctx.fechas is None:
        out["estado"] = "no_disponible"
        return out
    meses = {f"{hoy.year}-{hoy.month:02d}", f"{fin.year}-{fin.month:02d}"}
    bajados = [ctx.meses_bajado.get(m) for m in sorted(meses)]
    if any(b is None for b in bajados):
        out["estado"] = "no_disponible"
        return out
    mas_viejo = min(datetime.fromisoformat(b).date() for b in bajados)
    if (hoy - mas_viejo).days > CACHE_VIEJA_DIAS:
        out["estado"], out["bajado"] = "cache_vieja", mas_viejo.strftime("%d/%m")

    items = []   # (fecha, hora, orden en el yaml, título, fuente)
    for orden, pub in enumerate(cfg["publicaciones"]):
        for d in ctx.fechas.get(pub["id"], []):
            items.append((date.fromisoformat(d["fecha"]), d["hora"], orden,
                          titulo_publicacion(pub, d["periodo"], hoy.year), pub.get("fuente", "INDEC")))
    items.sort()
    # Bloque F1: eventos de otros organismos (FED, BCE, BoJ, BoE, BCRA) en la misma ventana, por fecha y hora
    # AR; sin hora van al final del día. Llevan `externo` (el mail no les agrega "el dato llega en el próximo
    # mail": no actualizan el dashboard).
    externos = [e for e in ctx.externos if hoy.isoformat() <= e["fecha_ar"] <= fin.isoformat()]
    del_dia = [((h, 0), {"titulo": t, "fuente": fu, "hora": F._hora(h)}) for f, h, _, t, fu in items if f == hoy]
    del_dia += [((e["hora_ar"] or "99:99", 1), {"titulo": e["titulo"], "fuente": e["organismo"], "hora": e["hora_txt"],
                                                 "externo": True}) for e in externos if e["fecha_ar"] == hoy.isoformat()]
    out["hoy"] = [x for _, x in sorted(del_dia, key=lambda z: z[0])]
    filas: dict[tuple, list] = {}
    for f, h, _, t, _fu in items:
        if hoy < f <= fin:
            filas.setdefault((f, h), []).append(t)
    semana = [((f, h, 0), {"dia": dia_corto(f), "hora": F._hora(h), "titulos": ts}) for (f, h), ts in filas.items()]
    for e in externos:   # mismo formato que las del INDEC: hora AR (hora local) + nombre del evento
        f = date.fromisoformat(e["fecha_ar"])
        if f > hoy:
            semana.append(((f, e["hora_ar"] or "99:99", 1), {"dia": dia_corto(f), "hora": e["hora_txt"], "titulos": [e["titulo"]]}))
    out["semana"] = [x for _, x in sorted(semana, key=lambda z: z[0])]
    if not out["semana"]:
        prox = next((x for x in items if x[0] > fin), None)
        if prox:
            out["proxima"] = {"titulo": prox[3], "dia": dia_corto(prox[0]), "hora": F._hora(prox[1])}
    return out


# ---------------------------------------------------------------------------------------------
# Página del calendario (Bloque E1): el mes completo, la próxima fecha de cada publicación y las
# series sin calendario oficial. Funciones puras: leen la caché del calendario, calendario.yaml y lo
# que ya calcularon estado_publicaciones / dashboard.generar (ctx.registro). Nada se estima.
# ---------------------------------------------------------------------------------------------
def _sin_periodo(titulo: str) -> str:
    """'Índice de producción industrial pesquero (IPI pesquero). Septiembre de 2026' -> sin el período."""
    return re.sub(r"\.\s*[^.]*\b\d{4}\.?\s*$", "", titulo).strip() or titulo


def _estado_en_mes(per: pd.Period | None, momento: datetime, monitor: dict | None, ahora: datetime) -> str | None:
    """'proximo' | 'incorporado' (el monitor ya muestra ese período o uno posterior) | el estado del B2
    de la publicación ('publicado' / 'atrasado') si salió y el monitor todavía no lo tiene."""
    if momento > ahora:
        return "proximo"
    if per is None or not monitor:
        return None
    en_monitor = pd.Period(monitor["periodo"])
    if per.freqstr[0] != en_monitor.freqstr[0]:
        per = per.asfreq(en_monitor.freqstr, how="end")
    if per <= en_monitor:
        return "incorporado"
    return monitor.get("estado") if monitor.get("estado") in ("publicado", "atrasado") else "publicado"


def armar_meses(cache: dict, cfg: dict, ctx: F.Contexto, publicaciones: dict, meses: list[str]) -> list[dict]:
    """Un dict por mes ("AAAA-MM") con todos sus días: feriado, hábil, hoy, pasado y las publicaciones
    del INDEC de la caché. Las que alimentan el monitor (matchean un `titulo_regex` de calendario.yaml)
    llevan `pid`, el título corto ("IPC de octubre") y su estado; las demás, `pid` None y el título del
    INDEC sin el período. Un mes que no está en la caché sale con `disponible` False."""
    salida = []
    for clave in meses:
        anio, mes = map(int, clave.split("-"))
        datos_mes = cache.get("meses", {}).get(clave)
        por_dia: dict[date, list] = {}
        for d in (datos_mes or {}).get("publicaciones", []):
            f = date.fromisoformat(d["fecha"])
            hits = [p for p in cfg["publicaciones"] if p["_re"].match(d["titulo"])]
            item = {"hora": F._hora(d["hora"]), "titulo_indec": d["titulo"], "pid": None,
                    "titulo": _sin_periodo(d["titulo"]), "estado": None}
            if len(hits) == 1:   # dos patrones a la vez es un error de config (lo avisa verificar_calendario)
                p = hits[0]
                try:
                    per = F.parsear_periodo_indec(p["_re"].match(d["titulo"]).group("periodo"))
                except ValueError:
                    per = None
                momento = datetime.combine(f, time.fromisoformat(d["hora"]))
                item.update(pid=p["id"], titulo=titulo_publicacion(p, per, ctx.hoy.year) if per else p["nombre_corto"],
                            estado=_estado_en_mes(per, momento, publicaciones.get(p["id"]), ctx.ahora))
            por_dia.setdefault(f, []).append(item)
        # Bloque F1: otros organismos, por fecha AR. Estado: 'publicado' (con link), 'proximo' (todavía no
        # llegó su momento) o 'anunciado' (pasó sin publicación encontrada: decisión B4 de Pedro, sin link y
        # sin afirmar que pasó).
        for e in ctx.externos:
            f = date.fromisoformat(e["fecha_ar"])
            if (f.year, f.month) != (anio, mes):
                continue
            momento = datetime.combine(f, time.fromisoformat(e["hora_ar"] or "23:59"))
            est = "publicado" if e["estado"] == "publicado" else ("proximo" if momento > ctx.ahora else "anunciado")
            por_dia.setdefault(f, []).append({"externo": True, "pid": None, "estado": None, "organismo": e["organismo"],
                                              "titulo": e["titulo"], "hora": e["hora_txt"], "orden": e["hora_ar"] or "99:99",
                                              "estado_ext": est, "url": e["url"] if est == "publicado" else None})
        dias, d = [], date(anio, mes, 1)
        while d.month == mes:
            pubs = sorted(por_dia.get(d, []), key=lambda x: (0 if x["pid"] else 1 if x.get("externo") else 2,
                                                             x.get("orden") or x["hora"]))
            dias.append({"fecha": d.isoformat(), "dia": DIAS_SEMANA[d.weekday()], "numero": d.day,
                         "habil": C.es_habil(d, ctx.no_habiles), "feriado": ctx.nombres_feriados.get(d),
                         "hoy": d == ctx.hoy, "pasado": d < ctx.hoy, "publicaciones": pubs})
            d += timedelta(days=1)
        salida.append({"clave": clave, "nombre": f"{F.MESES_LARGOS[mes - 1]} de {anio}",
                       "disponible": datos_mes is not None, "bajado": (datos_mes or {}).get("bajado"), "dias": dias})
    return salida


def proximas(ctx: F.Contexto, cfg: dict) -> dict:
    """Próxima fecha de cada publicación según la caché: {id: {titulo, fecha, dia, hora}}. Sin fecha
    futura en la caché, la publicación no aparece (nunca se estima)."""
    out = {}
    for pub in cfg["publicaciones"]:
        futuras = sorted((d for d in (ctx.fechas or {}).get(pub["id"], []) if _momento(d) > ctx.ahora), key=_momento)
        if futuras:
            d = futuras[0]
            f = date.fromisoformat(d["fecha"])
            out[pub["id"]] = {"titulo": titulo_publicacion(pub, d["periodo"], ctx.hoy.year), "fecha": d["fecha"],
                              "dia": dia_corto(f), "hora": F._hora(d["hora"])}
    return out


def sin_calendario(ctx: F.Contexto) -> list[str]:
    """Cards (de las que registró dashboard.generar) cuya serie principal no tiene calendario oficial y
    no está en rezago grave (esas van en "Datos demorados"). Las diarias no entran: su "próximo
    (estimado)" queda sólo en la card."""
    nombres = []
    for card, (estados, resumen) in ctx.registro.items():
        lineas = F.lineas_card(estados, resumen)
        if lineas and lineas[0][1].estado == "sin_calendario" and not lineas[0][1].grave:
            nombres.append(card)
    return nombres


# ---------------------------------------------------------------------------------------------
# Estado de cada publicación + bloque "Dato nuevo"
# ---------------------------------------------------------------------------------------------
def _serie_por_periodo(historico: pd.DataFrame, nombre: str) -> tuple[dict, str | None]:
    s = historico.loc[historico["indicador"] == nombre, ["fecha", "valor"]].dropna()
    if s.empty:
        return {}, None
    frec = F.frecuencia(s["fecha"])
    return {F.periodo_de(pd.Timestamp(f), frec): float(v) for f, v in zip(s["fecha"], s["valor"])}, frec


def _ref(p: pd.Period, compara: str) -> pd.Period:
    if compara == "anterior":
        return p - 1
    return p - (4 if p.freqstr.startswith("Q") else 12)


def _etiqueta_ref(ref: pd.Period, compara: str, per: pd.Period) -> str:
    if compara == "anterior" and ref.freqstr.startswith("M"):
        return nombre_periodo(ref, per.year)      # "agosto", "diciembre de 2025"
    return F.texto_periodo(ref)                    # "sep-25", "2T-26"


def armar_apertura(historico: pd.DataFrame, pub: dict, per: pd.Period, anio_ref: int) -> dict:
    ap = pub["apertura"]
    filas = []
    for fila in ap.get("filas", []):
        valores, _ = _serie_por_periodo(historico, fila["serie"])
        p = per.asfreq(next(iter(valores)).freqstr, how="end") if valores else per
        if p not in valores:
            continue   # fila sin dato para el período: se omite
        v, compara, tipo, unidad = valores[p], fila.get("compara", "anterior"), fila.get("variacion", "pct"), fila.get("unidad", "")
        ref = _ref(p, compara)
        r = valores.get(ref)
        var = None
        if r is not None:
            var = (v - r) if tipo in ("pp", "dif") else ((v / r - 1) * 100 if r else None)
        filas.append({"etiqueta": fila["etiqueta"], "valor": fmt_valor(v, unidad),
                      "ref": f"{_etiqueta_ref(ref, compara, p)} {fmt_valor(r, unidad)}" if r is not None else None,
                      "var": fmt_variacion(var, tipo, unidad) if var is not None else None,
                      "_var_signo": _con_signo(var, tipo, unidad) if var is not None else None,
                      "_ref": _etiqueta_ref(ref, compara, p)})
    campos = {"periodo": nombre_periodo(per, anio_ref), "periodo_corto": F.texto_periodo(per),
              "valor": filas[0]["valor"] if filas else "", "var": (filas[0]["_var_signo"] or "") if filas else "",
              "ref": filas[0]["_ref"] if filas else ""}
    if ap.get("filas") and (not filas or "{var}" in ap["titular"] and not filas[0]["_var_signo"]):
        titular = titulo_publicacion(pub, per, anio_ref)   # sin datos para la plantilla: título neutro
    else:
        titular = ap["titular"].format(**campos)
    return {"titular": titular, "detalle": ap["detalle"].format(**campos) if ap.get("detalle") else None,
            "filas": [{k: v for k, v in f.items() if not k.startswith("_")} for f in filas]}


def url_serie(serie: str, ctx: F.Contexto, ind_por_nombre: dict) -> str | None:
    """Página de serie (Bloque E4, relativa a la raíz del sitio) donde se ve `serie`: su card propia (mismo
    nombre); si no, la card que la tiene como serie principal; si no, la primera card que la dibuja; si no tiene card, su propia página cuando
    el yaml la marca con `pagina_serie` (ej. EMAE general). None = sin página."""
    import sitio
    cards = [(card, resumen) for card, (estados, resumen) in ctx.registro.items() if serie in dict(estados)]
    elegida = next((card for card, _ in cards if card == serie),          # la card propia de la serie
                   next((card for card, resumen in cards if resumen == serie), cards[0][0] if cards else None))
    if elegida is None and ind_por_nombre.get(serie, {}).get("pagina_serie"):
        elegida = serie
    if elegida is None:
        return None
    return f"serie/{sitio.slug(elegida, ind_por_nombre.get(elegida))}/"


def estado_publicaciones(historico: pd.DataFrame, ind_por_nombre: dict, cfg: dict, ctx: F.Contexto) -> dict:
    """Por publicación: período que muestra el dashboard, estado del B2 y bloque de apertura."""
    out = {}
    for pub in cfg["publicaciones"]:
        ap = pub.get("apertura")
        if not ap:
            continue
        serie = ap.get("serie_periodo") or ap["filas"][0]["serie"]
        fechas = historico.loc[historico["indicador"] == serie, "fecha"]
        if fechas.empty:
            continue
        frec = F.frecuencia(fechas)
        per = F.periodo_de(pd.to_datetime(fechas).max(), frec)
        f = F.calcular(ind_por_nombre.get(serie, {"nombre": serie}), serie, fechas, ctx)
        pubs = (ctx.fechas or {}).get(pub["id"], [])
        del_periodo = next((d for d in pubs if F._misma_frecuencia(d["periodo"], frec) == per), None)
        ya = [d for d in pubs if _momento(d) <= ctx.ahora]
        ultimo = max(ya, key=lambda d: d["periodo"].end_time) if ya else None
        # "ver gráfico" sólo si la serie se ve en alguna card del dashboard (ej. el EMAE general no tiene
        # card: abre el mail sin link; decisión de Pedro 07/11/2026). Anclado a la sección del bloque.
        en_card = any(serie in dict(estados) for estados, _ in ctx.registro.values())
        bloque = ind_por_nombre.get(serie, {}).get("bloque") if en_card else None
        url = url_serie(serie, ctx, ind_por_nombre)
        out[pub["id"]] = {
            "nombre_corto": pub["nombre_corto"],
            "periodo": str(per),
            "titulo": titulo_publicacion(pub, per, ctx.hoy.year),
            "estado": f.estado if f else None,
            "linea": F.texto_linea(f) if f else None,
            "titulo_publicado": (titulo_publicacion(pub, F._misma_frecuencia(ultimo["periodo"], frec), ctx.hoy.year)
                                 if ultimo else None),
            "publicado": (f"{date.fromisoformat(del_periodo['fecha']):%d/%m}, {F._hora(del_periodo['hora'])}"
                          if del_periodo else None),
            "fuente": pub.get("fuente", "INDEC"),
            "ancla": bloque,
            "url": url,
            "apertura": armar_apertura(historico, pub, per, ctx.hoy.year),
        }
    return out


# ---------------------------------------------------------------------------------------------
# Avisos: atrasados (por publicación) y rezago grave (por card / grupo de series)
# ---------------------------------------------------------------------------------------------
def resumen_frescura(ctx: F.Contexto, cfg: dict) -> tuple[list[dict], list[dict]]:
    """A partir de las cards que registró dashboard.generar. Misma redacción que el dashboard."""
    cortos = {p["id"]: p["nombre_corto"] for p in cfg["publicaciones"]}
    atrasados, candidatos = {}, []
    for card, (estados, resumen) in ctx.registro.items():
        for serie, f, quien in F.lineas_card(estados, resumen):
            if f.grave:
                nombre = quien or card
                clave_f = (f.periodo, f.grave, f.estado, f.detalle)
                series = frozenset(n for n, g in estados
                                   if g is not None and g.grave and (g.periodo, g.grave, g.estado, g.detalle) == clave_f)
                candidatos.append({"clave": f"{nombre}|{f.periodo}", "nombre": nombre,
                                   "texto": F.texto_linea(f, nombre), "dias": f.dias_rezago or 0,
                                   "_series": series, "_periodo": f.periodo})
            elif f.estado == "atrasado":
                pid = ctx.pub_de_indicador.get(serie) or ctx.pub_de_indicador.get(card)
                texto = F.texto_linea(f)
                clave = f"atrasado:{pid or card}:{f.periodo}"
                atrasados.setdefault(clave, {"clave": clave, "publicacion": pid,
                                             "texto": f"{cortos.get(pid, card)} · {texto}"})
    orden_pub = [p["id"] for p in cfg["publicaciones"]]
    lista_atr = sorted(atrasados.values(),
                       key=lambda a: orden_pub.index(a["publicacion"]) if a["publicacion"] in orden_pub else 99)
    # Una serie frenada que aparece en varias cards va una sola vez: se descarta la línea cuyas series
    # ya están cubiertas por otra del mismo período (ej. "Adelantos transitorios (pesos constantes)"
    # dentro de "Asistencia monetaria del BCRA al Tesoro"). Gana la de más series; a igual tamaño, la
    # primera card del dashboard.
    graves = []
    for c in sorted(candidatos, key=lambda c: -len(c["_series"])):
        if not any(c["_periodo"] == g["_periodo"] and c["_series"] <= g["_series"] for g in graves):
            graves.append(c)
    orden = {id(c): k for k, c in enumerate(candidatos)}
    graves.sort(key=lambda g: (-g["dias"], orden[id(g)]))
    return lista_atr, [{k: v for k, v in g.items() if not k.startswith("_")} for g in graves]


def armar(historico: pd.DataFrame, indicadores: list[dict], ctx: F.Contexto, cfg: dict) -> dict:
    atrasados, graves = resumen_frescura(ctx, cfg)
    return {"calendario": armar_calendario(ctx, cfg),
            "publicaciones": estado_publicaciones(historico, {i["nombre"]: i for i in indicadores}, cfg, ctx),
            "atrasados": atrasados, "graves": graves}


def avisar_atrasados(atrasados: list[dict], hoy: date, ruta: Path = ESTADO_AVISOS, enviar=None) -> list[str]:
    """Aviso a Pedro (decisión D1): semanal por publicación y período atrasado, máx. 1 mail por corrida.
    El estado sólo se actualiza si el mail salió (sin credenciales, p. ej. en el fallback del workflow
    del mail, no se manda ni se marca)."""
    if enviar is None:
        from fuentes_indec import enviar_alerta as enviar
    from fuentes_indec import _toca_aviso
    estado = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    avisos = estado.setdefault("avisos", {})
    hoy_s = hoy.isoformat()
    toca = [a for a in atrasados if _toca_aviso(avisos, a["clave"], hoy_s, REPETIR_AVISO_DIAS)]
    if toca:
        cuerpo = ("Publicaciones del INDEC que ya salieron y el dashboard todavía no muestra (pasó el margen "
                  "de 1 día hábil). Puede ser una demora de la fuente intermedia o una falla de la descarga:\n\n"
                  + "\n".join(f"- {a['texto']}" for a in toca)
                  + "\n\nEste aviso se repite cada 7 días mientras siga atrasado.")
        if enviar(f"[Coyuntura] {len(toca)} publicación(es) atrasada(s)", cuerpo):
            for a in toca:
                avisos[a["clave"]] = hoy_s
    estado["ultima_verificacion"] = hoy_s
    estado["atrasados_hoy"] = [a["texto"] for a in atrasados]
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps(estado, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return [a["clave"] for a in toca]

"""Secciones del mail diario del Bloque B3 (PROMPT_ronda_macro_indec.md, diseño aprobado por Pedro el
07/11/2026): "Dato nuevo", "Hoy se publica" y "Esta semana". La sección "Datos demorados" se sacó del mail
el 11/11/2026 (decisión de Pedro: no va nunca, ni con datos muy viejos); sigue en la página del calendario
(/calendario/#demorados) y en el aviso semanal de atrasados a Pedro (agenda.avisar_atrasados).

No recalcula nada: lee la clave "agenda" que run.py dejó en data/ultima_corrida.json (ver agenda.py)
y el estado del último envío (data/mail_enviado.json, que commitea email_diario.yml):
  - periodos_anunciados: último período anunciado de cada publicación. Un "Dato nuevo" abre el mail
    el PRIMER envío en que el período del dashboard supera al anunciado (aunque el pipeline lo haya
    levantado tarde). Si la clave no existe (primer envío con este código, o una publicación nueva en
    calendario.yaml), se inicializa sin anunciar nada.
Funciones puras: `seleccionar` (qué se muestra + estado a registrar) y `html_*` (HTML con tablas y CSS
inline, 640 px como el resto del mail hasta el Bloque 2 de PROMPT_mail_v3.md).
"""
from __future__ import annotations

from html import escape

from tema import TEMA as T

F = T["fuente"]


# ---------------------------------------------------------------------------------------------
# Selección
# ---------------------------------------------------------------------------------------------
def seleccionar(uc: dict, hoy_iso: str, estado_mail: dict) -> tuple[dict, dict]:
    """(vista, estado a registrar en mail_enviado.json si el envío sale bien)."""
    ag = uc.get("agenda") if uc.get("fecha") == hoy_iso else None
    vista = {"calendario": None, "feriado": None, "nuevos": [], "pendientes": []}
    if not ag:
        # La agenda no es de hoy (o falta): nunca mostrar la de otro día como si fuera la de hoy.
        vista["calendario"] = {"estado": "no_disponible"}
        return vista, {}
    cal = ag.get("calendario") or {"estado": "no_disponible"}
    vista["calendario"], vista["feriado"] = cal, cal.get("feriado_hoy")

    previos = estado_mail.get("periodos_anunciados")
    anunciados = dict(previos or {})
    for pid, p in (ag.get("publicaciones") or {}).items():
        prev = (previos or {}).get(pid)
        if prev is not None and p["periodo"] > prev:
            vista["nuevos"].append(p)
        elif p.get("estado") == "publicado":
            vista["pendientes"].append(p)
        if prev is None or p["periodo"] > prev:
            anunciados[pid] = p["periodo"]
    return vista, {"periodos_anunciados": anunciados}


# ---------------------------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------------------------
def _tabla(filas: str, extra: str = "") -> str:
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" '
            f'style="width:100%;border-collapse:collapse;font-family:{F};{extra}">{filas}</table>')


def _titulo_seccion(texto: str, sub: str = "") -> str:
    sub = f' <span style="font-weight:400;color:{T["texto_3"]};font-size:12px">· {escape(sub)}</span>' if sub else ""
    return (f'<tr><td colspan="3" style="padding:0 0 4px;font-size:15px;font-weight:700;'
            f'color:{T["texto"]}">{escape(texto)}{sub}</td></tr>')


def _link(titulo: str, url: str | None) -> str:
    """Título (escapado), con link si el evento lo tiene (hoy: licitaciones del Tesoro y publicados de la FED)."""
    if not url:
        return escape(titulo)
    return f'<a href="{escape(url)}" style="color:inherit;text-decoration:underline">{escape(titulo)}</a>'


def html_feriado(vista: dict) -> str:
    if not vista.get("feriado"):
        return ""
    return (f'<p style="font-family:{F};color:{T["texto_2"]};font-size:13px;margin:6px 0 0">Hoy es feriado '
            f'({escape(vista["feriado"])}): no publica el INDEC ni operan el BCRA y BYMA.</p>')


def _bloque_dato_nuevo(p: dict, dashboard_url: str) -> str:
    ap = p["apertura"]
    cab = f'Dato nuevo · {escape(p["fuente"])}' + (f', publicado el {escape(p["publicado"])}' if p.get("publicado") else "")
    filas = (f'<tr><td colspan="3" style="padding:6px 12px 0;font-size:11px;color:{T["texto_3"]};'
             f'letter-spacing:.04em;text-transform:uppercase">{cab}</td></tr>'
             f'<tr><td colspan="3" style="padding:2px 12px 8px;font-size:20px;font-weight:700;'
             f'color:{T["principal_1"]}">{escape(ap["titular"])}</td></tr>')
    if ap.get("detalle"):
        filas += (f'<tr><td colspan="3" style="padding:0 12px 6px;font-size:13px;color:{T["texto_2"]}">'
                  f'{escape(ap["detalle"])}</td></tr>')
    for f in ap["filas"]:
        comp = " · ".join(escape(x) for x in (f.get("ref"), f.get("var")) if x)
        filas += (f'<tr><td style="padding:3px 12px;font-size:13px;color:{T["texto_2"]};width:150px">{escape(f["etiqueta"])}</td>'
                  f'<td style="padding:3px 8px 3px 0;font-size:14px;color:{T["texto"]};font-weight:700;width:95px;'
                  f'white-space:nowrap">{escape(f["valor"])}</td>'
                  f'<td style="padding:3px 0;font-size:13px;color:{T["texto_2"]}">{comp}</td></tr>')
    if p.get("url") or p.get("ancla"):   # E4: la página de la serie; si no hay, el #ancla de siempre
        url = f'{dashboard_url}{p["url"]}' if p.get("url") else f'{dashboard_url}#{p["ancla"]}'
        filas += (f'<tr><td colspan="3" style="padding:6px 12px 8px;font-size:12px"><a href="{escape(url)}" '
                  f'style="color:{T["principal_2"]};text-decoration:none">ver gráfico →</a></td></tr>')
    else:
        filas += '<tr><td colspan="3" style="height:8px;line-height:8px;font-size:0">&nbsp;</td></tr>'
    return _tabla(filas, f'margin-top:12px;border-left:4px solid {T["principal_1"]}')


def html_apertura(vista: dict, dashboard_url: str) -> str:
    salida = "".join(_bloque_dato_nuevo(p, dashboard_url) for p in vista["nuevos"])
    for p in vista["pendientes"]:
        titulo = p.get("titulo_publicado") or p["nombre_corto"]
        salida += _tabla(
            f'<tr><td style="padding:8px 12px;font-size:13px;color:{T["texto"]};border-top:1px solid {T["principal_contexto"]};'
            f'border-bottom:1px solid {T["principal_contexto"]}"><b style="color:{T["principal_1"]}">{escape(titulo)}</b> · '
            f'{escape(p["linea"])}</td></tr>', f'margin-top:12px;border-left:4px solid {T["principal_3"]}')
    return salida


def html_calendario(vista: dict) -> str:
    cal = vista.get("calendario") or {"estado": "no_disponible"}
    if cal["estado"] == "no_disponible":
        return (f'<p style="font-family:{F};color:{T["texto_2"]};font-size:13px;margin:14px 0 0">'
                'Calendario del INDEC no disponible hoy: no se muestran fechas de publicación.</p>')
    salida = ""
    if cal["hoy"]:
        filas = (f'<tr><td style="padding:8px 12px 2px;font-size:12px;font-weight:700;color:{T["principal_1"]};'
                 'letter-spacing:.04em;text-transform:uppercase">Hoy se publica</td></tr>')
        for it in cal["hoy"]:
            if it.get("externo"):   # Bloque F1: mismo formato, sin "el dato llega" (no actualiza el dashboard)
                hora = f' · {escape(it["hora"])}' if it["hora"] else ""
                filas += (f'<tr><td style="padding:2px 12px 9px;font-size:15px;color:{T["texto"]}">'
                          f'<b style="color:{T["principal_1"]}">{_link(it["titulo"], it.get("url"))}</b> · '
                          f'{escape(it["fuente"])}{hora}</td></tr>')
                continue
            filas += (f'<tr><td style="padding:2px 12px 9px;font-size:15px;color:{T["texto"]}">'
                      f'<b style="color:{T["principal_1"]}">{escape(it["titulo"])}</b> · {escape(it["fuente"])} · '
                      f'{escape(it["hora"])} <span style="font-size:12px;color:{T["texto_2"]}">· el dato llega en el '
                      'próximo mail</span></td></tr>')
        salida += _tabla(filas, f'margin-top:12px;background:{T["principal_contexto"]}')
    filas = _titulo_seccion("Esta semana", "publicaciones del INDEC y de otros organismos")
    borde = f'border-top:1px solid {T["principal_contexto"]}'
    for it in cal["semana"]:
        filas += (f'<tr><td style="padding:4px 0;width:80px;font-size:13px;color:{T["texto_2"]};{borde};vertical-align:top">'
                  f'{escape(it["dia"])}</td><td style="padding:4px 8px 4px 0;width:44px;white-space:nowrap;font-size:13px;color:{T["texto_2"]};'
                  f'{borde};vertical-align:top">{escape(it["hora"])}</td><td style="padding:4px 0;font-size:13px;'
                  f'color:{T["texto"]};{borde}">{"<br>".join(_link(t, u) for t, u in zip(it["titulos"], it.get("urls") or [None] * len(it["titulos"])))}</td></tr>')
    if not cal["semana"]:
        texto = f'Sin publicaciones hasta el {cal["hasta"]}.'
        if cal.get("proxima"):
            pr = cal["proxima"]
            texto += f' Próxima: {pr["titulo"]} · {pr["dia"]} · {pr["hora"]}.'
        filas += f'<tr><td colspan="3" style="padding:4px 0;font-size:13px;color:{T["texto_2"]};{borde}">{escape(texto)}</td></tr>'
    if cal["estado"] == "cache_vieja":
        filas += (f'<tr><td colspan="3" style="padding:4px 0 0;font-size:12px;color:{T["texto_3"]}">Fechas según el '
                  f'calendario del INDEC bajado el {escape(cal["bajado"])} (no se pudo actualizar desde entonces).</td></tr>')
    return salida + _tabla(filas, "margin-top:14px")


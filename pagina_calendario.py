"""Página del calendario de publicaciones: docs/calendario/index.html (Bloque E1, diseño aprobado por
Pedro el 07/11/2026).

Sólo con datos que ya existen, sin estimar nada:
  - "Hoy" y "Esta semana": la misma ventana y los mismos textos que el mail (agenda.armar_calendario,
    agenda.fin_ventana), con los feriados de calendario.yaml;
  - estado de cada publicación en el monitor: período, estado y línea del B2 (agenda.estado_publicaciones)
    y la próxima fecha de la caché (agenda.proximas);
  - el mes: todas las publicaciones de la caché del calendario del INDEC (agenda.armar_meses); las que no
    alimentan el monitor van ocultas detrás de un botón (decisión de Pedro D6);
  - datos demorados (agenda.resumen_frescura) y series sin calendario oficial (agenda.sin_calendario).

`html()` es pura; `generar()` la escribe. run.py la llama después de agenda.armar.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

import pandas as pd

import agenda as A
import frescura as F
import sitio

SALIDA = Path(__file__).resolve().parent / "docs" / "calendario" / "index.html"
URL_CALENDARIO_INDEC = "https://www.indec.gob.ar/indec/web/Calendario-Fecha-0"
MESES_CORTOS = F.MESES_CORTOS
MARCA = {"incorporado": ("✓", "ya está en el monitor"), "atrasado": ("⚠", "atrasado: salió y el monitor no lo muestra"),
         "publicado": ("•", "publicado, entra en la próxima actualización"), "proximo": ("", "")}

CSS = """
  .cal-h2 { font-size:28px; line-height:1.15; margin:22px 0 0; }
  .aviso { font-size:13px; color:var(--atrasado); background:var(--franja-fondo); border-left:3px solid var(--franja-borde);
    padding:6px 10px; margin-top:12px; }
  .c-top { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,2fr); column-gap:40px; }
  .c-vacio { font-size:14px; color:var(--texto-2); margin:8px 0; }
  .c-hoy-pub { font-size:15px; margin:8px 0; } .c-hoy-pub b { color:var(--azul-1); }
  .c-hoy-pub span { display:block; font-size:12px; color:var(--texto-3); }
  .c-dia { display:flex; gap:12px; border-top:1px solid var(--linea); padding:8px 0; }
  .c-dia:first-of-type { border-top:0; }
  .tile { display:inline-flex; flex-direction:column; align-items:center; justify-content:center; width:40px; flex:none;
    border:1px solid var(--azul-1); color:var(--azul-1); line-height:1; padding:3px 0 4px; }
  .tile-d { font-size:9px; text-transform:uppercase; letter-spacing:.06em; }
  .tile-n { font-size:16px; font-weight:700; margin:2px 0 1px; }
  .tile-m { font-size:9px; text-transform:uppercase; color:var(--texto-3); }
  .c-dia-fer .tile { border-style:dashed; border-color:var(--texto-3); color:var(--texto-3); }
  .c-cont { flex:1; min-width:0; font-size:14px; }
  .c-fer { display:inline-block; font-size:12px; color:var(--texto-2); background:var(--franja-fondo); padding:3px 8px; }
  .c-nada { font-size:13px; color:var(--texto-3); padding-top:10px; }
  .c-pub b { color:var(--azul-1); } .c-pub .cf { margin-top:2px; }
  .c-pub + .c-pub { margin-top:6px; }
  .t-est td:first-child { font-weight:700; } .t-est .per { font-weight:600; color:var(--texto-2); white-space:nowrap; }
  .t-est .ok { color:var(--azul-2); font-weight:600; } .t-est .atr { color:var(--atrasado); font-weight:700; }
  .t-est .det { display:block; font-size:11px; color:var(--texto-3); }
  .mes-h { display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:6px 16px;
    border-top:1px solid var(--texto); margin-top:30px; padding-top:8px; }
  .mes-h h3.grupo { border:0; margin:0; padding:0; }
  .tabs { display:flex; gap:2px; flex-wrap:wrap; font-size:13px; }
  .tab { font:inherit; background:none; border:0; border-bottom:2px solid transparent; padding:2px 6px; color:var(--texto-2); cursor:pointer; }
  .tab.activo { color:var(--texto); font-weight:700; border-bottom-color:var(--azul-1); }
  .ver-otras { font-size:12px; color:var(--texto-2); display:flex; align-items:center; gap:5px; cursor:pointer; }
  .mes { display:none; } .mes.activo { display:block; }
  .m-grid { display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); border-left:1px solid var(--linea); margin-top:8px; }
  .m-h { font-size:10px; text-transform:uppercase; letter-spacing:.06em; color:var(--texto-3); padding:4px 6px; border-bottom:1px solid var(--texto); }
  .m-c { min-height:88px; border-right:1px solid var(--linea); border-bottom:1px solid var(--linea); padding:4px 6px; font-size:11px; line-height:1.3; min-width:0; }
  .m-n { font-weight:700; color:var(--texto-2); font-size:12px; }
  .m-fin { background:#FAFBFC; } .m-fer { background:var(--franja-fondo); }
  .m-fer-l { font-size:10px; color:var(--texto-3); }
  .m-hoy { outline:2px solid var(--azul-1); outline-offset:-2px; }
  .m-hoy-l { font-size:9px; font-weight:700; text-transform:uppercase; background:var(--azul-1); color:#fff; padding:0 4px; margin-left:5px; }
  .m-pub { color:var(--azul-1); margin-top:3px; padding-left:5px; border-left:3px solid var(--azul-1); overflow-wrap:anywhere; }
  .m-pub .mk { font-weight:700; margin-right:3px; }
  .m-pub.e-atrasado { border-left-color:var(--atrasado); color:var(--atrasado); }
  .m-pasado .m-n, .m-pasado .m-pub.e-incorporado { opacity:.6; }
  .m-otra { display:none; color:var(--texto-3); margin-top:3px; font-size:10px; overflow-wrap:anywhere; }
  body.otras .m-otra { display:block; }
  .m-lista { display:none; }
  .l-fila { display:flex; gap:10px; border-top:1px solid var(--linea); padding:6px 0; font-size:13px; }
  .l-d { width:66px; flex:none; color:var(--texto-2); } .l-t { min-width:0; }
  .l-t .m-pub, .l-t .m-otra { margin-top:0; font-size:13px; } .l-t .m-otra { font-size:12px; }
  .l-solo-otras { display:none; } body.otras .l-solo-otras { display:flex; }
  .leyenda { font-size:11px; color:var(--texto-3); margin-top:6px; }
  .avisos { list-style:none; padding:0; margin:8px 0; font-size:13px; color:var(--atrasado); }
  .avisos li { border-top:1px solid var(--linea); padding:5px 0; }
  .graves { list-style:none; padding:0; margin:6px 0 0; } .graves li { margin:4px 0; }
  .graves .cf { font-size:12px; }
  @media (max-width:760px) {
    .cal-h2 { font-size:23px; }
    .c-top { grid-template-columns:minmax(0,1fr); }
    .m-grid { display:none; } .m-lista { display:block; }
    .t-est thead { display:none; }
    .t-est tr { display:grid; grid-template-columns:minmax(0,1fr) auto; border-bottom:1px solid var(--linea); padding:6px 0; }
    .t-est td { border:0; padding:2px 0; }
    .t-est td:nth-child(2) { text-align:right; }
    .t-est td:nth-child(3), .t-est td:nth-child(4) { grid-column:1 / -1; }
  }
"""

JS = """
document.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('.tab, .mes').forEach(x => x.classList.remove('activo'));
  b.classList.add('activo'); document.getElementById('mes-' + b.dataset.mes).classList.add('activo');
}));
const otras = document.getElementById('ver-otras');
if (otras) otras.addEventListener('change', () => document.body.classList.toggle('otras', otras.checked));
"""


def _tile(d: date) -> str:
    return (f'<span class="tile"><span class="tile-d">{A.DIAS_SEMANA[d.weekday()]}</span>'
            f'<span class="tile-n">{d.day}</span><span class="tile-m">{MESES_CORTOS[d.month - 1]}</span></span>')


def _linea_html(linea: str, antes: str = "") -> str:
    """La línea del B2 (texto plano de agenda) con las mismas clases que el dashboard."""
    partes = [escape(p) for p in linea.split(" · ")]
    partes[0] = f'<span class="per">{partes[0]}</span>'
    partes = [{"✓ al día": '<span class="ok">✓ al día</span>',
               "⚠ atrasado": '<span class="atr">⚠ atrasado</span>'}.get(p, p) for p in partes]
    return f'<div class="cf">{escape(antes)}' + " · ".join(partes) + "</div>"


def _hoy(cal: dict, ctx: F.Contexto) -> str:
    if cal.get("estado") == "no_disponible":
        return '<p class="c-vacio">Calendario del INDEC no disponible hoy.</p>'
    if cal.get("hoy"):
        return "".join(f'<p class="c-hoy-pub"><b>{escape(i["titulo"])}</b> · {escape(i["fuente"])} · {escape(i["hora"])}'
                       '<span>el dato entra en la próxima actualización del monitor</span></p>' for i in cal["hoy"])
    if cal.get("feriado_hoy"):
        return (f'<p class="c-vacio">Hoy es feriado ({escape(cal["feriado_hoy"])}): no publica el INDEC ni operan '
                'el BCRA y BYMA.</p>')
    if not ctx.hoy.weekday() < 5:
        return '<p class="c-vacio">No hay publicaciones: hoy no es día hábil.</p>'
    return '<p class="c-vacio">Hoy no se publica nada de lo que usa el monitor.</p>'


def _semana(cal: dict, ctx: F.Contexto, dias: dict, publicaciones: dict) -> str:
    if cal.get("estado") == "no_disponible":
        return '<p class="c-vacio">Calendario del INDEC no disponible hoy.</p>'
    salida, d, fin = "", ctx.hoy + timedelta(days=1), A.fin_ventana(ctx)
    while d <= fin:
        dia = dias.get(d.isoformat(), {})
        seguidas = [p for p in dia.get("publicaciones", []) if p["pid"]]
        feriado = dia.get("feriado")
        if d.weekday() >= 5 and not seguidas and not feriado:
            d += timedelta(days=1)
            continue
        cont = f'<span class="c-fer">Feriado · {escape(feriado)}</span>' if feriado else ""
        for p in seguidas:
            linea = (publicaciones.get(p["pid"]) or {}).get("linea")
            if linea:   # sin "· próximo DD/MM, HH h": repetiría la fecha del día (pedido de Pedro)
                linea = " · ".join(x for x in linea.split(" · ") if not x.startswith("próximo"))
            cont += (f'<div class="c-pub"><b>{escape(p["titulo"])}</b> · INDEC · {escape(p["hora"])}'
                     + (_linea_html(linea, "hoy el monitor muestra ") if linea else "") + "</div>")
        if not cont:
            cont = '<div class="c-nada">sin publicaciones de las que usa el monitor</div>'
        salida += f'<div class="c-dia{" c-dia-fer" if feriado else ""}">{_tile(d)}<div class="c-cont">{cont}</div></div>'
        d += timedelta(days=1)
    return salida


def _estado(cfg: dict, publicaciones: dict, prox: dict) -> str:
    filas = ""
    for pub in cfg["publicaciones"]:
        p = publicaciones.get(pub["id"])
        if not p:
            continue
        resto = p["linea"].split(" · ")[1:] if p.get("linea") else []
        estado, detalle = "", ""
        if p.get("estado") == "al_dia":
            estado = '<span class="ok">✓ al día</span>'
        elif p.get("estado") == "atrasado":
            estado = '<span class="atr">⚠ atrasado</span>'
            detalle = " · ".join(resto[1:])
        elif resto:
            estado = escape(" · ".join(resto))
        pr = prox.get(pub["id"])
        proxima = f'{escape(pr["titulo"])}<span class="det">{escape(pr["dia"])}, {escape(pr["hora"])}</span>' if pr else \
            '<span class="det">todavía no figura en el calendario del INDEC</span>'
        filas += (f'<tr><td>{escape(pub["nombre_corto"])}</td>'
                  f'<td class="per">{F.texto_periodo(pd.Period(p["periodo"]))}</td>'
                  f'<td>{estado}{f"<span class=det>{escape(detalle)}</span>" if detalle else ""}</td>'
                  f'<td>{proxima}</td></tr>')
    return ('<table class="tabla t-est"><thead><tr><th>Publicación</th><th>En el monitor</th><th>Estado</th>'
            f'<th>Próxima</th></tr></thead><tbody>{filas}</tbody></table>')


def _item_mes(p: dict) -> str:
    if not p["pid"]:
        return f'<div class="m-otra">{escape(p["titulo"])}</div>'
    mk, tit = MARCA.get(p["estado"] or "proximo", ("", ""))
    marca = f'<span class="mk" title="{escape(tit)}">{mk}</span>' if mk else ""
    return f'<div class="m-pub e-{p["estado"] or "proximo"}" title="{escape(tit)}">{marca}{escape(p["titulo"])}</div>'


def _mes(m: dict) -> str:
    if not m["disponible"]:
        return f'<p class="c-vacio">El calendario de {escape(m["nombre"])} no está en la caché.</p>'
    primero = date.fromisoformat(m["dias"][0]["fecha"])
    celdas = '<div class="m-c m-vacia"></div>' * primero.weekday()
    lista = ""
    for d in m["dias"]:
        cls = "m-c" + (" m-hoy" if d["hoy"] else "") + (" m-fer" if d["feriado"] else "") + \
              (" m-fin" if date.fromisoformat(d["fecha"]).weekday() >= 5 and not d["feriado"] else "") + \
              (" m-pasado" if d["pasado"] else "")
        items = "".join(_item_mes(p) for p in d["publicaciones"])
        fer = f'<div class="m-fer-l">Feriado</div>' if d["feriado"] else ""
        hoy = '<span class="m-hoy-l">hoy</span>' if d["hoy"] else ""
        celdas += f'<div class="{cls}"><div class="m-n">{d["numero"]}{hoy}</div>{fer}{items}</div>'
        if d["publicaciones"] or d["feriado"]:
            solo_otras = not d["feriado"] and all(not p["pid"] for p in d["publicaciones"])
            fer_l = f'<div class="m-fer-l">Feriado · {escape(d["feriado"])}</div>' if d["feriado"] else ""
            lista += (f'<div class="l-fila{" l-solo-otras" if solo_otras else ""}{" m-pasado" if d["pasado"] else ""}">'
                      f'<span class="l-d">{d["dia"]} {d["numero"]:02d}/{d["fecha"][5:7]}</span>'
                      f'<span class="l-t">{fer_l}{items}</span></div>')
    cab = "".join(f'<div class="m-h">{x}</div>' for x in A.DIAS_SEMANA)
    return f'<div class="m-grid">{cab}{celdas}</div><div class="m-lista">{lista}</div>'


def html(agenda: dict | None, meses: list[dict], prox: dict, sin_cal: list[str], ctx: F.Contexto, cfg: dict) -> str:
    ahora_txt = ctx.ahora.strftime("%d/%m/%Y %H:%M")
    sub = f"Calendario de publicaciones · actualizado {ahora_txt}"
    if agenda is None:
        cuerpo = ('<h2 class="cal-h2">Calendario de publicaciones</h2>'
                  '<p class="aviso">Calendario del INDEC no disponible hoy: no se muestran fechas de publicación.</p>')
        return sitio.pagina("Calendario · Monitor de coyuntura", "Monitor de coyuntura · Argentina", sub,
                            sitio.nav_sitio("../", "Calendario"), cuerpo, css=CSS, pie=sitio.pie_sitio("../"))
    cal, publicaciones = agenda["calendario"], agenda["publicaciones"]
    dias = {d["fecha"]: d for m in meses for d in m["dias"]}
    actual = f"{ctx.hoy.year}-{ctx.hoy.month:02d}"
    bajado = next((m["bajado"] for m in meses if m["clave"] == actual and m["bajado"]), None)
    bajado_txt = datetime.fromisoformat(bajado).strftime("%d/%m a las %H:%M") if bajado else None
    aviso = ""
    if cal.get("estado") == "cache_vieja":
        aviso = (f'<p class="aviso">Fechas según el calendario del INDEC bajado el {escape(cal["bajado"])}: no se pudo '
                 'actualizar desde entonces.</p>')
    disponibles = [m for m in meses if m["disponible"]]
    tabs = "".join(f'<button class="tab{" activo" if m["clave"] == actual else ""}" data-mes="{m["clave"]}">'
                   f'{escape(m["nombre"].replace(" de " + str(ctx.hoy.year), ""))}</button>' for m in disponibles)
    meses_html = "".join(f'<div class="mes{" activo" if m["clave"] == actual else ""}" id="mes-{m["clave"]}">{_mes(m)}</div>'
                         for m in disponibles)
    leyenda = " · ".join(f"{mk} {t}" for mk, t in (MARCA["incorporado"], MARCA["publicado"], MARCA["atrasado"])) + \
        " · sin marca: todavía no se publicó"
    atr = "".join(f'<li>{escape(a["texto"])}</li>' for a in agenda.get("atrasados", []))
    graves = "".join(f'<li><div class="cf grave">{escape(g["texto"])}</div></li>' for g in agenda.get("graves", []))
    demorados = (f'<ul class="avisos">{atr}</ul>' if atr else "") + (f'<ul class="graves">{graves}</ul>' if graves else "")
    if not demorados:
        demorados = '<p class="c-vacio">No hay datos demorados.</p>'
    sin_cal_html = (f'<p class="bajada">Se actualizan cuando publica la fuente; el monitor no les inventa fecha: '
                    f'{escape(", ".join(sin_cal))}.</p>') if sin_cal else ""
    cuerpo = f"""
<h2 class="cal-h2">Calendario de publicaciones</h2>
<p class="bajada">Publicaciones del INDEC que alimentan el monitor, con las fechas de su calendario oficial{f" (bajado el {bajado_txt})" if bajado_txt else ""}.
Las series del BCRA, del Ministerio de Economía y de los mercados no tienen calendario oficial: no se les estima fecha.</p>
{aviso}
<div class="c-top">
  <section><h3 class="grupo">Hoy · {A.dia_corto(ctx.hoy)}</h3>{_hoy(cal, ctx)}</section>
  <section><h3 class="grupo">Esta semana · hasta el {escape(cal.get("hasta", ""))}</h3>{_semana(cal, ctx, dias, publicaciones)}</section>
</div>
<section><h3 class="grupo">Cada publicación en el monitor</h3>{_estado(cfg, publicaciones, prox)}</section>
<section>
  <div class="mes-h"><h3 class="grupo">Mes</h3><div class="tabs">{tabs}</div>
    <label class="ver-otras"><input type="checkbox" id="ver-otras"> mostrar también las publicaciones del INDEC que no usa el monitor</label></div>
  {meses_html}
  <p class="leyenda">{escape(leyenda)}</p>
</section>
<section id="demorados"><h3 class="grupo">Datos demorados</h3>{demorados}</section>
{f'<section><h3 class="grupo">Sin calendario oficial ({len(sin_cal)} series)</h3>{sin_cal_html}</section>' if sin_cal else ""}
"""
    pie = (f'Fechas: <a href="{URL_CALENDARIO_INDEC}">calendario oficial del INDEC</a>. Días no hábiles: los días en '
           'que no operan el INDEC, el BCRA y BYMA (feriados nacionales y los especiales que alcanzan a esos organismos).')
    return sitio.pagina("Calendario · Monitor de coyuntura", "Monitor de coyuntura · Argentina", sub,
                        sitio.nav_sitio("../", "Calendario"), cuerpo, css=CSS, js=JS, pie=sitio.pie_sitio("../", pie))


def generar(agenda: dict | None, meses: list[dict], prox: dict, sin_cal: list[str], ctx: F.Contexto, cfg: dict,
            ruta: Path = SALIDA) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(html(agenda, meses, prox, sin_cal, ctx, cfg), encoding="utf-8")
    return ruta


def meses_a_mostrar(hoy: date, atras: int = 1, adelante: int = 2) -> list[str]:
    """El mes anterior, el actual y los dos siguientes (los que estén en la caché se muestran como pestañas)."""
    claves = []
    for n in range(-atras, adelante + 1):
        a, m = divmod(hoy.year * 12 + hoy.month - 1 + n, 12)
        claves.append(f"{a}-{m + 1:02d}")
    return claves

"""
fuentes_trabajo.py
------------------
RIPTE (Remuneración Imponible Promedio de los Trabajadores Estables) desde la publicación de la Secretaría
de Trabajo, Empleo y Seguridad Social (decisión de Pedro del 08/11/2026, #1 y #21 de PENDIENTES): la API de
datos.gob.ar (158.1_REPTE_0_0_5) devuelve 0 filas y su CSV de distribución trae ago-2026 con el valor de
jun-2026. Sin fallback a datos.gob.ar.

Página: https://www.argentina.gob.ar/trabajo/seguridadsocial/ripte. Trae, en cada publicación:
  - el encabezado "Publicación <Mes> <Año>" y el valor destacado de ese mes;
  - un PDF con la serie completa desde jul-1994 (monto en $, variación % mensual, índice base 07/94 = 100 e
    índice no decreciente). Su nombre cambia con cada publicación y sin patrón fijo (ripte_mayo2025-mdch.pdf,
    ripte_octubre_2024.pdf, ripte_noviembre_2023-mdch_0.pdf...): se toma el link de la página;
  - una tabla HTML con los últimos 20 meses (cargada a mano: "Agosto2026", "Abril/2026").

Las dos son rascados; lo que impide que se rompan en silencio son los controles que trae la propia fuente:
  - PDF: cada línea con un monto tiene que leerse (mes, monto, variación, índice, índice no decreciente);
    los meses son consecutivos desde jul-1994 (874,87); el índice publicado coincide con monto / 874,87 × 100;
    la variación % publicada coincide fila por fila con la calculada desde los montos (si se pierde o se
    duplica una fila, la de al lado no cierra); el último mes es el del encabezado de la página y del título
    del PDF, su monto es el valor destacado, y los 20 meses de la tabla HTML coinciden con el PDF.
  - Tabla HTML (escalón de respaldo): encabezado de 5 columnas fijo, meses consecutivos, variación % fila por
    fila y último mes = encabezado "Publicación <Mes> <Año>".
Si el PDF falla (link, descarga o cualquier control) y la tabla pasa los suyos, se usan las filas de la tabla
(el merge de storage.py conserva lo anterior) y sale alerta. Si fallan los dos, RipteError: el indicador va a
`problemas` de ultima_corrida.json, el histórico queda intacto y sale alerta. Nunca una serie vacía.

Caché: en cada corrida se baja la página (liviana); el PDF sólo si cambió su link o el mes del encabezado
respecto de lo cacheado (data/_cache_ripte.csv + data/_cache_ripte_meta.json). Sólo una serie que pasó todos
los controles pisa el caché.

Estado y alertas: en el mismo _cache_ripte_meta.json (clave `estado`: racha de corridas seguidas sin el PDF,
último aviso por motivo). Mismo criterio que las alertas de datos.gob.ar/INDEC (fuentes_indec._toca_aviso y
enviar_alerta): el primer día y después una vez por semana, máx. 1 mail por corrida, SÓLO a Pedro.
"""
from __future__ import annotations

import html as _html
import io
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent
URL_PAGINA = "https://www.argentina.gob.ar/trabajo/seguridadsocial/ripte"
BASE = "https://www.argentina.gob.ar"
CACHE_CSV = RAIZ / "data" / "_cache_ripte.csv"
CACHE_META = RAIZ / "data" / "_cache_ripte_meta.json"

PRIMER_MES = pd.Timestamp("1994-07-01")
PRIMER_MONTO = 874.87
TOL_VAR = 0.0501        # pp: la variación se publica redondeada a 1 decimal
TOL_INDICE = 0.02       # puntos del índice (2 decimales; máx. observado 0,0054 en 386 meses)
TOL_MONTO = 0.005       # $: montos con 2 decimales
MIN_FILAS_TABLA = 12

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
         "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
ENCABEZADOS_TABLA = ["mes", "monto (en pesos)", "variacion respecto mes anterior", "ib 07/1994 = 100",
                     "ripte - ind"]


class RipteError(RuntimeError):
    """Ni el PDF ni la tabla de la página pasaron sus controles: no hay serie del RIPTE en esta corrida."""


class RipteFormatoError(ValueError):
    """Una de las dos fuentes (PDF o tabla) no pasó un control."""


# ---------------------------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------------------------
def _norm(s: str) -> str:
    """Minúsculas, sin acentos, sin &nbsp; y con los espacios colapsados."""
    s = _html.unescape(s).replace("\xa0", " ")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


def _texto(fragmento: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", fragmento)).replace("\xa0", " ")).strip()


def _monto(s: str) -> float:
    t = s.replace("$", "").replace(" ", "").replace("\xa0", "")
    if not re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d+)?|\d+(,\d+)?", t):
        raise RipteFormatoError(f"monto ilegible: {s!r}")
    return float(t.replace(".", "").replace(",", "."))


def _variacion(s: str) -> float | None:
    t = s.replace(" ", "").replace("\xa0", "")
    if t == "-":
        return None
    if not re.fullmatch(r"-?\d+(,\d+)?%", t):
        raise RipteFormatoError(f"variación ilegible: {s!r}")
    return float(t.rstrip("%").replace(",", "."))


def _mes(nombre: str, anio: str | int) -> pd.Timestamp:
    n = _norm(nombre)
    if n not in MESES:
        raise RipteFormatoError(f"mes desconocido: {nombre!r}")
    return pd.Timestamp(int(anio), MESES[n], 1)


def _mmm(f: pd.Timestamp) -> str:
    return f.strftime("%Y-%m")


# ---------------------------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------------------------
def parsear_pagina(html: str) -> dict:
    """Partes de la página, cada una por separado (una que falla no impide leer las otras):
    {mes, destacado, pdf_url, tabla} y, para la que no se pudo leer, {error_<parte>: motivo}."""
    out: dict = {}
    # Encabezado "Publicación <Mes> <Año>"
    h2 = [_texto(x) for x in re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S)]
    pub = [m for m in (re.fullmatch(r"publicacion ([a-z]+) (\d{4})", _norm(x)) for x in h2) if m]
    if len(pub) == 1:
        try:
            out["mes"] = _mes(*pub[0].groups())
        except RipteFormatoError as e:
            out["error_mes"] = f"encabezado de la publicación: {e}"
    else:
        out["error_mes"] = (f"se esperaba un encabezado 'Publicación <Mes> <Año>' y hay {len(pub)}")
    # Valor destacado: "$ 1.982.518,19" + "agosto 2026"
    m = re.search(r'<span class="h3">\s*([^<]*\$[^<]*)</span>\s*<p>([^<]*)</p>', html)
    try:
        if not m:
            raise RipteFormatoError("no se encontró el valor destacado")
        mm = re.fullmatch(r"([a-z]+) (\d{4})", _norm(m.group(2)))
        if not mm:
            raise RipteFormatoError(f"mes del valor destacado ilegible: {m.group(2)!r}")
        out["destacado"] = (_mes(*mm.groups()), _monto(m.group(1)))
    except RipteFormatoError as e:
        out["error_destacado"] = str(e)
    # Link del PDF (hoy viene como href="blank:#/sites/default/files/..."; se toma la ruta desde /sites/)
    rutas = sorted({r for r in re.findall(r'href="[^"]*?(/sites/default/files/[^"#?\s]+\.pdf)"', html, re.I)
                    if "ripte" in r.lower()})
    if len(rutas) == 1:
        out["pdf_url"] = BASE + rutas[0]
    else:
        out["error_pdf_url"] = f"se esperaba un link al PDF del RIPTE y hay {len(rutas)}: {rutas}"
    # Tabla de los últimos meses
    try:
        out["tabla"] = parsear_tabla(html)
    except RipteFormatoError as e:
        out["error_tabla"] = str(e)
    return out


def parsear_tabla(html: str) -> pd.DataFrame:
    """La única <table> cuyo encabezado es el del RIPTE -> fecha | valor | var (ordenada por fecha)."""
    candidatas = []
    for t in re.findall(r"<table[^>]*>(.*?)</table>", html, re.S):
        ths = [_norm(_texto(x)) for x in re.findall(r"<th[^>]*>(.*?)</th>", t, re.S)]
        if len(ths) == len(ENCABEZADOS_TABLA) and all(h.startswith(e) for h, e in zip(ths, ENCABEZADOS_TABLA)):
            candidatas.append(t)
    if len(candidatas) != 1:
        raise RipteFormatoError(f"se esperaba una tabla con el encabezado del RIPTE y hay {len(candidatas)}")
    filas = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", candidatas[0], re.S):
        tds = [_texto(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if not tds:
            continue
        if len(tds) != len(ENCABEZADOS_TABLA):
            raise RipteFormatoError(f"fila de la tabla con {len(tds)} columnas: {tds}")
        m = re.fullmatch(r"([a-z]+)\s*/?\s*(\d{4})", _norm(tds[0]))
        if not m:
            raise RipteFormatoError(f"mes de la tabla ilegible: {tds[0]!r}")
        filas.append({"fecha": _mes(*m.groups()), "valor": _monto(tds[1]), "var": _variacion(tds[2])})
    if not filas:
        raise RipteFormatoError("la tabla no tiene filas")
    return pd.DataFrame(filas).sort_values("fecha").reset_index(drop=True)


# ---------------------------------------------------------------------------------------------
# PDF (texto extraído con pdfplumber, una página tras otra)
# ---------------------------------------------------------------------------------------------
_FILA_PDF = re.compile(r"([A-Za-zÁÉÍÓÚáéíóú]+)\s+\$\s*([\d.]+(?:,\d+)?)\s+(-|-\s?\d+(?:,\d+)?%|\d+(?:,\d+)?%)"
                       r"\s+([\d.]+,\d+)\s+([\d.]+,\d+)")


def texto_pdf(contenido: bytes) -> str:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def parsear_pdf(texto: str) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    """(fecha | valor | var | indice, mes del título). Cada línea con un monto tiene que ser una fila
    legible bajo un año; si no, RipteFormatoError (nada se saltea en silencio)."""
    anio = None
    filas = []
    titulo = None
    for linea in (l.strip() for l in texto.splitlines()):
        if re.fullmatch(r"(19|20)\d\d", linea):
            anio = int(linea)
            continue
        if titulo is None:
            m = re.fullmatch(r"([A-Za-zÁÉÍÓÚáéíóú]+) ((?:19|20)\d\d)", linea)
            if m and _norm(m.group(1)) in MESES:
                titulo = _mes(*m.groups())
                continue
        m = _FILA_PDF.fullmatch(linea)
        if m:
            if anio is None:
                raise RipteFormatoError(f"fila del PDF antes de cualquier año: {linea!r}")
            filas.append({"fecha": _mes(m.group(1), anio), "valor": _monto(m.group(2)),
                          "var": _variacion(m.group(3)), "indice": _monto(m.group(4))})
        elif re.search(r"\$\s*\d", linea):
            raise RipteFormatoError(f"línea del PDF con un monto que no se pudo leer: {linea!r}")
    if not filas:
        raise RipteFormatoError("el PDF no tiene filas legibles")
    return pd.DataFrame(filas), titulo


# ---------------------------------------------------------------------------------------------
# Controles
# ---------------------------------------------------------------------------------------------
def _consecutivos(df: pd.DataFrame, donde: str):
    esperado = pd.date_range(df["fecha"].iloc[0], periods=len(df), freq="MS")
    if list(df["fecha"]) != list(esperado):
        malo = next(f for f, e in zip(df["fecha"], esperado) if f != e)
        raise RipteFormatoError(f"{donde}: los meses no son consecutivos (falta, sobra o se repite cerca de "
                                f"{_mmm(malo)})")


def _variaciones(df: pd.DataFrame, donde: str):
    calc = df["valor"].pct_change() * 100
    for i in range(1, len(df)):
        pub = df["var"].iloc[i]
        if pub is None or pd.isna(pub) or abs(pub - calc.iloc[i]) > TOL_VAR:
            raise RipteFormatoError(f"{donde}: la variación publicada de {_mmm(df['fecha'].iloc[i])} ({pub}) no "
                                    f"coincide con la calculada desde los montos ({calc.iloc[i]:.2f})")


def _ultimo_mes(df: pd.DataFrame, mes: pd.Timestamp, donde: str):
    if df["fecha"].iloc[-1] != mes:
        raise RipteFormatoError(f"{donde}: el último mes es {_mmm(df['fecha'].iloc[-1])} y el encabezado de la "
                                f"página dice {_mmm(mes)}")


def validar_tabla(tabla: pd.DataFrame, mes: pd.Timestamp) -> pd.DataFrame:
    """Controles propios de la tabla HTML (escalón de respaldo)."""
    if len(tabla) < MIN_FILAS_TABLA:
        raise RipteFormatoError(f"tabla: {len(tabla)} filas (mínimo {MIN_FILAS_TABLA})")
    _consecutivos(tabla, "tabla")
    _variaciones(tabla, "tabla")
    _ultimo_mes(tabla, mes, "tabla")
    return tabla[["fecha", "valor"]].reset_index(drop=True)


def validar_pdf(serie: pd.DataFrame, titulo, mes: pd.Timestamp, destacado, tabla: pd.DataFrame | None
                ) -> pd.DataFrame:
    """Controles del PDF: historia, índice, variación fila por fila y control cruzado con la página."""
    if serie["fecha"].iloc[0] != PRIMER_MES or abs(serie["valor"].iloc[0] - PRIMER_MONTO) > TOL_MONTO:
        raise RipteFormatoError(f"PDF: la serie no arranca en jul-1994 con $ 874,87 "
                                f"({_mmm(serie['fecha'].iloc[0])}, {serie['valor'].iloc[0]})")
    _consecutivos(serie, "PDF")
    dif = (serie["indice"] - serie["valor"] / PRIMER_MONTO * 100).abs()
    if dif.max() > TOL_INDICE:
        i = int(dif.idxmax())
        raise RipteFormatoError(f"PDF: el índice publicado de {_mmm(serie['fecha'].iloc[i])} no coincide con "
                                f"monto / 874,87 × 100 (diferencia {dif.iloc[i]:.4f})")
    _variaciones(serie, "PDF")
    _ultimo_mes(serie, mes, "PDF")
    if titulo != mes:
        raise RipteFormatoError(f"PDF: el título dice {_mmm(titulo) if titulo is not None else '¿?'} y la "
                                f"página {_mmm(mes)}")
    if destacado is None:
        raise RipteFormatoError("PDF: no hay valor destacado en la página para comparar")
    if destacado[0] != mes or abs(serie["valor"].iloc[-1] - destacado[1]) > TOL_MONTO:
        raise RipteFormatoError(f"PDF: el último monto ({serie['valor'].iloc[-1]}) no es el valor destacado de "
                                f"la página ({_mmm(destacado[0])}: {destacado[1]})")
    if tabla is None:
        raise RipteFormatoError("PDF: no hay tabla válida en la página para el control cruzado")
    cruce = tabla.merge(serie, on="fecha", how="left", suffixes=("_t", "_p"))
    malos = cruce[cruce["valor_p"].isna() | ((cruce["valor_t"] - cruce["valor_p"]).abs() > TOL_MONTO)]
    if not malos.empty:
        f = malos.iloc[0]
        raise RipteFormatoError(f"PDF: {_mmm(f['fecha'])} no coincide con la tabla de la página "
                                f"(PDF {f['valor_p']}, tabla {f['valor_t']})")
    return serie[["fecha", "valor"]].reset_index(drop=True)


# ---------------------------------------------------------------------------------------------
# Decisión: PDF (cacheado o nuevo) -> tabla -> error
# ---------------------------------------------------------------------------------------------
def resolver(html: str, cache: dict | None, bajar_pdf) -> tuple[pd.DataFrame, dict]:
    """Función sin red ni disco. `cache` = {"pdf_url", "mes" (AAAA-MM-01), "serie"} o None; `bajar_pdf(url)`
    devuelve el TEXTO del PDF. Devuelve (fecha | valor, info) con info = {fuente: pdf|pdf_cache|tabla, mes,
    pdf_url, motivo, cache_nuevo}; `cache_nuevo` (sólo si se bajó y validó un PDF) es lo que hay que guardar.
    Si fallan el PDF y la tabla, RipteError con los dos motivos."""
    pag = parsear_pagina(html)
    mes = pag.get("mes")
    tabla, error_tabla = None, None
    if mes is None:
        error_tabla = pag["error_mes"]
    elif "tabla" not in pag:
        error_tabla = pag["error_tabla"]
    else:
        try:
            tabla = validar_tabla(pag["tabla"], mes)
        except RipteFormatoError as e:
            error_tabla = str(e)
    info = {"mes": _mmm(mes) if mes is not None else None, "pdf_url": pag.get("pdf_url"), "cache_nuevo": None}
    # 1) PDF
    try:
        for k in ("mes", "pdf_url", "destacado"):
            if k not in pag:
                raise RipteFormatoError(pag[f"error_{k}"])
        en_cache = (cache is not None and cache.get("pdf_url") == pag["pdf_url"]
                    and cache.get("mes") == mes.strftime("%Y-%m-01") and cache.get("serie") is not None)
        if en_cache:
            serie = cache["serie"]
            # se repiten los controles contra la página de hoy (la tabla o el destacado pueden haber cambiado)
            _ultimo_mes(serie, mes, "PDF (caché)")
            if tabla is None:
                raise RipteFormatoError("PDF (caché): no hay tabla válida en la página para el control cruzado")
            cruce = tabla.merge(serie, on="fecha", how="left", suffixes=("_t", "_p"))
            if (cruce["valor_p"].isna() | ((cruce["valor_t"] - cruce["valor_p"]).abs() > TOL_MONTO)).any():
                en_cache = False   # la página cambió algún valor: se vuelve a bajar el PDF
            elif abs(serie["valor"].iloc[-1] - pag["destacado"][1]) > TOL_MONTO:
                en_cache = False
        if en_cache:
            return serie.copy(), dict(info, fuente="pdf_cache", motivo=None)
        try:
            texto = bajar_pdf(pag["pdf_url"])
        except Exception as e:
            raise RipteFormatoError(f"no se pudo bajar el PDF ({type(e).__name__}: {e})")
        crudo, titulo = parsear_pdf(texto)
        serie = validar_pdf(crudo, titulo, mes, pag["destacado"], tabla)
        nuevo = {"pdf_url": pag["pdf_url"], "mes": mes.strftime("%Y-%m-01"), "serie": serie}
        return serie.copy(), dict(info, fuente="pdf", motivo=None, cache_nuevo=nuevo)
    except RipteFormatoError as e:
        error_pdf = str(e)
    # 2) tabla
    if tabla is not None:
        return tabla.copy(), dict(info, fuente="tabla",
                                  motivo=f"el PDF no pasó los controles ({error_pdf}); se usaron los "
                                         f"{len(tabla)} meses de la tabla de la página")
    raise RipteError(f"RIPTE (Secretaría de Trabajo): fallaron el PDF ({error_pdf}) y la tabla ({error_tabla})")


# ---------------------------------------------------------------------------------------------
# Red, disco y estado (lo usa run.py vía fetchers.traer / cerrar_corrida)
# ---------------------------------------------------------------------------------------------
ULTIMA: dict | None = None   # resultado de esta corrida, para cerrar_corrida()


def cargar_meta() -> dict:
    if CACHE_META.exists():
        try:
            return json.loads(CACHE_META.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def _guardar_meta(meta: dict):
    CACHE_META.parent.mkdir(exist_ok=True)
    CACHE_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cargar_cache() -> dict | None:
    c = cargar_meta().get("cache")
    if not c or not CACHE_CSV.exists():
        return None
    try:
        return dict(c, serie=pd.read_csv(CACHE_CSV, parse_dates=["fecha"]))
    except (ValueError, OSError):
        return None


def guardar_cache(nuevo: dict, hoy: str):
    CACHE_CSV.parent.mkdir(exist_ok=True)
    nuevo["serie"].to_csv(CACHE_CSV, index=False)
    meta = cargar_meta()
    meta["cache"] = {"pdf_url": nuevo["pdf_url"], "mes": nuevo["mes"], "descargado": hoy}
    _guardar_meta(meta)


def serie(start_date: str | None = None) -> pd.DataFrame:
    """RIPTE en pesos corrientes, mensual (fecha = 1.º del mes). Levanta RipteError si no hay serie."""
    global ULTIMA
    import fetchers
    from fuentes_indec import _hoy
    hoy = _hoy()
    try:
        r = fetchers._get(URL_PAGINA)
        html = r.content.decode("utf-8", errors="replace")
    except Exception as e:
        ULTIMA = {"fuente": "error", "motivo": f"no se pudo bajar la página {URL_PAGINA} ({e})"}
        raise RipteError(f"RIPTE (Secretaría de Trabajo): {ULTIMA['motivo']}")

    def bajar_pdf(url):
        return texto_pdf(fetchers._get(url).content)

    try:
        df, info = resolver(html, cargar_cache(), bajar_pdf)
    except RipteError as e:
        ULTIMA = {"fuente": "error", "motivo": str(e)}
        raise
    if info["cache_nuevo"] is not None:
        guardar_cache(info["cache_nuevo"], hoy)
    ULTIMA = {k: info[k] for k in ("fuente", "motivo", "mes", "pdf_url")}
    print(f"  [trabajo] RIPTE: {info['fuente']} (publicación {info['mes']}, {len(df)} meses)"
          + (f" — {info['motivo']}" if info["motivo"] else ""))
    if info["fuente"] == "tabla":
        print(f"::warning title=RIPTE (Secretaría de Trabajo)::{info['motivo']}")
    if start_date:
        df = df[df["fecha"] >= pd.to_datetime(start_date)]
    return df.reset_index(drop=True)


def actualizar_estado(estado: dict, ultima: dict | None, hoy: str) -> list[tuple[str, str]]:
    """Racha de corridas seguidas sin el PDF y alertas a mandar (función pura sobre `estado`). Sin
    corrida del RIPTE (`ultima` None) no cambia nada. Alerta el primer día de cada motivo y después una vez
    por semana mientras siga."""
    from fuentes_indec import _toca_aviso, DIAS_REPETICION
    if ultima is None:
        return []
    avisos = estado.setdefault("avisos", {})
    if ultima["fuente"] in ("pdf", "pdf_cache"):
        estado["racha"] = 0
        return []
    estado["racha"] = estado.get("racha", 0) + 1
    clave = f"ripte:{ultima['fuente']}"
    if estado["racha"] == 1 or _toca_aviso(avisos, clave, hoy, DIAS_REPETICION):
        que = ("se usó la tabla de la página (últimos 20 meses; el resto queda del histórico)"
               if ultima["fuente"] == "tabla" else "no hay serie nueva: el histórico guardado queda intacto")
        return [(clave, f"{ultima['motivo']}. Resultado: {que}. Corridas seguidas sin el PDF: {estado['racha']}. "
                        f"Página: {URL_PAGINA}")]
    return []


def cerrar_corrida() -> dict | None:
    """Guarda el estado, manda (como mucho) un mail a Pedro y devuelve el resumen para ultima_corrida.json."""
    from fuentes_indec import _hoy, enviar_alerta
    if ULTIMA is None:
        return None
    hoy = _hoy()
    meta = cargar_meta()
    estado = meta.setdefault("estado", {})
    items = actualizar_estado(estado, ULTIMA, hoy)
    if items:
        if enviar_alerta("[Coyuntura] RIPTE (Secretaría de Trabajo): " +
                         ("se usó la tabla de la página" if ULTIMA["fuente"] == "tabla" else "sin datos en la corrida"),
                         "\n\n".join(t for _, t in items) + "\n\nEstado: data/_cache_ripte_meta.json en el repo.",
                         titulo="RIPTE (Secretaría de Trabajo)"):
            for clave, _ in items:
                estado["avisos"][clave] = hoy
    estado["ultima"] = dict(ULTIMA, fecha=hoy)
    _guardar_meta(meta)
    return dict(ULTIMA, racha=estado.get("racha", 0))

"""
fuentes_indec.py
----------------
Bloque A (A4-A5) de PROMPT_ronda_macro_indec.md: las series del INDEC se traen de la API del
INDEC como fuente PRIMARIA y, si falla, de su fuente original como FALLBACK.

  - ResolverIndec: trae cada serie (o variación publicada) de la API, con fallback, y registra
    qué fuente se usó en cada indicador de la corrida.
  - cerrar_corrida(): guarda el estado entre corridas (data/indec_estado.json: rachas de
    fallback, última fuente por indicador, fechas de avisos) y manda las alertas a Pedro.

Mapeo datos.gob.ar -> API: sección `equivalencias_indec` de indicadores.yaml (verificada en
fuentes/indec_equivalencias.md). El token NUNCA se imprime ni entra en un mensaje.
"""
from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from fetchers import (fetch_indec_api, fetch_datos_gob, fetch_argentinadatos, datos_gob_filas,
                      indec_token_exp, IndecAuthError)

RAIZ = Path(__file__).resolve().parent
ESTADO = RAIZ / "data" / "indec_estado.json"
ZONA_AR = ZoneInfo("America/Argentina/Buenos_Aires")

# Alertas: SÓLO a Pedro, no al MAIL_TO general del resumen diario (PROMPT_ronda_macro_indec.md, A5).
ALERTA_DESTINO = "pedrothill31@gmail.com"
DIAS_AVISO_VENCIMIENTO = 30   # aviso cuando faltan 30 días o menos para el `exp` del token
DIAS_REPETICION = 7           # los avisos persistentes se repiten una vez por semana
RACHA_FALLBACK_AVISO = 3      # aviso cuando el fallback se usa MÁS de 3 corridas seguidas

API = "indec_api"
FALLBACK_DG = "datos_gob_ar"
FALLBACK_AD = "argentinadatos"
DOCS_API = "https://api.indec.gob.ar/docs"
# Ficha pública de cada tabla: el slug es el nombre de la tabla de la API (verificado el 07/11/2026
# para las 6 tablas en uso; un slug inexistente muestra "Dataset no encontrado" con HTTP 200).
DATASET_API = "https://api.indec.gob.ar/datasets/{tabla}"


def _hoy() -> str:
    return datetime.now(ZONA_AR).date().isoformat()


class ResolverIndec:
    def __init__(self, equivalencias: dict | None, start: str | None, fetch_dg=None):
        self.eq = equivalencias or {}
        # cómo se baja una serie de datos.gob.ar (fallback y series sin equivalencia); run.py pasa el
        # ResolverDatosGob (con el fallback al CSV de distribución)
        self._fetch_dg = fetch_dg
        self.start = start
        self._memo: dict[str, tuple[pd.DataFrame, dict]] = {}
        self.auth_error: str | None = None        # 1er 401/403: el resto de la corrida va directo al fallback
        self.por_indicador: dict[str, list[dict]] = {}
        self.por_clave: dict[str, dict] = {}       # clave (id o nombre) -> uso de esta corrida
        self._actual: list[dict] | None = None

    def fetch_dg(self, serie_id: str, start: str | None):
        # el default se busca al llamar (no al crear el resolver): los tests parchean fetch_datos_gob
        return (self._fetch_dg or fetch_datos_gob)(serie_id, start)

    # --- contexto: qué indicador se está calculando -------------------------------------------
    def empezar(self, nombre: str):
        self._actual = []
        self._nombre = nombre

    def terminar(self, ok: bool):
        if ok and self._actual:
            self.por_indicador[self._nombre] = self._actual
        self._actual = None

    def _registrar(self, uso: dict):
        self.por_clave[uso["clave"]] = uso
        if self._actual is not None and uso not in self._actual:
            self._actual.append(uso)

    # --- núcleo: API con fallback ----------------------------------------------------------------
    def _con_fallback(self, clave: str, spec: dict, fallback, nombre_fallback: str,
                      etiqueta_fallback: str) -> pd.DataFrame:
        memo_k = json.dumps([clave, spec], sort_keys=True, ensure_ascii=False)
        if memo_k in self._memo:
            df, uso = self._memo[memo_k]
            self._registrar(uso)
            return df.copy()
        motivo = None
        if self.auth_error:
            motivo = f"autenticación ({self.auth_error})"
        else:
            try:
                df = fetch_indec_api(spec["tabla"], spec["filtros"], columna_valor=spec.get("columna", "valor"),
                                     start_date=self.start)
                if df.empty:
                    motivo = "la API devolvió 0 filas"
                else:
                    uso = {"clave": clave, "fuente": API, "tabla": spec["tabla"], "motivo": None}
                    self._memo[memo_k] = (df, uso)
                    self._registrar(uso)
                    return df.copy()
            except IndecAuthError as e:
                self.auth_error = str(e)
                motivo = f"autenticación ({e})"
            except Exception as e:  # error de red tras reintentos, filas != total, mapeo ambiguo...
                motivo = f"{type(e).__name__}: {e}"
        print(f"  [indec_api] {clave}: la API falló ({motivo}); se usa el fallback ({etiqueta_fallback})")
        print(f"::warning title=Fallback INDEC::{clave} — API del INDEC falló ({motivo}); se usó {etiqueta_fallback}")
        df = fallback()
        uso = {"clave": clave, "fuente": nombre_fallback, "tabla": spec["tabla"], "motivo": motivo,
               "fallback": etiqueta_fallback}
        self._memo[memo_k] = (df, uso)
        self._registrar(uso)
        return df.copy()

    # --- usos ----------------------------------------------------------------------------------
    def serie_dg(self, serie_id: str, start: str | None = None) -> pd.DataFrame:
        """Reemplazo de fetch_datos_gob(id): si el id tiene equivalencia en la API del INDEC, la API
        es la primaria y datos.gob.ar el fallback; si no, datos.gob.ar directo (como siempre)."""
        spec = self.eq.get(serie_id)
        if not spec:
            return self.fetch_dg(serie_id, start)
        return self._con_fallback(serie_id, spec, lambda: self.fetch_dg(serie_id, start),
                                  FALLBACK_DG, f"datos.gob.ar {serie_id}")

    def variacion_publicada(self, serie_id: str, calculo: str, fallback) -> pd.DataFrame | None:
        """Variación PUBLICADA por el INDEC (criterio de Pedro: no recalcular el IPC desde el índice).
        None si el id no declara esa variación en su equivalencia (el llamador calcula como antes).
        `fallback`: cálculo desde el índice de datos.gob.ar (lo que hacía el pipeline antes)."""
        spec = self.eq.get(serie_id)
        tipo = (spec or {}).get("variaciones", {}).get(calculo)
        if not tipo:
            return None
        spec_var = {**spec, "filtros": {**spec["filtros"], "tipo_de_indicador": tipo}}
        clave = f"{serie_id}:{calculo}"
        return self._con_fallback(clave, spec_var, fallback, FALLBACK_DG,
                                  f"calculada desde el índice de datos.gob.ar {serie_id}")

    def serie_directa(self, ind: dict, start: str | None) -> pd.DataFrame:
        """Indicador con `fuente_primaria: indec_api` y sin `calculo`."""
        fb = ind.get("fuente_fallback")
        if fb == FALLBACK_DG:
            spec = self.eq.get(ind["id"])
            if not spec:
                raise ValueError(f"'{ind['id']}' no tiene entrada en equivalencias_indec")
            clave, fallback, etiqueta = ind["id"], (lambda: self.fetch_dg(ind["id"], start)), f"datos.gob.ar {ind['id']}"
        elif fb == FALLBACK_AD:
            spec = ind.get("indec")
            if not spec:
                raise ValueError(f"{ind['nombre']}: fuente_fallback argentinadatos requiere el bloque 'indec'")
            clave, fallback, etiqueta = ind["nombre"], (lambda: fetch_argentinadatos(ind["endpoint"], start)), \
                f"ArgentinaDatos {ind['endpoint']}"
        else:
            raise ValueError(f"{ind['nombre']}: fuente_fallback desconocida: {fb!r}")
        df = self._con_fallback(clave, spec, fallback, fb, etiqueta)
        factor = ind.get("factor_fallback")
        if factor and self.por_clave[clave]["fuente"] != API:
            df = df.assign(valor=df["valor"] * factor)   # la API ya publica en la unidad final
        return df

    def ids_fallback_dg(self) -> list[str]:
        return sorted(k for k in self.eq)


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


def _toca_aviso(avisos: dict, clave: str, hoy: str, repetir_dias: int | None) -> bool:
    ultimo = avisos.get(clave)
    if not ultimo:
        return True
    if repetir_dias is None:
        return ultimo != hoy
    return (datetime.fromisoformat(hoy) - datetime.fromisoformat(ultimo)).days >= repetir_dias


def enviar_alerta(asunto: str, cuerpo: str, titulo: str = "Alerta INDEC") -> bool:
    """Mail SÓLO a Pedro. Sin credenciales (corrida local, o el fallback del workflow del mail),
    no se envía: queda en el log y como anotación de Actions."""
    print(f"::warning title={titulo}::{asunto}")
    user, pw = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    destino = os.environ.get("ALERTA_MAIL_TO") or ALERTA_DESTINO
    if not user or not pw:
        print(f"  [alerta NO enviada: sin credenciales de Gmail en este entorno]\n{cuerpo}")
        return False
    msg = MIMEText(cuerpo, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = asunto, user, destino
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as srv:
            srv.login(user, pw)
            srv.sendmail(user, [destino], msg.as_string())
        print(f"  Alerta enviada a {destino}: {asunto}")
        return True
    except Exception as e:
        print(f"  [alerta NO enviada: {type(e).__name__}: {e}]\n{cuerpo}")
        return False


def cerrar_corrida(resolver: ResolverIndec, chequear_fallbacks: bool = True) -> dict:
    """Actualiza data/indec_estado.json y manda (como mucho) un mail de alertas a Pedro.
    Devuelve {nombre_indicador: [usos]} con la última fuente conocida de cada indicador (para las
    notas del dashboard, aunque un indicador haya fallado en esta corrida)."""
    estado = cargar_estado()
    hoy = _hoy()
    rachas = estado.setdefault("rachas_fallback", {})
    avisos = estado.setdefault("avisos", {})
    ultima = estado.setdefault("ultima_fuente_por_indicador", {})
    corridas = estado.setdefault("corridas", [])

    for clave, uso in resolver.por_clave.items():
        rachas[clave] = 0 if uso["fuente"] == API else rachas.get(clave, 0) + 1
    ultima.update(resolver.por_indicador)
    corridas.append({"fecha": hoy, "hora": datetime.now(ZONA_AR).strftime("%H:%M:%S"),
                     "disparo": os.environ.get("GITHUB_EVENT_NAME", "local"),
                     "fallbacks": sorted(k for k, u in resolver.por_clave.items() if u["fuente"] != API),
                     "error_autenticacion": bool(resolver.auth_error)})
    del corridas[:-30]   # sólo las últimas 30 corridas

    items = []
    # 1) autenticación: una vez por día como mucho
    if resolver.auth_error and _toca_aviso(avisos, "auth", hoy, None):
        afectadas = sorted({n for n, usos in resolver.por_indicador.items()
                            for u in usos if u["fuente"] != API})
        items.append(("auth", "Falla de autenticación con la API del INDEC "
                      f"(token vencido, inválido o sin permisos).\nError: {resolver.auth_error}\n"
                      "Series afectadas (se usó el fallback): " + (", ".join(afectadas) or "ninguna con datos")))
    # 2) vencimiento del token (campo `exp`; un token nuevo con `exp` lejano corta el aviso solo)
    exp = indec_token_exp()
    estado["token_exp"] = exp.date().isoformat() if exp else None
    estado["token_fecha_informativa"] = os.environ.get("INDEC_TOKEN_FECHA") or estado.get("token_fecha_informativa")
    if exp:
        dias = (exp - datetime.now(timezone.utc)).days
        clave_aviso = f"vencimiento:{exp.date().isoformat()}"
        if dias <= DIAS_AVISO_VENCIMIENTO and _toca_aviso(avisos, clave_aviso, hoy, DIAS_REPETICION):
            items.append((clave_aviso, f"El token de la API del INDEC vence el {exp:%d/%m/%Y} "
                          f"(quedan {max(dias, 0)} días, según su campo exp). Renovarlo en api.indec.gob.ar "
                          "y actualizar el secret INDEC_API_TOKEN (y el .env local). Este aviso se repite "
                          "cada semana hasta que el token nuevo tenga otro vencimiento."))
    # 3) fallback usado más de 3 corridas seguidas
    for clave, n in sorted(rachas.items()):
        if n > RACHA_FALLBACK_AVISO and _toca_aviso(avisos, f"racha:{clave}", hoy, DIAS_REPETICION):
            uso = resolver.por_clave.get(clave, {})
            items.append((f"racha:{clave}", f"La serie {clave} lleva {n} corridas seguidas usando el "
                          f"fallback ({uso.get('fallback', '?')}). Último motivo: {uso.get('motivo', '?')}"))
    # 4) fallback de datos.gob.ar que devuelve 0 filas (el fallback no serviría si la API se cae)
    if chequear_fallbacks:
        vacias = []
        for sid in resolver.ids_fallback_dg():
            try:
                if datos_gob_filas(sid) == 0:
                    vacias.append(sid)
            except Exception as e:
                print(f"  [ADVERTENCIA] no se pudo chequear el fallback {sid} en datos.gob.ar: {e}")
        estado["fallback_dg_vacios"] = vacias
        for sid in vacias:
            print(f"::warning title=Fallback vacío::{sid} — datos.gob.ar devuelve 0 filas (el fallback no serviría)")
            if _toca_aviso(avisos, f"vacio:{sid}", hoy, DIAS_REPETICION):
                items.append((f"vacio:{sid}", f"El fallback {sid} de datos.gob.ar devuelve 0 filas: si la "
                              "API del INDEC falla, esa serie no se puede actualizar por ninguna vía."))

    if items:
        cuerpo = ("Alertas del pipeline de coyuntura (API del INDEC):\n\n"
                  + "\n\n".join(f"- {t}" for _, t in items)
                  + "\n\nEstado completo: data/indec_estado.json en el repo.")
        if enviar_alerta(f"[Coyuntura] {len(items)} alerta(s) de la API del INDEC", cuerpo):
            for clave, _ in items:
                avisos[clave] = hoy
    _guardar_estado(estado)
    return dict(ultima)


def describir_fuente(usos: list[dict]) -> str | None:
    """Texto para la nota metodológica: 'Fuente: INDEC (API) ...' o 'Fuente: INDEC vía ...'."""
    if not usos:
        return None
    api_tablas = sorted({u["tabla"] for u in usos if u["fuente"] == API})
    partes = []
    if api_tablas:
        tablas = ", ".join(f'<a href="{DATASET_API.format(tabla=t)}" target="_blank" rel="noopener">'
                           f"<code>{t}</code></a>" for t in api_tablas)
        partes.append(f'Fuente: INDEC (<a href="{DOCS_API}" target="_blank" rel="noopener">API del INDEC</a>, '
                      f'tabla{"s" if len(api_tablas) > 1 else ""} {tablas}).')
    if any(u["fuente"] == FALLBACK_DG for u in usos):
        partes.append('Fuente: INDEC vía <a href="https://datos.gob.ar/series" target="_blank" '
                      'rel="noopener">datos.gob.ar</a>.')
    if any(u["fuente"] == FALLBACK_AD for u in usos):
        partes.append('Fuente: INDEC vía <a href="https://argentinadatos.com" target="_blank" '
                      'rel="noopener">ArgentinaDatos</a>.')
    return " ".join(partes)

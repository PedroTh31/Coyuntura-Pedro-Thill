"""Agenda del mail diario (Bloque B3, agenda.py). Sin red: contexto y calendario sintéticos con las
fechas reales de nov-dic 2026."""
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agenda as A  # noqa: E402
import calendario_indec as C  # noqa: E402
import frescura as F  # noqa: E402

FERIADOS = {date(2026, 11, 9): "Visita de Su Santidad el Papa León XIV",
            date(2026, 11, 10): "Visita de Su Santidad el Papa León XIV",
            date(2026, 11, 23): "Día de la Soberanía Nacional (20/11)",
            date(2026, 12, 7): "Día no laborable con fines turísticos",
            date(2026, 12, 8): "Inmaculada Concepción de María"}


def _pub(id_, corto, apertura=None):
    return {"id": id_, "nombre_corto": corto, "apertura": apertura}


CFG = {"publicaciones": [
    _pub("ipc", "IPC", {"titular": "Inflación de {periodo}: {valor} mensual", "filas": [
        {"serie": "Inflación mensual (IPC)", "etiqueta": "Mensual", "unidad": "%", "compara": "anterior", "variacion": "pp"},
        {"serie": "Inflación interanual (IPC)", "etiqueta": "Interanual", "unidad": "%", "compara": "anterior", "variacion": "pp"},
        {"serie": "IPC Núcleo (var. mensual)", "etiqueta": "Núcleo", "unidad": "%", "compara": "anterior", "variacion": "pp"}]}),
    _pub("salarios", "Índice de salarios", {"titular": "Salario real de {periodo}: {var} contra {ref}", "filas": [
        {"serie": "Salario real", "etiqueta": "Salario real (índice)", "unidad": "", "compara": "anterior", "variacion": "pct"}]}),
    _pub("ica", "Comercio exterior (ICA)", {"titular": "Saldo comercial de {periodo}: {valor}", "filas": [
        {"serie": "Saldo comercial", "etiqueta": "Saldo", "unidad": "USD M", "compara": "interanual", "variacion": "dif"},
        {"serie": "Exportaciones totales", "etiqueta": "Exportaciones", "unidad": "USD M", "compara": "interanual", "variacion": "pct"}]}),
    _pub("eph", "Mercado de trabajo (EPH)", {"titular": "Desempleo del {periodo}: {valor}", "filas": [
        {"serie": "Tasa de desempleo", "etiqueta": "Desempleo", "unidad": "%", "compara": "interanual", "variacion": "pp"}]}),
    _pub("avance", "Informe de avance del nivel de actividad", {
        "titular": "Informe de avance del {periodo}: se incorporó al dashboard", "serie_periodo": "PBI nominal",
        "detalle": "PBI nominal y deuda pública bruta / PBI, actualizados al {periodo_corto}.", "filas": []}),
]}


def _pubs(*filas):
    return [{"fecha": f, "hora": h, "periodo": F.parsear_periodo_indec(p)} for f, h, p in filas]


FECHAS = {
    "ipc": _pubs(("2026-10-13", "16:00", "Septiembre de 2026"), ("2026-11-12", "16:00", "Octubre de 2026"),
                 ("2026-12-15", "16:00", "Noviembre de 2026"), ("2027-01-14", "16:00", "Diciembre de 2026")),
    "salarios": _pubs(("2026-10-21", "16:00", "Agosto de 2026"), ("2026-11-13", "16:00", "Septiembre de 2026"),
                      ("2026-12-16", "16:00", "Octubre de 2026")),
    "ica": _pubs(("2026-10-19", "16:00", "Septiembre de 2026"), ("2026-11-19", "16:00", "Octubre de 2026"),
                 ("2026-12-18", "16:00", "Noviembre de 2026")),
    "eph": _pubs(("2026-09-17", "16:00", "Segundo trimestre de 2026"), ("2026-12-18", "16:00", "Tercer trimestre de 2026")),
    "avance": _pubs(("2026-09-17", "16:00", "Segundo trimestre de 2026"), ("2026-12-16", "16:00", "Tercer trimestre de 2026")),
}
BAJADO = "2026-11-07T06:20:00-03:00"
MESES = {m: BAJADO for m in ("2026-09", "2026-10", "2026-11", "2026-12", "2027-01", "2027-02")}


def ctx(ahora, fechas=FECHAS, meses=MESES):
    return F.Contexto(ahora=ahora, no_habiles=set(FERIADOS), nombres_feriados=FERIADOS,
                      pub_de_indicador={"Inflación mensual (IPC)": "ipc", "Saldo comercial": "ica",
                                        "Exportaciones totales": "ica", "Tasa de desempleo": "eph"},
                      fechas=fechas, meses_bajado=meses)


def cal(ahora, **kw):
    return A.armar_calendario(ctx(ahora, **kw), CFG)


def historico(series: dict) -> pd.DataFrame:
    filas = [(n, pd.Timestamp(f), v) for n, pts in series.items() for f, v in pts]
    return pd.DataFrame(filas, columns=["indicador", "fecha", "valor"])


def mensual(desde, valores, fin_de_mes=False):
    fechas = pd.date_range(desde, periods=len(valores), freq="ME" if fin_de_mes else "MS")
    return list(zip(fechas, valores))


class TestCalendario(unittest.TestCase):

    def test_miercoles_despues_de_dos_feriados(self):
        c = cal(datetime(2026, 11, 11, 6, 30))
        self.assertEqual(c["estado"], "ok")
        self.assertEqual(c["hoy"], [])
        self.assertEqual(c["hasta"], "mar 17/11")      # 11, 12, 13, 16, 17
        self.assertEqual([(s["dia"], s["hora"], s["titulos"]) for s in c["semana"]],
                         [("jue 12/11", "16 h", ["IPC de octubre"]),
                          ("vie 13/11", "16 h", ["Índice de salarios de septiembre"])])
        self.assertTrue(c["primer_habil_semana"])      # lunes y martes fueron feriados
        self.assertIsNone(c["feriado_hoy"])

    def test_dia_del_ipc(self):
        c = cal(datetime(2026, 11, 12, 6, 30))
        self.assertEqual(c["hoy"], [{"titulo": "IPC de octubre", "fuente": "INDEC", "hora": "16 h"}])
        self.assertEqual([s["titulos"] for s in c["semana"]], [["Índice de salarios de septiembre"]])
        self.assertFalse(c["primer_habil_semana"])

    def test_viernes_incluye_la_semana_siguiente(self):
        c = cal(datetime(2026, 11, 13, 6, 30))
        self.assertEqual(c["hasta"], "jue 19/11")      # 13, 16, 17, 18, 19
        self.assertEqual([(s["dia"], s["titulos"]) for s in c["semana"]],
                         [("jue 19/11", ["Comercio exterior (ICA) de octubre"])])

    def test_lunes_empieza_hoy(self):
        c = cal(datetime(2026, 11, 16, 6, 30))
        self.assertEqual(c["hasta"], "vie 20/11")
        self.assertTrue(c["primer_habil_semana"])

    def test_feriado(self):
        c = cal(datetime(2026, 11, 9, 6, 30))
        self.assertEqual(c["feriado_hoy"], "Visita de Su Santidad el Papa León XIV")
        self.assertFalse(c["primer_habil_semana"])
        self.assertEqual(c["hasta"], "mar 17/11")      # los 5 hábiles siguientes: 11..17

    def test_semana_sin_publicaciones_muestra_la_proxima(self):
        c = cal(datetime(2026, 11, 25, 6, 30))
        self.assertEqual(c["semana"], [])
        self.assertEqual(c["hasta"], "mar 01/12")
        self.assertEqual(c["proxima"], {"titulo": "IPC de noviembre", "dia": "mar 15/12", "hora": "16 h"})

    def test_dos_publicaciones_el_mismo_dia_y_trimestral(self):
        c = cal(datetime(2026, 12, 14, 6, 30), meses={**MESES})
        dias = {s["dia"]: s["titulos"] for s in c["semana"]}
        self.assertEqual(dias["mié 16/12"], ["Índice de salarios de octubre",
                                             "Informe de avance del nivel de actividad del tercer trimestre"])
        self.assertEqual(dias["vie 18/12"], ["Comercio exterior (ICA) de noviembre",
                                             "Mercado de trabajo (EPH) del tercer trimestre"])

    def test_anio_distinto_al_del_mail(self):
        c = cal(datetime(2027, 1, 14, 6, 30))
        self.assertEqual(c["hoy"][0]["titulo"], "IPC de diciembre de 2026")

    def test_publicacion_en_dia_no_habil_se_muestra(self):
        fechas = {**FECHAS, "ica": _pubs(("2026-11-10", "16:00", "Octubre de 2026"))}
        c = cal(datetime(2026, 11, 9, 6, 30), fechas=fechas)
        self.assertIn(["Comercio exterior (ICA) de octubre"], [s["titulos"] for s in c["semana"]])

    def test_sin_cache(self):
        self.assertEqual(cal(datetime(2026, 11, 11, 6, 30), fechas=None)["estado"], "no_disponible")

    def test_falta_un_mes_de_la_ventana(self):
        c = cal(datetime(2026, 11, 27, 6, 30), meses={"2026-11": BAJADO})   # la ventana llega a diciembre
        self.assertEqual(c["estado"], "no_disponible")

    def test_cache_vieja(self):
        c = cal(datetime(2026, 11, 11, 6, 30), meses={**MESES, "2026-11": "2026-11-02T06:20:00-03:00"})
        self.assertEqual((c["estado"], c["bajado"]), ("cache_vieja", "02/11"))
        self.assertEqual(len(c["semana"]), 2)       # las fechas se muestran igual

    def test_cache_de_hace_7_dias_no_es_vieja(self):
        c = cal(datetime(2026, 11, 11, 6, 30), meses={**MESES, "2026-11": "2026-11-04T06:20:00-03:00"})
        self.assertEqual(c["estado"], "ok")


IPC = {"Inflación mensual (IPC)": mensual("2025-08-01", [1.9, 2.0, 2.1, 2.2, 2.3, 2.0, 2.4, 2.1, 1.9, 1.8, 2.1, 2.1, 1.7, 1.9], True),
       "Inflación interanual (IPC)": mensual("2025-08-01", [40, 39, 38, 37, 36, 35, 34.5, 34.2, 34, 33.9, 33.9, 33.8, 33.5, 33.4]),
       "IPC Núcleo (var. mensual)": mensual("2025-08-01", [2] * 12 + [1.8, 1.7])}


class TestPublicaciones(unittest.TestCase):

    def test_ipc_al_dia_con_apertura(self):
        c = ctx(datetime(2026, 10, 14, 6, 30))
        c.registro = {"Inflación mensual (IPC)": ([("Inflación mensual (IPC)", None)], "Inflación mensual (IPC)")}
        p = A.estado_publicaciones(historico(IPC), {"Inflación mensual (IPC)": {"bloque": "precios"}}, CFG, c)["ipc"]
        self.assertEqual((p["periodo"], p["estado"], p["titulo"]), ("2026-09", "al_dia", "IPC de septiembre"))
        self.assertEqual(p["publicado"], "13/10, 16 h")
        self.assertEqual(p["ancla"], "precios")
        ap = p["apertura"]
        self.assertEqual(ap["titular"], "Inflación de septiembre: 1,9% mensual")
        self.assertEqual(ap["filas"], [
            {"etiqueta": "Mensual", "valor": "1,9%", "ref": "agosto 1,7%", "var": "▲ 0,2 pp"},
            {"etiqueta": "Interanual", "valor": "33,4%", "ref": "agosto 33,5%", "var": "▼ 0,1 pp"},
            {"etiqueta": "Núcleo", "valor": "1,7%", "ref": "agosto 1,8%", "var": "▼ 0,1 pp"}])

    def test_serie_sin_card_no_lleva_link(self):
        p = A.estado_publicaciones(historico(IPC), {"Inflación mensual (IPC)": {"bloque": "precios"}},
                                   CFG, ctx(datetime(2026, 10, 14, 6, 30)))["ipc"]
        self.assertIsNone(p["ancla"])

    def test_publicado_sin_incorporar(self):
        p = A.estado_publicaciones(historico(IPC), {}, CFG, ctx(datetime(2026, 11, 13, 6, 30)))["ipc"]
        self.assertEqual(p["estado"], "publicado")
        self.assertEqual(p["titulo_publicado"], "IPC de octubre")
        self.assertEqual(p["linea"], "sep-26 · oct-26 publicado el 12/11, entra en la próxima actualización")

    def test_fila_sin_dato_se_omite(self):
        h = historico({k: v for k, v in IPC.items() if "Núcleo" not in k})
        ap = A.estado_publicaciones(h, {}, CFG, ctx(datetime(2026, 10, 14, 6, 30)))["ipc"]["apertura"]
        self.assertEqual([f["etiqueta"] for f in ap["filas"]], ["Mensual", "Interanual"])

    def test_sin_cambios(self):
        h = historico({"Inflación mensual (IPC)": mensual("2026-08-01", [1.9, 1.9], True)})
        ap = A.estado_publicaciones(h, {}, CFG, ctx(datetime(2026, 10, 14, 6, 30)))["ipc"]["apertura"]
        self.assertEqual(ap["filas"][0]["var"], "= sin cambios")

    def test_salario_real_titular_con_variacion(self):
        h = historico({"Salario real": mensual("2026-06-01", [77.675, 78.211, 79.034])})
        ap = A.estado_publicaciones(h, {}, CFG, ctx(datetime(2026, 10, 22, 6, 30)))["salarios"]["apertura"]
        self.assertEqual(ap["titular"], "Salario real de agosto: +1,1% contra julio")
        self.assertEqual(ap["filas"][0], {"etiqueta": "Salario real (índice)", "valor": "79,0",
                                          "ref": "julio 78,2", "var": "▲ 1,1%"})

    def test_ica_interanual_con_diferencia_en_usd(self):
        h = historico({"Saldo comercial": mensual("2025-09-01", [1200.0] + [2000.0] * 11 + [2186.0]),
                       "Exportaciones totales": mensual("2025-09-01", [8000.0] + [8500.0] * 11 + [8800.0])})
        ap = A.estado_publicaciones(h, {}, CFG, ctx(datetime(2026, 10, 20, 6, 30)))["ica"]["apertura"]
        self.assertEqual(ap["titular"], "Saldo comercial de septiembre: USD 2.186 M")
        self.assertEqual(ap["filas"][0], {"etiqueta": "Saldo", "valor": "USD 2.186 M",
                                          "ref": "sep-25 USD 1.200 M", "var": "▲ USD 986 M"})
        self.assertEqual(ap["filas"][1]["var"], "▲ 10,0%")

    def test_trimestral_contra_el_mismo_trimestre_del_anio_anterior(self):
        h = historico({"Tasa de desempleo": [("2025-04-01", 7.6), ("2025-07-01", 6.9), ("2025-10-01", 7.5),
                                             ("2026-01-01", 7.8), ("2026-04-01", 7.9)]})
        p = A.estado_publicaciones(h, {}, CFG, ctx(datetime(2026, 11, 11, 6, 30)))["eph"]
        self.assertEqual((p["periodo"], p["titulo"]), ("2026Q2", "Mercado de trabajo (EPH) del segundo trimestre"))
        self.assertEqual(p["apertura"]["titular"], "Desempleo del segundo trimestre: 7,9%")
        self.assertEqual(p["apertura"]["filas"][0]["ref"], "2T-25 7,6%")
        self.assertEqual(p["apertura"]["filas"][0]["var"], "▲ 0,3 pp")

    def test_publicacion_sin_filas(self):
        h = historico({"PBI nominal": [("2026-01-01", 1.0), ("2026-04-01", 2.0)]})
        ap = A.estado_publicaciones(h, {}, CFG, ctx(datetime(2026, 11, 11, 6, 30)))["avance"]["apertura"]
        self.assertEqual(ap["titular"], "Informe de avance del segundo trimestre: se incorporó al dashboard")
        self.assertEqual(ap["detalle"], "PBI nominal y deuda pública bruta / PBI, actualizados al 2T-26.")
        self.assertEqual(ap["filas"], [])

    def test_sin_serie_en_el_historico_no_hay_publicacion(self):
        self.assertNotIn("salarios", A.estado_publicaciones(historico(IPC), {}, CFG, ctx(datetime(2026, 11, 11))))


def _f(per, estado="sin_calendario", detalle="próximo: sin calendario oficial", grave=None, dias=None):
    return F.Frescura(per, estado, detalle, "", grave=grave, dias_rezago=dias)


class TestAvisos(unittest.TestCase):

    def test_atrasados_por_publicacion_y_graves_con_la_redaccion_del_b2(self):
        c = ctx(datetime(2026, 11, 11, 6, 30))
        atr = _f("ago-26", "atrasado", "sep-26 se publicó el 19/10")
        c.registro = {
            "Comercio exterior (expo/impo espejo)": ([("Exportaciones totales", atr), ("Saldo comercial", atr)], "Saldo comercial"),
            "Saldo comercial": ([("Saldo comercial", atr)], "Saldo comercial"),
            "Tipo de cambio real multilateral": ([("Tipo de cambio real multilateral",
                                                   _f("28/01/26", "diaria", "próximo 12/11 (estimado)", "sin datos nuevos hace 9 meses", 283))],
                                                 "Tipo de cambio real multilateral"),
            "Salario real y capacidad de compra": ([("Salario real", _f("ago-26", "al_dia", "próximo 13/11, 16 h")),
                                                    ("Capacidad de compra del salario (RIPTE / CBT)",
                                                     _f("jul-26", grave="sin datos nuevos hace 3 meses", dias=99))],
                                                   "Salario real"),
        }
        atrasados, graves = A.resumen_frescura(c, CFG)
        self.assertEqual([a["texto"] for a in atrasados],
                         ["Comercio exterior (ICA) · ago-26 · ⚠ atrasado · sep-26 se publicó el 19/10"])
        self.assertEqual([g["texto"] for g in graves], [
            "⏸ Tipo de cambio real multilateral: 28/01/26 · sin datos nuevos hace 9 meses · sin calendario oficial",
            "⏸ Capacidad de compra del salario (RIPTE / CBT): jul-26 · sin datos nuevos hace 3 meses · sin calendario oficial"])
        self.assertEqual(graves[0]["clave"], "Tipo de cambio real multilateral|28/01/26")

    def test_serie_frenada_en_dos_cards_va_una_sola_vez(self):
        c = ctx(datetime(2026, 11, 11, 6, 30))
        at = _f("may-26", grave="sin datos nuevos hace 5 meses", dias=160)
        tu = _f("may-26", grave="sin datos nuevos hace 5 meses", dias=160)
        c.registro = {
            "Adelantos Transitorios vs. Inflación interanual (con rezago)": (
                [("Adelantos (pc)", at), ("Inflación interanual (IPC)", _f("sep-26", "al_dia", "próximo 12/11, 16 h"))],
                "Inflación interanual (IPC)"),
            "Asistencia monetaria del BCRA al Tesoro": ([("Adelantos (pc)", at), ("Transferencias (pc)", tu)], "Adelantos (pc)"),
            "Compras por contraparte": ([("Privado", at), ("Tesoro", at)], "Tesoro"),
            "Balance cambiario": ([("Compras total", at), ("Reservas", _f("03/11", "diaria", "próximo 09/11 (estimado)"))], "Reservas"),
        }
        _, graves = A.resumen_frescura(c, CFG)
        self.assertEqual([g["nombre"] for g in graves],
                         ["Asistencia monetaria del BCRA al Tesoro", "Compras por contraparte", "Compras total"])

    def test_aviso_semanal_a_pedro(self):
        enviados = []
        atr = [{"clave": "atrasado:ica:ago-26", "publicacion": "ica", "texto": "Comercio exterior (ICA) · ago-26 · ⚠ atrasado"}]
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "frescura_estado.json"
            ok = lambda asunto, cuerpo: enviados.append(cuerpo) or True   # noqa: E731
            self.assertEqual(A.avisar_atrasados(atr, date(2026, 11, 11), ruta, ok), ["atrasado:ica:ago-26"])
            self.assertEqual(A.avisar_atrasados(atr, date(2026, 11, 17), ruta, ok), [])
            self.assertEqual(A.avisar_atrasados(atr, date(2026, 11, 18), ruta, ok), ["atrasado:ica:ago-26"])
            self.assertEqual(len(enviados), 2)

    def test_sin_credenciales_no_marca_el_aviso(self):
        atr = [{"clave": "atrasado:ica:ago-26", "publicacion": "ica", "texto": "x"}]
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "frescura_estado.json"
            A.avisar_atrasados(atr, date(2026, 11, 11), ruta, lambda a, c: False)
            self.assertEqual(A.avisar_atrasados(atr, date(2026, 11, 12), ruta, lambda a, c: True), ["atrasado:ica:ago-26"])


class TestFeriados(unittest.TestCase):

    def test_nombre_sin_la_cita_normativa(self):
        cfg = C.cargar_config()
        n = C.nombres_feriados(cfg)
        self.assertEqual(n[date(2026, 11, 9)], "Visita de Su Santidad el Papa León XIV")
        self.assertEqual(n[date(2026, 11, 10)], "Visita de Su Santidad el Papa León XIV")
        self.assertEqual(n[date(2026, 11, 23)], "Día de la Soberanía Nacional (20/11)")

    def test_calendario_yaml_tiene_apertura_y_nombre_corto(self):
        for p in C.cargar_config()["publicaciones"]:
            self.assertTrue(p["nombre_corto"])
            self.assertIn("titular", p["apertura"])
            self.assertNotIn("REM", str(p["apertura"]))   # decisión de Pedro: el REM queda fuera del B3


if __name__ == "__main__":
    unittest.main()

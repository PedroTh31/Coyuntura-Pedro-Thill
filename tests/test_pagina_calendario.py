"""Página del calendario (Bloque E1): agenda.armar_meses / proximas / sin_calendario / fin_ventana y
pagina_calendario.html. Sin red: caché sintética con títulos reales del calendario del INDEC de oct-nov
2026 y la configuración real de calendario.yaml."""
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agenda as A  # noqa: E402
import calendario_indec as C  # noqa: E402
import frescura as F  # noqa: E402
import pagina_calendario as P  # noqa: E402

CFG = C.cargar_config()
FERIADOS = {date(2026, 11, 9): "Visita de Su Santidad el Papa León XIV",
            date(2026, 11, 10): "Visita de Su Santidad el Papa León XIV",
            date(2026, 11, 23): "Día de la Soberanía Nacional (20/11)"}
IPC = "Índice de precios al consumidor (IPC). Cobertura nacional. {}"
ICA = "Intercambio comercial argentino (ICA). Bienes. {}"
CACHE = {"meses": {
    "2026-10": {"bajado": "2026-11-07T06:20:00-03:00", "publicaciones": [
        {"fecha": "2026-10-13", "hora": "16:00", "titulo": IPC.format("Septiembre de 2026")},
        {"fecha": "2026-10-19", "hora": "16:00", "titulo": ICA.format("Septiembre de 2026")}]},
    "2026-11": {"bajado": "2026-11-07T06:20:00-03:00", "publicaciones": [
        {"fecha": "2026-11-05", "hora": "16:00", "titulo": "Índice de producción industrial pesquero (IPI pesquero). Septiembre de 2026"},
        {"fecha": "2026-11-12", "hora": "16:00", "titulo": IPC.format("Octubre de 2026")},
        {"fecha": "2026-11-13", "hora": "16:00", "titulo": "Índice de salarios. Septiembre de 2026"},
        {"fecha": "2026-11-19", "hora": "16:00", "titulo": ICA.format("Octubre de 2026")},
        {"fecha": "2026-11-30", "hora": "16:00", "titulo": "INDEC Informa"}]},
}}
# Lo que deja agenda.estado_publicaciones: período que muestra el monitor + estado del B2.
PUBLICACIONES = {
    "ipc": {"nombre_corto": "IPC", "periodo": "2026-09", "estado": "al_dia",
            "linea": "sep-26 · ✓ al día · próximo 12/11, 16 h"},
    "ica": {"nombre_corto": "Comercio exterior (ICA)", "periodo": "2026-08", "estado": "atrasado",
            "linea": "ago-26 · ⚠ atrasado · sep-26 se publicó el 19/10"},
}


def _pubs(*filas):
    return [{"fecha": f, "hora": h, "periodo": F.parsear_periodo_indec(p)} for f, h, p in filas]


def ctx(ahora=datetime(2026, 11, 7, 6, 30)):
    return F.Contexto(ahora=ahora, no_habiles=set(FERIADOS), nombres_feriados=FERIADOS,
                      fechas={"ipc": _pubs(("2026-10-13", "16:00", "Septiembre de 2026"),
                                           ("2026-11-12", "16:00", "Octubre de 2026"),
                                           ("2026-12-15", "16:00", "Noviembre de 2026")),
                              "ica": _pubs(("2026-10-19", "16:00", "Septiembre de 2026"),
                                           ("2026-11-19", "16:00", "Octubre de 2026"))},
                      meses_bajado={m: "2026-11-07T06:20:00-03:00" for m in ("2026-10", "2026-11", "2026-12")})


def meses(c=None, claves=("2026-10", "2026-11", "2026-12")):
    return A.armar_meses(CACHE, CFG, c or ctx(), PUBLICACIONES, list(claves))


def dia(ms, iso):
    return next(d for m in ms for d in m["dias"] if d["fecha"] == iso)


class TestMeses(unittest.TestCase):

    def test_publicacion_del_monitor_con_titulo_corto_y_proxima(self):
        p = dia(meses(), "2026-11-12")["publicaciones"]
        self.assertEqual([(x["pid"], x["titulo"], x["hora"], x["estado"]) for x in p],
                         [("ipc", "IPC de octubre", "16 h", "proximo")])

    def test_publicacion_ya_incorporada(self):
        p = dia(meses(), "2026-10-13")["publicaciones"][0]
        self.assertEqual((p["titulo"], p["estado"]), ("IPC de septiembre", "incorporado"))

    def test_publicacion_que_salio_y_el_monitor_no_tiene_es_atrasada(self):
        p = dia(meses(), "2026-10-19")["publicaciones"][0]
        self.assertEqual((p["pid"], p["estado"]), ("ica", "atrasado"))

    def test_publicada_hoy_dentro_del_margen(self):
        pubs = dict(PUBLICACIONES, ica=dict(PUBLICACIONES["ica"], estado="publicado"))
        ms = A.armar_meses(CACHE, CFG, ctx(datetime(2026, 10, 19, 18, 0)), pubs, ["2026-10"])
        self.assertEqual(dia(ms, "2026-10-19")["publicaciones"][0]["estado"], "publicado")

    def test_publicacion_que_no_usa_el_monitor(self):
        p = dia(meses(), "2026-11-05")["publicaciones"][0]
        self.assertEqual((p["pid"], p["titulo"], p["estado"]),
                         (None, "Índice de producción industrial pesquero (IPI pesquero)", None))
        self.assertEqual(dia(meses(), "2026-11-30")["publicaciones"][0]["titulo"], "INDEC Informa")

    def test_dias_feriados_hoy_y_pasados(self):
        ms = meses()
        nov = next(m for m in ms if m["clave"] == "2026-11")
        self.assertEqual(len(nov["dias"]), 30)
        self.assertEqual(dia(ms, "2026-11-10")["feriado"], "Visita de Su Santidad el Papa León XIV")
        self.assertFalse(dia(ms, "2026-11-10")["habil"])
        self.assertTrue(dia(ms, "2026-11-07")["hoy"])
        self.assertTrue(dia(ms, "2026-11-06")["pasado"])
        self.assertFalse(dia(ms, "2026-11-08")["pasado"])

    def test_mes_fuera_de_la_cache(self):
        dic = next(m for m in meses() if m["clave"] == "2026-12")
        self.assertFalse(dic["disponible"])
        self.assertEqual(len(dic["dias"]), 31)

    def test_sin_periodo(self):
        self.assertEqual(A._sin_periodo("Encuesta de tendencia de negocios. Industria manufacturera. "
                                        "Expectativas noviembre de 2026- enero de 2027"),
                         "Encuesta de tendencia de negocios. Industria manufacturera")
        self.assertEqual(A._sin_periodo("Dosier estadístico en conmemoración del Día Mundial del Niño. Sexta edición"),
                         "Dosier estadístico en conmemoración del Día Mundial del Niño. Sexta edición")


class TestProximasYSinCalendario(unittest.TestCase):

    def test_proximas(self):
        pr = A.proximas(ctx(), CFG)
        self.assertEqual(pr["ipc"], {"titulo": "IPC de octubre", "fecha": "2026-11-12", "dia": "jue 12/11", "hora": "16 h"})
        self.assertNotIn("salarios", pr)   # sin fechas en la caché: no se estima nada

    def test_el_dia_del_ipc_despues_de_las_16_pasa_a_la_siguiente(self):
        self.assertEqual(A.proximas(ctx(datetime(2026, 11, 12, 17, 0)), CFG)["ipc"]["titulo"], "IPC de noviembre")

    def test_sin_calendario_excluye_diarias_graves_y_las_que_tienen_calendario(self):
        c = ctx()
        sin = F.Frescura("ago-26", "sin_calendario", "próximo: sin calendario oficial", "")
        grave = F.Frescura("may-26", "sin_calendario", "próximo: sin calendario oficial", "", grave="sin datos nuevos hace 5 meses")
        diaria = F.Frescura("06/11", "diaria", "próximo 11/11 (estimado)", "")
        al_dia = F.Frescura("sep-26", "al_dia", "próximo 12/11, 16 h", "")
        c.registro = {"Base monetaria": ([("Base monetaria", sin)], "Base monetaria"),
                      "Asistencia monetaria": ([("AT", grave)], "AT"),
                      "Dólar oficial": ([("Dólar oficial", diaria)], "Dólar oficial"),
                      "Inflación mensual (IPC)": ([("Inflación mensual (IPC)", al_dia)], "Inflación mensual (IPC)")}
        self.assertEqual(A.sin_calendario(c), ["Base monetaria"])

    def test_fin_ventana_es_la_del_mail(self):
        for ahora in (datetime(2026, 11, 7, 6, 30), datetime(2026, 11, 11, 6, 30), datetime(2026, 11, 13, 6, 30)):
            c = ctx(ahora)
            self.assertEqual(A.dia_corto(A.fin_ventana(c)), A.armar_calendario(c, CFG)["hasta"])

    def test_meses_a_mostrar(self):
        self.assertEqual(P.meses_a_mostrar(date(2026, 12, 3)), ["2026-11", "2026-12", "2027-01", "2027-02"])


class TestHtml(unittest.TestCase):

    def _agenda(self, c):
        return {"calendario": A.armar_calendario(c, CFG), "publicaciones": PUBLICACIONES,
                "atrasados": [{"texto": "Comercio exterior (ICA) · ago-26 · ⚠ atrasado · sep-26 se publicó el 19/10"}],
                "graves": [{"texto": "⏸ Tipo de cambio real multilateral: 28/01/26 · sin datos nuevos hace 9 meses · sin calendario oficial"}]}

    def _html(self, c=None):
        c = c or ctx()
        return P.html(self._agenda(c), meses(c, ("2026-10", "2026-11")), A.proximas(c, CFG), ["Base monetaria"], c, CFG)

    def test_secciones_y_textos_de_la_agenda(self):
        h = self._html()
        self.assertIn("No hay publicaciones: hoy no es día hábil.", h)             # sábado 07/11
        self.assertIn("Feriado · Visita de Su Santidad el Papa León XIV", h)        # lunes 9 en "Esta semana"
        self.assertIn("<b>IPC de octubre</b> · INDEC · 16 h", h)
        self.assertIn("hoy el monitor muestra", h)
        self.assertIn('<span class="atr">⚠ atrasado</span>', h)
        self.assertIn("sep-26 se publicó el 19/10", h)
        self.assertIn('<div class="cf grave">⏸ Tipo de cambio real multilateral', h)
        self.assertIn("Sin calendario oficial (1 series)", h)
        self.assertIn('id="demorados"', h)

    def test_esta_semana_sin_el_proximo_que_repite_la_fecha_del_dia(self):
        h = self._html()
        semana = h[h.index("Esta semana"):h.index("Cada publicación en el monitor")]
        self.assertIn('hoy el monitor muestra <span class="per">sep-26</span> · <span class="ok">✓ al día</span></div>', semana)
        self.assertNotIn("próximo", semana)
        self.assertIn("jue 12/11, 16 h", h[h.index("Cada publicación en el monitor"):])   # la tabla no cambia

    def test_las_publicaciones_que_no_usa_el_monitor_van_ocultas(self):
        h = self._html()
        self.assertIn('<div class="m-otra">Índice de producción industrial pesquero (IPI pesquero)</div>', h)
        self.assertIn(".m-otra { display:none;", h)
        self.assertIn('id="ver-otras"', h)

    def test_nada_estimado(self):
        self.assertNotIn("estimad", self._html().lower().replace("no se les estima", ""))

    def test_feriado_hoy(self):
        h = self._html(ctx(datetime(2026, 11, 9, 6, 30)))
        self.assertIn("Hoy es feriado (Visita de Su Santidad el Papa León XIV)", h)

    def test_dia_del_ipc(self):
        h = self._html(ctx(datetime(2026, 11, 12, 6, 30)))
        self.assertIn('<p class="c-hoy-pub"><b>IPC de octubre</b> · INDEC · 16 h', h)

    def test_sin_agenda_no_muestra_fechas(self):
        h = P.html(None, [], {}, [], ctx(), CFG)
        self.assertIn("Calendario del INDEC no disponible hoy", h)
        self.assertNotIn("IPC de octubre", h)

    def test_cache_vieja(self):
        c = ctx(datetime(2026, 11, 20, 6, 30))
        self.assertIn("bajado el 07/11: no se pudo actualizar", self._html(c))


if __name__ == "__main__":
    unittest.main()

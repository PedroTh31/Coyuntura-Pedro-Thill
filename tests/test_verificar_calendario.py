"""Caché con fallback, asignación por título, ventanas de alerta, días hábiles y feriados del
calendario (calendario_indec + verificar_calendario). Sin red: descargas simuladas."""
import copy
import re
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import calendario_indec as C  # noqa: E402
import verificar_calendario as V  # noqa: E402

P = C.Publicacion
CFG_BASE = {
    "fuente": {"meses_a_bajar": 5},
    "publicaciones": [
        {"id": "ipc", "nombre": "IPC", "frecuencia": "mensual", "meses_siguientes_alerta": 1,
         "titulo_regex": r"^Índice de precios al consumidor \(IPC\)\. Cobertura nacional\. (?P<periodo>.+)$"},
        {"id": "eph", "nombre": "Mercado de trabajo", "frecuencia": "trimestral", "meses_siguientes_alerta": 3,
         "titulo_regex": r"^Mercado de trabajo\. Tasas e indicadores socioeconómicos\. (?P<periodo>.+)$"},
    ],
    "feriados": {"2026": {"verificado": True, "fechas": [
        {"fecha": "2026-11-09", "tipo": "inamovible", "nombre": "Papa"},
        {"fecha": "2026-11-10", "tipo": "especial", "nombre": "Papa CABA"},
        {"fecha": "2026-11-23", "tipo": "trasladable", "nombre": "Soberanía"}],
        "especiales_descartados": [{"fecha": "2026-11-11", "motivo": "sólo PBA"}]}},
}


def cfg():
    c = copy.deepcopy(CFG_BASE)
    for p in c["publicaciones"]:
        p["_re"] = re.compile(p["titulo_regex"])
    return c


def ipc(d, periodo):
    return P(d, "16:00", f"Índice de precios al consumidor (IPC). Cobertura nacional. {periodo}")


EPH_DIC = P(date(2026, 12, 18), "16:00", "Mercado de trabajo. Tasas e indicadores socioeconómicos. Tercer trimestre de 2026")
POR_MES = {(2026, 11): [ipc(date(2026, 11, 12), "Octubre de 2026")],
           (2026, 12): [ipc(date(2026, 12, 15), "Noviembre de 2026"), EPH_DIC],
           (2027, 1): [ipc(date(2027, 1, 14), "Diciembre de 2026")],
           (2027, 2): [ipc(date(2027, 2, 12), "Enero de 2027")],
           (2027, 3): [ipc(date(2027, 3, 12), "Febrero de 2027")]}


def bajar_ok(a, m, exigir_publicaciones=False):
    return POR_MES[(a, m)]


def oficiales_ok(anio):
    return {"nacionales": {"2026-11-09": "Papa", "2026-11-23": "Soberanía"},
            "especiales": {"2026-11-10": "Papa CABA", "2026-11-11": "Papa PBA"}} if anio == 2026 else None


class TestCacheYAsignacion(unittest.TestCase):

    def test_todo_ok_sin_alertas(self):
        cache = {"meses": {}}
        d, s, asig, est = V.verificar(date(2026, 11, 7), cfg(), cache, bajar_ok, oficiales_ok)
        self.assertEqual((d, s), ([], []))
        self.assertEqual(asig["ipc"][0], {"fecha": "2026-11-12", "hora": "16:00", "periodo": "Octubre de 2026",
                                          "titulo": POR_MES[(2026, 11)][0].titulo})
        self.assertEqual(set(cache["meses"]), {"2026-11", "2026-12", "2027-01", "2027-02", "2027-03"})
        self.assertTrue(all(v["fuente"] == "endpoint" for v in est.values()))

    def test_mes_que_falla_usa_el_cache_marcado_y_alerta(self):
        cache = {"meses": {}}
        V.verificar(date(2026, 11, 7), cfg(), cache, bajar_ok, oficiales_ok)   # llena el caché

        def bajar_dic_roto(a, m, exigir_publicaciones=False):
            if (a, m) == (2026, 12):
                raise C.CalendarioFormatoError("Diciembre 2026: no se encontró el encabezado del mes")
            return bajar_ok(a, m)
        d, s, asig, est = V.verificar(date(2026, 11, 7), cfg(), cache, bajar_dic_roto, oficiales_ok)
        self.assertEqual(est["2026-12"]["fuente"], "cache")
        self.assertEqual(len(d), 1)
        self.assertIn("encabezado del mes", d[0][1])
        self.assertIn("2026-12-18", [x["fecha"] for x in asig["eph"]])   # el dato del caché se usa igual
        self.assertEqual(len(cache["meses"]["2026-12"]["publicaciones"]), 2)  # el fallo no pisó el caché

    def test_mes_que_falla_sin_cache(self):
        def bajar_roto(a, m, exigir_publicaciones=False):
            raise C.CalendarioFormatoError("HTTP 500")
        d, s, asig, est = V.verificar(date(2026, 11, 7), cfg(), {"meses": {}}, bajar_roto, oficiales_ok)
        self.assertEqual(len(d), 5)
        self.assertTrue(all(v["fuente"] == "sin_datos" for v in est.values()))
        self.assertEqual({k for k, _ in s}, {"falta:ipc", "falta:eph"})

    def test_exige_publicaciones_en_los_primeros_3_meses(self):
        pedidos = []

        def bajar(a, m, exigir_publicaciones=False):
            pedidos.append(exigir_publicaciones)
            return bajar_ok(a, m)
        C.obtener_publicaciones(date(2026, 11, 7), 5, {"meses": {}}, bajar)
        self.assertEqual(pedidos, [True, True, True, False, False])

    def test_titulo_que_matchea_dos_patrones(self):
        c = cfg()
        c["publicaciones"][1]["_re"] = re.compile(r"^Índice de precios (?P<periodo>.+)$")
        d, s, asig, est = V.verificar(date(2026, 11, 7), c, {"meses": {}}, bajar_ok, oficiales_ok)
        self.assertTrue(any(k == "asignacion" for k, _ in d))
        self.assertEqual(asig["ipc"], [])


class TestVentanas(unittest.TestCase):

    def test_mensual_y_trimestral(self):
        asig, _ = C.asignar([p for v in POR_MES.values() for p in v], cfg())
        self.assertEqual(C.faltantes_en_ventana(asig, cfg(), date(2026, 11, 7)), [])
        # 05/01: la EPH de diciembre ya pasó y la próxima es en marzo. Con 3 meses siguientes
        # (ene-abr) alcanza si marzo la trae; si no la trae (caso de prueba), alerta.
        self.assertEqual(C.faltantes_en_ventana(asig, cfg(), date(2027, 1, 5)), ["eph"])
        asig["eph"].append({"fecha": "2027-03-18", "hora": "16:00", "periodo": "Cuarto trimestre de 2026", "titulo": "x"})
        self.assertEqual(C.faltantes_en_ventana(asig, cfg(), date(2027, 1, 5)), [])

    def test_cambio_de_titulo_dispara_la_alerta(self):
        renombrada = {k: [P(p.fecha, p.hora, p.titulo.replace("Índice de precios al consumidor", "IPC"))
                          for p in v] for k, v in POR_MES.items()}
        d, s, _, _ = V.verificar(date(2026, 11, 7), cfg(), {"meses": {}},
                                 lambda a, m, exigir_publicaciones=False: renombrada[(a, m)], oficiales_ok)
        self.assertEqual([k for k, _ in s], ["falta:ipc"])


class TestFeriadosYDiasHabiles(unittest.TestCase):

    def test_dias_habiles(self):
        nh = C.feriados(cfg())
        self.assertFalse(C.es_habil(date(2026, 11, 10), nh))       # especial CABA: cuenta
        self.assertTrue(C.es_habil(date(2026, 11, 11), nh))        # sólo PBA: no cuenta
        self.assertEqual(C.sumar_dias_habiles(date(2026, 11, 6), 1, nh), date(2026, 11, 11))  # vie -> 9 y 10 feriados
        self.assertEqual(C.sumar_dias_habiles(date(2026, 11, 20), 1, nh), date(2026, 11, 24))  # 23 trasladable

    def test_feriados_que_difieren_de_los_oficiales(self):
        def oficiales(anio):
            o = oficiales_ok(anio)
            if o:
                o["nacionales"]["2026-12-07"] = "Puente"
                o["especiales"]["2026-12-24"] = "Nochebuena CABA"
            return o
        claves = {k for k, _ in V.chequear_feriados(cfg(), date(2026, 11, 7), oficiales)}
        self.assertEqual(claves, {"feriados:2026:difieren", "feriados:2026:especiales"})

    def test_anio_provisorio_ya_publicado_y_anio_faltante_en_diciembre(self):
        c = cfg()
        c["feriados"]["2027"] = {"verificado": False, "fechas": [{"fecha": "2027-01-01", "tipo": "inamovible", "nombre": "Año"}]}

        def oficiales(anio):
            return oficiales_ok(2026) if anio == 2026 else {"nacionales": {"2027-01-01": "Año"}, "especiales": {}}
        self.assertIn("feriados:2027:publicados", {k for k, _ in V.chequear_feriados(c, date(2026, 11, 7), oficiales)})
        self.assertIn("feriados:2027:faltan", {k for k, _ in V.chequear_feriados(cfg(), date(2026, 12, 1), oficiales_ok)})

    def test_error_al_bajar_feriados_es_alerta_diaria(self):
        def oficiales_rotos(anio):
            raise V.requests.HTTPError("503")
        d, s, _, _ = V.verificar(date(2026, 11, 7), cfg(), {"meses": {}}, bajar_ok, oficiales_rotos)
        self.assertEqual([k for k, _ in d], ["feriados:error"])


class TestConfigReal(unittest.TestCase):
    """calendario.yaml real: patrones con grupo `periodo` y nombres que existen en indicadores.yaml."""

    def test_calendario_yaml(self):
        import yaml
        c = C.cargar_config()
        ind = yaml.safe_load((C.RAIZ / "indicadores.yaml").read_text(encoding="utf-8"))
        nombres = {i["nombre"] for lista in ("indicadores", "indicadores_financiera") for i in ind[lista]}
        asignados = [n for p in c["publicaciones"] for n in p["indicadores"]]
        self.assertEqual([n for n in asignados if n not in nombres], [])
        self.assertEqual(len(asignados), len(set(asignados)))
        for p in c["publicaciones"]:
            self.assertIn(p["frecuencia"], ("mensual", "trimestral"))


if __name__ == "__main__":
    unittest.main()

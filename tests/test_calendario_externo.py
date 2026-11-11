"""Bloque F1 (calendario ampliado): parsers de cada organismo contra las páginas reales guardadas el 09/11/2026
(tests/fixtures/cal_*, sin <script>/<style>), unión anunciado/publicado, hora AR, caché, alertas y su paso
por la agenda, la página del calendario y el mail. Sin red."""
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agenda as A  # noqa: E402
import cal_bce  # noqa: E402
import cal_bcra  # noqa: E402
import cal_boe  # noqa: E402
import cal_boj  # noqa: E402
import cal_fed  # noqa: E402
import calendario_externo as X  # noqa: E402
import calendario_indec as C  # noqa: E402
import frescura as F  # noqa: E402
import mail_agenda as M  # noqa: E402
import pagina_calendario as P  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
CFG = C.cargar_config()
ORGS = {o["id"]: o for o in X.organismos(CFG)}


def fx(nombre: str) -> str:
    return (FIX / nombre).read_text(encoding="utf-8")


class TestFed(unittest.TestCase):
    def test_reuniones(self):
        ev = cal_fed.parsear_reuniones(fx("cal_fed_fomccalendars.html"), 2025)
        fechas = [e["fecha"] for e in ev]
        self.assertEqual(len(ev), 24)                       # 8 por año 2025-2027; la "notation vote" no cuenta
        self.assertIn("2026-10-28", fechas)                 # "October 27-28": la decisión es el día 2
        self.assertIn("2026-12-09", fechas)                 # "December 8-9*"
        self.assertNotIn("2025-08-22", fechas)              # "August 22 (notation vote)"
        self.assertEqual(fechas[-1], "2027-12-08")
        self.assertTrue(all(e["hora"] is None and e["tipo"] == "decision" for e in ev))

    def test_reunion_que_cruza_de_mes(self):
        ev = cal_fed.parsear_reuniones(fx("cal_fed_fomccalendars.html"), 2023)
        fechas = {e["fecha"] for e in ev}
        self.assertIn("2024-05-01", fechas)                 # "Apr/May 30-1"
        self.assertIn("2023-11-01", fechas)                 # "Oct/Nov 31-1"
        self.assertIn("2023-02-01", fechas)                 # "Jan/Feb 31-1"

    def test_pagina_del_mes_y_horas(self):
        filas = cal_fed.parsear_mes(fx("cal_fed_2026-december.html"), 2026, 12)
        self.assertIn({"evento": "FOMC Meeting", "hora": "14:00", "fechas": ["2026-12-09"]}, filas)
        self.assertIn({"evento": "FOMC Minutes", "hora": "14:00", "fechas": ["2026-12-30"]}, filas)
        ev = [{"tipo": "decision", "fecha": "2026-12-09", "hora": None}]
        self.assertEqual(cal_fed.aplicar_horas(ev, filas), [])
        self.assertEqual(ev[0]["hora"], "14:00")
        avisos = cal_fed.aplicar_horas([{"tipo": "decision", "fecha": "2026-12-10", "hora": None}], filas)
        self.assertEqual(len(avisos), 1)                    # reunión que no está en fomccalendars

    def test_pagina_del_mes_de_otro_mes_es_error(self):
        with self.assertRaises(X.ExternoFormatoError):
            cal_fed.parsear_mes(fx("cal_fed_2026-december.html"), 2026, 11)

    def test_links_del_indice_sin_patron(self):
        idx = fx("cal_fed_calendar_index.html")
        self.assertEqual(cal_fed.link_mes(idx, 2026, 11), "/newsevents/2026-november.htm")
        self.assertEqual(cal_fed.link_mes(idx, 2026, 4), "/newsevents/2026-04.htm")
        self.assertIsNone(cal_fed.link_mes(idx, 2030, 1))

    def test_bajar_anunciados_con_hora(self):
        paginas = {ORGS["fed"]["url"]: fx("cal_fed_fomccalendars.html"),
                   ORGS["fed"]["url_indice_mes"]: fx("cal_fed_calendar_index.html"),
                   "https://www.federalreserve.gov/newsevents/2026-november.htm": fx("cal_fed_2026-november.html"),
                   "https://www.federalreserve.gov/newsevents/2026-december.htm": fx("cal_fed_2026-december.html")}
        ev, avisos = cal_fed.bajar_anunciados(ORGS["fed"], date(2026, 11, 9), bajar=paginas.__getitem__)
        self.assertEqual(avisos, [])
        self.assertEqual(next(e for e in ev if e["fecha"] == "2026-12-09")["hora"], "14:00")

    def test_sin_pagina_del_mes_va_sin_hora_con_aviso(self):
        def bajar(url):
            if url == ORGS["fed"]["url"]:
                return fx("cal_fed_fomccalendars.html")
            raise X.ExternoFormatoError("HTTP 500")
        ev, avisos = cal_fed.bajar_anunciados(ORGS["fed"], date(2026, 11, 9), bajar=bajar)
        self.assertTrue(ev and all(e["hora"] is None for e in ev))
        self.assertEqual(len(avisos), 1)

    def test_rss_solo_statement_y_minutas(self):
        pubs = cal_fed.parsear_rss(fx("cal_fed_press_monetary.xml"), ORGS["fed"])
        self.assertEqual(len(pubs), 8)                      # fuera: SEP, minutas de tasa de descuento, otros
        self.assertEqual(pubs[0], {"tipo": "decision", "fecha": "2026-10-28", "hora": "14:00",   # 18:00 GMT (EDT)
                                   "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm",
                                   "titulo_fuente": "Federal Reserve issues FOMC statement"})
        self.assertEqual(sum(p["tipo"] == "minutas" for p in pubs), 4)
        self.assertFalse(any("discount" in p["titulo_fuente"] or "projections" in p["titulo_fuente"] for p in pubs))

    def test_formato_desconocido(self):
        for f in (lambda c: cal_fed.parsear_reuniones(c, 2025), lambda c: cal_fed.parsear_rss(c, ORGS["fed"])):
            with self.assertRaises(X.ExternoFormatoError):
                f("<html><body>Página en mantenimiento</body></html>")


class TestOtrosOrganismos(unittest.TestCase):
    def test_bce_solo_decisiones(self):
        ev = cal_bce.parsear(fx("cal_bce_mgcgc.html"), ORGS["bce"])
        fechas = [e["fecha"] for e in ev]
        self.assertEqual(len(ev), 17)
        self.assertEqual(fechas[0], "2026-12-17")           # día 2; el 16/12 (día 1) y el 25/11 (no monetaria) no
        self.assertNotIn("2026-12-16", fechas)
        self.assertNotIn("2026-11-25", fechas)
        self.assertNotIn("2026-11-26", fechas)              # General Council
        self.assertEqual(fechas[-1], "2028-12-07")

    def test_boj(self):
        ev = cal_boj.parsear(fx("cal_boj_mpmsche.html"), ORGS["boj"])
        fechas = [e["fecha"] for e in ev]
        self.assertEqual(len(ev), 16)
        self.assertEqual(fechas[:2], ["2026-01-23", "2026-03-19"])
        self.assertIn("2026-12-18", fechas)
        self.assertEqual(fechas[-1], "2027-12-17")

    def test_boj_reunion_que_cruza_de_mes(self):
        html = ('<table><caption class="non-caption">Table : 2027</caption><tbody><tr>'
                '<td>Apr. 30 (Fri.), May 1 (Sat.)</td><td>-</td></tr></tbody></table>')
        self.assertEqual(cal_boj.parsear(html, ORGS["boj"])[0]["fecha"], "2027-05-01")

    def test_boe(self):
        ev = cal_boe.parsear(fx("cal_boe_mpc_dates.html"), ORGS["boe"])
        fechas = [e["fecha"] for e in ev]
        self.assertEqual(len(ev), 16)
        self.assertIn("2026-11-05", fechas)
        self.assertIn("2026-12-17", fechas)
        self.assertEqual(fechas[-1], "2027-12-16")

    def test_boe_dia_de_la_semana_no_coincide(self):
        html = ('<h2>2028 confirmed dates</h2><table><tr><td>Thursday 5 February</td>'
                '<td>February MPC Summary and minutes</td></tr></table>')
        with self.assertRaises(X.ExternoFormatoError):   # el 05/02/2028 es sábado: año o formato cambiaron
            cal_boe.parsear(html, ORGS["boe"])

    def test_bcra_rem_e_ipom_con_sus_dos_nombres(self):
        ev = cal_bcra.parsear(fx("cal_bcra_calendario_informes.html"), ORGS["bcra"])
        por_tipo = {t: [e["fecha"] for e in ev if e["tipo"] == t] for t in ("rem", "ipom")}
        self.assertEqual(por_tipo["ipom"], ["2026-05-13", "2026-08-06", "2026-10-29"])
        self.assertEqual(len(por_tipo["rem"]), 11)
        self.assertEqual(por_tipo["rem"][-1], "2026-11-05")

    def test_bcra_encabezado_distinto(self):
        with self.assertRaises(X.ExternoFormatoError):
            cal_bcra.parsear("<table><tr><th>Informe</th><th>Día</th></tr></table>", ORGS["bcra"])

    def test_formato_desconocido(self):
        for mod, oid in ((cal_bce, "bce"), (cal_boj, "boj"), (cal_boe, "boe"), (cal_bcra, "bcra")):
            with self.subTest(oid), self.assertRaises(X.ExternoFormatoError):
                mod.parsear("<html><body>Página en mantenimiento</body></html>", ORGS[oid])


class TestHoraYUnion(unittest.TestCase):
    def test_hora_ar_con_horario_de_verano(self):
        self.assertEqual(X.a_ar("2026-12-09", "14:00", "America/New_York"), ("2026-12-09", "16:00"))   # EST
        self.assertEqual(X.a_ar("2026-07-29", "14:00", "America/New_York"), ("2026-07-29", "15:00"))   # EDT
        self.assertEqual(X.a_ar("2026-12-28", "08:50", "Asia/Tokyo"), ("2026-12-27", "20:50"))         # cambia el día
        self.assertEqual(X.a_ar("2026-12-17", None, "Europe/Berlin"), ("2026-12-17", None))
        self.assertEqual(X.texto_hora("16:00", "14:00", ORGS["fed"]), "16:00 AR (14:00 ET)")
        self.assertEqual(X.texto_hora(None, None, ORGS["bce"]), "")

    def cache(self):
        return {"anunciados": {
            "fed": {"bajado": "x", "eventos": [{"tipo": "decision", "fecha": "2026-10-28", "hora": None},
                                               {"tipo": "decision", "fecha": "2026-12-09", "hora": "14:00"}]},
            "bce": {"bajado": "x", "eventos": [{"tipo": "decision", "fecha": "2026-10-29", "hora": None}]}},
            "publicados": {"fed": {"bajado": "x", "items": [
                {"tipo": "decision", "fecha": "2026-10-28", "hora": "14:00", "url": "u1", "titulo_fuente": "s"},
                {"tipo": "minutas", "fecha": "2026-10-07", "hora": "14:00", "url": "u2", "titulo_fuente": "m"}]}}}

    def test_union_anunciado_publicado(self):
        ev = X.eventos(self.cache(), CFG, date(2026, 11, 9))
        fed = [e for e in ev if e["org"] == "fed"]
        self.assertEqual(len(fed), 3)                       # la decisión del 28/10 queda una sola
        d = next(e for e in fed if e["fecha"] == "2026-10-28")
        self.assertEqual((d["estado"], d["url"], d["hora_txt"]), ("publicado", "u1", "15:00 AR (14:00 ET)"))
        m = next(e for e in fed if e["tipo"] == "minutas")
        self.assertEqual((m["estado"], m["titulo"]), ("publicado", "Minutas del FOMC"))
        futuro = next(e for e in fed if e["fecha"] == "2026-12-09")
        self.assertEqual((futuro["estado"], futuro["url"], futuro["hora_txt"]), ("anunciado", None, "16:00 AR (14:00 ET)"))
        bce = next(e for e in ev if e["org"] == "bce")
        self.assertEqual((bce["estado"], bce["hora_txt"], bce["organismo"]), ("anunciado", "", "BCE"))

    def test_fusionar_anunciados(self):
        previos = [{"tipo": "decision", "fecha": "2026-10-29", "hora": None},     # pasado que la fuente ya no lista
                   {"tipo": "decision", "fecha": "2026-12-09", "hora": "14:00"},  # hora conocida
                   {"tipo": "decision", "fecha": "2027-01-20", "hora": None}]     # futuro que desapareció
        nuevos = [{"tipo": "decision", "fecha": "2026-12-09", "hora": None},
                  {"tipo": "decision", "fecha": "2027-01-27", "hora": None}]
        out = X.fusionar_anunciados(previos, nuevos, date(2026, 11, 9))
        self.assertEqual([(e["fecha"], e["hora"]) for e in out],
                         [("2026-10-29", None), ("2026-12-09", "14:00"), ("2027-01-27", None)])

    def test_fusionar_publicados_acumula(self):
        a = [{"tipo": "minutas", "fecha": "2026-05-20", "hora": "14:00", "url": "u0"}]
        b = [{"tipo": "decision", "fecha": "2026-10-28", "hora": "14:00", "url": "u1"}]
        self.assertEqual([p["url"] for p in X.fusionar_publicados(a, b)], ["u0", "u1"])


class FalsoOk:
    def __init__(self, eventos, avisos=(), pubs=None):
        self.eventos, self.avisos, self.pubs = eventos, list(avisos), pubs

    def bajar_anunciados(self, org, hoy):
        return [dict(e) for e in self.eventos], self.avisos

    def bajar_publicados(self, org):
        if self.pubs is None:
            raise X.ExternoFormatoError("HTTP 503")
        return self.pubs


class FalsoMal:
    def bajar_anunciados(self, org, hoy):
        raise X.ExternoFormatoError("HTTP 500")


class TestActualizar(unittest.TestCase):
    def test_falla_no_pisa_la_cache_y_avisa(self):
        futuro = [{"tipo": "decision", "fecha": "2026-12-17", "hora": None}]
        cache = {"anunciados": {"bce": {"bajado": "2026-11-01T06:00:00-03:00", "eventos": futuro}}, "publicados": {}}
        modulos = {"fed": FalsoOk(futuro, pubs=[]), "bce": FalsoMal(), "boj": FalsoOk(futuro),
                   "boe": FalsoOk(futuro), "bcra": FalsoOk([]), "tesoro": FalsoOk(futuro, pubs=[])}
        diarios, semanales, estado = X.actualizar(cache, CFG, date(2026, 11, 9), modulos)
        self.assertEqual(cache["anunciados"]["bce"]["eventos"], futuro)
        self.assertEqual(estado["bce"]["anunciados"]["fuente"], "cache")
        self.assertEqual([k for k, _ in diarios], ["externo:bce:descarga"])
        self.assertEqual([k for k, _ in semanales], ["externo:bcra:sin_futuros"])   # el BCRA sin fechas futuras

    def test_publicados_fallidos_avisan(self):
        ev = [{"tipo": "decision", "fecha": "2026-12-09", "hora": None}]
        modulos = {k: FalsoOk(ev) for k in ("fed", "bce", "boj", "boe", "bcra")}
        modulos["tesoro"] = FalsoOk(ev, pubs=[])
        cache = {"anunciados": {}, "publicados": {}}
        diarios, _, _ = X.actualizar(cache, CFG, date(2026, 11, 9), modulos)
        self.assertEqual([k for k, _ in diarios], ["externo:fed:publicados"])
        self.assertNotIn("fed", cache["publicados"])   # la descarga fallida de la FED no pisa nada


# ---------------------------------------------------------------------------------------------
# Agenda, página y mail
# ---------------------------------------------------------------------------------------------
def _ext(org, titulo, fecha_ar, hora_ar=None, hora_txt="", estado="anunciado", url=None):
    return {"org": org.lower(), "organismo": org, "tipo": "decision", "titulo": titulo, "fecha": fecha_ar, "hora": None,
            "zona": "", "fecha_ar": fecha_ar, "hora_ar": hora_ar, "hora_txt": hora_txt, "estado": estado, "url": url,
            "url_fuente": ""}


EXTERNOS = [_ext("FED", "Minutas del FOMC", "2026-11-05", "15:00", "15:00 AR (13:00 ET)", "publicado", "https://fed/m"),
            _ext("BoE", "Decisión de tasa (BoE)", "2026-11-05"),
            _ext("BCRA", "Relevamiento de Expectativas de Mercado (REM)", "2026-11-11"),
            _ext("FED", "Decisión de tasa (FOMC)", "2026-11-12", "16:00", "16:00 AR (14:00 ET)")]


def ctx(ahora=datetime(2026, 11, 11, 6, 30), externos=EXTERNOS, fechas=None):
    pubs = [{"fecha": "2026-12-15", "hora": "16:00", "periodo": F.parsear_periodo_indec("Noviembre de 2026")}]
    return F.Contexto(ahora=ahora, fechas=fechas if fechas is not None else {"ipc": pubs},
                      meses_bajado={m: "2026-11-10T06:20:00-03:00" for m in ("2026-11", "2026-12")},
                      externos=externos)


class TestAgenda(unittest.TestCase):
    def test_hoy_y_semana(self):
        cal = A.armar_calendario(ctx(), CFG)
        self.assertEqual(cal["hoy"], [{"titulo": "Relevamiento de Expectativas de Mercado (REM)", "fuente": "BCRA",
                                       "hora": "", "externo": True}])
        self.assertEqual(cal["semana"], [{"dia": "jue 12/11", "hora": "16:00 AR (14:00 ET)",
                                          "titulos": ["Decisión de tasa (FOMC)"], "urls": [None], "fuente": "FED"}])
        self.assertIsNone(cal["proxima"])   # la semana tiene ítems: sin "próxima" (igual que antes del F1)

    def test_sin_externos_no_cambia(self):
        cal = A.armar_calendario(ctx(externos=[]), CFG)
        self.assertEqual((cal["hoy"], cal["semana"]), ([], []))

    def test_meses(self):
        m = A.armar_meses({"meses": {}}, CFG, ctx(), {}, ["2026-11"])[0]
        dias = {d["fecha"]: d["publicaciones"] for d in m["dias"]}
        self.assertEqual([(p["organismo"], p["estado_ext"], p["url"]) for p in dias["2026-11-05"]],
                         [("FED", "publicado", "https://fed/m"), ("BoE", "anunciado", None)])
        self.assertEqual(dias["2026-11-11"][0]["estado_ext"], "proximo")   # hoy, sin hora: todavía no
        self.assertEqual(dias["2026-11-12"][0]["estado_ext"], "proximo")


class TestRender(unittest.TestCase):
    def test_pagina(self):
        c = ctx()
        cfg = dict(CFG)
        agenda = {"calendario": A.armar_calendario(c, cfg), "publicaciones": {}, "atrasados": [], "graves": []}
        meses = A.armar_meses({"meses": {"2026-11": {"bajado": "2026-11-10T06:20:00-03:00", "publicaciones": []}}},
                              cfg, c, {}, ["2026-11"])
        h = P.html(agenda, meses, {}, [], c, cfg)
        self.assertIn('<a href="https://fed/m">Minutas del FOMC</a>', h)
        self.assertIn('<span class="org">BoE</span>Decisión de tasa (BoE) <span class="an">· anunciado</span>', h)
        self.assertIn("Las series diarias del BCRA, de MinEco y de mercados no tienen calendario oficial: no se les "
                      "estima fecha. Las publicaciones del BCRA con fecha anunciada (IPOM, REM) figuran en el calendario, "
                      "igual que las licitaciones del Tesoro", h)
        self.assertIn('<span class="org">FED</span><b>Decisión de tasa (FOMC)</b> · 16:00 AR (14:00 ET)', h)   # esta semana
        self.assertIn("https://www.federalreserve.gov/feeds/press_monetary.xml", h)
        self.assertNotIn('id="ver-otras-ext"', h)   # sin checkbox para los externos

    def test_mail(self):
        cal = A.armar_calendario(ctx(), CFG)
        h = M.html_calendario({"calendario": cal})
        self.assertIn("Relevamiento de Expectativas de Mercado (REM)</b> · BCRA</td>", h)
        self.assertNotIn("el dato llega en el próximo mail", h)
        self.assertIn(">16:00 AR (14:00 ET)</td>", h)
        self.assertIn(">Decisión de tasa (FOMC)</td>", h)
        self.assertNotIn("Del INDEC", h)
        self.assertIn("publicaciones del INDEC y de otros organismos</span>", h)


if __name__ == "__main__":
    unittest.main()

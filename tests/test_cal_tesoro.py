"""Licitaciones del Tesoro en el calendario ampliado (cal_tesoro.py + calendario_externo). Sin red: fixtures
reales bajados el 11/11/2026 (tests/fixtures/cal_tesoro_*)."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cal_tesoro as T  # noqa: E402
import calendario_externo as X  # noqa: E402
import calendario_indec as C  # noqa: E402

FX = Path(__file__).resolve().parent / "fixtures"
HOY = date(2026, 11, 11)
CRONOGRAMA = "https://www.argentina.gob.ar/economia/finanzas/licitaciones-de-letras-y-bonos-del-tesoro/cronograma-2026"
LLAMADO = "https://www.argentina.gob.ar/noticias/llamado-licitacion-de-instrumentos-del-tesoro-nacional-denominados-en-pesos-y-en-dolares-{}"
RESULTADO_16 = "https://www.argentina.gob.ar/noticias/resultado-de-la-licitacion-por-efectivo-de-instrumentos-del-tesoro-nacional-denominados-16"


def leer(nombre):
    return (FX / nombre).read_text(encoding="utf-8")


def org():
    return next(o for o in X.organismos(C.cargar_config()) if o["id"] == "tesoro")


def bajar(url):
    o = org()
    paginas = {o["url"]: "cal_tesoro_landing.html", CRONOGRAMA: "cal_tesoro_cronograma_2026.html",
               o["publicados"]["url"]: "cal_tesoro_noticias.html"}
    paginas.update({LLAMADO.format(n): f"cal_tesoro_llamado_{n}.html" for n in range(12, 17)})
    if url not in paginas:
        raise AssertionError(f"URL inesperada: {url}")
    return leer(paginas[url])


def pdf(_url):
    return (FX / "cal_tesoro_cronograma_2026.pdf").read_bytes()


def cache_real():
    an, _ = T.bajar_anunciados(org(), HOY, bajar=bajar, bajar_pdf=pdf)
    return {"anunciados": {"tesoro": {"eventos": an}}, "publicados": {"tesoro": {"items": T.bajar_publicados(org(), bajar=bajar)}}}


def cfg_tesoro():
    cfg = C.cargar_config()
    return {**cfg, "externos": [o for o in cfg["externos"] if o["id"] == "tesoro"]}


class TestCronograma(unittest.TestCase):

    def test_pdf_2026_23_ciclos(self):
        ev = T.parsear_pdf(pdf(None), 2026)
        self.assertEqual(len(ev), 69)
        lic = [e["fecha"][5:] for e in ev if e["tipo"] == "licitacion"]
        self.assertEqual(lic, ["01-14", "01-28", "02-11", "02-25", "03-12", "03-27", "04-15", "04-28", "05-13", "05-27",
                               "06-10", "06-26", "07-15", "07-29", "08-12", "08-27", "09-11", "09-28", "10-14", "10-28",
                               "11-11", "11-26", "12-11"])
        nov = [(e["tipo"], e["fecha"]) for e in ev if e["ciclo"] == "2026-11-11"]
        self.assertEqual(nov, [("llamado", "2026-11-09"), ("licitacion", "2026-11-11"), ("liquidacion", "2026-11-13")])
        self.assertTrue(all(e["hora"] is None for e in ev))   # la fuente no da hora

    def test_pdf_de_otro_anio_falla(self):
        with self.assertRaises(X.ExternoFormatoError):
            T.parsear_pdf(pdf(None), 2027)

    def test_ciclos_incompletos_o_desordenados_fallan(self):
        d = date
        with self.assertRaises(X.ExternoFormatoError):
            T.armar_ciclos([(d(2026, 1, 12), "llamado"), (d(2026, 1, 14), "licitacion")], 2026)
        with self.assertRaises(X.ExternoFormatoError):
            T.armar_ciclos([(d(2026, 1, 16), "llamado"), (d(2026, 1, 14), "licitacion"), (d(2026, 1, 20), "liquidacion")], 2026)

    def test_links_del_cronograma(self):
        self.assertEqual(T.cronogramas(leer("cal_tesoro_landing.html"), HOY), {2026: CRONOGRAMA})   # sin el de 2025
        with self.assertRaises(X.ExternoFormatoError):   # en 2027 sin la página de 2027: alerta, nunca silencio
            T.cronogramas(leer("cal_tesoro_landing.html"), date(2027, 1, 5))
        self.assertEqual(T.url_pdf(leer("cal_tesoro_cronograma_2026.html")),
                         "https://www.argentina.gob.ar/sites/default/files/calendario_prensa_0.pdf")


class TestPublicados(unittest.TestCase):

    def test_fechas_de_los_llamados(self):
        esperado = {12: ("2026-09-11", "2026-09-15"), 13: ("2026-09-28", "2026-09-30"), 14: ("2026-10-14", "2026-10-16"),
                    15: ("2026-10-28", "2026-10-30"), 16: ("2026-11-11", "2026-11-13")}
        for n, (lic, liq) in esperado.items():
            self.assertEqual(tuple(x.isoformat() for x in T.fechas_llamado(leer(f"cal_tesoro_llamado_{n}.html"))), (lic, liq))

    def test_llamado_con_fechas_que_no_coinciden_falla(self):
        roto = leer("cal_tesoro_llamado_16.html").replace("comunicado_llamado_20261111", "comunicado_llamado_20261112")
        with self.assertRaises(X.ExternoFormatoError):
            T.fechas_llamado(roto)

    def test_listado_solo_llamados_y_resultados_por_efectivo(self):
        items = T.bajar_publicados(org(), bajar=bajar)
        self.assertEqual([(i["tipo"], i["fecha"], i["ciclo"]) for i in items], [
            ("llamado", "2026-11-05", "2026-11-11"), ("licitacion", "2026-10-28", "2026-10-28"),
            ("llamado", "2026-10-26", "2026-10-28"), ("licitacion", "2026-10-14", "2026-10-14"),
            ("llamado", "2026-10-09", "2026-10-14"), ("licitacion", "2026-09-28", "2026-09-28"),
            ("llamado", "2026-09-24", "2026-09-28"), ("licitacion", "2026-09-11", "2026-09-11"),
            ("llamado", "2026-09-09", "2026-09-11")])
        self.assertNotIn("conversion", " ".join(i["url"] for i in items))


class TestEventos(unittest.TestCase):

    def eventos(self):
        return {(e["tipo"], e["ciclo"]): e for e in X.eventos(cache_real(), cfg_tesoro(), HOY)}

    def test_decision_A_el_llamado_publicado_manda_sobre_el_cronograma(self):
        todos = X.eventos(cache_real(), cfg_tesoro(), HOY)
        llamados_nov = [e for e in todos if e["tipo"] == "llamado" and e["ciclo"] == "2026-11-11"]
        self.assertEqual(len(llamados_nov), 1)   # el 09/11 del PDF no queda duplicado
        e = llamados_nov[0]
        self.assertEqual((e["fecha_ar"], e["estado"], e["link"]), ("2026-11-05", "publicado", LLAMADO.format(16)))
        self.assertEqual(e["titulo"], "Llamado a licitación del Tesoro — 11/11")

    def test_links_por_ciclo_y_general(self):
        ev = self.eventos()
        # licitación de hoy, todavía sin resultado: el link va al llamado de su ciclo
        lic = ev[("licitacion", "2026-11-11")]
        self.assertEqual((lic["estado"], lic["link"]), ("anunciado", LLAMADO.format(16)))
        self.assertEqual(lic["titulo"], "Licitación del Tesoro — 11/11 (resultados el mismo día por la tarde)")
        # licitación con resultado publicado: link directo al resultado; la liquidación de ese ciclo, también
        self.assertEqual(ev[("licitacion", "2026-10-28")]["link"], RESULTADO_16)
        self.assertEqual(ev[("liquidacion", "2026-10-28")]["link"], RESULTADO_16)
        # ciclo sin nada publicado: la página general de licitaciones
        for tipo in ("llamado", "licitacion", "liquidacion"):
            self.assertEqual(ev[(tipo, "2026-11-26")]["link"], "https://www.argentina.gob.ar/economia/licitaciones")
            self.assertIsNone(ev[(tipo, "2026-11-26")]["url"])

    def test_la_liquidacion_sale_del_llamado(self):
        cache = cache_real()
        for p in cache["publicados"]["tesoro"]["items"]:
            if p["ciclo"] == "2026-11-11" and p["tipo"] == "llamado":
                p["fechas_ciclo"]["liquidacion"] = "2026-11-16"   # ej. el llamado corre la liquidación
        ev = {(e["tipo"], e["ciclo"]): e for e in X.eventos(cache, cfg_tesoro(), HOY)}
        self.assertEqual(ev[("liquidacion", "2026-11-11")]["fecha_ar"], "2026-11-16")

    def test_publicado_de_un_ciclo_que_no_esta_en_el_cronograma_avisa(self):
        cache = cache_real()
        movido = dict(cache["publicados"]["tesoro"]["items"][0], ciclo="2026-11-12", url="https://x/llamado-movido")

        class Mod:
            @staticmethod
            def bajar_anunciados(o, hoy):
                return cache["anunciados"]["tesoro"]["eventos"], []

            @staticmethod
            def bajar_publicados(o):
                return [movido]

        _, semanales, _ = X.actualizar({"anunciados": {}, "publicados": {}}, cfg_tesoro(), HOY, modulos={"tesoro": Mod})
        self.assertIn("externo:tesoro:ciclo:2026-11-12", [k for k, _ in semanales])


if __name__ == "__main__":
    unittest.main()


class TestLinksEnPantalla(unittest.TestCase):
    """El link del evento llega al mail (Hoy / Esta semana) y a la franja de la home."""

    def setUp(self):
        import agenda as A  # noqa: F401
        self.ev = [e for e in X.eventos(cache_real(), cfg_tesoro(), HOY) if e["ciclo"] in ("2026-11-11", "2026-11-26")]

    def vista(self):
        import frescura as F
        import agenda as A
        from datetime import datetime
        ctx = F.Contexto(ahora=datetime(2026, 11, 11, 8, 0), fechas={},
                         meses_bajado={m: "2026-11-10T06:20:00-03:00" for m in ("2026-11", "2026-12")}, externos=self.ev)
        return A.armar_calendario(ctx, C.cargar_config())

    def test_mail(self):
        import mail_agenda as MA
        cal = self.vista()
        h = MA.html_calendario({"calendario": {**cal, "estado": "ok", "fecha": HOY.isoformat()}})
        self.assertIn(f'<a href="{LLAMADO.format(16)}"', h)   # licitación de hoy -> llamado de su ciclo
        self.assertIn("Licitación del Tesoro — 11/11 (resultados el mismo día por la tarde)</a>", h)
        self.assertIn("Liquidación de la licitación del Tesoro — 11/11</a>", h)   # Esta semana: vie 13/11

    def test_home(self):
        import pagina_home as H
        h = H._franja({"calendario": {**self.vista(), "estado": "ok"}})
        self.assertIn(f'<a href="{LLAMADO.format(16)}">Licitación del Tesoro — 11/11', h)
        self.assertIn("Finanzas", h)
        self.assertNotIn("INDEC · ", h)   # la franja ya no rotula "INDEC" a otro organismo

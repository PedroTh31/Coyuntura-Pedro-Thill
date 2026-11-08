"""Bloque E2: mapeo de temas (temas.py + bloque `temas:` de indicadores.yaml), slugs y home. Sin red."""
import unittest
from pathlib import Path

import pandas as pd
import yaml

import pagina_home as H
import sitio
import temas as T

RAIZ = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((RAIZ / "indicadores.yaml").read_text(encoding="utf-8"))
LISTA = CFG["indicadores"] + [i for i in CFG["indicadores_financiera"] if not i.get("solo_referencia")]


class TestMapeoTemas(unittest.TestCase):
    def test_cada_card_en_un_solo_tema(self):
        temas, sin_tema, inexistentes = T.completar(CFG["temas"], LISTA)
        self.assertEqual(sin_tema, [], "cards sin tema en indicadores.yaml")
        self.assertEqual(inexistentes, [], "ítems de `temas:` que no son cards")
        self.assertEqual(T.repetidos(CFG["temas"]), [])

    def test_ocho_temas_en_el_orden_del_nav(self):
        self.assertEqual([(t["titulo"], t["slug"]) for t in CFG["temas"]], sitio.TEMAS_NAV)

    def test_solo_referencia_no_es_item(self):
        ref = [i for i in CFG["indicadores_financiera"] if i.get("solo_referencia")]
        self.assertTrue(ref)
        self.assertTrue(all(T.item_de(i) is None for i in ref))

    def test_decisiones_d8(self):
        de = T.tema_de_item(CFG["temas"])
        self.assertEqual(de["Riesgo país (EMBI)"], "mercados")
        self.assertEqual(de["PBI nominal (precios corrientes)"], "actividad")
        for n in ("Tasa TAMAR bancos privados (bonos duales)", "Tasa BADLAR (bancos privados)",
                  "Tasa de plazo fijo a 30 días", "Depósitos: sector privado en pesos"):
            self.assertEqual(de[n], "dinero-y-credito", n)
        for n in ("Caución en pesos (1 día)", "Caución en dólares (1 día)",
                  "CER (Coeficiente de Estabilización de Referencia)", T.MURO, T.ACCIONES):
            self.assertEqual(de[n], "mercados", n)
        self.assertEqual(de["Canje MEP/CCL"], "dolar-y-reservas")
        self.assertEqual(de[T.DDF], "dolar-y-reservas")

    def test_card_sin_tema_no_desaparece(self):
        nueva = {"nombre": "Serie nueva", "bloque": "fiscal", "grupo": "Fiscal"}
        temas, sin_tema, _ = T.completar(CFG["temas"], LISTA + [nueva])
        self.assertEqual(sin_tema, ["Serie nueva"])
        fiscal = next(t for t in temas if t["slug"] == "fiscal-y-deuda")
        self.assertEqual(fiscal["secciones"][-1], {"titulo": T.SIN_TEMA, "items": ["Serie nueva"]})
        # la lista original no se toca
        self.assertNotIn(T.SIN_TEMA, [s["titulo"] for t in CFG["temas"] for s in t["secciones"]])

    def test_extra_ausente_no_va_a_sin_tema(self):
        sin_muro = [t for t in (T.completar(CFG["temas"], LISTA, extras_presentes=())[1])]
        self.assertEqual(sin_muro, [])

    def test_indicadores_de_incluye_componentes(self):
        precios = next(t for t in CFG["temas"] if t["slug"] == "precios")
        inds = T.indicadores_de(precios, LISTA)
        nombres = [i["nombre"] for i in inds]
        self.assertIn("IPC división: Salud", nombres)            # componente de la incidencia
        self.assertIn("Inflación mensual (IPC)", nombres)
        self.assertNotIn("Dólar oficial", nombres)

    def test_semaforo_y_tablas(self):
        de = T.tema_de_item(CFG["temas"])
        self.assertEqual(de[T.SEMAFORO], "actividad")
        self.assertEqual(de["Exportaciones por gran rubro"], "sector-externo")
        self.assertEqual(de["Importaciones por uso económico"], "sector-externo")


class TestSlugs(unittest.TestCase):
    def test_slugs_unicos(self):
        nombres = list(T.items_esperados(LISTA))
        slugs = [sitio.slug(n) for n in nombres]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_ejemplos(self):
        self.assertEqual(sitio.slug("Inflación mensual (IPC)"), "inflacion-mensual")
        self.assertEqual(sitio.slug("Deuda pública bruta / PBI"), "deuda-publica-bruta-pbi")
        self.assertEqual(sitio.slug("Cualquiera", {"slug": "fijo"}), "fijo")


class TestSitio(unittest.TestCase):
    def test_mail_ofuscado(self):
        pie = sitio.pie_sitio("../")
        self.assertNotIn("pedrothill31", pie)
        self.assertNotIn("@gmail", pie)
        self.assertIn("linkedin.com/in/pedro-thill-286076218", pie)
        self.assertIn("/commit/730dd39", pie)
        self.assertIn("9 de julio de 2026", pie)

    def test_nav(self):
        nav = sitio.nav_sitio("../", "Precios")
        self.assertIn('href="../"', nav)
        self.assertIn('href="../calendario/"', nav)
        self.assertIn('<a href="../precios/" class="activo">Precios</a>', nav)


class TestHome(unittest.TestCase):
    def test_datos_clave(self):
        dc = CFG["home"]["datos_clave"]
        self.assertEqual(len(dc), 9)
        de = T.tema_de_item(CFG["temas"])
        por_nombre = {i["nombre"]: i for i in LISTA}
        slugs = [t["slug"] for t in CFG["temas"]]
        for d in dc:
            # card de un tema, o serie sin card con página propia (`pagina_serie: <tema>`, ej. EMAE)
            self.assertTrue(d["card"] in de or por_nombre[d["card"]].get("pagina_serie") in slugs, d)
        self.assertEqual(por_nombre["EMAE (actividad económica)"]["pagina_serie"], "actividad")

    def test_redireccion_anclas(self):
        js = H.js_redireccion()
        for a in ("precios", "monetario_financiero", "externo", "real", "social", "fiscal", "mercados"):
            self.assertIn(f'"{a}"', js)
        slugs = {t["slug"] + "/" for t in CFG["temas"]}
        self.assertTrue(set(sitio.REDIRECCION_ANCLAS.values()) <= slugs)

    def test_mini(self):
        f = pd.date_range("2020-01-31", periods=40, freq="ME")
        h = pd.DataFrame({"indicador": "x", "fecha": f, "valor": range(40)})
        m = H._mini(h, "x", "%", True)
        self.assertEqual(len(m["y"]), 24)
        self.assertEqual(m["x"][-1], "abr-23")
        self.assertTrue(m["bar"])
        f = pd.bdate_range("2024-01-01", "2026-11-06")
        h = pd.DataFrame({"indicador": "d", "fecha": f, "valor": 1.0})
        m = H._mini(h, "d", "$", False)
        self.assertLessEqual(len(m["y"]), 262)

    def test_html_home(self):
        datos = [dict(etiqueta="Inflación mensual", valor="1,9", unidad="% mensual",
                      cambio={"signo": 1, "texto": "+0,2 pp", "ref": "ago-26"}, frescura='<div class="cf">x</div>',
                      href="precios/#inflacion-mensual", mini={"x": ["a", "b"], "y": [1, 2], "u": "%", "bar": True})]
        tr = [dict(slug="precios", titulo="Precios", n=4, titulares=["La inflación mensual sube a 1,9% en septiembre"])]
        ag = {"calendario": {"estado": "ok", "hoy": [], "semana": [{"dia": "jue 12/11", "hora": "16 h", "titulos": ["IPC de octubre"]}]},
              "atrasados": [{"texto": "Comercio exterior (ICA) · ago-26 · ⚠ atrasado"}], "graves": [{"texto": "a"}, {"texto": "b"}]}
        out = H.html(datos, tr, ag, "07/11/2026 18:40")
        self.assertIn('href="precios/#inflacion-mensual"', out)
        self.assertIn("IPC de octubre", out)
        self.assertIn("2 series sin datos nuevos", out)
        self.assertIn('href="calendario/#demorados"', out)
        self.assertIn("▲", out)
        self.assertNotIn("pedrothill31", out)
        self.assertIn("Calendario del INDEC no disponible hoy", H.html(datos, tr, None, "x"))

    def test_acerca(self):
        out = H.html_acerca("07/11/2026")
        self.assertIn("9 de julio de 2026", out)
        self.assertNotIn("pedrothill31", out)
        self.assertNotIn("[canal a definir]", out)


if __name__ == "__main__":
    unittest.main()

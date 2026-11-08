"""Bloque E3: cards compactas, minis, bajada del tema, páginas de serie y redirección de financiera.html.
Sin red."""
import unittest
from datetime import datetime

import pandas as pd

import dashboard as D
import frescura as F
import pagina_home as H


def _hist(nombre, n=40, freq="ME", valores=None, inicio="2023-01-31"):
    f = pd.date_range(inicio, periods=n, freq=freq)
    return pd.DataFrame({"indicador": nombre, "fecha": f, "valor": valores if valores is not None else range(n)})


class TestMinis(unittest.TestCase):
    def test_simple_mensual_24(self):
        m = D._mini_card({"nombre": "x", "unidad": "%", "barras": True}, None, _hist("x"))
        self.assertEqual(len(m["x"]), 24)
        self.assertTrue(m["ds"][0]["bar"])
        self.assertEqual(m["ds"][0]["rol"], 0)

    def test_trimestral_8(self):
        m = D._mini_card({"nombre": "q", "unidad": "%"}, None, _hist("q", 20, "QE"))
        self.assertEqual(len(m["x"]), 8)
        self.assertTrue(m["x"][-1].endswith("T-27"))

    def test_overlay_protagonista_la_ultima(self):
        h = pd.concat([_hist("a"), _hist("b")])
        m = D._mini_card({"nombre": "o", "vista": "overlay", "series": ["a", "b"], "unidad": "u"}, None, h)
        self.assertEqual([d["label"] for d in m["ds"]], ["a", "b"])
        self.assertEqual([d["rol"] for d in m["ds"]], [1, 0])

    def test_combo_rezago_es_texto(self):
        m = D._mini_card({"nombre": "c", "vista": "combo_rezago"}, None, _hist("c"))
        self.assertEqual(m, {"texto": D.TEXTO_MINI_COMPLETO})

    def test_espejo_impo_negativa_sin_arena(self):
        h = pd.concat([_hist("e"), _hist("i"), _hist("s")])
        m = D._mini_card({"nombre": "x", "vista": "comercio_espejo", "series": ["e", "i", "s"]}, None, h)
        self.assertLessEqual(max(v for v in m["ds"][1]["y"] if v is not None), 0)
        self.assertFalse(m["ds"][1]["signo"])
        self.assertEqual(m["ds"][2]["rol"], 0)

    def test_combo_usa_la_serie_resumen(self):
        h = pd.concat([_hist("izq"), _hist("der")])
        m = D._mini_card({"nombre": "c", "vista": "combo_2lineas", "linea_izq": "izq", "linea_der": "der"}, None, h)
        self.assertEqual([d["label"] for d in m["ds"]], ["izq"])

    def test_extra_ddf(self):
        m = D._mini_extra({"kind": "bar", "x": ["nov", "dic"], "y": [1, 2], "unidad": "$"})
        self.assertTrue(m["categorias"])


class TestCardCompacta(unittest.TestCase):
    CARD = dict(i=3, nombre="Inflación mensual (IPC)", slug="inflacion-mensual", titular="La inflación sube",
                valor="1,9", unidad="% mensual", cambio={"signo": 1, "texto": "+0,2 pp", "ref": "ago-26"},
                frescura='<div class="cf">sep-26</div>', nota_num=2, fuente_indec=True,
                mini={"x": ["a"], "u": "%", "ds": []})

    def test_toda_la_card_linkea_a_la_serie(self):
        h = D._card_compacta(self.CARD)
        self.assertTrue(h.startswith('<a class="cc" id="inflacion-mensual" href="../serie/inflacion-mensual/">'))
        self.assertEqual(h.count("<a "), 1)          # sin links anidados: el asterisco va como texto
        self.assertIn("Fuente: INDEC · *2", h)
        self.assertIn('data-mini="3"', h)
        self.assertIn("Ver serie →", h)

    def test_sin_mini(self):
        h = D._card_compacta(dict(self.CARD, mini={"texto": D.TEXTO_MINI_COMPLETO}))
        self.assertIn(D.TEXTO_MINI_COMPLETO, h)
        self.assertNotIn("<canvas", h)


class TestAviso(unittest.TestCase):
    def test_aviso_en_card_compacta_y_completa(self):
        c = dict(TestCardCompacta.CARD, aviso="Dato en revisión: posible cambio de escala")
        self.assertIn('<div class="aviso-card">Dato en revisión: posible cambio de escala</div>', D._card_compacta(c))
        self.assertIn('<div class="aviso-card">Dato en revisión', D._card_cell(dict(c, maxv="1", minv="0")))
        self.assertNotIn("aviso-card", D._card_compacta(TestCardCompacta.CARD))

    def test_merval_en_revision(self):
        import yaml
        from pathlib import Path
        cfg = yaml.safe_load((Path(__file__).resolve().parent.parent / "indicadores.yaml").read_text(encoding="utf-8"))
        m = next(i for i in cfg["indicadores_financiera"] if i["nombre"] == "S&P MERVAL")
        self.assertTrue(m["ocultar_variacion"])
        self.assertEqual(m["aviso"], "Dato en revisión: posible cambio de escala en la fuente desde el 19/10/2026")

    def test_completar_card_lleva_aviso_y_oculta_variacion(self):
        ind = {"nombre": "x", "unidad": "puntos", "ocultar_variacion": True, "aviso": "En revisión"}
        card = {"unidad": "puntos"}
        D._completar_card(card, ind, _hist("x", freq="D"), {"x": ind}, False, False, 2026)
        self.assertEqual(card["aviso"], "En revisión")
        self.assertIsNone(card["cambio"])


class TestBajada(unittest.TestCase):
    def test_bajada(self):
        ctx = F.Contexto(ahora=datetime(2026, 11, 7, 18), pub_de_indicador={"x": "ipc"})
        ok = F.Frescura("sep-26", "al_dia", "", "")
        grave = F.Frescura("may-26", "sin_calendario", "", "", grave="sin datos nuevos hace 5 meses")
        ctx.registro = {"X": ([("x", ok)], "x"), "Y": ([("y", grave)], "y")}
        prox = {"ipc": {"titulo": "IPC de octubre", "fecha": "2026-11-12", "dia": "jue 12/11", "hora": "16 h"}}
        b = D._bajada_tema([{"nombre": "X"}, {"nombre": "Y"}], ctx, prox)
        self.assertEqual(b, "2 series · 1 al día con el calendario del INDEC · 1 sin datos nuevos de la fuente "
                            "hace más de 3 meses · próxima publicación del INDEC: IPC de octubre, jue 12/11, 16 h")
        self.assertEqual(D._bajada_tema([{"nombre": "X"}], None, {}), "1 serie")


class TestRedireccion(unittest.TestCase):
    def test_financiera(self):
        h = H.html_redireccion("mercados/")
        self.assertIn('http-equiv="refresh" content="0; url=mercados/"', h)
        self.assertIn('location.replace("mercados/")', h)


if __name__ == "__main__":
    unittest.main()

"""Bloque de identidad visual (09/11/2026): contraste de la paleta, escala de 5A/Máx (D), firma (C1/C3). Sin red."""
import unittest
from pathlib import Path

import yaml

import dashboard as D
import pagina_home
import sitio
from tema import TEMA

RAIZ = Path(__file__).resolve().parent.parent


def _lum(h):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(int(h[i:i + 2], 16)) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class TestContraste(unittest.TestCase):
    def test_texto_aa_sobre_blanco(self):
        for k in ("principal_1", "principal_2", "texto", "texto_2", "texto_3", "atrasado"):
            self.assertGreaterEqual(contraste(TEMA[k], TEMA["fondo"]), 4.5, k)

    def test_principal_3_llega_a_3_para_graficos(self):
        self.assertGreaterEqual(contraste(TEMA["principal_3"], TEMA["fondo"]), 3.0)

    def test_etiqueta_de_principal_3_va_en_principal_2(self):
        s = (RAIZ / "dashboard.py").read_text(encoding="utf-8")
        self.assertIn("r === 2 ? TEMA.principal_2 : col", s)
        self.assertIn("etiqueta:{ u:s.unidad_der, arriba:13, color:TEMA.principal_2 }", s)


def _sj_linea(vals, kind="line"):
    return {"i": 0, "kind": kind, "full_y": vals, "full_x": ["a"] * len(vals), "full_dates": ["2020-01-01"] * len(vals)}


class TestEscalaLarga(unittest.TestCase):
    def test_nominal_en_pesos_positiva_va_en_log(self):
        self.assertEqual(D.escala_larga({"nominal_pesos": True}, _sj_linea([1.0, 10.0, None, 100.0])), "log")
        self.assertEqual(D.escala_larga({"escala_log_largo": True}, {
            "kind": "overlay", "datasets": [{"full_y": [1, 2]}, {"full_y": [3, None]}]}), "log")

    def test_con_negativos_sin_max(self):
        sj = {"kind": "overlay", "barras": True, "datasets": [{"full_y": [5, -3]}, {"full_y": [2, 1]}]}
        self.assertEqual(D.escala_larga({"nominal_pesos": True}, sj), "sin_max")
        self.assertEqual(D.escala_larga({"nominal_pesos": True}, _sj_linea([0, 4])), "sin_max")

    def test_sin_marca_o_ya_log_o_barras_no_cambia(self):
        self.assertIsNone(D.escala_larga({}, _sj_linea([1, 1000])))
        self.assertIsNone(D.escala_larga({"nominal_pesos": True, "escala_log": True}, _sj_linea([1, 1000])))
        self.assertIsNone(D.escala_larga({"nominal_pesos": True}, _sj_linea([1, 1000], kind="bar")))
        self.assertIsNone(D.escala_larga({"nominal_pesos": True}, _sj_linea([])))

    def _card(self, **kw):
        return dict(i=7, nombre="N", valor="1", unidad="$", grupo="g", slug="n", **kw)

    def test_card_log_lleva_rotulo_oculto_y_maximo(self):
        h = D._card_cell(self._card(escala_larga="log"))
        self.assertIn('<span class="escala-log" data-idx="7" hidden>escala logarítmica</span>', h)
        self.assertIn('data-rango="todo"', h)

    def test_card_sin_max(self):
        h = D._card_cell(self._card(escala_larga="sin_max"))
        self.assertNotIn('data-rango="todo"', h)
        self.assertIn('data-rango="5a"', h)
        self.assertNotIn("escala-log", h)

    def test_card_normal_igual_que_antes(self):
        h = D._card_cell(self._card())
        self.assertIn('data-rango="todo"', h)
        self.assertNotIn("escala-log", h)

    def test_js_cambia_la_escala_en_5a_y_max(self):
        s = (RAIZ / "dashboard.py").read_text(encoding="utf-8")
        self.assertIn("if (serie.escala_larga === 'log') {", s)
        self.assertIn("const log = rango === '5a' || rango === 'todo';", s)
        self.assertEqual(D.RANGOS_LOG, ("5a", "todo"))

    def test_yaml_marca_las_series_nominales(self):
        cfg = yaml.safe_load((RAIZ / "indicadores.yaml").read_text(encoding="utf-8"))
        marcadas = {i["nombre"] for i in cfg["indicadores"] + cfg["indicadores_financiera"]
                    if i.get("escala_log_largo") or i.get("nominal_pesos")}
        for n in ("Base monetaria", "Préstamos al sector privado", "PBI nominal (precios corrientes)",
                  "Resultado fiscal (primario y financiero)", "Dólar oficial", "Dólar blue", "Dólar MEP", "Dólar CCL",
                  "Agregados monetarios (M2, M3)", "Depósitos bancarios (privado vs. público)"):
            self.assertIn(n, marcadas)


class TestFirma(unittest.TestCase):
    def test_firma_en_la_cabecera(self):
        self.assertEqual(sitio.firma("../"), '<div class="firma">por <a href="../acerca/">Pedro Thill</a></div>')
        h = sitio.pagina("t", "Sitio", "sub", "", "", inicio="../")
        self.assertIn('<div class="firma">por <a href="../acerca/">Pedro Thill</a></div>', h)
        self.assertIn("__FIRMA__", (RAIZ / "dashboard.py").read_text(encoding="utf-8"))

    def test_acerca_con_autor_y_sin_fred(self):
        h = pagina_home.html_acerca("09/11/2026 10:00")
        self.assertIn('<div class="autor-n">Pedro Thill</div>', h)
        self.assertNotIn("FRED", h)
        self.assertIn("H.15", h)


if __name__ == "__main__":
    unittest.main()

"""Bloque E5: identidad A+B+C (serif + ciruela + sello). Sin red."""
import unittest
from pathlib import Path

import dashboard as D
import frescura as F
import sitio
from tema import TEMA

RAIZ = Path(__file__).resolve().parent.parent


class TestTema(unittest.TestCase):
    def test_rampa_principal(self):
        self.assertEqual([TEMA[f"principal_{i}"] for i in (1, 2, 3)] + [TEMA["principal_contexto"]],
                         ["#1F3A5F", "#4A6FA5", "#7696C2", "#DCE5F0"])
        self.assertFalse([k for k in TEMA if k.startswith("azul")])
        self.assertIn("serif", TEMA["fuente_titulares"])

    def test_sin_azul_viejo_en_el_codigo(self):
        for f in ("dashboard.py", "pagina_home.py", "pagina_calendario.py", "sitio.py", "mail_agenda.py", "enviar_mail.py"):
            s = (RAIZ / f).read_text(encoding="utf-8")
            for viejo in ("azul_1", "azul_2", "azul_3", "azul_contexto", "--azul-", "#1D4E89", "#3A7CA5", "#0B3C5D"):
                self.assertNotIn(viejo, s, f"{viejo} en {f}")

    def test_sin_hex_de_la_paleta_fuera_de_tema(self):
        # Bloque de identidad visual: ningún hex de la paleta (vieja ciruela ni actual) escrito a mano fuera de tema.py.
        hexes = {v.upper() for k, v in TEMA.items() if isinstance(v, str) and v.startswith("#")} - {"#FFFFFF", "#111111"}
        hexes |= {"#46245A", "#85559B", "#C2A3D1", "#E3D5EA", "#9DB4D3", "#7A8C9A"}
        for f in ("dashboard.py", "pagina_home.py", "pagina_calendario.py", "sitio.py", "mail_agenda.py", "enviar_mail.py",
                  "frescura.py", "run.py", "temas.py", "agenda.py"):
            s = (RAIZ / f).read_text(encoding="utf-8").upper()
            for h in hexes:
                self.assertNotIn(h, s, f"{h} en {f}")

    def test_nombres_de_color_desde_tema(self):
        from tema import NOMBRE_COLOR
        self.assertEqual(set(NOMBRE_COLOR), {"principal", "negativo"})
        for f in ("dashboard.py", "pagina_home.py"):
            s = (RAIZ / f).read_text(encoding="utf-8")
            self.assertNotIn("en arena", s, f)
            self.assertNotIn("Ciruela:", s, f)

    def test_anclas_no_quedan_bajo_la_barra(self):
        self.assertIn("[id] { scroll-margin-top:", sitio.CSS_IDENTIDAD)

    def test_variables_css(self):
        css = sitio.css_variables()
        self.assertIn("--principal-1: #1F3A5F;", css)
        self.assertIn("--fuente-titulares:", css)


class TestSello(unittest.TestCase):
    def test_al_dia(self):
        f = F.Frescura("sep-26", "al_dia", "próximo 12/11, 16 h", "t")
        h = F.html_sello(f)
        self.assertIn('class="sello sello-ok"', h)
        self.assertIn('<span class="se-per">sep-26</span>', h)
        self.assertIn("✓ al día", h)
        self.assertIn("próximo 12/11, 16 h", h)

    def test_atrasado_grave_y_sin_calendario(self):
        self.assertIn("sello-atr", F.html_sello(F.Frescura("ago-26", "atrasado", "sep-26 se publicó el 19/10", "t")))
        g = F.html_sello(F.Frescura("may-26", "sin_calendario", "próximo: sin calendario oficial", "t",
                                    grave="sin datos nuevos hace 5 meses"))
        self.assertIn("sello-grave", g)
        self.assertIn("⏸ sin datos nuevos<", g)            # los meses quedan en la franja de la card
        self.assertIn("sin calendario oficial", g)
        n = F.html_sello(F.Frescura("06/11", "diaria", "próximo 11/11 (estimado)", "t"))
        self.assertIn("sello-neutro", n)
        self.assertNotIn("se-est", n)
        self.assertEqual(F.html_sello(None), "")

    def test_card_compacta_con_sello(self):
        c = dict(i=0, nombre="N", titular="T", valor="1", unidad="%", slug="n", frescura='<div class="cf">x</div>',
                 sello='<span class="sello sello-ok">s</span>')
        h = D._card_compacta(c)
        self.assertIn('class="cc con-sello"', h)
        self.assertIn('<div class="cc-cab"><div class="cc-tx">', h)
        self.assertNotIn("con-sello", D._card_compacta(dict(c, sello="")))


class TestTile(unittest.TestCase):
    def test_tile(self):
        self.assertEqual(sitio.tile("jue", 12, "nov"),
                         '<span class="tile"><span class="tile-d">jue</span><span class="tile-n">12</span>'
                         '<span class="tile-m">nov</span></span>')

    def test_franja_home(self):
        import pagina_home as H
        self.assertIn('<span class="tile-n">12</span>', H._tile_dia("jue 12/11"))
        self.assertIn('<span class="tile-m">nov</span>', H._tile_dia("jue 12/11"))
        self.assertEqual(H._tile_dia("raro"), "<span>raro</span>")


if __name__ == "__main__":
    unittest.main()

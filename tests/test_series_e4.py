"""Bloque E4: url de cada publicación (agenda -> mail), páginas de serie (próximo dato, últimos datos,
contexto) y EMAE con página propia. Sin red."""
import unittest
from datetime import datetime

import pandas as pd

import agenda as A
import dashboard as D
import frescura as F
import mail_agenda as M


def _ctx(registro=None, pubs=None):
    c = F.Contexto(ahora=datetime(2026, 11, 7, 18), pub_de_indicador=pubs or {})
    c.registro = registro or {}
    return c


class TestUrlSerie(unittest.TestCase):
    def test_card_con_la_serie_como_principal(self):
        reg = {"Comercio exterior (expo/impo espejo)": ([("Saldo comercial", None), ("Exportaciones totales", None)], "Saldo comercial"),
               "Saldo comercial": ([("Saldo comercial", None)], "Saldo comercial")}
        self.assertEqual(A.url_serie("Saldo comercial", _ctx(reg), {}), "serie/saldo-comercial/")

    def test_primera_card_que_la_dibuja(self):
        reg = {"Salario real y capacidad de compra": ([("Salario real (deflactado por IPC)", None)], "Salario real (deflactado por IPC)")}
        self.assertEqual(A.url_serie("Salario real (deflactado por IPC)", _ctx(reg), {}),
                         "serie/salario-real-y-capacidad-de-compra/")

    def test_sin_card_con_pagina_serie(self):
        ind = {"EMAE (actividad económica)": {"pagina_serie": "actividad"}}
        self.assertEqual(A.url_serie("EMAE (actividad económica)", _ctx(), ind), "serie/emae/")

    def test_sin_card_ni_pagina(self):
        self.assertIsNone(A.url_serie("X", _ctx(), {}))

    def test_slug_congelado(self):
        reg = {"Tasa de desempleo": ([("Tasa de desempleo", None)], "Tasa de desempleo")}
        ind = {"Tasa de desempleo": {"slug": "desempleo"}}
        self.assertEqual(A.url_serie("Tasa de desempleo", _ctx(reg), ind), "serie/desempleo/")


class TestMailLinks(unittest.TestCase):
    P = {"fuente": "INDEC", "publicado": None, "apertura": {"titular": "T", "detalle": None, "filas": []}}

    def test_dato_nuevo_va_a_la_serie(self):
        h = M._bloque_dato_nuevo(dict(self.P, url="serie/inflacion-mensual/", ancla="precios"), "https://x/")
        self.assertIn('href="https://x/serie/inflacion-mensual/"', h)

    def test_sin_url_cae_al_ancla(self):
        h = M._bloque_dato_nuevo(dict(self.P, ancla="precios"), "https://x/")
        self.assertIn('href="https://x/#precios"', h)

    def test_sin_url_ni_ancla_sin_link(self):
        self.assertNotIn("ver gráfico", M._bloque_dato_nuevo(dict(self.P), "https://x/"))


class TestPaginaSerie(unittest.TestCase):
    def test_proximo_dato(self):
        c = _ctx(pubs={"ipc": "ipc"})
        prox = {"ipc": {"titulo": "IPC de octubre", "fecha": "2026-11-12", "dia": "jue 12/11", "hora": "16 h"}}
        h = D._proximo_dato(None, "ipc", c, prox)
        self.assertIn("<b>IPC de octubre</b> · jue 12/11, 16 h · según el calendario oficial del INDEC", h)
        self.assertIn("todavía sin fecha", D._proximo_dato(None, "ipc", c, {}))
        sin = F.Frescura("ago-26", "sin_calendario", "", "")
        self.assertIn("sin calendario oficial", D._proximo_dato(sin, "x", c, {}))
        self.assertEqual(D._proximo_dato(sin, "x", None, {}), "")

    def test_ultimos_13(self):
        f = pd.date_range("2024-01-31", periods=20, freq="ME")
        h = pd.DataFrame({"indicador": "x", "fecha": f, "valor": [float(v) for v in range(20)]})
        t = D._tabla_ultimos({"nombre": "x", "unidad": "%"}, h, {})
        self.assertIn("Últimos 13 datos", t)
        self.assertEqual(t.count('<td class="sec">'), 13)
        self.assertLess(t.index("ago-25"), t.index("jul-25"))    # el más reciente primero

    def test_ultimos_sin_columna_de_otra_frecuencia(self):
        d = pd.bdate_range("2026-01-01", periods=60)
        m = pd.date_range("2025-01-31", periods=12, freq="ME")
        h = pd.concat([pd.DataFrame({"indicador": "res", "fecha": d, "valor": 1.0}),
                       pd.DataFrame({"indicador": "comp", "fecha": m, "valor": 2.0})])
        ind = {"nombre": "combo", "vista": "balance_cambiario", "series": ["comp", "res"], "unidad": "x"}
        t = D._tabla_ultimos(ind, h, {})
        self.assertNotIn("s/d", t)
        self.assertNotIn("<th>comp</th>", t)

    def test_fuentes_de_vista_con_fuente_propia(self):
        res = {"nombre": "R", "vista": "reservas_combo", "fuente": "bcra"}
        combo = {"nombre": "C", "vista": "balance_cambiario", "series": ["R"]}
        self.assertEqual(D.fuentes_de_pagina([combo, res]), "BCRA")
        self.assertEqual(D.fuentes_de_pagina([combo]), "")

    def test_cabeza_serie(self):
        c = dict(nombre="EMAE (actividad económica)", titular="El EMAE baja", valor="147,8", unidad="índice",
                 cambio={"signo": -1, "texto": "−1,7%", "ref": "ago-25"}, frescura='<div class="cf">ago-26</div>')
        h = D._cabeza_serie(c, {"descripcion": "Actividad mensual"}, None, "x", None, {})
        self.assertIn('<h2 class="s-tit">El EMAE baja</h2>', h)
        self.assertIn("Actividad mensual", h)
        self.assertIn("▼", h)

    def test_card_cell_solo_grafico(self):
        c = dict(i=0, nombre="N", titular="Tit", valor="1", unidad="%", frescura='<div class="cf">x</div>', maxv="1", minv="0")
        h = D._card_cell(c, solo_grafico=True)
        self.assertNotIn("Tit", h)
        self.assertNotIn('class="cf"', h)
        self.assertIn('<canvas id="ch0">', h)


if __name__ == "__main__":
    unittest.main()

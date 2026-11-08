"""RIPTE desde la Secretaría de Trabajo (fuentes_trabajo.py): parseo de la página y del PDF, controles, escalón
PDF -> tabla -> error, caché y alertas. Sin red: fixtures recortados de la publicación de ago-2026 (página
bajada el 08/11/2026 y texto que extrae pdfplumber de ripte_agosto_2026-mdch.pdf)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fuentes_trabajo as ft   # noqa: E402
import fetchers                # noqa: E402
import dashboard               # noqa: E402
import storage                 # noqa: E402
import run                     # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
HTML = (FIX / "ripte_pagina_ago2026.html").read_text(encoding="utf-8")
PDF = (FIX / "ripte_pdf_ago2026.txt").read_text(encoding="utf-8")
URL_PDF = "https://www.argentina.gob.ar/sites/default/files/ripte_agosto_2026-mdch.pdf"


def sin_linea(texto, empieza):
    lineas = texto.splitlines()
    i = next(k for k, l in enumerate(lineas) if l.startswith(empieza))
    return "\n".join(lineas[:i] + lineas[i + 1:])


def pdf_ok(_url):
    return PDF


def pdf_no_llamar(_url):
    raise AssertionError("no tenía que bajar el PDF")


class Parseo(unittest.TestCase):
    def test_pdf_completo(self):
        df, info = ft.resolver(HTML, None, pdf_ok)
        self.assertEqual(info["fuente"], "pdf")
        self.assertEqual(len(df), 386)
        self.assertEqual((df["fecha"].iloc[0], df["valor"].iloc[0]), (pd.Timestamp("1994-07-01"), 874.87))
        self.assertEqual((df["fecha"].iloc[-1], df["valor"].iloc[-1]), (pd.Timestamp("2026-08-01"), 1982518.19))
        # jun-2026 es distinto de ago-2026 (el CSV de datos.gob.ar repetía junio en agosto)
        self.assertEqual(df.set_index("fecha").loc["2026-06-01", "valor"], 1915878.76)
        self.assertEqual(info["cache_nuevo"]["pdf_url"], URL_PDF)
        self.assertEqual(info["cache_nuevo"]["mes"], "2026-08-01")

    def test_variacion_con_espacio(self):
        """'- 2,3%' (jul-2000) se lee como −2,3."""
        crudo, _ = ft.parsear_pdf(PDF)
        self.assertEqual(crudo.set_index("fecha").loc["2000-07-01", "var"], -2.3)

    def test_nov_2017_valor_de_la_secretaria(self):
        df, _ = ft.resolver(HTML, None, pdf_ok)
        self.assertEqual(df.set_index("fecha").loc["2017-11-01", "valor"], 26177.33)

    def test_link_con_prefijo_blank_y_variantes(self):
        self.assertIn('href="blank:#/sites/', HTML)
        self.assertEqual(ft.parsear_pagina(HTML)["pdf_url"], URL_PDF)
        for nombre in ("ripte_mayo2025-mdch.pdf", "ripte_octubre_2024.pdf", "ripte_noviembre_2023-mdch_0.pdf"):
            h = HTML.replace("ripte_agosto_2026-mdch.pdf", nombre)
            self.assertEqual(ft.parsear_pagina(h)["pdf_url"], f"https://www.argentina.gob.ar/sites/default/files/{nombre}")

    def test_dos_links_es_error(self):
        h = HTML.replace("</table>", '</table><a href="/sites/default/files/ripte_julio_2026-mdch.pdf">x</a>')
        self.assertIn("error_pdf_url", ft.parsear_pagina(h))

    def test_tabla_meses_con_y_sin_barra(self):
        self.assertIn("Agosto2026", HTML)
        self.assertIn("Abril/2026", HTML)
        tabla = ft.parsear_pagina(HTML)["tabla"]
        self.assertEqual(len(tabla), 20)
        self.assertEqual(list(tabla["fecha"]), list(pd.date_range("2025-01-01", "2026-08-01", freq="MS")))
        self.assertEqual(tabla["valor"].iloc[-1], 1982518.19)


class ControlesPdf(unittest.TestCase):
    def _validar(self, texto, html=HTML):
        pag = ft.parsear_pagina(html)
        crudo, titulo = ft.parsear_pdf(texto)
        return ft.validar_pdf(crudo, titulo, pag["mes"], pag["destacado"], ft.validar_tabla(pag["tabla"], pag["mes"]))

    def test_fila_borrada_falla(self):
        with self.assertRaisesRegex(ft.RipteFormatoError, "no son consecutivos|variación"):
            self._validar(sin_linea(PDF, "Marzo $ 1.363.510,33"))

    def test_fila_borrada_en_el_medio_de_un_anio_falla(self):
        with self.assertRaises(ft.RipteFormatoError):
            self._validar(sin_linea(PDF, "Julio $ 882,35"))

    def test_indice_que_no_cierra_falla(self):
        with self.assertRaisesRegex(ft.RipteFormatoError, "índice"):
            self._validar(PDF.replace("Julio $ 1.946.028,12 1,6% 222.436,26", "Julio $ 1.946.028,12 1,6% 222.436,96"))

    def test_monto_ilegible_falla(self):
        with self.assertRaisesRegex(ft.RipteFormatoError, "no se pudo leer"):
            ft.parsear_pdf(PDF.replace("Julio $ 1.946.028,12 1,6%", "Julio $ 1.946.028,12 1,6 %"))

    def test_monto_distinto_de_la_tabla_falla(self):
        # un centavo distinto en la tabla de la página (sus variaciones siguen cerrando): el cruce lo detecta
        h = HTML.replace("$1.775.664,12", "$1.775.664,13")
        with self.assertRaisesRegex(ft.RipteFormatoError, "2026-03 no coincide con la tabla"):
            self._validar(PDF, h)


class Escalon(unittest.TestCase):
    def test_pdf_falla_y_la_tabla_pasa(self):
        """El PDF no pasa un control -> se usan las 20 filas de la tabla, con motivo (para la alerta)."""
        df, info = ft.resolver(HTML, None, lambda u: sin_linea(PDF, "Marzo $ 1.363.510,33"))
        self.assertEqual(info["fuente"], "tabla")
        self.assertEqual(len(df), 20)
        self.assertEqual(df["fecha"].iloc[-1], pd.Timestamp("2026-08-01"))
        self.assertIn("PDF", info["motivo"])
        self.assertIsNone(info["cache_nuevo"])

    def test_descarga_del_pdf_falla_y_la_tabla_pasa(self):
        def falla(_):
            raise RuntimeError("HTTP 500")
        df, info = ft.resolver(HTML, None, falla)
        self.assertEqual((info["fuente"], len(df)), ("tabla", 20))
        self.assertIn("no se pudo bajar el PDF", info["motivo"])

    def test_pagina_sin_link_usa_la_tabla(self):
        h = HTML.replace("ripte_agosto_2026-mdch.pdf", "otra_cosa.docx")
        df, info = ft.resolver(h, None, pdf_no_llamar)
        self.assertEqual((info["fuente"], len(df)), ("tabla", 20))

    def test_fallan_los_dos(self):
        """Último mes distinto del encabezado: no pasa ni el PDF ni la tabla -> RipteError (nunca vacío)."""
        h = HTML.replace("Publicación Agosto 2026", "Publicación Septiembre 2026")
        with self.assertRaisesRegex(ft.RipteError, "PDF.*tabla"):
            ft.resolver(h, None, pdf_ok)

    def test_tabla_con_variacion_que_no_cierra(self):
        h = HTML.replace(">5,3%<", ">5,9%<")
        with self.assertRaisesRegex(ft.RipteError, "tabla.*variación"):
            ft.resolver(h, None, lambda u: sin_linea(PDF, "Marzo $ 1.363.510,33"))

    def test_sin_encabezado_fallan_los_dos(self):
        with self.assertRaises(ft.RipteError):
            ft.resolver(HTML.replace("Publicación Agosto 2026", "Novedades"), None, pdf_ok)


class Cache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.p = [mock.patch.object(ft, "CACHE_CSV", d / "c.csv"), mock.patch.object(ft, "CACHE_META", d / "m.json")]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.tmp.cleanup()

    def _correr(self, html, pdf):
        """ft.serie() con la red simulada: la página y el PDF (texto o excepción)."""
        def get(url, *a, **k):
            if url == ft.URL_PAGINA:
                return mock.Mock(content=html.encode("utf-8"))
            if isinstance(pdf, Exception):
                raise pdf
            return mock.Mock(content=b"%PDF")
        with mock.patch.object(fetchers, "_get", side_effect=get) as g, \
                mock.patch.object(ft, "texto_pdf", side_effect=lambda b: pdf):
            df = ft.serie()
        return df, [c.args[0] for c in g.call_args_list]

    def test_sin_cambio_de_link_ni_mes_no_baja_el_pdf(self):
        df1, urls1 = self._correr(HTML, PDF)
        self.assertEqual(urls1, [ft.URL_PAGINA, URL_PDF])
        self.assertEqual(ft.ULTIMA["fuente"], "pdf")
        df2, urls2 = self._correr(HTML, PDF)
        self.assertEqual(urls2, [ft.URL_PAGINA])            # sólo la página
        self.assertEqual(ft.ULTIMA["fuente"], "pdf_cache")
        pd.testing.assert_frame_equal(df1, df2)

    def test_link_nuevo_baja_el_pdf(self):
        self._correr(HTML, PDF)
        h = HTML.replace("ripte_agosto_2026-mdch.pdf", "ripte_agosto_2026-mdch_0.pdf")
        _, urls = self._correr(h, PDF)
        self.assertEqual(len(urls), 2)

    def test_descarga_fallida_no_pisa_el_cache(self):
        self._correr(HTML, PDF)
        antes = (ft.CACHE_CSV.read_bytes(), ft.cargar_meta()["cache"])
        h = HTML.replace("ripte_agosto_2026-mdch.pdf", "ripte_agosto_2026-mdch_0.pdf")
        df, _ = self._correr(h, RuntimeError("timeout"))
        self.assertEqual((ft.ULTIMA["fuente"], len(df)), ("tabla", 20))
        self.assertEqual((ft.CACHE_CSV.read_bytes(), ft.cargar_meta()["cache"]), antes)

    def test_pdf_invalido_no_pisa_el_cache(self):
        self._correr(HTML, PDF)
        antes = ft.CACHE_CSV.read_bytes()
        h = HTML.replace("ripte_agosto_2026-mdch.pdf", "ripte_agosto_2026-mdch_0.pdf")
        self._correr(h, sin_linea(PDF, "Marzo $ 1.363.510,33"))
        self.assertEqual(ft.CACHE_CSV.read_bytes(), antes)

    def test_pagina_caida_es_error(self):
        def get(url, *a, **k):
            raise RuntimeError("Falló la consulta")
        with mock.patch.object(fetchers, "_get", side_effect=get):
            with self.assertRaises(ft.RipteError):
                ft.serie()
        self.assertEqual(ft.ULTIMA["fuente"], "error")


class Estado(unittest.TestCase):
    def test_racha_y_avisos(self):
        est = {}
        self.assertEqual(ft.actualizar_estado(est, {"fuente": "pdf", "motivo": None}, "2026-11-08"), [])
        self.assertEqual(est["racha"], 0)
        tabla = {"fuente": "tabla", "motivo": "el PDF no pasó los controles (x)"}
        items = ft.actualizar_estado(est, tabla, "2026-11-09")
        self.assertEqual([c for c, _ in items], ["ripte:tabla"])
        est["avisos"]["ripte:tabla"] = "2026-11-09"          # lo marca cerrar_corrida si el mail salió
        self.assertEqual(ft.actualizar_estado(est, tabla, "2026-11-10"), [])
        self.assertEqual(est["racha"], 2)
        self.assertEqual(len(ft.actualizar_estado(est, tabla, "2026-11-16")), 1)   # semanal
        err = {"fuente": "error", "motivo": "fallaron el PDF y la tabla"}
        self.assertIn("intacto", ft.actualizar_estado(est, err, "2026-11-17")[0][1])
        ft.actualizar_estado(est, {"fuente": "pdf_cache", "motivo": None}, "2026-11-18")
        self.assertEqual(est["racha"], 0)

    def test_sin_corrida_no_cambia(self):
        est = {"racha": 3}
        self.assertEqual(ft.actualizar_estado(est, None, "2026-11-08"), [])
        self.assertEqual(est, {"racha": 3})


class Integracion(unittest.TestCase):
    def test_ratio_con_numerador_de_trabajo_llega_hasta_agosto(self):
        ripte, _ = ft.resolver(HTML, None, pdf_ok)
        cbt = pd.DataFrame({"fecha": pd.date_range("2016-04-01", "2026-09-01", freq="MS")})
        cbt["valor"] = 500000.0
        ind = {"calculo": "ratio", "numerador": {"fuente": "trabajo_ripte"}, "denominador_id": "150.1_CSTA_BATAL_0_D_20"}
        with mock.patch.object(run, "traer", return_value=ripte) as tr, mock.patch.object(run, "_dg", return_value=cbt):
            s = run._calcular(ind, None)
        tr.assert_called_once_with({"fuente": "trabajo_ripte"}, None)
        self.assertEqual(s["fecha"].min(), pd.Timestamp("2016-04-01"))
        self.assertEqual(s["fecha"].max(), pd.Timestamp("2026-08-01"))
        self.assertAlmostEqual(s["valor"].iloc[-1], 1982518.19 / 500000)

    def test_traer_despacha_a_fuentes_trabajo(self):
        with mock.patch.object(ft, "serie", return_value="ok") as s:
            self.assertEqual(fetchers.traer({"fuente": "trabajo_ripte"}, "2004-01-01"), "ok")
        s.assert_called_once_with("2004-01-01")

    def test_fuente_en_la_nota(self):
        ind = {"nombre": "x", "calculo": "ratio", "numerador": {"fuente": "trabajo_ripte"},
               "denominador_id": "150.1_CSTA_BATAL_0_D_20"}
        self.assertIn("Secretaría de Trabajo", dashboard._fuentes_de_indicador(ind, {}))

    def test_yaml_sin_datos_gob_para_el_ripte(self):
        import yaml
        cfg = yaml.safe_load((Path(run.__file__).parent / "indicadores.yaml").read_text(encoding="utf-8"))
        self.assertNotIn("158.1_REPTE_0_0_5", cfg.get("fallback_csv_excluir") or [])
        ind = next(i for i in cfg["indicadores"] if i["nombre"] == "RIPTE medido en canastas básicas (CBT, GBA)")
        self.assertEqual(ind["numerador"], {"fuente": "trabajo_ripte"})
        self.assertNotIn("numerador_id", ind)
        combo = next(i for i in cfg["indicadores"] if i["nombre"] == "Salario real y capacidad de compra")
        self.assertEqual(combo["linea_der"], ind["nombre"])

    def test_si_fallan_los_dos_el_historico_queda(self):
        """Sin filas nuevas del indicador (RipteError -> `problemas`), el merge conserva lo guardado."""
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(storage, "DATA_DIR", Path(d)), \
                mock.patch.object(storage, "LARGO", Path(d) / "l.csv"), \
                mock.patch.object(storage, "ANCHO", Path(d) / "a.csv"):
            viejo = pd.DataFrame({"fecha": pd.to_datetime(["2026-06-01", "2026-07-01"]), "indicador": "R",
                                  "bloque": "social", "unidad": "canastas", "valor": [3.86, 3.84]})
            storage.actualizar(viejo)
            otro = pd.DataFrame({"fecha": pd.to_datetime(["2026-07-01"]), "indicador": "Otro",
                                 "bloque": "social", "unidad": "x", "valor": [1.0]})
            h = storage.actualizar(otro)
            self.assertEqual(list(h[h["indicador"] == "R"]["valor"]), [3.86, 3.84])


if __name__ == "__main__":
    unittest.main()

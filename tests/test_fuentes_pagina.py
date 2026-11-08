"""Encabezado 'fuentes: ...' de cada página (dashboard.fuentes_de_pagina). Sin red."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dashboard as D  # noqa: E402

API = {"clave": "148.3_INIVELNAL_DICI_M_26", "fuente": "indec_api", "tabla": "ipc_nacional"}
FB = {**API, "fuente": "datos_gob_ar"}


class TestFuentesDePagina(unittest.TestCase):

    def test_financiera_sin_indec(self):
        # referencias a la macro (dólar vía ArgentinaDatos, TAMAR vía BCRA) + fuentes propias
        macro = [{"nombre": "Dólar oficial", "fuente": "dolar", "casa": "oficial"},
                 {"nombre": "TAMAR", "fuente": "bcra", "id_variable": 135}]
        fin = [{"nombre": "Dólar oficial", "solo_referencia": True},
               {"nombre": "TAMAR", "solo_referencia": True},
               {"nombre": "S&P MERVAL", "fuente": "byma", "symbol": "M"},
               {"nombre": "Spread", "calculo": "spread_bono_ust", "ticker_bono": "GD30", "ust_plazo": "10 Yr"},
               {"nombre": "Combo", "vista": "overlay", "series": ["TAMAR"]}]
        txt = D.fuentes_de_pagina(fin, {}, macro + fin, extra=["MAE", "data912"])
        self.assertEqual(txt, "ArgentinaDatos · BCRA · BYMA · MAE · Tesoro de EE.UU. · data912")
        self.assertNotIn("INDEC", txt)

    def test_indec_api_vs_fallback(self):
        ind = [{"nombre": "Salario real", "calculo": "real", "nominal_id": "149.1_X",
                "deflactor_id": "148.3_INIVELNAL_DICI_M_26"}]
        usos_nominal = {"clave": "149.1_X", "fuente": "indec_api", "tabla": "indice_salarios"}
        self.assertEqual(D.fuentes_de_pagina(ind, {"Salario real": [usos_nominal, API]}), "API del INDEC")
        self.assertEqual(D.fuentes_de_pagina(ind, {"Salario real": [usos_nominal, FB]}),
                         "API del INDEC · apis.datos.gob.ar")
        # sin registro de uso, los ids van a datos.gob.ar (no hay equivalencia conocida)
        self.assertEqual(D.fuentes_de_pagina(ind, {}), "apis.datos.gob.ar")

    def test_variacion_publicada_y_primaria_argentinadatos(self):
        ind = [{"nombre": "Inflación interanual (IPC)", "calculo": "interanual",
                "base_id": "148.3_INIVELNAL_DICI_M_26", "fuente_primaria": "indec_api"},
               {"nombre": "Inflación mensual (IPC)", "fuente_primaria": "indec_api",
                "fuente_fallback": "argentinadatos"}]
        usos = {"Inflación interanual (IPC)": [{**API, "clave": "148.3_INIVELNAL_DICI_M_26:interanual"}],
                "Inflación mensual (IPC)": [{"clave": "Inflación mensual (IPC)", "fuente": "argentinadatos",
                                             "tabla": "ipc_nacional"}]}
        self.assertEqual(D.fuentes_de_pagina(ind, usos), "API del INDEC · ArgentinaDatos")
        self.assertEqual(D.fuentes_de_pagina(ind, {}), "API del INDEC · apis.datos.gob.ar")


class TestEncabezadoEnHtml(unittest.TestCase):
    """generar() escribe el encabezado recibido (y el default si no recibe ninguno)."""

    def _generar(self, **kw):
        import tempfile
        import pandas as pd
        hist = pd.DataFrame({"fecha": pd.date_range("2025-01-01", periods=14, freq="MS"),
                             "indicador": "Tasa X", "bloque": "monetario_financiero",
                             "unidad": "% TNA", "valor": range(14)})
        cfg = [{"nombre": "Tasa X", "bloque": "monetario_financiero", "grupo": "Tasas",
                "fuente": "bcra", "id_variable": 1, "unidad": "% TNA", "neutral": True}]
        with tempfile.TemporaryDirectory() as tmp:
            out_original, D.OUT = D.OUT, Path(tmp)
            try:
                D.generar(hist, cfg, archivo_salida="p.html", **kw)
                return (Path(tmp) / "p.html").read_text(encoding="utf-8")
            finally:
                D.OUT = out_original

    def test_encabezado(self):
        self.assertIn("fuentes: BCRA</div>", self._generar(fuentes_pagina="BCRA"))
        self.assertIn(f"fuentes: {D.FUENTES_HEADER_DEFAULT}</div>", self._generar())


if __name__ == "__main__":
    unittest.main()

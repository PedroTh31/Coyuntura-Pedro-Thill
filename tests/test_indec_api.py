"""
Tests sin red del fetcher de la API del INDEC (fetchers.fetch_indec_tabla / fetch_indec_api).

Correr con:  python -m unittest discover tests
Todas las respuestas HTTP son simuladas: no se usa el token real ni se sale a internet.
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fetchers  # noqa: E402

TOKEN_FALSO = "eyJ.token-de-prueba.firma"
TABLA = "estimador-mensual-de-actividad-economica-nivel-general"


class Resp:
    """Respuesta HTTP mínima (lo que usa el fetcher de requests.Response)."""

    def __init__(self, status=200, filas=None, content_range=None, json_err=None):
        self.status_code = status
        self._filas = filas if filas is not None else []
        self.headers = {"Content-Range": content_range} if content_range else {}
        self._json_err = json_err
        self.text = ""

    def json(self):
        if self._json_err is not None:
            return self._json_err
        return self._filas


def filas_mensuales(n, desde=(2020, 1)):
    anio, mes = desde
    out = []
    for i in range(n):
        out.append({"periodo": f"{anio:04d}{mes:02d}", "valor": float(i)})
        mes += 1
        if mes == 13:
            anio, mes = anio + 1, 1
    return out


def paginador(todas, total=None):
    """Simula a la API: corta de a 1000 filas según el offset pedido."""
    total = len(todas) if total is None else total
    llamadas = []

    def _get(url, params=None, headers=None, timeout=None):
        llamadas.append(dict(params))
        off = params["offset"]
        lote = todas[off:off + fetchers.INDEC_PAGINA]
        fin = off + len(lote) - 1
        return Resp(206 if len(lote) < total else 200, lote, f"{off}-{fin}/{total}")
    return _get, llamadas


@mock.patch.dict(os.environ, {"INDEC_API_TOKEN": TOKEN_FALSO})
@mock.patch.object(fetchers.time, "sleep", lambda s: None)
class TestIndecApi(unittest.TestCase):

    def test_paginacion_por_offset_hasta_el_total(self):
        todas = filas_mensuales(2500)
        get, llamadas = paginador(todas)
        with mock.patch.object(fetchers.requests, "get", side_effect=get):
            filas = fetchers.fetch_indec_tabla(TABLA)
        self.assertEqual(len(filas), 2500)
        self.assertEqual([c["offset"] for c in llamadas], [0, 1000, 2000])
        # siempre ordenado por la clave completa del spec y con limit = tope de la API
        clave = fetchers._indec_clave(TABLA)
        self.assertTrue(all(c["order"] == clave and c["limit"] == 1000 for c in llamadas))

    def test_filtros_se_envian_como_eq_salvo_operador_explicito(self):
        get, llamadas = paginador(filas_mensuales(3))
        with mock.patch.object(fetchers.requests, "get", side_effect=get):
            fetchers.fetch_indec_tabla(TABLA, {"tipo_de_indicador_descripcion": "Índice serie original",
                                               "periodo": "gte.202001"})
        self.assertEqual(llamadas[0]["tipo_de_indicador_descripcion"], "eq.Índice serie original")
        self.assertEqual(llamadas[0]["periodo"], "gte.202001")

    def test_filas_distintas_del_total_es_error(self):
        # la API informa 1500 pero sólo hay 1200 filas: la segunda página vuelve corta y vacía
        get, _ = paginador(filas_mensuales(1200), total=1500)
        with mock.patch.object(fetchers.requests, "get", side_effect=get):
            with self.assertRaises(fetchers.IndecIncompletoError):
                fetchers.fetch_indec_tabla(TABLA)

    def test_429_se_reintenta_y_despues_sigue(self):
        ok = Resp(200, filas_mensuales(2), "0-1/2")
        respuestas = [Resp(429), Resp(503), ok]
        with mock.patch.object(fetchers.requests, "get", side_effect=respuestas) as g:
            filas = fetchers.fetch_indec_tabla(TABLA)
        self.assertEqual(len(filas), 2)
        self.assertEqual(g.call_count, 3)

    def test_429_persistente_falla_tras_los_reintentos(self):
        with mock.patch.object(fetchers.requests, "get", return_value=Resp(429)) as g:
            with self.assertRaises(RuntimeError) as cm:
                fetchers.fetch_indec_tabla(TABLA)
        self.assertEqual(g.call_count, fetchers.INDEC_REINTENTOS)
        self.assertNotIsInstance(cm.exception, fetchers.IndecAuthError)

    def test_401_no_se_reintenta_y_es_error_de_autenticacion(self):
        for status in (401, 403):
            with mock.patch.object(fetchers.requests, "get", return_value=Resp(status)) as g:
                with self.assertRaises(fetchers.IndecAuthError) as cm:
                    fetchers.fetch_indec_tabla(TABLA)
            self.assertEqual(g.call_count, 1)
            self.assertNotIn(TOKEN_FALSO, str(cm.exception))

    def test_token_faltante_es_error_de_autenticacion(self):
        with mock.patch.dict(os.environ, {"INDEC_API_TOKEN": ""}), \
                mock.patch.object(fetchers, "__file__", str(Path("/no/existe/fetchers.py"))):
            with self.assertRaises(fetchers.IndecAuthError):
                fetchers._indec_token()

    def test_400_no_se_reintenta_y_no_filtra_el_token(self):
        err = Resp(400, json_err={"code": "PGRST100", "message": "failed to parse filter"})
        with mock.patch.object(fetchers.requests, "get", return_value=err) as g:
            with self.assertRaises(RuntimeError) as cm:
                fetchers.fetch_indec_tabla(TABLA)
        self.assertEqual(g.call_count, 1)
        self.assertIn("failed to parse filter", str(cm.exception))
        self.assertNotIn(TOKEN_FALSO, str(cm.exception))

    def test_serie_a_dataframe_descarta_nulos_y_ordena(self):
        filas = [{"periodo": "202402", "valor": 2.0}, {"periodo": "202401", "valor": 1.0},
                 {"periodo": "202403", "valor": None, "valor_null": "///"}]
        with mock.patch.object(fetchers.requests, "get", return_value=Resp(200, filas, "0-2/3")):
            df = fetchers.fetch_indec_api(TABLA)
        self.assertEqual(list(df["valor"]), [1.0, 2.0])
        self.assertEqual(str(df["fecha"].iloc[0].date()), "2024-01-01")

    def test_periodo_repetido_es_mapeo_ambiguo(self):
        filas = [{"periodo": "202401", "valor": 1.0}, {"periodo": "202401", "valor": 9.0}]
        with mock.patch.object(fetchers.requests, "get", return_value=Resp(200, filas, "0-1/2")):
            with self.assertRaises(ValueError):
                fetchers.fetch_indec_api(TABLA)

    def test_formatos_de_periodo(self):
        f = fetchers._indec_periodo_a_fecha
        self.assertEqual(str(f("202609").date()), "2026-09-01")
        self.assertEqual(str(f("20262T").date()), "2026-04-01")
        self.assertEqual(str(f("20264T").date()), "2026-10-01")
        self.assertEqual(str(f("20261S").date()), "2026-01-01")
        self.assertEqual(str(f("20162S").date()), "2016-07-01")
        with self.assertRaises(ValueError):
            f("2026")


if __name__ == "__main__":
    unittest.main()

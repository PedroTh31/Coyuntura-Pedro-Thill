"""
Tests sin red de fuentes_indec.py (Bloque A4-A5): API del INDEC con fallback + alertas.

Correr con:  python -m unittest discover tests
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fuentes_indec as FI  # noqa: E402
from fetchers import IndecAuthError, IndecRedError  # noqa: E402

SPEC = {"tabla": "ipc_nacional", "filtros": {"region": "Nacional", "codigo": "0", "tipo_de_indicador": "Indice"},
        "variaciones": {"mensual": "v_m"}}
EQ = {"148.3_X": SPEC, "45.2_D": {"tabla": "mercado_trabajo_eph", "filtros": {"area_geografica_nom": "T_31_A"},
                                   "columna": "tasa_de_desocupacion"}}


def df(*vals):
    return pd.DataFrame({"fecha": pd.date_range("2024-01-01", periods=len(vals), freq="MS"), "valor": list(vals)})


class TestResolver(unittest.TestCase):

    def test_api_ok_no_toca_el_fallback(self):
        r = FI.ResolverIndec(EQ, None)
        with mock.patch.object(FI, "fetch_indec_api", return_value=df(1.0, 2.0)), \
                mock.patch.object(FI, "fetch_datos_gob") as dg:
            r.empezar("X"); out = r.serie_dg("148.3_X"); r.terminar(True)
        self.assertEqual(list(out["valor"]), [1.0, 2.0])
        dg.assert_not_called()
        self.assertEqual(r.por_indicador["X"][0]["fuente"], FI.API)

    def test_error_o_vacio_usa_fallback_y_lo_registra(self):
        for efecto in (RuntimeError("HTTP 503"), df()):
            r = FI.ResolverIndec(EQ, None)
            kw = {"side_effect": efecto} if isinstance(efecto, Exception) else {"return_value": efecto}
            with mock.patch.object(FI, "fetch_indec_api", **kw), \
                    mock.patch.object(FI, "fetch_datos_gob", return_value=df(9.0)):
                r.empezar("X"); out = r.serie_dg("148.3_X"); r.terminar(True)
            self.assertEqual(list(out["valor"]), [9.0])
            uso = r.por_indicador["X"][0]
            self.assertEqual(uso["fuente"], FI.FALLBACK_DG)
            self.assertTrue(uso["motivo"])

    def test_401_corta_la_api_para_el_resto_de_la_corrida(self):
        r = FI.ResolverIndec(EQ, None)
        with mock.patch.object(FI, "fetch_indec_api", side_effect=IndecAuthError("HTTP 401")) as api, \
                mock.patch.object(FI, "fetch_datos_gob", return_value=df(0.07)):
            r.serie_dg("148.3_X")
            r.serie_dg("45.2_D")
        self.assertEqual(api.call_count, 1)
        self.assertIn("401", r.auth_error)

    def test_api_caida_corta_la_api_para_el_resto_de_la_corrida(self):
        # 11/11/2026: la API daba ReadTimeout y cada serie volvía a gastar 5 reintentos (~2,75 min c/u)
        r = FI.ResolverIndec(EQ, None)
        caida = IndecRedError("API INDEC tabla=ipc_nacional: falló tras 5 intentos (error de red (ReadTimeout))")
        with mock.patch.object(FI, "fetch_indec_api", side_effect=caida) as api, \
                mock.patch.object(FI, "fetch_datos_gob", return_value=df(0.07)):
            r.empezar("A"); r.serie_dg("148.3_X"); r.terminar(True)
            r.empezar("B"); r.serie_dg("45.2_D"); r.terminar(True)
        self.assertEqual(api.call_count, 1)
        self.assertIn("ReadTimeout", r.red_error)
        self.assertEqual(r.por_indicador["B"][0]["fuente"], FI.FALLBACK_DG)
        self.assertIn("no se reintenta", r.por_indicador["B"][0]["motivo"])

    def test_error_no_de_red_no_corta_la_api(self):
        r = FI.ResolverIndec(EQ, None)
        with mock.patch.object(FI, "fetch_indec_api", side_effect=RuntimeError("HTTP 400")) as api, \
                mock.patch.object(FI, "fetch_datos_gob", return_value=df(0.07)):
            r.serie_dg("148.3_X")
            r.serie_dg("45.2_D")
        self.assertEqual(api.call_count, 2)
        self.assertIsNone(r.red_error)

    def test_id_sin_equivalencia_va_directo_a_datos_gob(self):
        r = FI.ResolverIndec(EQ, None)
        with mock.patch.object(FI, "fetch_indec_api") as api, \
                mock.patch.object(FI, "fetch_datos_gob", return_value=df(5.0)):
            r.serie_dg("91.1_OTRA")
        api.assert_not_called()

    def test_factor_fallback_solo_si_se_uso_el_fallback(self):
        ind = {"nombre": "Tasa de desempleo", "id": "45.2_D", "fuente_fallback": "datos_gob_ar", "factor_fallback": 100}
        r = FI.ResolverIndec(EQ, None)
        with mock.patch.object(FI, "fetch_indec_api", return_value=df(7.6)):
            self.assertEqual(r.serie_directa(ind, None)["valor"].iloc[0], 7.6)
        r = FI.ResolverIndec(EQ, None)
        with mock.patch.object(FI, "fetch_indec_api", side_effect=RuntimeError("caída")), \
                mock.patch.object(FI, "fetch_datos_gob", return_value=df(0.076)):
            self.assertAlmostEqual(r.serie_directa(ind, None)["valor"].iloc[0], 7.6)

    def test_variacion_publicada_reemplaza_el_tipo_de_indicador(self):
        r = FI.ResolverIndec(EQ, None)
        with mock.patch.object(FI, "fetch_indec_api", return_value=df(2.1)) as api:
            out = r.variacion_publicada("148.3_X", "mensual", fallback=lambda: df(99.0))
        self.assertEqual(api.call_args.args[1]["tipo_de_indicador"], "v_m")
        self.assertEqual(list(out["valor"]), [2.1])
        self.assertIsNone(r.variacion_publicada("148.3_X", "interanual", fallback=lambda: df()))


class TestCierreYAlertas(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.estado = Path(self.tmp.name) / "indec_estado.json"
        self.p_estado = mock.patch.object(FI, "ESTADO", self.estado)
        self.p_estado.start()

    def tearDown(self):
        self.p_estado.stop()
        self.tmp.cleanup()

    def _cerrar(self, resolver, hoy, exp=None, vacias=(), enviar_ok=True):
        enviadas = []

        def enviar(asunto, cuerpo):
            enviadas.append(cuerpo)
            return enviar_ok
        with mock.patch.object(FI, "_hoy", return_value=hoy), \
                mock.patch.object(FI, "indec_token_exp", return_value=exp), \
                mock.patch.object(FI, "datos_gob_filas", side_effect=lambda i: 0 if i in vacias else 10), \
                mock.patch.object(FI, "enviar_alerta", side_effect=enviar):
            FI.cerrar_corrida(resolver)
        return enviadas

    def _resolver_en_fallback(self):
        r = FI.ResolverIndec(EQ, None)
        with mock.patch.object(FI, "fetch_indec_api", side_effect=RuntimeError("caída")), \
                mock.patch.object(FI, "fetch_datos_gob", return_value=df(1.0)):
            r.empezar("X"); r.serie_dg("148.3_X"); r.terminar(True)
        return r

    def test_aviso_cuando_el_fallback_supera_3_corridas_seguidas(self):
        avisos = []
        for dia in range(1, 6):
            avisos.append(self._cerrar(self._resolver_en_fallback(), f"2026-11-0{dia}"))
        self.assertEqual([len(a) for a in avisos[:3]], [0, 0, 0])   # rachas 1, 2, 3
        self.assertIn("4 corridas seguidas", avisos[3][0])          # racha 4 (> 3): avisa
        self.assertEqual(avisos[4], [])                             # al día siguiente no repite
        estado = json.loads(self.estado.read_text(encoding="utf-8"))
        self.assertEqual(estado["rachas_fallback"]["148.3_X"], 5)

    def test_la_racha_se_corta_cuando_la_api_vuelve(self):
        for dia in range(1, 4):
            self._cerrar(self._resolver_en_fallback(), f"2026-11-0{dia}")
        r = FI.ResolverIndec(EQ, None)
        with mock.patch.object(FI, "fetch_indec_api", return_value=df(1.0)):
            r.serie_dg("148.3_X")
        self._cerrar(r, "2026-11-04")
        self.assertEqual(json.loads(self.estado.read_text(encoding="utf-8"))["rachas_fallback"]["148.3_X"], 0)

    def test_aviso_si_un_fallback_de_datos_gob_devuelve_0_filas(self):
        r = FI.ResolverIndec(EQ, None)
        enviadas = self._cerrar(r, "2026-11-05", vacias={"45.2_D"})
        self.assertEqual(len(enviadas), 1)
        self.assertIn("45.2_D", enviadas[0])
        self.assertEqual(self._cerrar(r, "2026-11-06", vacias={"45.2_D"}), [])     # no repite al día siguiente
        self.assertEqual(len(self._cerrar(r, "2026-11-12", vacias={"45.2_D"})), 1)  # sí a la semana

    def test_vencimiento_del_token_30_dias_antes_y_semanal(self):
        r = FI.ResolverIndec(EQ, None)
        lejos = datetime.now(timezone.utc) + timedelta(days=90)
        cerca = datetime.now(timezone.utc) + timedelta(days=20)
        self.assertEqual(self._cerrar(r, "2026-11-05", exp=lejos), [])
        self.assertIn("vence el", self._cerrar(r, "2026-11-06", exp=cerca)[0])
        self.assertEqual(self._cerrar(r, "2026-11-08", exp=cerca), [])
        self.assertEqual(len(self._cerrar(r, "2026-11-13", exp=cerca)), 1)
        # token renovado: exp nuevo lejano -> el aviso se corta solo
        self.assertEqual(self._cerrar(r, "2026-11-20", exp=lejos), [])

    def test_falla_de_autenticacion_avisa_una_vez_por_dia(self):
        r = FI.ResolverIndec(EQ, None)
        with mock.patch.object(FI, "fetch_indec_api", side_effect=IndecAuthError("HTTP 401")), \
                mock.patch.object(FI, "fetch_datos_gob", return_value=df(1.0)):
            r.empezar("IPC"); r.serie_dg("148.3_X"); r.terminar(True)
        primera = self._cerrar(r, "2026-11-05")
        self.assertIn("autenticación", primera[0])
        self.assertIn("IPC", primera[0])
        self.assertEqual(self._cerrar(r, "2026-11-05"), [])

    def test_si_el_mail_no_sale_el_aviso_se_reintenta(self):
        r = FI.ResolverIndec(EQ, None)
        self.assertEqual(len(self._cerrar(r, "2026-11-05", vacias={"45.2_D"}, enviar_ok=False)), 1)
        self.assertEqual(len(self._cerrar(r, "2026-11-05", vacias={"45.2_D"})), 1)


class TestDescribirFuente(unittest.TestCase):

    def test_textos(self):
        api = [{"clave": "a", "fuente": FI.API, "tabla": "ipc_nacional"}]
        self.assertIn("Fuente: INDEC (", FI.describir_fuente(api))
        self.assertIn("ipc_nacional", FI.describir_fuente(api))
        self.assertIn('href="https://api.indec.gob.ar/datasets/ipc_nacional"', FI.describir_fuente(api))
        dg = [{"clave": "a", "fuente": FI.FALLBACK_DG, "tabla": "ipc_nacional"}]
        self.assertIn("Fuente: INDEC vía", FI.describir_fuente(dg))
        self.assertIsNone(FI.describir_fuente([]))


if __name__ == "__main__":
    unittest.main()

"""Bloque MAE (08/11/2026): cauciones del histórico del MAE, UST del Tesoro / H.15, extras con último dato
válido, alertas, fechas de los snapshots y frecuencia de la línea de frescura. Sin red."""
import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fetchers  # noqa: E402
import frescura as F  # noqa: E402
import fuentes_mercados as M  # noqa: E402
import reconstruir_series as R  # noqa: E402
import run  # noqa: E402

FERIADOS = {date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 23)}


def _op(ticker, plazo, tasa, monto, **extra):
    return dict({"ticker": ticker, "plazo": plazo, "tasaPP": tasa, "montoConcertado": monto, "ultimo": 0,
                 "ultimaTasa": tasa}, **extra)


class TestCauciones(unittest.TestCase):

    def test_plazo_mas_corto_operado_del_dia(self):
        # viernes 30/10: no hay 001; el más corto operado es 003 (el 012 en dólares no cuenta para pesos)
        det = [_op("CAARS", "003", 21.46, 2.9e12), _op("CAARS", "007", 23.8, 1e9), _op("CAUSD", "003", 1.04, 3e8)]
        self.assertEqual(M.caucion_del_dia(det, "CAARS"), {"plazo": 3, "tasa": 21.46, "monto": 2.9e12})

    def test_cero_es_sin_dato(self):
        # #13: un plazo listado pero sin operar (tasa 0 o monto 0) no es un dato
        det = [_op("CAUSD", "001", 0, 0), _op("CAUSD", "006", 1.1583, 3.1e8), _op("CAARS", "001", 0, 5e9)]
        self.assertEqual(M.caucion_del_dia(det, "CAUSD")["plazo"], 6)
        self.assertIsNone(M.caucion_del_dia(det, "CAARS"))
        self.assertIsNone(M.caucion_del_dia([], "CAARS"))

    def test_lee_tasaPP_no_ultimo(self):
        det = [_op("CAARS", "001", 20.561, 3.2e12, ultimo=0, ultimaTasa=25.0)]
        self.assertAlmostEqual(M.caucion_del_dia(det, "CAARS")["tasa"], 20.561)

    def test_varios_segmentos_del_mismo_plazo_se_ponderan_por_monto(self):
        det = [_op("CAARS", "001", 20.0, 3e12), _op("CAARS", "001", 30.0, 1e12)]
        self.assertAlmostEqual(M.caucion_del_dia(det, "CAARS")["tasa"], 22.5)

    def test_serie_hasta_el_dia_habil_anterior_del_mae(self):
        dias = [{"fecha": "2026-11-05", "details": [_op("CAARS", "006", 24.71, 2.88e12), _op("CAARS", "001", 30.0, 1.3e10)]},
                {"fecha": "2026-11-04", "details": [_op("CAARS", "001", 22.16, 3.07e12)]},
                {"fecha": "2026-11-03", "details": [_op("CAUSD", "001", 1.03, 3.3e8)]}]
        with mock.patch.object(M, "fecha_habil_anterior", return_value=pd.Timestamp("2026-11-06")), \
             mock.patch.object(M, "bajar_historico_cauciones", return_value=dias) as baj:
            s = M.serie_caucion("CAARS")
        self.assertEqual(baj.call_args[0], (pd.Timestamp("2024-01-01"), pd.Timestamp("2026-11-06")))
        self.assertEqual(list(s["fecha"].dt.strftime("%d/%m")), ["04/11", "05/11"])
        self.assertEqual(list(s["plazo"]), [1, 1])   # el 05/11 el más corto operado es 001 (con 2 días previos, sin umbral)
        self.assertEqual(list(s["valor"]), [22.16, 30.0])

    def test_umbral_de_monto_05_11_2026_queda_sin_dato(self):
        # 20 días previos con ~$3 billones a 1 día; el 05/11 el 001 operó $12.932 MM (0,4%): sin dato, sin sustituto
        fechas = pd.bdate_range("2026-10-07", periods=21)
        dias = [{"fecha": f.strftime("%Y-%m-%d"), "details": [_op("CAARS", "001", 22.0, 3.0e12)]} for f in fechas[:-1]]
        dias.append({"fecha": "2026-11-05", "details": [_op("CAARS", "006", 24.71, 2.883e12),
                                                        _op("CAARS", "001", 30.0, 1.2932e10)]})
        with mock.patch.object(M, "fecha_habil_anterior", return_value=pd.Timestamp("2026-11-06")),              mock.patch.object(M, "bajar_historico_cauciones", return_value=dias):
            s = M.serie_caucion("CAARS")
        self.assertNotIn(pd.Timestamp("2026-11-05"), set(s["fecha"]))
        self.assertEqual(len(s), 20)

    def test_umbral_al_5_por_ciento(self):
        df = pd.DataFrame({"fecha": pd.bdate_range("2026-01-01", periods=7), "valor": 20.0,
                           "monto": [100, 100, 100, 100, 100, 5.0, 4.9]})
        queda, fuera = M.filtrar_monto_minimo(df)
        self.assertEqual(list(queda["monto"]), [100, 100, 100, 100, 100, 5.0])   # 5% justo queda
        self.assertEqual(list(fuera["monto"]), [4.9])
        # con menos de 5 días previos no se filtra (comienzo del histórico)
        self.assertEqual(len(M.filtrar_monto_minimo(df.iloc[[0, 1, 2, 6]])[0]), 4)

    def test_resumen_mae_cero_es_sin_dato(self):
        with mock.patch.dict(fetchers._CACHE_MAE_RESUMEN, {"CAU": [{"ticker": "CAUSD D 001", "ultimo": 0}]}):
            self.assertTrue(fetchers.fetch_mae_resumen_campo("CAU", "CAUSD D 001").empty)


class TestFechasSnapshot(unittest.TestCase):

    def test_hoy_ar_no_es_la_fecha_utc(self):
        # 23:30 de Argentina del 04/11 = 02:30 UTC del 05/11: el dato es del 04/11
        ahora = pd.Timestamp("2026-11-05 02:30", tz="UTC")
        with mock.patch.object(pd.Timestamp, "now", return_value=ahora.tz_convert(fetchers.ZONA_AR)):
            self.assertEqual(fetchers.hoy_ar(), pd.Timestamp("2026-11-04"))

    def test_fecha_del_mae_si_la_informa(self):
        self.assertEqual(fetchers.fecha_snapshot_mae({"fecha": "2026-11-05T00:00:00"}), pd.Timestamp("2026-11-05"))
        with mock.patch.object(fetchers, "hoy_ar", return_value=pd.Timestamp("2026-11-04")):
            self.assertEqual(fetchers.fecha_snapshot_mae({"especie": "GD30"}), pd.Timestamp("2026-11-04"))

    def test_snapshots_sin_fines_de_semana_ni_feriados(self):
        s = pd.DataFrame({"fecha": pd.to_datetime(["2026-10-30", "2026-10-31", "2026-11-01", "2026-11-09", "2026-11-11"]),
                          "valor": [1, 2, 3, 4, 5]})
        quedan, fuera = run.solo_habiles(s, FERIADOS)
        self.assertEqual(list(quedan["valor"]), [1, 5])
        self.assertEqual(fuera, [date(2026, 10, 31), date(2026, 11, 1), date(2026, 11, 9)])
        self.assertTrue(run.es_snapshot_diario({"fuente": "mae_bono"}))
        self.assertFalse(run.es_snapshot_diario({"calculo": "spread_bono_ust"}))   # TIR de BYMA con fecha (#28)
        self.assertFalse(run.es_snapshot_diario({"fuente": "tesoro_ust"}))   # serie histórica con calendario de EE.UU.

    def test_reconstruir_solo_no_habiles(self):
        largo = [["fecha", "indicador", "bloque", "unidad", "valor"],
                 ["2026-10-30", "TIR AL30 (USD)", "mercados", "% anual", "14.7"],
                 ["2026-10-31", "TIR AL30 (USD)", "mercados", "% anual", "11.0"],
                 ["2026-10-31", "Otra", "mercados", "", "1"]]
        queda, borra = R.separar_no_habiles(largo, ["TIR AL30 (USD)"], FERIADOS)
        self.assertEqual([f[0] for f in borra[1:]], ["2026-10-31"])
        self.assertEqual(len(queda), 3)
        ancho = [["fecha", "Otra", "TIR AL30 (USD)"], ["2026-10-30", "", "14.7"], ["2026-10-31", "1", "11.0"]]
        self.assertEqual(R.vaciar_celdas(ancho, borra), [ancho[0], ["2026-10-30", "", "14.7"], ["2026-10-31", "1", ""]])


CSV_TESORO = ('Date,"1 Mo","2 Yr","10 Yr","30 Yr"\n11/06/2026,4.02,4.51,4.86,5.26\n11/05/2026,4.03,4.46,4.84,5.25\n')
CSV_H15 = ('"Series Description","1-month","10-year"\n"Unit:","Percent","Percent"\n"Multiplier:","1","1"\n'
           '"Currency:","NA","NA"\n"Unique Identifier: ","H15/H15/RIFLGFCM01_N.B","H15/H15/RIFLGFCY10_N.B"\n'
           '"Time Period","RIFLGFCM01_N.B","RIFLGFCY10_N.B"\n2026-11-04,4.01,4.90\n2026-11-05,4.03,4.84\n2026-11-06,ND,ND\n')


class TestUST(unittest.TestCase):

    def setUp(self):
        M.ALERTAS.clear(), M.RESUMEN.clear(), M._CACHE_UST.clear()

    def test_parseo_tesoro_y_h15(self):
        t = M.parsear_tesoro(CSV_TESORO, "10 Yr")
        self.assertEqual(list(t.sort_values("fecha")["valor"]), [4.84, 4.86])
        h = M.parsear_h15(CSV_H15, "10 Yr")
        self.assertEqual(list(h["valor"]), [4.90, 4.84])   # "ND" = sin dato
        with self.assertRaises(ValueError):
            M.parsear_tesoro("Date,1 Mo\n", "10 Yr")

    def test_tesoro_sin_alerta(self):
        with mock.patch.object(M, "fetch_tesoro", return_value=M.parsear_tesoro(CSV_TESORO, "10 Yr")):
            self.assertEqual(len(M.serie_ust("10 Yr")), 2)
        self.assertEqual(M.ALERTAS, [])
        self.assertEqual(M.RESUMEN["ust:10 Yr"]["fuente"], "tesoro")

    def test_falla_el_tesoro_entra_h15_con_alerta(self):
        with mock.patch.object(M, "fetch_tesoro", side_effect=RuntimeError("timeout")), \
             mock.patch.object(M, "fetch_h15", return_value=M.parsear_h15(CSV_H15, "10 Yr")):
            self.assertEqual(len(M.serie_ust("10 Yr")), 2)
        self.assertEqual([c for c, _ in M.ALERTAS], ["ust:10 Yr:h15"])
        self.assertEqual(M.RESUMEN["ust:10 Yr"]["fuente"], "h15")

    def test_fallan_los_dos_queda_el_historico_con_alerta(self):
        with mock.patch.object(M, "fetch_tesoro", side_effect=RuntimeError("a")), \
             mock.patch.object(M, "fetch_h15", side_effect=RuntimeError("b")):
            self.assertTrue(M.serie_ust("10 Yr").empty)
        self.assertEqual([c for c, _ in M.ALERTAS], ["ust:10 Yr:sin_datos"])


class TestExtras(unittest.TestCase):

    def setUp(self):
        M.ALERTAS.clear(), M.RESUMEN.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(M, "EXTRAS", Path(self.tmp.name) / "extras.json")
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_guarda_el_ultimo_valido_y_lo_usa_si_viene_vacio(self):
        ec = {"card": {"nombre": "Muro", "valor": "—"}, "serie_js": {"kind": "muro", "x": ["2027"]}, "nota": "n"}
        out, f = M.extra_con_respaldo("Muro", ec, pd.Timestamp("2026-11-06"))
        self.assertIs(out, ec)
        self.assertEqual(M.ALERTAS, [])
        out, f = M.extra_con_respaldo("Muro", None, pd.Timestamp("2026-11-08"))
        self.assertEqual(f, pd.Timestamp("2026-11-06"))
        self.assertEqual(out["serie_js"], ec["serie_js"])
        self.assertEqual(out["card"]["aviso"], M.AVISO_EXTRA_VACIO)
        self.assertNotIn("aviso", ec["card"])   # lo guardado no se toca
        self.assertEqual([c for c, _ in M.ALERTAS], ["extra:Muro"])
        self.assertEqual(json.loads(M.EXTRAS.read_text(encoding="utf-8"))["Muro"]["fecha"], "2026-11-06")

    def test_sin_dato_anterior_no_hay_card_pero_si_alerta(self):
        out, f = M.extra_con_respaldo("DDF", None, pd.Timestamp("2026-11-08"))
        self.assertIsNone(out)
        self.assertEqual([c for c, _ in M.ALERTAS], ["extra:DDF"])

    def test_alerta_primer_dia_y_despues_semanal(self):
        al = [("extra:Muro", "x")]
        self.assertEqual(M.a_avisar({}, al, [], "2026-11-08"), al)
        self.assertEqual(M.a_avisar({"extra:Muro": "2026-11-08"}, al, ["extra:Muro"], "2026-11-11"), [])
        self.assertEqual(M.a_avisar({"extra:Muro": "2026-11-08"}, al, ["extra:Muro"], "2026-11-15"), al)
        # vuelve a fallar después de haberse arreglado: aviso de nuevo aunque no pasó una semana
        self.assertEqual(M.a_avisar({"extra:Muro": "2026-11-08"}, al, [], "2026-11-10"), al)


def _ctx(ahora):
    return F.Contexto(ahora=ahora, no_habiles=FERIADOS)


class TestFrecuenciaDeLaFuente(unittest.TestCase):
    """#24: la frecuencia sale del yaml o de la fuente; nunca se deduce con menos de 2 puntos."""

    SAB = datetime(2026, 11, 7, 10, 0)

    def test_spread_con_un_solo_punto_es_diario(self):
        ind = {"nombre": "Spread", "calculo": "spread_bono_ust"}
        f = F.calcular(ind, "Spread", pd.Series([pd.Timestamp("2026-09-01")]), _ctx(self.SAB))
        self.assertEqual(f.estado, "diaria")
        self.assertEqual(f.periodo, "01/09/26")   # frenada: con el año
        self.assertEqual(f.grave, "sin datos nuevos hace 2 meses")
        self.assertNotIn("sep-26", F.html_sello(f))

    def test_un_solo_punto_sin_frecuencia_conocida_no_se_adivina(self):
        self.assertIsNone(F.frecuencia_de({"nombre": "X"}, pd.Series([pd.Timestamp("2026-09-01")])))
        f = F.calcular({"nombre": "X"}, "X", pd.Series([pd.Timestamp("2026-10-15")]), _ctx(self.SAB))
        self.assertEqual(f.periodo, "15/10/26")
        self.assertNotIn("oct-26", F.html_linea(f))

    def test_frecuencia_del_yaml_manda(self):
        self.assertEqual(F.frecuencia_de({"frecuencia": "mensual", "fuente": "mae_bono"}, pd.Series([], dtype="datetime64[ns]")), "mensual")
        with self.assertRaises(ValueError):
            F.frecuencia_de({"nombre": "X", "frecuencia": "semanal"}, pd.Series([], dtype="datetime64[ns]"))
        for fuente in ("mae_bono", "mae_resumen", "mae_caucion", "tesoro_ust", "byma", "dolar"):
            self.assertEqual(F.frecuencia_de({"fuente": fuente}, pd.Series([pd.Timestamp("2026-01-01")])), "diaria")

    def test_diaria_grave_a_los_10_dias_habiles(self):
        # último dato vie 23/10; al sábado 07/11 van 10 días hábiles (26/10 al 06/11) -> franja
        fechas = pd.Series(pd.bdate_range("2026-01-01", "2026-10-23"))
        f = F.calcular({"nombre": "Caución", "fuente": "mae_caucion"}, "Caución", fechas, _ctx(self.SAB))
        self.assertEqual(f.grave, "sin datos nuevos hace 10 días hábiles")
        # un día después (lun 26/10): 9 días hábiles, sin franja
        fechas = pd.Series(pd.bdate_range("2026-01-01", "2026-10-26"))
        self.assertIsNone(F.calcular({"nombre": "C", "fuente": "mae_caucion"}, "C", fechas, _ctx(self.SAB)).grave)

    def test_feriados_no_cuentan_como_dias_habiles(self):
        # último dato vie 06/11; al jueves 19/11 son 7 hábiles (11, 12, 13, 16, 17, 18, 19): el 9 y el 10 no cuentan
        self.assertEqual(F.dias_habiles_entre(date(2026, 11, 6), date(2026, 11, 19), FERIADOS), 7)

    def test_diaria_respeta_rezago_normal_dias(self):
        fechas = pd.Series(pd.bdate_range("2026-01-01", "2026-10-01"))
        ind = {"nombre": "TCR", "fuente": "byma", "rezago_normal_dias": 60}
        self.assertIsNone(F.calcular(ind, "TCR", fechas, _ctx(self.SAB)).grave)


if __name__ == "__main__":
    unittest.main()

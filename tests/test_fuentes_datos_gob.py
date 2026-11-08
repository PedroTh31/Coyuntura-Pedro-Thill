"""Fallback de la API de series de datos.gob.ar al CSV de distribución (fuentes_datos_gob.py), mensualización
de series diarias del BCRA, rebase de overlays al dibujar y reconstrucción de series. Sin red."""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fuentes_datos_gob as fdg   # noqa: E402
import fetchers                    # noqa: E402
import dashboard                   # noqa: E402
import reconstruir_series          # noqa: E402


def serie(valores, desde="2025-01-01", freq="MS"):
    return pd.DataFrame({"fecha": pd.date_range(desde, periods=len(valores), freq=freq),
                         "valor": [float(v) for v in valores]})


CSV = serie(range(100, 124))     # 24 meses, la "verdad" del CSV de distribución
META = {"size": 24, "fin": "2026-12-01", "url": "https://infra.datos.gob.ar/x.csv", "columna": "col"}


def resolver(api, meta=META, csv=CSV, excluidos=(), csv_falla=False):
    llamadas = {"csv": 0}

    def fetch_csv(url, columna, start):
        llamadas["csv"] += 1
        if csv_falla:
            raise RuntimeError("sin red")
        return csv.copy()
    r = fdg.ResolverDatosGob(excluidos, fetch_api=lambda sid, start: api.copy(),
                             fetch_meta=lambda sid: dict(meta), fetch_csv=fetch_csv)
    return r, llamadas


class TestDecidir(unittest.TestCase):
    def test_api_bien_no_usa_csv(self):
        self.assertIsNone(fdg.decidir(CSV, 24, 24, CSV))

    def test_cero_filas(self):
        self.assertIn("0 filas", fdg.decidir(CSV.iloc[:0], 0, 24, CSV))

    def test_historia_cortada(self):
        # caso real: 74.3_IICL_0_M_42 devolvía 138 de 416 filas (1992-01 a 2003-06)
        self.assertIn("138 de 416", fdg.decidir(CSV, 138, 416, CSV))

    def test_valores_erroneos_con_filas_completas(self):
        # caso real: base monetaria, filas completas y la mitad del valor desde jun-2026
        api = CSV.copy()
        api.loc[api.index[-3:], "valor"] = api["valor"].iloc[-3:] / 2
        self.assertIn("difieren", fdg.decidir(api, 24, 24, CSV))

    def test_revision_chica_dentro_de_tolerancia(self):
        api = CSV.copy()
        api.loc[api.index[-1], "valor"] *= 1.005   # 0,5% en el último dato
        self.assertIsNone(fdg.decidir(api, 24, 24, CSV))

    def test_solo_compara_ultimos_12(self):
        api = CSV.copy()
        api.loc[api.index[0], "valor"] = 0           # error viejo, fuera de la ventana
        self.assertIsNone(fdg.decidir(api, 24, 24, CSV))

    def test_serie_que_cruza_el_cero_usa_escala_de_la_ventana(self):
        csv = serie([1000, -1000, 5, 1000, -1000, 1000, 1000, -1000, 1000, 1000, -1000, 1000])
        api = csv.copy()
        api.loc[2, "valor"] = 6                      # +20% sobre un dato chico, 0,1% de la escala
        self.assertIsNone(fdg.decidir(api, 12, 12, csv))

    def test_sin_csv_no_compara(self):
        self.assertIsNone(fdg.decidir(CSV, 24, 24, None))


class TestResolver(unittest.TestCase):
    def test_usa_csv_y_registra_por_indicador(self):
        r, _ = resolver(CSV.iloc[:0])
        r.empezar("M2 (agregado total)")
        df = r.serie("90.1_AMTM2_0_0_31", "2025-06-01")
        r.terminar(ok=True)
        self.assertEqual(df["fecha"].min(), pd.Timestamp("2025-06-01"))
        self.assertEqual(len(df), 19)
        self.assertEqual(r.por_indicador, {"M2 (agregado total)": ["90.1_AMTM2_0_0_31"]})
        self.assertEqual(r.por_id["90.1_AMTM2_0_0_31"]["indicadores"], ["M2 (agregado total)"])

    def test_api_bien_no_registra(self):
        r, _ = resolver(CSV)
        r.empezar("X")
        pd.testing.assert_frame_equal(r.serie("id", None), CSV)
        r.terminar(ok=True)
        self.assertEqual(r.por_id, {})
        self.assertEqual(r.por_indicador, {})

    def test_excluido_nunca_baja_el_csv(self):
        r, llamadas = resolver(CSV.iloc[:0], excluidos=["158.1_REPTE_0_0_5"])
        self.assertTrue(r.serie("158.1_REPTE_0_0_5", None).empty)
        self.assertEqual(llamadas["csv"], 0)
        self.assertEqual(r.por_id, {})

    def test_csv_que_falla_deja_la_api(self):
        api = CSV.iloc[:5]
        r, _ = resolver(api, csv_falla=True)
        self.assertEqual(len(r.serie("id", None)), 5)
        self.assertEqual(r.por_id, {})

    def test_memo_registra_cada_indicador_que_usa_el_id(self):
        r, llamadas = resolver(CSV.iloc[:0])
        for nombre in ("Balance comercial energético", "Combustibles y energía"):
            r.empezar(nombre)
            r.serie("74.3_IECE_0_M_35", "2004-01-01")
            r.terminar(ok=True)
        self.assertEqual(llamadas["csv"], 1)
        self.assertEqual(r.por_id["74.3_IECE_0_M_35"]["indicadores"],
                         ["Balance comercial energético", "Combustibles y energía"])
        self.assertEqual(set(r.por_indicador), {"Balance comercial energético", "Combustibles y energía"})

    def test_indicador_que_falla_no_queda_en_por_indicador(self):
        r, _ = resolver(CSV.iloc[:0])
        r.empezar("X")
        r.serie("id", None)
        r.terminar(ok=False)
        self.assertEqual(r.por_indicador, {})
        self.assertIn("id", r.por_id)   # el uso del CSV igual se registra (y alerta)


class TestCsvMasNuevo(unittest.TestCase):
    def test_csv_con_periodos_mas_nuevos_dispara(self):
        # caso real: comercio exterior, el CSV llega a sep-2026 y la API a ago-2026
        self.assertIn("más nuevos", fdg.decidir(CSV.iloc[:-1], 23, 23, CSV))

    def test_mismo_fin_no_dispara(self):
        self.assertIsNone(fdg.decidir(CSV, 24, 24, CSV))


class TestGuardaRepetido(unittest.TestCase):
    """Guarda anti-RIPTE: el período más nuevo del CSV repite exactamente el valor anterior."""
    CSV_REP = pd.concat([CSV, pd.DataFrame({"fecha": [pd.Timestamp("2027-01-01")], "valor": [123.0]})],
                        ignore_index=True)

    def test_unico_motivo_mas_nuevo_queda_la_api_y_alerta(self):
        r, _ = resolver(CSV, csv=self.CSV_REP)
        r.empezar("Salario RIPTE")
        df = r.serie("158.1_X", None)
        r.terminar(ok=True)
        pd.testing.assert_frame_equal(df, CSV)
        self.assertEqual(r.por_id, {})
        self.assertIn("repite exactamente", r.descartados["158.1_X"]["motivo"])
        self.assertEqual(r.descartados["158.1_X"]["indicadores"], ["Salario RIPTE"])
        items = fdg.actualizar_estado({}, r.por_id, "2026-11-09", r.descartados)
        self.assertEqual([k for k, _ in items], ["repetido:158.1_X"])

    def test_otro_motivo_usa_el_csv_sin_el_periodo_repetido(self):
        r, _ = resolver(CSV.iloc[:0], csv=self.CSV_REP)   # API vacía: el CSV se usa, pero sin ene-2027
        df = r.serie("id", None)
        pd.testing.assert_frame_equal(df, CSV)
        self.assertIn("id", r.por_id)
        self.assertIn("id", r.descartados)

    def test_api_con_el_mismo_periodo_y_valor_no_salta(self):
        # caso real: informalidad 2T-2026 = 0,379 como el 1T, y la API también publica 2T-2026 = 0,379;
        # la API está cortada (falta historia vieja), así que igual se usa el CSV, completo
        api = self.CSV_REP.iloc[5:]
        r, _ = resolver(api, csv=self.CSV_REP, meta=dict(META, size=25))
        df = r.serie("52.2_ASDJ_0_0_37", None)
        self.assertEqual(df["fecha"].max(), pd.Timestamp("2027-01-01"))
        self.assertIn("52.2_ASDJ_0_0_37", r.por_id)
        self.assertEqual(r.descartados, {})

    def test_api_con_el_mismo_periodo_y_otro_valor_salta(self):
        api = self.CSV_REP.copy()
        api.loc[api.index[-1], "valor"] = 130.0
        r, _ = resolver(api, csv=self.CSV_REP, meta=dict(META, size=25))
        r.serie("id", None)
        self.assertIn("id", r.descartados)

    def test_sin_repetido_no_descarta(self):
        r, _ = resolver(CSV.iloc[:-1])
        self.assertEqual(len(r.serie("id", None)), 24)
        self.assertEqual(r.descartados, {})


class TestCoherencia(unittest.TestCase):
    URL_A, URL_B = "https://infra.datos.gob.ar/a.csv", "https://infra.datos.gob.ar/b.csv"

    def resolver(self, apis, urls):
        r = fdg.ResolverDatosGob(fetch_api=lambda sid, start: apis[sid].copy(),
                                 fetch_meta=lambda sid: {"size": len(apis[sid]), "url": urls[sid], "columna": sid},
                                 fetch_csv=lambda url, col, start: CSV.copy())
        return r

    def test_misma_distribucion_en_la_card_usa_el_csv(self):
        # expo cae al CSV (más nuevo); impo coincide con el CSV hasta su fin pero es de la misma distribución
        apis = {"expo": CSV.iloc[:0], "impo": CSV.copy(), "otro": CSV.copy()}
        urls = {"expo": self.URL_A, "impo": self.URL_A, "otro": self.URL_B}
        r = self.resolver(apis, urls)
        r.preparar([("Comercio exterior", {"expo", "impo", "otro"})])
        for sid in ("expo", "impo", "otro"):
            r.serie(sid, None)
        self.assertEqual(set(r.por_id), {"expo", "impo"})
        self.assertIn("coherencia", r.por_id["impo"]["motivo"])
        self.assertIn("Comercio exterior", r.por_id["impo"]["motivo"])

    def test_otra_card_no_se_contagia(self):
        apis = {"expo": CSV.iloc[:0], "impo": CSV.copy()}
        urls = {"expo": self.URL_A, "impo": self.URL_A}
        r = self.resolver(apis, urls)
        r.preparar([("Card de expo y algo", {"expo", "x"}), ("Card de impo", {"impo", "y"})])
        r.serie("impo", None)
        self.assertEqual(r.por_id, {})

    def test_se_propaga_entre_cards(self):
        # a cae; b comparte card con a; c comparte otra card con b -> c también (misma distribución)
        apis = {"a": CSV.iloc[:0], "b": CSV.copy(), "c": CSV.copy()}
        urls = dict.fromkeys(apis, self.URL_A)
        r = self.resolver(apis, urls)
        r.preparar([("Card 2", {"b", "c"}), ("Card 1", {"a", "b"})])
        self.assertTrue(all(r._eval[s]["usa_csv"] for s in "abc"))

    def test_excluido_no_se_fuerza(self):
        apis = {"a": CSV.iloc[:0], "ripte": CSV.copy()}
        r = self.resolver(apis, dict.fromkeys(apis, self.URL_A))
        r.excluidos = {"ripte"}
        r.preparar([("Card", {"a", "ripte"})])
        r.serie("ripte", None)
        self.assertNotIn("ripte", r.por_id)

    def test_grupos_por_card(self):
        inds = [
            {"nombre": "Expo", "fuente": "datos_gob", "id": "E", "solo_componente": True},
            {"nombre": "Impo", "fuente": "datos_gob", "id": "I", "solo_componente": True},
            {"nombre": "Saldo", "calculo": "resta", "minuendo_id": "E", "sustraendo_id": "I"},
            {"nombre": "Espejo", "vista": "comercio_espejo", "series": ["Expo", "Impo", "Saldo"]},
            {"nombre": "Combo", "vista": "combo_barras_linea", "barras": [{"serie": "Expo", "signo": 1}],
             "linea": "Reservas"},
            {"nombre": "Reservas", "fuente": "bcra", "id_variable": 1},
            {"nombre": "IPC", "fuente": "datos_gob", "id": "IPC1"},
            {"nombre": "Real", "calculo": "real", "nominal_id": "N", "deflactor_id": "IPC1"},
            {"nombre": "T1", "fuente": "datos_gob", "id": "R1", "tabla": "Rubros"},
            {"nombre": "T2", "fuente": "datos_gob", "id": "R2", "tabla": "Rubros"},
        ]
        g = dict(fdg.grupos_por_card(inds, equivalencias={"IPC1": {}}))
        self.assertEqual(g["Saldo"], {"E", "I"})
        self.assertEqual(g["Espejo"], {"E", "I"})
        self.assertNotIn("Combo", g)          # E + una serie del BCRA: un solo id de datos.gob
        self.assertNotIn("Real", g)           # el IPC tiene equivalencia del INDEC: queda afuera
        self.assertEqual(g["tabla Rubros"], {"R1", "R2"})


class TestEstado(unittest.TestCase):
    def uso(self):
        return {"motivo": "la API devolvió 0 filas", "url": "u", "columna": "c", "indicadores": ["M2"]}

    def test_racha_y_alertas(self):
        estado = {}
        items = fdg.actualizar_estado(estado, {"a": self.uso()}, "2026-11-09")
        self.assertEqual(estado["rachas"]["a"], 1)
        self.assertEqual(len(items), 1)                       # alerta el primer día
        estado["avisos"] = {"csv:a": "2026-11-09"}
        items = fdg.actualizar_estado(estado, {"a": self.uso()}, "2026-11-10")
        self.assertEqual((estado["rachas"]["a"], items), (2, []))   # al día siguiente, nada
        items = fdg.actualizar_estado(estado, {"a": self.uso()}, "2026-11-16")
        self.assertEqual(len(items), 1)                       # una semana después, recordatorio
        self.assertIn("Corridas seguidas usando el CSV: 3", items[0][1])

    def test_csv_mas_nuevo_y_coherencia_no_alertan_pero_suman_racha(self):
        estado = {}
        usos = {"a": dict(self.uso(), motivo="el CSV tiene períodos más nuevos que la API (CSV hasta 2026-09, "
                                              "API hasta 2026-08)"),
                "b": dict(self.uso(), motivo="coherencia: a, de la misma distribución, sale del CSV en la card 'X'"),
                "c": dict(self.uso(), motivo="la API devolvió 91 de 93 filas (historia cortada)")}
        items = fdg.actualizar_estado(estado, usos, "2026-11-09")
        self.assertEqual([k for k, _ in items], ["csv:c"])
        self.assertEqual(estado["rachas"], {"a": 1, "b": 1, "c": 1})
        self.assertEqual(usos["a"]["racha"], 1)

    def test_motivos_que_alertan(self):
        for m in ("la API devolvió 0 filas", "la API devolvió 26 de 41 filas (historia cortada)",
                  "los últimos 12 períodos difieren del CSV un 1.3% (tolerancia 1%)"):
            self.assertTrue(fdg.motivo_alerta(m))
        self.assertFalse(fdg.motivo_alerta(fdg.decidir(CSV.iloc[:-1], 23, 23, CSV)))

    def test_racha_vuelve_a_cero(self):
        estado = {"rachas": {"a": 5}, "avisos": {"csv:a": "2026-11-09"}}
        self.assertEqual(fdg.actualizar_estado(estado, {}, "2026-11-10"), [])
        self.assertEqual(estado["rachas"]["a"], 0)
        items = fdg.actualizar_estado(estado, {"a": self.uso()}, "2026-11-11")
        self.assertEqual(len(items), 1)                       # vuelve a empezar: alerta de nuevo

    def test_describir_csv(self):
        self.assertIsNone(fdg.describir_csv([]))
        self.assertIn("vía CSV de distribución de datos.gob.ar", fdg.describir_csv(["b", "a"]))
        self.assertTrue(fdg.describir_csv(["b", "a"]).endswith("a, b."))


class TestAgregarMensual(unittest.TestCase):
    # vie 30/01, lun 02/02 y vie 27/02 (hábiles); el mes en curso nunca se incluye
    DIARIA = pd.DataFrame({"fecha": pd.to_datetime(["2026-01-30", "2026-02-02", "2026-02-27"]),
                           "valor": [10.0, 20.0, 50.0]})

    def test_promedio_corridos_arrastra_el_ultimo_habil(self):
        m = fetchers.agregar_mensual(self.DIARIA, "promedio_corridos").set_index("fecha")["valor"]
        # feb: 01/02 arrastra el 10 del viernes 30/01, 02..26 valen 20, 27 y 28 valen 50 -> (10+25*20+2*50)/28
        self.assertAlmostEqual(m[pd.Timestamp("2026-02-01")], (10 + 25 * 20 + 2 * 50) / 28)

    def test_promedio_habiles_y_fin_de_mes(self):
        hab = fetchers.agregar_mensual(self.DIARIA, "promedio_habiles").set_index("fecha")["valor"]
        fin = fetchers.agregar_mensual(self.DIARIA, "fin_de_mes").set_index("fecha")["valor"]
        self.assertEqual(hab[pd.Timestamp("2026-02-01")], 35.0)
        self.assertEqual(fin[pd.Timestamp("2026-02-01")], 50.0)

    def test_excluye_el_mes_en_curso(self):
        hoy = pd.Timestamp.today().normalize()
        d = pd.DataFrame({"fecha": [hoy - pd.offsets.MonthBegin(1) - timedelta(days=3), hoy], "valor": [1.0, 2.0]})
        m = fetchers.agregar_mensual(d, "promedio_habiles")
        self.assertTrue((m["fecha"] < hoy.replace(day=1)).all())

    def test_regla_desconocida(self):
        with self.assertRaises(ValueError):
            fetchers.agregar_mensual(self.DIARIA, "promedio")


class TestRebaseVista(unittest.TestCase):
    def test_rebasa_en_el_primer_mes_del_desde_sin_tocar_el_original(self):
        h = pd.DataFrame({"fecha": pd.to_datetime(["2025-12-01", "2026-01-01", "2026-02-01"] * 2),
                          "indicador": ["A"] * 3 + ["B"] * 3, "valor": [50.0, 200.0, 220.0, 1.0, 4.0, 5.0]})
        inds = [{"nombre": "O", "vista": "overlay", "series": ["A", "B"], "rebase_vista": True, "desde": "2026-01-01"}]
        r = dashboard.rebase_vista(h, inds)
        self.assertEqual([round(v, 9) for v in r[r.indicador == "A"]["valor"].tolist()], [25.0, 100.0, 110.0])
        self.assertEqual([round(v, 9) for v in r[r.indicador == "B"]["valor"].tolist()], [25.0, 100.0, 125.0])
        self.assertEqual(h["valor"].iloc[1], 200.0)

    def test_tabla_ultimos_con_unidad_de_la_card(self):
        # las series se guardan en millones de $, pero la tabla muestra el índice rebasado
        h = pd.DataFrame({"fecha": pd.to_datetime(["2026-01-01", "2026-02-01"] * 2),
                          "indicador": ["A"] * 2 + ["B"] * 2, "valor": [200.0, 220.0, 4.0, 5.0]})
        ov = {"nombre": "O", "vista": "overlay", "series": ["A", "B"], "rebase_vista": True,
              "desde": "2026-01-01", "unidad": "índice, ene-2026 = 100"}
        por_nombre = {"A": {"nombre": "A", "unidad": "millones de $"}, "B": {"nombre": "B", "unidad": "millones de $"},
                      "O": ov}
        html = dashboard._tabla_ultimos(ov, dashboard.rebase_vista(h, [ov]), por_nombre)
        self.assertIn("índice, ene-2026 = 100", html)
        self.assertNotIn("millones de $", html)

    def test_cortar_comun_en_el_ultimo_periodo_comun(self):
        h = pd.DataFrame({"fecha": pd.to_datetime(["2026-08-01", "2026-09-01", "2026-10-01",
                                                   "2026-08-01", "2026-09-01", "2026-10-01"]),
                          "indicador": ["M2"] * 3 + ["M3"] * 2 + ["Otra"], "valor": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]})
        ov = {"nombre": "O", "vista": "overlay", "series": ["M2", "M3"], "cortar_comun": True}
        r = dashboard.cortar_comun(h, [ov])
        self.assertEqual(r[r.indicador == "M2"]["fecha"].max(), pd.Timestamp("2026-09-01"))
        self.assertEqual(len(r[r.indicador == "Otra"]), 1)      # las series que no dibuja quedan intactas
        self.assertEqual(len(h), 6)                             # lo guardado no se toca
        self.assertIs(dashboard.cortar_comun(h, [dict(ov, cortar_comun=False)]), h)

    def test_cortar_comun_sin_datos_de_una_serie_no_corta(self):
        h = pd.DataFrame({"fecha": pd.to_datetime(["2026-10-01"]), "indicador": ["M2"], "valor": [1.0]})
        r = dashboard.cortar_comun(h, [{"nombre": "O", "vista": "overlay", "series": ["M2", "M3"], "cortar_comun": True}])
        self.assertEqual(len(r), 1)

    def test_sin_flag_no_cambia(self):
        h = pd.DataFrame({"fecha": pd.to_datetime(["2026-01-01"]), "indicador": ["A"], "valor": [7.0]})
        self.assertIs(dashboard.rebase_vista(h, [{"nombre": "O", "vista": "overlay", "series": ["A"]}]), h)


class TestReconstruir(unittest.TestCase):
    LARGO = [["fecha", "indicador", "bloque", "unidad", "valor"],
             ["2026-01-01", "A", "x", "u", "1.10000000000000001"],
             ["2026-01-01", "B", "x", "u", "2"], ["2026-02-01", "A", "x", "u", "3"]]

    def test_separar_sin_tocar_el_formato_de_los_numeros(self):
        queda, borra = reconstruir_series.separar(self.LARGO, ["B"])
        self.assertEqual(queda, [self.LARGO[0], self.LARGO[1], self.LARGO[3]])
        self.assertEqual(borra, [self.LARGO[0], self.LARGO[2]])

    def test_nombre_inexistente_corta(self):
        with self.assertRaises(SystemExit):
            reconstruir_series.separar(self.LARGO, ["X"])

    def test_sacar_columnas_del_ancho(self):
        ancho = [["fecha", "A", "B"], ["2026-01-01", "1", "2"], ["2026-02-01", "", "5"]]
        self.assertEqual(reconstruir_series.sacar_columnas(ancho, ["B"]), [["fecha", "A"], ["2026-01-01", "1"]])


if __name__ == "__main__":
    unittest.main()

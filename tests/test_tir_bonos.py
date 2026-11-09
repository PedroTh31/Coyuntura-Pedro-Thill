"""Bloque TIR (#28, decisiones de Pedro del 08/11/2026): TIR y MD con cierres de BYMA + flujo del MAE, corte en el
último pago (BYMA ajusta hacia atrás sus cierres en cada pago), spread contra el Treasury interpolado a la
duración, `sin_alerta_rezago`, redirección de un slug viejo y el muro sin valor. Sin red."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dashboard as D  # noqa: E402
import fetchers  # noqa: E402
import fuentes_mercados as M  # noqa: E402
import pagina_home  # noqa: E402
import run  # noqa: E402
import sitio  # noqa: E402
import storage  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
T = pd.Timestamp


def ff(pagos):
    """Flujo de fondos con la forma de emisiones/flujofondos/{ticker} del MAE."""
    return {"especie": "GD30", "detalle": [{"fechaPago": f"{f}T00:00:00", "cashFlow": cf, "renta": r, "vr": 64.0}
                                           for f, cf, r in pagos]}


# Flujo tipo GD30 (cupones de la ficha del MAE al 08/11/2026)
GD30 = [("2027-01-09", 8.24, 0.24), ("2027-07-09", 8.21, 0.21), ("2028-01-09", 8.42, 0.42),
        ("2028-07-09", 8.35, 0.35), ("2029-01-09", 8.28, 0.28), ("2029-07-09", 8.21, 0.21),
        ("2030-01-09", 8.14, 0.14), ("2030-07-09", 8.07, 0.07)]


class TestConvencion(unittest.TestCase):

    def test_tir_efectiva_act365_y_md(self):
        # un solo pago de 110 a 365 días, precio 100 -> TIR 10% exacta; MD = 1 / 1,1
        fl = [(T("2027-11-11"), 110.0)]
        self.assertAlmostEqual(M.tir_efectiva(100.0, T("2026-11-11"), fl), 10.0, places=8)
        self.assertAlmostEqual(M.duracion_modificada(10.0, T("2026-11-11"), fl), 1 / 1.1, places=10)

    def test_precio_recalculado_con_la_tir_es_el_de_entrada(self):
        fl = M.flujos_bono(ff(GD30))
        liq = T("2026-11-11")
        tir = M.tir_efectiva(53.13, liq, fl)
        precio = sum(cf / (1 + tir / 100) ** ((f - liq).days / 365) for f, cf in fl)
        self.assertAlmostEqual(precio, 53.13, places=8)
        self.assertAlmostEqual(tir, 12.54, places=2)   # mismo valor del diagnóstico (cierre del 06/11/2026, liquida el 11/11)

    def test_liquidacion_t1_habil_saltea_feriados(self):
        # viernes 06/11/2026: el 9 y el 10 son feriados -> liquida el miércoles 11/11. Con un pago de 110 un año
        # después de ESA fecha, precio 100 da 10% sólo si la liquidación es el 11/11.
        cierres = pd.DataFrame({"fecha": [T("2026-11-06")], "precio": [100.0]})
        fl = [(T("2026-07-09"), 1.0), (T("2027-11-11"), 110.0)]
        df = M.calcular_bono(cierres, fl, T("2026-07-10"), T("2026-11-08"), {T("2026-11-09").date(), T("2026-11-10").date()})
        self.assertAlmostEqual(df["tir"].iloc[0], 10.0, places=8)

    def test_pagos_ya_liquidados_no_cuentan(self):
        fl = [(T("2026-11-11"), 50.0), (T("2027-11-12"), 110.0)]
        # liquidación el 11/11: el pago de ese día ya no es del comprador
        self.assertAlmostEqual(M.tir_efectiva(100.0, T("2026-11-11"), fl),
                               M.tir_efectiva(100.0, T("2026-11-11"), fl[1:]), places=10)


class TestCorteEnElUltimoPago(unittest.TestCase):

    def test_ultimo_pago_listado_o_deducido(self):
        fl = M.flujos_bono(ff(GD30))
        # el MAE ya sacó el pago del 09/07/2026: primer pago menos el período entre los dos primeros
        self.assertEqual(M.ultimo_pago(fl, T("2026-11-08")), T("2026-07-09"))
        # el MAE todavía lista el pago del 09/01/2027 después de hecho: ése
        self.assertEqual(M.ultimo_pago(fl, T("2027-01-12")), T("2027-01-09"))

    def test_solo_dias_habiles_posteriores_al_ultimo_pago(self):
        fl = M.flujos_bono(ff(GD30))
        cierres = pd.DataFrame({"fecha": pd.to_datetime(["2026-07-08", "2026-07-10", "2026-07-11", "2026-07-13",
                                                         "2026-11-06"]),
                                "precio": [57.4, 57.9, 57.9, 57.5, 53.13]})
        df = M.calcular_bono(cierres, fl, T("2026-07-10"), T("2026-11-08"), {T("2026-07-10").date()})
        # 08/07 es anterior al pago (ajustado por BYMA), 10/07 feriado, 11/07 sábado
        self.assertEqual(list(df["fecha"]), [T("2026-07-13"), T("2026-11-06")])

    def _correr(self, hoy, flujo, cierres):
        M._CACHE_BONOS.clear()
        with mock.patch.object(fetchers, "hoy_ar", return_value=hoy), \
                mock.patch.object(fetchers, "fetch_mae_flujofondos_ticker", return_value=ff(flujo)), \
                mock.patch.object(M, "fetch_byma_cierres", side_effect=lambda t, desde: cierres):
            s = M.serie_bono("GD30", "tir")
        M._CACHE_BONOS.clear()
        return s.assign(indicador="TIR GD30 (USD)", bloque="mercados", unidad="% anual")

    def test_reajuste_de_byma_despues_de_un_pago_no_cambia_lo_guardado(self):
        """Obligatorio (Pedro): después del pago del 09/01/2027, BYMA reescribe hacia atrás los cierres de
        diciembre (ajustados por el pago). Las filas de diciembre ya guardadas NO cambian."""
        dic = pd.to_datetime(["2026-12-14", "2026-12-15", "2026-12-16"])
        ene = pd.to_datetime(["2027-01-11", "2027-01-12"])
        cierres_dic = pd.DataFrame({"fecha": dic, "precio": [54.0, 54.2, 54.1]})
        # misma fecha, precio ajustado por el pago (8,24 menos), más los días nuevos posteriores al pago
        reajustados = pd.DataFrame({"fecha": dic.append(ene), "precio": [45.8, 46.0, 45.9, 46.3, 46.1]})
        for flujo_enero in (GD30, GD30[1:]):   # el MAE todavía lista el pago del 09/01 / ya lo sacó
            with self.subTest(lista_pago_hecho=flujo_enero is GD30), tempfile.TemporaryDirectory() as d:
                d = Path(d)
                with mock.patch.object(storage, "DATA_DIR", d), mock.patch.object(storage, "LARGO", d / "l.csv"), \
                        mock.patch.object(storage, "ANCHO", d / "a.csv"):
                    primera = self._correr(T("2026-12-17"), GD30, cierres_dic)
                    self.assertEqual(list(primera["fecha"]), list(dic))
                    storage.actualizar(primera)
                    antes = storage.cargar_largo().set_index("fecha")["valor"]
                    segunda = self._correr(T("2027-01-13"), flujo_enero, reajustados)
                    self.assertEqual(list(segunda["fecha"]), list(ene))   # diciembre no se recalcula
                    storage.actualizar(segunda)
                    despues = storage.cargar_largo().set_index("fecha")["valor"]
                self.assertEqual(list(despues.index), list(dic) + list(ene))
                for f in dic:   # mismos valores que antes del pago (storage puede reescribir el último dígito del
                    # float al releer el CSV: no es un recálculo, el valor es el mismo a 1e-12)
                    self.assertAlmostEqual(despues[f], antes[f], places=12)
                    self.assertAlmostEqual(despues[f], primera.set_index("fecha")["valor"][f], places=12)

    def test_falla_de_byma_deja_la_serie_vacia(self):
        M._CACHE_BONOS.clear()
        with mock.patch.object(fetchers, "fetch_mae_flujofondos_ticker", return_value=ff(GD30)), \
                mock.patch.object(M, "fetch_byma_cierres", side_effect=RuntimeError("HTTP 500")):
            self.assertTrue(M.serie_bono("GD30", "tir").empty)
        self.assertIn("error", M.RESUMEN["bono:GD30"])
        M._CACHE_BONOS.clear()


class TestSpreadDuracion(unittest.TestCase):

    UST = {"6 Mo": pd.DataFrame({"fecha": [T("2026-11-05")], "valor": [4.2]}),
           "1 Yr": pd.DataFrame({"fecha": [T("2026-11-05")], "valor": [4.0]}),
           "2 Yr": pd.DataFrame({"fecha": [T("2026-11-05")], "valor": [5.0]}),
           "3 Yr": pd.DataFrame({"fecha": [T("2026-11-05")], "valor": [6.0]})}

    def _spread(self, md, fecha="2026-11-06"):
        tir = pd.DataFrame({"fecha": [T(fecha)], "valor": [10.0]})
        return M.spread_duracion(tir, pd.DataFrame({"fecha": [T(fecha)], "valor": [md]}), self.UST)

    def test_interpolacion_lineal_en_plazo(self):
        # MD 1,5 entre 1 Yr (4,0) y 2 Yr (5,0) -> 4,5; TIR 10 -> 550 pb. Toma el Treasury del día anterior.
        self.assertAlmostEqual(self._spread(1.5)["valor"].iloc[0], 550.0)
        self.assertAlmostEqual(self._spread(0.75)["valor"].iloc[0], (10 - 4.1) * 100)   # entre 6 Mo y 1 Yr

    def test_fuera_de_rango_usa_el_plazo_extremo(self):
        self.assertAlmostEqual(self._spread(0.2)["valor"].iloc[0], (10 - 4.2) * 100)
        self.assertAlmostEqual(self._spread(4.5)["valor"].iloc[0], (10 - 6.0) * 100)

    def test_treasury_viejo_no_se_arrastra(self):
        self.assertTrue(self._spread(1.5, fecha="2026-11-20").empty)   # más de 5 días sin dato del Tesoro

    def test_yaml_del_spread(self):
        cfg = yaml.safe_load((RAIZ / "indicadores.yaml").read_text(encoding="utf-8"))
        sp = next(i for i in cfg["indicadores_financiera"] if i.get("calculo") == "spread_bono_ust")
        self.assertEqual(sp["nombre"], "Spread GD30 vs. Treasury de igual duración")
        self.assertEqual(sp["ust_plazos"], ["6 Mo", "1 Yr", "2 Yr", "3 Yr"])
        self.assertTrue(all(p in M.H15_SERIE for p in sp["ust_plazos"]))   # todos con respaldo en el H.15
        self.assertFalse(run.es_snapshot_diario(sp))


class TestSinAlertaRezago(unittest.TestCase):

    def test_campo_apaga_la_alerta_de_rezago(self):
        fechas = pd.bdate_range("2026-07-01", "2026-09-01")
        hist = pd.DataFrame({"fecha": fechas, "indicador": "Spread", "valor": 1.0})
        with mock.patch.object(run, "_avisar"), mock.patch.object(run, "hoy_ar", return_value=T("2026-11-08")):
            self.assertEqual([r[0] for r in run.chequear_frescura(hist, [{"nombre": "Spread"}])], ["Spread"])
            self.assertEqual(run.chequear_frescura(hist, [{"nombre": "Spread", "sin_alerta_rezago": True}]), [])

    def test_solo_el_spread_lo_usa(self):
        cfg = yaml.safe_load((RAIZ / "indicadores.yaml").read_text(encoding="utf-8"))
        con = [i["nombre"] for k in ("indicadores", "indicadores_financiera") for i in cfg[k] if i.get("sin_alerta_rezago")]
        self.assertEqual(con, ["Spread GD30 vs. Treasury de igual duración"])
        merval = next(i for i in cfg["indicadores_financiera"] if i["nombre"] == "S&P MERVAL")
        self.assertNotIn("sin_alerta_rezago", merval)   # su alerta sigue aunque tenga aviso


class TestSlugViejoYMuro(unittest.TestCase):

    def test_redireccion_del_slug_viejo(self):
        nombre = "Spread GD30 vs. Treasury de igual duración"
        self.assertEqual(sitio.slug(nombre), "spread-gd30-vs-treasury-de-igual-duracion")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(pagina_home, "DOCS", Path(d)):
            ruta = pagina_home.generar_redireccion("serie/spread-soberano-gd30-vs-ust10y/index.html",
                                                   "../spread-gd30-vs-treasury-de-igual-duracion/")
            html = ruta.read_text(encoding="utf-8")
        self.assertIn('url=../spread-gd30-vs-treasury-de-igual-duracion/', html)
        self.assertIn('location.replace("../spread-gd30-vs-treasury-de-igual-duracion/")', html)

    def test_ancla_vieja_del_tema_lleva_a_la_card_nueva(self):
        nuevo = "spread-gd30-vs-treasury-de-igual-duracion"
        card = dict(i=0, nombre="Spread GD30 vs. Treasury de igual duración", slug=nuevo,
                    slug_anterior="spread-soberano-gd30-vs-ust10y", valor="811", unidad="puntos básicos",
                    frescura='<div class="cf">06/11</div>', mini={"x": ["a"], "u": "pb", "ds": []})
        tema = {"slug": "mercados", "titulo": "Mercados",
                "secciones": [{"titulo": "Renta fija", "items": [card["nombre"]]}]}
        html = D._seccion_tema(tema, [card], {}, [], None, None, {})
        self.assertIn(f'id="{nuevo}"', html)
        self.assertIn('{"spread-soberano-gd30-vs-ust10y": "#%s"}' % nuevo, html)
        self.assertIn("location.replace(m[h])", html)
        # mismo script que las anclas viejas de la home
        self.assertEqual(pagina_home.js_redireccion(), sitio.js_anclas(sitio.REDIRECCION_ANCLAS))
        self.assertEqual(sitio.js_anclas({}), "")
        # una card sin slug_anterior no agrega script
        self.assertNotIn("location.replace", D._seccion_tema(tema, [dict(card, slug_anterior=None)], {}, [], None, None, {}))

    def test_ust_10y_fuera_del_yaml(self):
        cfg = yaml.safe_load((RAIZ / "indicadores.yaml").read_text(encoding="utf-8"))
        todos = [i for k in ("indicadores", "indicadores_financiera") for i in cfg[k]]
        self.assertNotIn("UST 10Y (Treasury)", [i["nombre"] for i in todos])
        self.assertEqual([i["nombre"] for i in todos if i.get("fuente") == "tesoro_ust"], [])

    def test_nombre_viejo_no_queda_en_temas(self):
        cfg = yaml.safe_load((RAIZ / "indicadores.yaml").read_text(encoding="utf-8"))
        items = [it for t in cfg["temas"] for s in t["secciones"] for it in s["items"]]
        self.assertIn("Spread GD30 vs. Treasury de igual duración", items)
        self.assertNotIn("Spread soberano GD30 vs. UST10Y (proxy)", items)

    def test_muro_sin_valor(self):
        c = dict(i=1, nombre="Muro de vencimientos (AL30/GD30/GD35)", slug="muro-de-vencimientos", valor="—",
                 unidad="% VN", sin_valor=True, frescura='<div class="cf">08/11</div>', mini={"x": ["2027"], "u": "%", "ds": []})
        for h in (D._card_compacta(c), D._card_cell(dict(c, maxv="—", minv="—")),
                  D._cabeza_serie(c, None, None, "x", None, {})):
            self.assertNotIn('class="cv"', h)
            self.assertNotIn("% VN</span>", h)
        self.assertIn('class="cv"', D._card_compacta(dict(c, sin_valor=False)))


if __name__ == "__main__":
    unittest.main()

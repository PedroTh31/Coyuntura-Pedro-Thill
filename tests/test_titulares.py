"""Titulares por reglas y variación de la card (titulares.py, Bloque C3). Sin red."""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import titulares as T  # noqa: E402

ANIO = 2026


def mensual(valores, fin="2026-09-01"):
    idx = pd.date_range(end=pd.Timestamp(fin), periods=len(valores), freq="MS")
    return pd.Series(valores, index=idx)


def trimestral(valores, fin="2026-04-01"):
    idx = pd.date_range(end=pd.Timestamp(fin), periods=len(valores), freq="QS")
    return pd.Series(valores, index=idx)


IPC = {"titular_regla": "direccion", "titular_sujeto": "La inflación mensual", "comparar": "anterior"}


class TestDireccionAnterior(unittest.TestCase):

    def test_sube(self):
        self.assertEqual(T.titular(IPC, mensual([2.1, 1.7, 1.9]), "% mensual", ANIO),
                         "La inflación mensual sube a 1,9% en septiembre")

    def test_baja(self):
        self.assertEqual(T.titular(IPC, mensual([1.8, 1.8, 1.7]), "% mensual", ANIO),
                         "La inflación mensual baja a 1,7% en septiembre")

    def test_sin_cambio_al_decimal_mostrado(self):
        self.assertEqual(T.titular(IPC, mensual([2.0, 1.94, 1.9]), "% mensual", ANIO),
                         "La inflación mensual se mantiene en 1,9% en septiembre")

    def test_primer_dato_vuelve_al_nombre(self):
        self.assertIsNone(T.titular(IPC, mensual([1.9]), "% mensual", ANIO))

    def test_sin_regla_vuelve_al_nombre(self):
        self.assertIsNone(T.titular({}, mensual([1.0, 2.0]), "% mensual", ANIO))

    def test_rezago_grave_vuelve_al_nombre(self):
        self.assertIsNone(T.titular(IPC, mensual([1.0, 2.0]), "% mensual", ANIO, grave=True))

    def test_override_manual(self):
        cfg = dict(IPC, titular="Texto fijo")
        self.assertEqual(T.titular(cfg, mensual([1.0, 2.0]), "% mensual", ANIO), "Texto fijo")

    def test_racha_desde_3(self):
        self.assertEqual(T.titular(IPC, mensual([3.0, 2.8, 2.5, 2.2]), "% mensual", ANIO),
                         "La inflación mensual baja a 2,2% en septiembre · 3.º mes seguido de baja")
        self.assertEqual(T.titular(IPC, mensual([3.0, 3.0, 2.8, 2.5]), "% mensual", ANIO),
                         "La inflación mensual baja a 2,5% en septiembre")

    def test_maximo_desde_al_menos_12_meses(self):
        s = mensual([3.5] + [2.0] * 12 + [3.0])
        self.assertEqual(T.titular(IPC, s, "% mensual", ANIO),
                         "La inflación mensual sube a 3,0% en septiembre · Máximo desde agosto de 2025")

    def test_empate_con_maximo_no_se_anuncia(self):
        s = mensual([3.0] + [2.0] * 12 + [3.0])
        self.assertEqual(T.titular(IPC, s, "% mensual", ANIO), "La inflación mensual sube a 3,0% en septiembre")

    def test_maximo_reciente_no_se_anuncia(self):
        self.assertEqual(T.titular(IPC, mensual([2.0, 2.1, 1.7, 1.9]), "% mensual", ANIO),
                         "La inflación mensual sube a 1,9% en septiembre")

    def test_mes_de_otro_anio_lleva_el_anio(self):
        self.assertEqual(T.titular(IPC, mensual([1.0, 2.0], fin="2025-12-01"), "% mensual", ANIO),
                         "La inflación mensual sube a 2,0% en diciembre de 2025")

    def test_indice_usa_variacion(self):
        cfg = {"titular_regla": "direccion", "titular_sujeto": "El salario real", "comparar": "anterior"}
        self.assertEqual(T.titular(cfg, mensual([78.21, 79.03]), "índice base 100", ANIO),
                         "El salario real sube 1,0% en septiembre")

    def test_diaria_con_formato_y_plural(self):
        cfg = {"titular_regla": "direccion", "titular_sujeto": "Las reservas", "titular_formato": "USD {} M"}
        s = pd.Series([50460.0, 50298.0], index=pd.to_datetime(["2026-11-05", "2026-11-06"]))
        self.assertEqual(T.titular(cfg, s, "millones de USD", ANIO),
                         "Las reservas bajan a USD 50.298 M el 06/11")


class TestDireccionInteranual(unittest.TestCase):
    CFG = {"titular_regla": "direccion", "titular_sujeto": "El desempleo"}

    def test_trimestral_lleva_el_anio_y_compara_contra_un_anio_antes(self):
        s = trimestral([7.9, 7.6, 6.6, 7.5, 7.8, 7.9])
        self.assertEqual(T.titular(self.CFG, s, "% de la PEA", ANIO),
                         "El desempleo del 2.º trimestre de 2026 fue 7,9%, 0,3 pp más que un año antes")

    def test_racha_interanual(self):
        s = mensual([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.5, 1.5, 1.5])
        cfg = {"titular_regla": "direccion", "titular_sujeto": "La inflación núcleo"}
        self.assertEqual(T.titular(cfg, s, "% mensual", ANIO),
                         "La inflación núcleo de septiembre fue 1,5%, 0,5 pp más que un año antes · "
                         "3.º mes seguido por encima del año anterior")

    def test_empate_interanual(self):
        s = mensual([2.0] * 13)
        cfg = {"titular_regla": "direccion", "titular_sujeto": "La inflación núcleo"}
        self.assertEqual(T.titular(cfg, s, "% mensual", ANIO),
                         "La inflación núcleo de septiembre fue 2,0%, igual que un año antes")

    def test_nivel_en_porcentaje_con_genero(self):
        s = mensual([100.0] * 12 + [145.2])
        cfg = {"titular_regla": "direccion", "titular_sujeto": "La base monetaria"}
        self.assertEqual(T.titular(cfg, s, "millones de $", ANIO),
                         "La base monetaria de septiembre está 45,2% por encima de la de un año antes")
        cfg = {"titular_regla": "direccion", "titular_sujeto": "Los préstamos"}
        self.assertEqual(T.titular(cfg, s, "millones de $", ANIO),
                         "Los préstamos de septiembre están 45,2% por encima de los de un año antes")

    def test_sin_mismo_periodo_del_anio_anterior_vuelve_al_nombre(self):
        self.assertIsNone(T.titular(self.CFG, trimestral([7.0, 7.5, 7.9]), "% de la PEA", ANIO))

    def test_sin_maximo_desde_en_series_estacionales(self):   # D12
        s = mensual([5.0] + [1.0] * 12 + [4.0])
        cfg = {"titular_regla": "direccion", "titular_sujeto": "La inflación núcleo"}
        self.assertNotIn("Máximo", T.titular(cfg, s, "% mensual", ANIO))

    def test_excepcion_explicita_comparar_anterior(self):
        s = mensual([2.1] + [2.0] * 11 + [1.7, 1.9])
        self.assertEqual(T.titular(IPC, s, "% mensual", ANIO), "La inflación mensual sube a 1,9% en septiembre")


class TestRachas(unittest.TestCase):   # decisión de Pedro (Bloque C)

    def test_nominal_en_pesos_sin_racha_de_direccion_pero_con_racha_de_signo(self):
        cfg = {"titular_regla": "direccion", "titular_sujeto": "Los préstamos al sector privado",
               "nominal_pesos": True}
        s = mensual([100.0 * 1.03 ** i for i in range(30)])
        self.assertEqual(T.titular(cfg, s, "millones de $", ANIO),
                         "Los préstamos al sector privado de septiembre están 42,6% por encima de los de un año antes")
        cfg_saldo = {"titular_regla": "saldo", "titular_sujeto": "financiero", "titular_formato": "$ {} M",
                     "nominal_pesos": True}
        self.assertEqual(T.titular(cfg_saldo, mensual([10.0, 20.0, 30.0, 40.0]), "millones de $", ANIO),
                         "Superávit financiero de $ 40 M en septiembre: 4.º mes seguido")

    def test_racha_de_direccion_hasta_24_periodos(self):
        cfg = {"titular_regla": "direccion", "titular_sujeto": "Las exportaciones"}
        s = mensual([100.0] * 12 + [100.0 * 1.01 ** i for i in range(1, 25)])   # 24 meses por encima
        self.assertTrue(T.titular(cfg, s, "millones de USD", ANIO).endswith(
            "· 24.º mes seguido por encima del año anterior"))

    def test_racha_de_direccion_de_mas_de_24_periodos_se_omite(self):
        cfg = {"titular_regla": "direccion", "titular_sujeto": "El PBI"}
        s = trimestral([100.0 * 1.1 ** i for i in range(30)])
        self.assertEqual(T.titular(cfg, s, "millones de USD", ANIO),
                         "El PBI del 2.º trimestre de 2026 está 46,4% por encima del de un año antes")

    def test_racha_de_signo_sin_tope(self):
        cfg = {"titular_regla": "saldo", "titular_sujeto": "comercial", "titular_formato": "USD {} M"}
        self.assertEqual(T.titular(cfg, mensual([100.0] * 33), "millones de USD", ANIO),
                         "Superávit comercial de USD 100 M en septiembre: 33.º mes seguido")
        cfg = {"titular_regla": "signo", "titular_sujeto": "La tasa real"}
        self.assertEqual(T.titular(cfg, mensual([-1.0] * 30), "% anual", ANIO),
                         "La tasa real sigue negativa: −1,0% en septiembre (30.º mes seguido)")


class TestSignoSaldoAporte(unittest.TestCase):

    def test_signo_sigue_negativa(self):
        cfg = {"titular_regla": "signo", "titular_sujeto": "La tasa real", "comparar": "anterior"}
        s = mensual([3.3, -0.9, -4.4, -1.8, -3.3, -7.2, -10.0, -11.6, -11.6, -12.2, -9.9, -9.65][-12:])
        self.assertEqual(T.titular(cfg, s, "% anual", ANIO),
                         "La tasa real sigue negativa: −9,7% en septiembre (11.º mes seguido)")

    def test_signo_pasa_a_ser_y_genero(self):
        cfg = {"titular_regla": "signo", "titular_sujeto": "El resultado"}
        self.assertEqual(T.titular(cfg, mensual([1.0, -2.0]), "%", ANIO),
                         "El resultado pasa a ser negativo: −2,0% en septiembre")

    def test_saldo(self):
        cfg = {"titular_regla": "saldo", "titular_sujeto": "comercial", "titular_formato": "USD {} M"}
        self.assertEqual(T.titular(cfg, mensual([906.9, 2098.1, 2186.6], fin="2026-08-01"), "millones de USD", ANIO),
                         "Superávit comercial de USD 2.187 M en agosto: 3.º mes seguido")
        self.assertEqual(T.titular(cfg, mensual([906.9, -500.0], fin="2026-08-01"), "millones de USD", ANIO),
                         "Déficit comercial de USD 500 M en agosto")

    def test_aporte(self):
        cfg = {"titular_regla": "aporte", "titular_sujeto": "de la inflación"}
        self.assertEqual(T.titular_aporte(cfg, "Alimentos y bebidas no alcohólicas", 0.541, "2026-09-01", ANIO),
                         "Alimentos y bebidas no alcohólicas aportó 0,54 pp de la inflación de septiembre")
        self.assertIsNone(T.titular(cfg, mensual([1.0, 2.0]), "p.p.", ANIO))   # se resuelve aparte


class TestCambioDeLaCard(unittest.TestCase):

    def test_tasa_en_pp_contra_el_mes_anterior(self):
        self.assertEqual(T.cambio(mensual([1.7, 1.9]), "% mensual", "anterior", "mensual"),
                         {"signo": 1, "texto": "+0,2 pp", "ref": "ago-26"})

    def test_interanual_contra_el_mismo_mes(self):
        c = T.cambio(mensual([100.0] + [90.0] * 11 + [101.6]), "índice", "interanual", "mensual")
        self.assertEqual(c, {"signo": 1, "texto": "+1,6%", "ref": "sep-25"})

    def test_trimestral(self):
        c = T.cambio(trimestral([7.6, 6.6, 7.5, 7.8, 7.9]), "% de la PEA", "interanual", "trimestral")
        self.assertEqual(c, {"signo": 1, "texto": "+0,3 pp", "ref": "2T-25"})

    def test_saldo_que_cruza_cero_usa_diferencia(self):
        c = T.cambio(mensual([-100.0, 50.0]), "millones de USD", "anterior", "mensual")
        self.assertEqual(c["texto"], "+150")

    def test_sin_cambio(self):
        self.assertEqual(T.cambio(mensual([1.92, 1.9]), "% mensual", "anterior", "mensual")["signo"], 0)

    def test_sin_dato_de_comparacion(self):
        self.assertIsNone(T.cambio(mensual([1.0]), "%", "anterior", "mensual"))
        self.assertIsNone(T.cambio(mensual([1.0, 2.0]), "%", "interanual", "mensual"))


class TestAuxiliares(unittest.TestCase):

    def test_frecuencia(self):
        self.assertEqual(T.frecuencia(mensual([1, 2, 3]).index), "mensual")
        self.assertEqual(T.frecuencia(trimestral([1, 2, 3]).index), "trimestral")
        self.assertEqual(T.frecuencia(pd.date_range("2026-01-01", periods=10, freq="B")), "diaria")

    def test_comparar_por_defecto(self):
        self.assertEqual(T.comparar_de({}, "diaria"), "anterior")
        self.assertEqual(T.comparar_de({}, "mensual"), "interanual")
        self.assertEqual(T.comparar_de({}, "trimestral"), "interanual")
        self.assertEqual(T.comparar_de({"comparar": "anterior"}, "mensual"), "anterior")

    def test_formato_argentino_y_decimales_por_unidad(self):
        self.assertEqual(T.fmt_valor(1.904, "% mensual"), "1,9")
        self.assertEqual(T.fmt_valor(-9.65, "% anual"), "−9,7")
        self.assertEqual(T.fmt_valor(1.92, "p.p."), "1,92")
        self.assertEqual(T.fmt_valor(50298.4, "millones de USD"), "50.298")
        self.assertEqual(T.fmt_valor(94.48, "índice"), "94,5")


if __name__ == "__main__":
    unittest.main()

"""Línea de frescura de las cards (Bloque B2, frescura.py). Sin red: contexto sintético."""
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import calendario_indec as C  # noqa: E402
import frescura as F  # noqa: E402

FERIADOS = {date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 23)}


def _pubs(*filas):
    return [{"fecha": f, "hora": h, "periodo": F.parsear_periodo_indec(p)} for f, h, p in filas]


def ctx(ahora):
    return F.Contexto(
        ahora=ahora, no_habiles=FERIADOS,
        pub_de_indicador={"IPC": "ipc", "Expo": "ica", "Desempleo": "eph"},
        fechas={"ipc": _pubs(("2026-10-14", "16:00", "Septiembre de 2026"),
                             ("2026-11-12", "16:00", "Octubre de 2026"),
                             ("2026-12-15", "16:00", "Noviembre de 2026")),
                "ica": _pubs(("2026-10-19", "16:00", "Septiembre de 2026"),
                             ("2026-11-19", "16:00", "Octubre de 2026")),
                "eph": _pubs(("2026-09-18", "16:00", "Segundo trimestre de 2026"),
                             ("2026-12-18", "16:00", "Tercer trimestre de 2026"))})


def mensual(desde, hasta, fin_de_mes=False):
    return pd.Series(pd.date_range(desde, hasta, freq="ME" if fin_de_mes else "MS"))


def linea(nombre, fechas, ahora, **ind):
    f = F.calcular(dict(nombre=nombre, **ind), nombre, fechas, ctx(ahora))
    return f, F.html_linea(f)


SAB = datetime(2026, 11, 7, 6, 30)


class TestEstados(unittest.TestCase):

    def test_al_dia(self):
        f, h = linea("IPC", mensual("2025-01-01", "2026-09-01"), SAB)
        self.assertEqual((f.periodo, f.estado, f.detalle), ("sep-26", "al_dia", "próximo 12/11, 16 h"))
        self.assertIn('<span class="ok">✓ al día</span>', h)
        self.assertNotIn("grave", h)

    def test_al_dia_con_fechas_a_fin_de_mes(self):
        f, _ = linea("IPC", mensual("2025-01-01", "2026-09-30", fin_de_mes=True), SAB)
        self.assertEqual((f.periodo, f.estado), ("sep-26", "al_dia"))

    def test_el_dia_de_la_publicacion_antes_de_la_hora(self):
        f, _ = linea("IPC", mensual("2025-01-01", "2026-09-01"), datetime(2026, 11, 12, 6, 30))
        self.assertEqual((f.estado, f.detalle), ("al_dia", "próximo hoy, 16 h"))

    def test_publicado_dentro_del_margen(self):
        # Publicado el jueves 12/11 a las 16: el viernes 13 (1 día hábil después) todavía es margen.
        for ahora in (datetime(2026, 11, 12, 18, 0), datetime(2026, 11, 13, 6, 30)):
            f, h = linea("IPC", mensual("2025-01-01", "2026-09-01"), ahora)
            self.assertEqual(f.estado, "publicado")
            self.assertEqual(f.detalle, "oct-26 publicado el 12/11, entra en la próxima actualización")
            self.assertNotIn("✓", h)
            self.assertNotIn("⚠", h)

    def test_atrasado_pasado_el_margen(self):
        f, _ = linea("IPC", mensual("2025-01-01", "2026-09-01"), datetime(2026, 11, 16, 6, 30))
        self.assertEqual((f.estado, f.detalle), ("atrasado", "oct-26 se publicó el 12/11"))

    def test_margen_en_dias_habiles(self):
        # ICA de septiembre publicado el lunes 19/10: margen hasta el martes 20; el miércoles, atrasado.
        self.assertEqual(linea("Expo", mensual("2025-01-01", "2026-08-01"), datetime(2026, 10, 20, 6, 30))[0].estado,
                         "publicado")
        f, h = linea("Expo", mensual("2025-01-01", "2026-08-01"), SAB)
        self.assertEqual((f.periodo, f.estado, f.detalle), ("ago-26", "atrasado", "sep-26 se publicó el 19/10"))
        self.assertIn('<span class="atr">⚠ atrasado</span>', h)
        # Con feriados en el medio: publicado el viernes 06/11 -> margen hasta el miércoles 11/11.
        self.assertEqual(C.sumar_dias_habiles(date(2026, 11, 6), 1, FERIADOS), date(2026, 11, 11))

    def test_atrasado_dos_periodos_muestra_el_mas_nuevo(self):
        f, _ = linea("Expo", mensual("2025-01-01", "2026-08-01"), datetime(2026, 11, 25, 6, 30))
        self.assertEqual(f.detalle, "oct-26 se publicó el 19/11")

    def test_trimestral(self):
        fechas = pd.Series(pd.date_range("2023-01-01", "2026-04-01", freq="QS"))
        f, _ = linea("Desempleo", fechas, SAB)
        self.assertEqual((f.periodo, f.estado, f.detalle, f.grave), ("2T-26", "al_dia", "próximo 18/12, 16 h", None))

    def test_sin_calendario_oficial(self):
        f, h = linea("Base monetaria", mensual("2025-01-01", "2026-08-01"), SAB)
        self.assertEqual((f.estado, f.detalle), ("sin_calendario", "próximo: sin calendario oficial"))
        self.assertEqual(h.split(">", 1)[1], '<span class="per">ago-26</span> · próximo: sin calendario oficial</div>')

    def test_diaria_proximo_dia_habil_estimado(self):
        fechas = pd.Series(pd.bdate_range("2026-01-01", "2026-11-04"))
        f, _ = linea("TAMAR", fechas, SAB)   # sábado; lunes 9 y martes 10 son feriados
        self.assertEqual((f.periodo, f.estado, f.detalle), ("04/11", "diaria", "próximo 11/11 (estimado)"))

    def test_caso_sin_cache_del_calendario(self):
        c = ctx(SAB)
        c.fechas = None
        f = F.calcular({"nombre": "IPC"}, "IPC", mensual("2025-01-01", "2026-09-01"), c)
        self.assertEqual((f.estado, f.detalle), ("sin_fecha", ""))
        self.assertEqual(F.html_linea(f).split(">", 1)[1], '<span class="per">sep-26</span></div>')


class TestRezagoGrave(unittest.TestCase):

    def test_adelantos_frenados_en_mayo(self):
        f, h = linea("Adelantos", mensual("2020-01-01", "2026-05-01"), SAB)
        self.assertEqual(f.grave, "sin datos nuevos hace 5 meses")
        self.assertIn('class="cf grave"', h)
        self.assertIn("⏸ <span class=\"per\">may-26</span> · sin datos nuevos hace 5 meses · sin calendario oficial", h)

    def test_meses_y_dias_desde_el_cierre_del_periodo(self):
        # may-26 cierra el 31/05: al 07/11 son 160 días y 5 meses completos (no 190 / 6, desde el 01/05).
        f, _ = linea("Adelantos", mensual("2020-01-01", "2026-05-01"), SAB)
        self.assertIn("160 días", f.tooltip)
        self.assertEqual(f.grave, "sin datos nuevos hace 5 meses")
        self.assertEqual(linea("Adelantos", mensual("2020-01-01", "2026-05-01"), datetime(2026, 12, 1))[0].grave,
                         "sin datos nuevos hace 6 meses")

    def test_umbral_mensual_contado_desde_el_cierre_del_periodo(self):
        # jul-26 cierra el 31/07: 98 días al 06/11 (grave); ago-26 cierra el 31/08: 68 días (no).
        self.assertIsNotNone(linea("X", mensual("2025-01-01", "2026-07-01"), datetime(2026, 11, 6))[0].grave)
        self.assertIsNone(linea("X", mensual("2025-01-01", "2026-08-01"), datetime(2026, 11, 6))[0].grave)

    def test_trimestral_tiene_un_trimestre_de_tolerancia(self):
        fechas = pd.Series(pd.date_range("2023-01-01", "2026-04-01", freq="QS"))   # 2T-26, cierra 30/06
        self.assertIsNone(linea("Desempleo", fechas, datetime(2026, 12, 17))[0].grave)       # 170 días
        self.assertIsNotNone(linea("Empleo SIPA", fechas, datetime(2027, 1, 5))[0].grave)    # 189 días

    def test_rezago_normal_dias_pone_piso(self):
        fechas = pd.Series(pd.bdate_range("2025-01-01", "2026-06-30"))
        self.assertIsNotNone(linea("TCR", fechas, SAB)[0].grave)
        self.assertIsNone(linea("TCR", fechas, SAB, rezago_normal_dias=210)[0].grave)

    def test_diaria_frenada_muestra_el_anio(self):
        fechas = pd.Series(pd.bdate_range("2025-01-01", "2026-01-28"))
        f, h = linea("TCR", fechas, SAB)
        self.assertEqual((f.periodo, f.grave), ("28/01/26", "sin datos nuevos hace 9 meses"))
        self.assertNotIn("estimado", h)

    def test_atrasado_y_grave_a_la_vez(self):
        f, h = linea("Expo", mensual("2025-01-01", "2026-06-01"), SAB)
        self.assertIsNotNone(f.grave)
        self.assertIn("⚠ atrasado", h)
        self.assertIn("sep-26 se publicó el 19/10", h)


class TestCardsMixtas(unittest.TestCase):

    def _estados(self, **series):
        return [(n, linea(n, fechas, SAB)[0]) for n, fechas in series.items()]

    def test_mixta_resumen_al_dia_y_componente_frenado(self):
        est = self._estados(Adelantos=mensual("2020-01-01", "2026-05-01"), IPC=mensual("2020-01-01", "2026-09-01"))
        h = F.html_card(est, "IPC")
        self.assertTrue(h.startswith('<div class="cf" '))
        self.assertIn("✓ al día", h)
        self.assertIn('⏸ Adelantos: <span class="per">may-26</span> · sin datos nuevos hace 5 meses', h)

    def test_mixta_resumen_frenado_usa_la_otra_serie_para_la_linea_normal(self):
        est = self._estados(**{"Deuda/PBI": mensual("2020-01-01", "2026-09-01"),
                               "TCR": pd.Series(pd.bdate_range("2025-01-01", "2026-01-28"))})
        h = F.html_card(est, "TCR")
        self.assertIn('<span class="per">sep-26</span>', h.split("</div>")[0])
        self.assertIn("⏸ TCR: ", h)

    def test_todas_frenadas_una_sola_franja_sin_nombres(self):
        est = self._estados(A=mensual("2020-01-01", "2026-05-01"), B=mensual("2020-01-01", "2026-05-01"))
        h = F.html_card(est, "A")
        self.assertEqual(h.count('class="cf'), 1)
        self.assertIn('⏸ <span class="per">may-26</span>', h)

    def test_frenadas_en_el_mismo_periodo_comparten_franja(self):
        est = self._estados(A=mensual("2020-01-01", "2026-05-01"), B=mensual("2020-01-01", "2026-05-01"),
                            C=mensual("2020-01-01", "2026-09-01"))
        h = F.html_card(est, "C")
        self.assertEqual(h.count('class="cf grave"'), 1)
        self.assertIn("⏸ A y B: ", h)

    def test_una_sola_serie_frenada_no_lleva_nombre(self):
        h = F.html_card(self._estados(Adelantos=mensual("2020-01-01", "2026-05-01")), "Adelantos")
        self.assertNotIn("Adelantos:", h)


class TestPeriodosIndec(unittest.TestCase):

    def test_parseo(self):
        self.assertEqual(F.parsear_periodo_indec("Octubre de 2026"), pd.Period("2026-10", "M"))
        self.assertEqual(F.parsear_periodo_indec("Tercer trimestre de 2026"), pd.Period("2026Q3", "Q"))
        for malo in ("Octubre 2026", "Quinto trimestre de 2026", "Año 2026"):
            with self.subTest(malo), self.assertRaises(ValueError):
                F.parsear_periodo_indec(malo)

    def test_cache_real_se_parsea_entera(self):
        cfg = C.cargar_config()
        cache = C.cargar_cache()
        pubs = [C._de_dict(d) for mes in cache["meses"].values() for d in mes["publicaciones"]]
        asignadas, errores = C.asignar(pubs, cfg)
        self.assertEqual(errores, [])
        for lista in asignadas.values():
            for d in lista:
                F.parsear_periodo_indec(d["periodo"])


if __name__ == "__main__":
    unittest.main()

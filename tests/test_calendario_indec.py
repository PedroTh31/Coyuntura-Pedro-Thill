"""Parser del calendario del INDEC (calendario_indec.parsear_mes). Sin red: HTML sintético con la
misma estructura que devuelve FiltrosCalendario/mes/{Mes}-{AAAA}/0 (verificada el 07/11/2026)."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import calendario_indec as C  # noqa: E402


def _pub(titulo, hora="16:00hs"):
    return (f'<div class="col-xl-8"><div class="cal-content text-calendario">\n  {titulo}\n</div></div>'
            f'<div class="col-xl-2 col-6"><div class="cal-content text-calendario text-center">\n\n  {hora}\n</div></div>'
            '<div class="cal-content text-center"><img class="img-flecha " /></div>')


def _dia(nro, nombre, *pubs):
    return (f'<div class="col-xl-3"><div class="text-center"><div class="nro-dia">{nro}</div>\n\n'
            f'<div class="dia">{nombre}</div></div></div><div class="col-xl-9">{"".join(pubs)}</div>'
            '<div class="col-12"><hr class="cal-separator2" /></div>')


def _mes(encabezado, *dias):
    return f'<div class="mes-ano">{encabezado}</div>' + "".join(dias)


NOV = _mes("Noviembre 2026",
           _dia(12, "JUEVES", _pub("&#205;ndice de precios al consumidor (IPC). Cobertura nacional. Octubre de 2026"),
                _pub("Valorizaci&#243;n mensual de la CBA y CBT. Octubre de 2026")),
           _dia(24, "MARTES", _pub("Estimador mensual de actividad econ&#243;mica (EMAE). Septiembre de 2026")))
VACIO = "No hay publicaciones en la fecha seleccionada. <script>$(document)</script>"


class TestParsearMes(unittest.TestCase):

    def test_mes_normal(self):
        pubs = C.parsear_mes(NOV, 2026, 11, exigir_publicaciones=True)
        self.assertEqual(len(pubs), 3)
        self.assertEqual(pubs[0], C.Publicacion(date(2026, 11, 12), "16:00",
                                                "Índice de precios al consumidor (IPC). Cobertura nacional. Octubre de 2026"))
        self.assertEqual(pubs[2].fecha, date(2026, 11, 24))

    def test_mes_sin_publicaciones(self):
        self.assertEqual(C.parsear_mes(VACIO, 2027, 12), [])
        with self.assertRaises(C.CalendarioFormatoError):
            C.parsear_mes(VACIO, 2027, 12, exigir_publicaciones=True)

    def test_fallas_ruidosas_si_cambia_el_formato(self):
        casos = {
            "sin encabezado": NOV.replace('class="mes-ano"', 'class="titulo-mes"'),
            "otro mes": NOV.replace("Noviembre 2026", "Octubre 2026"),
            "sin bloques de día": _mes("Noviembre 2026"),
            "día ilegible": NOV.replace('<div class="nro-dia">12</div>', '<div class="nro-dia">doce</div>'),
            "nombre de día raro": NOV.replace(">JUEVES<", ">JUE<"),
            "título sin horario": NOV.replace('text-calendario text-center', 'text-hora', 1),
            "horario inválido": NOV.replace("16:00hs", "a confirmar", 1),
            "día inexistente": NOV.replace('<div class="nro-dia">24</div>', '<div class="nro-dia">31</div>'),
            "HTML desconocido": "<html><body>Mantenimiento</body></html>",
        }
        for nombre, html in casos.items():
            with self.subTest(nombre), self.assertRaises((C.CalendarioFormatoError, ValueError)):
                C.parsear_mes(html, 2026, 11)


if __name__ == "__main__":
    unittest.main()

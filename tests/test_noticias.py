"""
Tests de regresión del filtro de noticias del mail (Bloque 3 de PROMPT_mail_v3.md).

Cada caso es una nota REAL (título y bajada textuales, tomados de los feeds del
2026-11-05): los que "no tienen que pasar" son notas que se colaron en el mail y los que
"tienen que seguir pasando" protegen contra arreglar un caso rompiendo otro. Regla del
Bloque 3: todo ajuste de keywords arranca agregando acá el ejemplo real que lo justifica.

Correr con:  python -m unittest discover tests
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import enviar_mail as em  # noqa: E402

# Se colaron en el mail del 2026-11-05: Banco Central DE PARAGUAY, sin ninguna mención
# a Argentina -- 'banco central' contaba como contexto argentino.
PARAGUAY = [
    ('Instituciones paraguayas pidieron calma ante los rumores de nuevas intervenciones financieras',
     'La Asociación de Bancos del Paraguay, el Banco Central y legisladores salieron a contener el pánico bancario desatado tras la resolución de Ueno Bank, que dejó a casi 3 millones de ahorristas sin acceso a sus depósitos'),
    ('La Fiscalía de Paraguay pidió prisión preventiva para el fundador del intervenido Ueno Bank',
     'Miguel Vásquez, mayor accionista de la entidad clausurada por el Banco Central, compareció junto a otros siete directivos ante el Ministerio Público'),
    ('Santiago Peña anunció cambios en el Banco Central y una ley de emergencia para devolver los ahorros del Ueno Bank',
     'El mandatario paraguayo prometió pagos a los depositantes desde esta semana y advirtió que los responsables del colapso bancario ya responden ante la justicia'),
    ('Qué pasó en Paraguay con la intervención del Ueno Bank: ¿Es un corralito?',
     'La crisis de Ueno Bank provocó la detención de ocho ejecutivos y la renuncia del titular del Banco Central; hay preocupación por los depósitos de los ahorristas y fondos jubilatorios por US$380 millones'),
    ('El Senado de Paraguay aprobó adelantar el pago a los ahorristas de Ueno Bank en 24 horas: cómo cobrarán',
     'La Cámara Alta modificó la ley de garantía de depósitos para habilitar un anticipo de hasta 40 salarios mínimos. El Banco Central dividió a los depositantes en tres tramos, aunque aún faltan precisar fechas y requisitos'),
]

# Mismo error con el banco central de México (no llegó al mail por el corte en 6, pero pasaba).
MEXICO = [
    ('Analistas ven más riesgos que beneficios si Banxico decide recortar la tasa de interés',
     'Un ajuste a la baja en la tasa de interés se tomaría como sorpresivo en un momento en el que se desvanece el argumento del banco central de la holgura económica.'),
]

# Notas argentinas legítimas. La primera depende SOLO de 'banco central' como contexto argentino
# (por eso no se borra 'banco central' de la lista); la tercera menciona Brasil pero tiene
# contexto argentino propio. Las 4 últimas estaban en el mail del 2026-11-05.
AR_LEGITIMAS = [
    ('Tras dos días sin sumar divisas, el Banco Central volvió a comprar dólares',
     'La autoridad monetaria adquirió USD 9 millones luego de un comienzo de noviembre sin compras oficiales. Las reservas internacionales se acercaron a USD 50.500 millones'),
    ('La visita del Papa dejará hasta US$ 270 millones en la Argentina y ya impacta en el turismo',
     'Miles de turistas se preparan para un evento histórico con reservas colmadas, promociones y ciudades en alerta ante una ola de visitantes'),
    ('La incertidumbre política aleja a los inversores de los activos argentinos y el riesgo país alcanzó un nuevo máximo anual',
     'Los bonos soberanos no pudieron acoplarse al rally global de los mercados. A las dudas que generó la elección de Brasil ahora se suma la incertidumbre por el futuro respaldo de Estados Unidos al Gobierno en materia…'),
    ('Reactivar sin hacer un “plan platita”: qué medidas anunció el Gobierno para impulsar la economía y sostener el superávit',
     'Desde agosto, el ministro de Economía, Luis Caputo, encabezó una serie de anuncios para impulsar el nivel de actividad. Las nuevas iniciativas en las que trabaja el Banco Central y la Comisión Nacional de Valores…'),
    ('Fin del serrucho: el Santander proyecta cuatro años seguidos de crecimiento para Argentina y un "amortiguador" frente a los shocks',
     'En un contexto global condicionado por mayor deuda pública e inflación, los analistas sostienen que el país contará con un "colchón" inédito de dólares. Por qué Argentina es una "rara avis" en un contexto volátil.'),
]

# Notas internacionales sobre otro país (Brasil, México) que pasan el filtro internacional: la
# lista de 'otros países' se aplica SOLO en evaluar_ar, nunca en el filtro internacional.
INTL_OTRO_PAIS = [
    ('Telefónica Brasil negocia la compra del operador de fibra Vero en medio de la consolidación del sector',
     'Vivo busca ampliar su red fija en el país, aunque la compañía brasileña arrastra un fuerte endeudamiento'),
    ('Quién es Bobby Pulido, la estrella de la música tejana que devolvió a los demócratas un condado de Texas fronterizo con México',
     'Su triunfo se suma a la ola que este martes llevó a los demócratas a hacerse con el control de ambas cámaras del Congreso de Estados Unidos y dejó victorias clave en Texas, incluidas la de Gina Hinojosa como gobernadora…'),
]


class TestFiltroArgentina(unittest.TestCase):
    def test_paraguay_no_entra(self):
        for titulo, bajada in PARAGUAY:
            with self.subTest(titulo=titulo):
                entra, regla, detalle = em.evaluar_ar(titulo, bajada)
                self.assertFalse(entra, f"entró por {regla}: {detalle}")
                self.assertEqual(regla, "banco_central_otro_pais")

    def test_mexico_no_entra(self):
        for titulo, bajada in MEXICO:
            with self.subTest(titulo=titulo):
                entra, regla, detalle = em.evaluar_ar(titulo, bajada)
                self.assertFalse(entra, f"entró por {regla}: {detalle}")
                self.assertEqual(regla, "banco_central_otro_pais")

    def test_argentinas_legitimas_siguen_entrando(self):
        for titulo, bajada in AR_LEGITIMAS:
            with self.subTest(titulo=titulo):
                entra, regla, detalle = em.evaluar_ar(titulo, bajada)
                self.assertTrue(entra, f"quedó afuera por {regla}: {detalle}")

    def test_mexico_con_tilde(self):
        # "mexic" tiene que reconocer "México" (con tilde) además de "mexicano".
        entra, regla, _ = em.evaluar_ar("El Banco Central de México subió la tasa de interés", "")
        self.assertEqual((entra, regla), (False, "banco_central_otro_pais"))


class TestFiltroInternacional(unittest.TestCase):
    def test_notas_de_otro_pais_siguen_pasando(self):
        for titulo, bajada in INTL_OTRO_PAIS:
            with self.subTest(titulo=titulo):
                entra, regla, detalle = em.evaluar_intl(titulo, bajada)
                self.assertTrue(entra, f"quedó afuera por {regla}: {detalle}")


class TestLogNoticias(unittest.TestCase):
    def test_conserva_solo_14_dias(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = em.LOG_NOTICIAS
            em.LOG_NOTICIAS = Path(tmp) / "noticias_log.jsonl"
            try:
                ahora = datetime.now(em.ZONA_AR)
                viejas = [{"corrida": (ahora - timedelta(days=d)).isoformat(timespec="seconds"), "titulo": f"hace {d} días"}
                          for d in (20, 14, 13, 1)]
                em.LOG_NOTICIAS.write_text("\n".join(json.dumps(v) for v in viejas) + "\nlinea corrupta\n", encoding="utf-8")
                em.escribir_log_noticias([dict(bloque="ar", titulo="hoy", fuente="x", link="#", entro=True, regla="entra", detalle=None)])
                titulos = [json.loads(l)["titulo"] for l in em.LOG_NOTICIAS.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(titulos, ["hace 13 días", "hace 1 días", "hoy"])
            finally:
                em.LOG_NOTICIAS = original


if __name__ == "__main__":
    unittest.main()

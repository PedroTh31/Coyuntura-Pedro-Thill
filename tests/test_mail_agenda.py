"""Secciones del Bloque B3 en el mail diario (mail_agenda.py + enviar_mail.armar_html). Sin red."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import enviar_mail as M  # noqa: E402
import mail_agenda as MA  # noqa: E402

URL = "https://ejemplo/"


def _pub(periodo, estado="al_dia", **kw):
    base = {"nombre_corto": "IPC", "periodo": periodo, "titulo": "IPC de septiembre", "estado": estado,
            "linea": "sep-26 · ✓ al día · próximo 12/11, 16 h", "titulo_publicado": "IPC de septiembre",
            "publicado": "13/10, 16 h", "fuente": "INDEC", "ancla": "precios",
            "apertura": {"titular": "Inflación de septiembre: 1,9% mensual", "detalle": None,
                         "filas": [{"etiqueta": "Mensual", "valor": "1,9%", "ref": "agosto 1,7%", "var": "▲ 0,2 pp"}]}}
    base.update(kw)
    return base


def _grave(n, dias):
    return {"clave": f"{n}|may-26", "nombre": n, "texto": f"⏸ {n}: may-26 · sin datos nuevos hace 5 meses", "dias": dias}


def uc(fecha="2026-11-11", pubs=None, atrasados=None, graves=None, **cal):
    calendario = {"fecha": fecha, "estado": "ok", "bajado": None, "feriado_hoy": None, "primer_habil_semana": False,
                  "hoy": [], "semana": [{"dia": "jue 12/11", "hora": "16 h", "titulos": ["IPC de octubre"]}],
                  "hasta": "mar 17/11", "proxima": None}
    calendario.update(cal)
    return {"fecha": fecha, "agenda": {"calendario": calendario, "publicaciones": pubs or {},
                                       "atrasados": atrasados or [], "graves": graves or []}}


class TestSeleccion(unittest.TestCase):

    def test_primer_envio_inicializa_sin_anunciar(self):
        vista, est = MA.seleccionar(uc(pubs={"ipc": _pub("2026-09")}), "2026-11-11", {})
        self.assertEqual(vista["nuevos"], [])
        self.assertEqual(est["periodos_anunciados"], {"ipc": "2026-09"})

    def test_dato_nuevo_una_sola_vez(self):
        u = uc(fecha="2026-11-13", pubs={"ipc": _pub("2026-10")})
        vista, est = MA.seleccionar(u, "2026-11-13", {"periodos_anunciados": {"ipc": "2026-09"}})
        self.assertEqual([p["periodo"] for p in vista["nuevos"]], ["2026-10"])
        u = uc(fecha="2026-11-16", pubs={"ipc": _pub("2026-10")})
        vista, _ = MA.seleccionar(u, "2026-11-16", est)
        self.assertEqual(vista["nuevos"], [])

    def test_levantado_tarde_abre_igual_el_primer_dia_que_esta(self):
        est = {"periodos_anunciados": {"ipc": "2026-09"}}
        u = uc(fecha="2026-11-13", pubs={"ipc": _pub("2026-09", "publicado", linea="sep-26 · oct-26 publicado el 12/11, "
                                                     "entra en la próxima actualización", titulo_publicado="IPC de octubre")})
        vista, est2 = MA.seleccionar(u, "2026-11-13", est)
        self.assertEqual((vista["nuevos"], len(vista["pendientes"])), ([], 1))
        self.assertEqual(est2["periodos_anunciados"], {"ipc": "2026-09"})
        u = uc(fecha="2026-11-17", pubs={"ipc": _pub("2026-10")})
        vista, _ = MA.seleccionar(u, "2026-11-17", est2)
        self.assertEqual(len(vista["nuevos"]), 1)

    def test_trimestral_compara_strings_de_periodo(self):
        u = uc(pubs={"eph": _pub("2026Q3")})
        vista, _ = MA.seleccionar(u, "2026-11-11", {"periodos_anunciados": {"eph": "2026Q2"}})
        self.assertEqual(len(vista["nuevos"]), 1)

    def test_agenda_de_otro_dia_no_se_muestra(self):
        vista, est = MA.seleccionar(uc(fecha="2026-11-10"), "2026-11-11", {"periodos_anunciados": {"ipc": "2026-09"}})
        self.assertEqual(vista["calendario"], {"estado": "no_disponible"})
        self.assertEqual(est, {})   # no se toca lo anunciado

    def test_sin_ultima_corrida(self):
        vista, est = MA.seleccionar({}, "2026-11-11", {})
        self.assertEqual((vista["calendario"]["estado"], est), ("no_disponible", {}))

    def test_la_seleccion_no_arma_datos_demorados(self):
        graves = [_grave(f"S{i}", 400) for i in range(5)]
        atr = [{"clave": "a", "publicacion": "x", "texto": "t"}]
        vista, est = MA.seleccionar(uc(graves=graves, atrasados=atr, primer_habil_semana=True), "2026-11-11", {})
        self.assertFalse({"atrasados", "graves"} & set(vista))
        self.assertEqual(set(est), {"periodos_anunciados"})


class TestHtml(unittest.TestCase):

    def html(self, u, hoy="2026-11-11", est=None):
        vista, _ = MA.seleccionar(u, hoy, est or {})
        return M.armar_html([], [], [], agenda=vista)

    def test_dia_sin_publicaciones_no_tiene_hoy_se_publica(self):
        h = self.html(uc())
        self.assertNotIn("Hoy se publica", h)
        self.assertIn("Esta semana", h)
        self.assertIn("IPC de octubre", h)
        self.assertNotIn("Datos demorados", h)

    def test_hoy_se_publica(self):
        h = self.html(uc(hoy=[{"titulo": "IPC de octubre", "fuente": "INDEC", "hora": "16 h"}]))
        self.assertIn("Hoy se publica", h)
        self.assertIn("el dato llega en el próximo mail", h)

    def test_orden_de_las_secciones(self):
        u = uc(fecha="2026-11-13", pubs={"ipc": _pub("2026-10")}, hoy=[{"titulo": "Índice de salarios de septiembre",
               "fuente": "INDEC", "hora": "16 h"}], atrasados=[{"clave": "a", "publicacion": "ica", "texto": "Comercio exterior (ICA) · ago-26 · ⚠ atrasado · sep-26 se publicó el 19/10"}])
        h = self.html(u, "2026-11-13", {"periodos_anunciados": {"ipc": "2026-09"}})
        pos = [h.index(x) for x in ("Dato nuevo", "Hoy se publica", "Esta semana", "Indicadores clave",
                                     "Noticias argentinas")]
        self.assertEqual(pos, sorted(pos))
        self.assertIn("Inflación de septiembre: 1,9% mensual", h)
        self.assertIn("publicado el 13/10, 16 h", h)
        self.assertIn(f'{M.DASHBOARD_URL}#precios', h)
        self.assertNotIn("REM", h)

    def test_datos_demorados_nunca_va_en_el_mail(self):
        # Decisión de Pedro del 11/11/2026: ni con atrasados ni con series sin datos hace más de un año.
        graves = [_grave(f"S{i}", 400 + i) for i in range(6)]
        atr = [{"clave": f"a{i}", "publicacion": "x", "texto": f"Serie {i} · ⚠ atrasado"} for i in range(5)]
        for primer_habil in (True, False):
            h = self.html(uc(graves=graves, atrasados=atr, primer_habil_semana=primer_habil),
                          est={"graves_vistos": []})
            for txt in ("Datos demorados", "Sin datos nuevos de la fuente", "⚠ atrasado", "sin datos nuevos hace",
                        "calendario/#demorados"):
                self.assertNotIn(txt, h)

    def test_dato_nuevo_sin_card_no_tiene_link(self):
        u = uc(pubs={"emae": _pub("2026-09", ancla=None)})
        h = self.html(u, est={"periodos_anunciados": {"emae": "2026-08"}})
        self.assertIn("Dato nuevo", h)
        self.assertNotIn("ver gráfico", h)

    def test_semana_vacia(self):
        h = self.html(uc(semana=[], hasta="mar 01/12",
                         proxima={"titulo": "IPC de noviembre", "dia": "mar 15/12", "hora": "16 h"}))
        self.assertIn("Sin publicaciones hasta el mar 01/12. Próxima: IPC de noviembre · mar 15/12 · 16 h.", h)

    def test_calendario_no_disponible(self):
        h = self.html(uc(estado="no_disponible"))
        self.assertIn("Calendario del INDEC no disponible hoy: no se muestran fechas de publicación.", h)
        self.assertNotIn("Esta semana", h)

    def test_cache_vieja(self):
        h = self.html(uc(estado="cache_vieja", bajado="02/11"))
        self.assertIn("Fechas según el calendario del INDEC bajado el 02/11 (no se pudo actualizar desde entonces).", h)

    def test_feriado(self):
        h = self.html(uc(feriado_hoy="Visita de Su Santidad el Papa León XIV"))
        self.assertIn("Hoy es feriado (Visita de Su Santidad el Papa León XIV): no publica el INDEC ni operan el "
                      "BCRA y BYMA.", h)

    def test_pendiente(self):
        u = uc(pubs={"ipc": _pub("2026-09", "publicado", linea="sep-26 · oct-26 publicado el 12/11, entra en la "
                                 "próxima actualización", titulo_publicado="IPC de octubre")})
        h = self.html(u, est={"periodos_anunciados": {"ipc": "2026-09"}})
        self.assertIn("IPC de octubre</b> · sep-26 · oct-26 publicado el 12/11, entra en la próxima actualización", h)

    def test_sin_agenda_el_mail_queda_como_antes(self):
        h = M.armar_html([], [], [])
        self.assertNotIn("Esta semana", h)
        self.assertNotIn("Calendario del INDEC", h)


class TestRegistro(unittest.TestCase):

    def test_registrar_envio_mergea_el_estado(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "mail_enviado.json"
            ruta.write_text(json.dumps({"fecha": "2026-11-11", "periodos_anunciados": {"ipc": "2026-09"},
                                        "graves_vistos": ["X|may-26"]}), encoding="utf-8")
            with mock.patch.object(M, "MAIL_ENVIADO", ruta), mock.patch.object(M, "RAIZ", Path(d)):
                M.registrar_envio(False, {})   # agenda no disponible: se conserva lo anterior
                datos = json.loads(ruta.read_text(encoding="utf-8"))
                self.assertEqual(datos["periodos_anunciados"], {"ipc": "2026-09"})
                M.registrar_envio(False, {"periodos_anunciados": {"ipc": "2026-10"}})
                datos = json.loads(ruta.read_text(encoding="utf-8"))
                self.assertEqual(datos["periodos_anunciados"], {"ipc": "2026-10"})
                self.assertNotIn("graves_vistos", datos)   # era de "Datos demorados", que ya no va en el mail


if __name__ == "__main__":
    unittest.main()

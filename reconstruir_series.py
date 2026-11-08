"""
reconstruir_series.py
---------------------
Borra del histórico (data/series_largo.csv y series_ancho.csv) TODAS las filas de los indicadores que se
le pasan, para que la próxima corrida de run.py los reescriba completos desde una sola fuente. Es la única
excepción al merge idempotente de storage.py y se usa a mano, con OK de Pedro, cuando lo guardado quedó
mal y el merge no lo puede corregir solo (ej. #23 de PENDIENTES: M1/M2/M3 guardados ya rebasados, con
bases mezcladas).

Con --solo-no-habiles borra SÓLO las filas de esos indicadores fechadas en días no hábiles (fines de semana
y feriados de calendario.yaml): snapshots diarios guardados un sábado o un domingo (bloque MAE, 08/11/2026),
que no se pueden reescribir enteros porque la fuente no tiene historia.

Antes de borrar escribe un backup de esas filas en --backup (fuera de data/, no se commitea).

Uso:
    python reconstruir_series.py --backup "C:/ruta/backup.csv" "M2 (agregado total)" "M3 (agregado amplio)"
    python reconstruir_series.py --solo-no-habiles --backup "C:/ruta/backup.csv" "TIR AL30 (USD)"
"""
from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path

import storage


def _leer(path: Path) -> list[list[str]]:
    return list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"), newline="")))


def _escribir(path: Path, filas: list[list[str]]):
    buf = io.StringIO(newline="")
    csv.writer(buf, lineterminator="\n").writerows(filas)
    path.write_text(buf.getvalue(), encoding="utf-8-sig", newline="")


def separar(largo: list[list[str]], nombres: list[str]) -> tuple[list[list[str]], list[list[str]]]:
    """Filas del CSV largo (como texto, sin tocar el formato de los números): (quedan, se borran), con el
    encabezado en las dos. Falla si algún nombre no está en el histórico."""
    enc, filas = largo[0], largo[1:]
    col = enc.index("indicador")
    faltan = [n for n in nombres if n not in {f[col] for f in filas}]
    if faltan:
        raise SystemExit(f"No están en el histórico: {faltan}")
    return [enc] + [f for f in filas if f[col] not in nombres], [enc] + [f for f in filas if f[col] in nombres]


def separar_no_habiles(largo: list[list[str]], nombres: list[str], no_habiles: set) -> tuple[list[list[str]], list[list[str]]]:
    """Como separar(), pero sólo se borran las filas de esos indicadores en días no hábiles."""
    import calendario_indec as C
    from datetime import date
    enc, filas = largo[0], largo[1:]
    col, col_f = enc.index("indicador"), enc.index("fecha")
    faltan = [n for n in nombres if n not in {f[col] for f in filas}]
    if faltan:
        raise SystemExit(f"No están en el histórico: {faltan}")
    borrar = lambda f: f[col] in nombres and not C.es_habil(date.fromisoformat(f[col_f][:10]), no_habiles)
    return [enc] + [f for f in filas if not borrar(f)], [enc] + [f for f in filas if borrar(f)]


def vaciar_celdas(ancho: list[list[str]], borradas: list[list[str]]) -> list[list[str]]:
    """CSV ancho con las celdas (fecha, indicador) borradas en blanco (y sin las fechas que quedan vacías)."""
    enc = ancho[0]
    i_ind, i_f = borradas[0].index("indicador"), borradas[0].index("fecha")
    quitar = {(f[i_f][:10], f[i_ind]) for f in borradas[1:]}
    filas = [[("" if k and (f[0][:10], enc[k]) in quitar else v) for k, v in enumerate(f)] for f in ancho[1:]]
    return [enc] + [f for f in filas if any(v != "" for v in f[1:])]


def sacar_columnas(ancho: list[list[str]], nombres: list[str]) -> list[list[str]]:
    """CSV ancho sin las columnas de esos indicadores (y sin las fechas que quedan vacías)."""
    enc = ancho[0]
    keep = [i for i, c in enumerate(enc) if c not in nombres]
    filas = [[f[i] if i < len(f) else "" for i in keep] for f in ancho[1:]]
    return [[enc[i] for i in keep]] + [f for f in filas if any(v != "" for v in f[1:])]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("indicadores", nargs="+")
    ap.add_argument("--backup", required=True, help="CSV donde guardar las filas borradas (fuera de data/)")
    ap.add_argument("--solo-no-habiles", action="store_true",
                    help="borrar sólo las filas fechadas en fines de semana y feriados de calendario.yaml")
    args = ap.parse_args()
    backup = Path(args.backup).resolve()
    if storage.DATA_DIR.resolve() in backup.parents:
        raise SystemExit("El backup no puede ir dentro de data/ (se commitearía)")
    largo = _leer(storage.LARGO)
    if args.solo_no_habiles:
        import calendario_indec as C
        queda, borra = separar_no_habiles(largo, args.indicadores, C.feriados(C.cargar_config()))
        if len(borra) == 1:
            print("No hay filas en días no hábiles: nada que borrar.")
            return
    else:
        queda, borra = separar(largo, args.indicadores)
    backup.parent.mkdir(parents=True, exist_ok=True)
    _escribir(backup, borra)
    _escribir(storage.LARGO, queda)
    ancho = _leer(storage.ANCHO)
    _escribir(storage.ANCHO, vaciar_celdas(ancho, borra) if args.solo_no_habiles else sacar_columnas(ancho, args.indicadores))
    col_ind, col_f = borra[0].index("indicador"), borra[0].index("fecha")
    for n in args.indicadores:
        fs = sorted(f[col_f] for f in borra[1:] if f[col_ind] == n)
        if fs:
            print(f"  {n}: {len(fs)} filas borradas ({fs[0][:10]} a {fs[-1][:10]})")
    borra = borra[1:]
    print(f"Total: {len(borra)} filas borradas; backup en {backup}")


if __name__ == "__main__":
    main()

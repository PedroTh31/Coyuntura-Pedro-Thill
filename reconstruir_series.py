"""
reconstruir_series.py
---------------------
Borra del histórico (data/series_largo.csv y series_ancho.csv) TODAS las filas de los indicadores que se
le pasan, para que la próxima corrida de run.py los reescriba completos desde una sola fuente. Es la única
excepción al merge idempotente de storage.py y se usa a mano, con OK de Pedro, cuando lo guardado quedó
mal y el merge no lo puede corregir solo (ej. #23 de PENDIENTES: M1/M2/M3 guardados ya rebasados, con
bases mezcladas).

Antes de borrar escribe un backup de esas filas en --backup (fuera de data/, no se commitea).

Uso:
    python reconstruir_series.py --backup "C:/ruta/backup.csv" "M2 (agregado total)" "M3 (agregado amplio)"
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
    args = ap.parse_args()
    backup = Path(args.backup).resolve()
    if storage.DATA_DIR.resolve() in backup.parents:
        raise SystemExit("El backup no puede ir dentro de data/ (se commitearía)")
    largo = _leer(storage.LARGO)
    queda, borra = separar(largo, args.indicadores)
    backup.parent.mkdir(parents=True, exist_ok=True)
    _escribir(backup, borra)
    _escribir(storage.LARGO, queda)
    _escribir(storage.ANCHO, sacar_columnas(_leer(storage.ANCHO), args.indicadores))
    col_ind, col_f = borra[0].index("indicador"), borra[0].index("fecha")
    for n in args.indicadores:
        fs = sorted(f[col_f] for f in borra[1:] if f[col_ind] == n)
        print(f"  {n}: {len(fs)} filas borradas ({fs[0][:7]} a {fs[-1][:7]})")
    borra = borra[1:]
    print(f"Total: {len(borra)} filas borradas; backup en {backup}")


if __name__ == "__main__":
    main()

"""
storage.py
----------
Guarda y actualiza la historia en disco SIN perder datos viejos.

Genera dos archivos en data/:
  - series_largo.csv : formato tidy (una fila por fecha/indicador). Ideal para código.
  - series_ancho.csv : pivot (una columna por indicador). Ideal para abrir en Excel.

La lógica es "merge idempotente": cada corrida vuelve a traer la serie completa,
la une con lo guardado y deduplica por (fecha, indicador) quedándose con el valor
más reciente. Así, si una fuente corrige un dato viejo, queda corregido también.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LARGO = DATA_DIR / "series_largo.csv"
ANCHO = DATA_DIR / "series_ancho.csv"


def _cargar_largo() -> pd.DataFrame:
    if LARGO.exists():
        df = pd.read_csv(LARGO, parse_dates=["fecha"])
        return df
    return pd.DataFrame(columns=["fecha", "indicador", "bloque", "unidad", "valor"])


def actualizar(nuevos: pd.DataFrame) -> pd.DataFrame:
    """
    nuevos: DataFrame con columnas [fecha, indicador, bloque, unidad, valor]
    Devuelve el histórico completo actualizado (formato largo).
    """
    DATA_DIR.mkdir(exist_ok=True)
    previo = _cargar_largo()

    combinado = pd.concat([previo, nuevos], ignore_index=True)
    combinado["fecha"] = pd.to_datetime(combinado["fecha"])

    # dedup: nos quedamos con la última aparición de cada (fecha, indicador)
    combinado = (combinado
                 .drop_duplicates(subset=["fecha", "indicador"], keep="last")
                 .sort_values(["indicador", "fecha"])
                 .reset_index(drop=True))

    # guardar largo
    combinado.to_csv(LARGO, index=False, encoding="utf-8-sig")

    # guardar ancho (pivot) para Excel
    ancho = (combinado
             .pivot_table(index="fecha", columns="indicador", values="valor")
             .sort_index())
    ancho.to_csv(ANCHO, encoding="utf-8-sig")

    return combinado

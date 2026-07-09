"""
run.py  ·  Punto de entrada.  Corré:  python run.py

Flujo:
  1. lee config/indicadores.yaml
  2. trae cada serie de su fuente (con la historia completa)
  3. mergea con el histórico guardado (sin perder datos viejos)
  4. regenera los CSV (largo + ancho) y el dashboard HTML
"""
from pathlib import Path
import sys
import yaml
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / "src"))
from fetchers import traer          # noqa: E402
import storage                      # noqa: E402
import dashboard                    # noqa: E402

RAIZ = Path(__file__).parent
CONFIG = RAIZ / "config" / "indicadores.yaml"


def main():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    start = cfg.get("start_date")
    indicadores = cfg["indicadores"]

    filas = []
    for ind in indicadores:
        nombre = ind["nombre"]
        try:
            serie = traer(ind, start_date=start)
            if serie.empty:
                print(f"  [vacío]  {nombre}")
                continue
            serie = serie.assign(indicador=nombre,
                                 bloque=ind["bloque"],
                                 unidad=ind.get("unidad", ""))
            filas.append(serie[["fecha", "indicador", "bloque", "unidad", "valor"]])
            print(f"  [ok]     {nombre}  ({len(serie)} obs, últ. {serie['fecha'].max().date()})")
        except Exception as e:
            print(f"  [ERROR]  {nombre}: {e}")

    if not filas:
        print("No se trajo ningún dato. ¿Hay conexión / IDs válidos?")
        return

    nuevos = pd.concat(filas, ignore_index=True)
    historico = storage.actualizar(nuevos)
    print(f"\nHistórico total: {len(historico)} filas, "
          f"{historico['indicador'].nunique()} indicadores.")

    dashboard.generar(historico, indicadores)
    print("Listo -> data/series_largo.csv, data/series_ancho.csv, output/index.html")


if __name__ == "__main__":
    main()

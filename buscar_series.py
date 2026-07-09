"""
buscar_series.py
----------------
Ayuda a encontrar el 'id' exacto de una serie en apis.datos.gob.ar/series
para pegarlo en config/indicadores.yaml.

Uso:
    python src/buscar_series.py "reservas internacionales"
    python src/buscar_series.py "M2 privado"
    python src/buscar_series.py "tasa de desempleo"
"""
import sys
import requests

def buscar(q: str, limite: int = 15):
    url = "https://apis.datos.gob.ar/series/api/search/"
    r = requests.get(url, params={"q": q, "limit": limite}, timeout=30)
    r.raise_for_status()
    data = r.json().get("data", [])
    if not data:
        print(f'Sin resultados para "{q}".')
        return

    print(f'\nResultados para "{q}":\n' + "-" * 90)
    for s in data:
        sid = s.get("field_id", "?")
        titulo = s.get("field_description") or s.get("serie_titulo") or ""
        unidad = s.get("field_units", "")
        freq = s.get("field_frequency", "")
        print(f"{sid:<40} | {freq:<10} | {unidad:<18} | {titulo[:60]}")
    print("-" * 90)
    print("Copiá el id de la primera columna al campo 'id:' de config/indicadores.yaml\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Falta el término de búsqueda. Ej: python src/buscar_series.py "reservas"')
        sys.exit(1)
    buscar(" ".join(sys.argv[1:]))

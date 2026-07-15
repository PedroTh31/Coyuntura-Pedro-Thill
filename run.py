"""
run.py  ·  Punto de entrada.  Corré:  python run.py

Flujo:
  1. lee indicadores.yaml
  2. trae cada serie de su fuente (con la historia completa)
  3. calcula las series DERIVADAS (M1 = suma de componentes; salario real = nominal/IPC)
  4. mergea con el histórico guardado (sin perder datos viejos)
  5. regenera los CSV (largo + ancho) y el dashboard HTML
"""
from pathlib import Path
import yaml
import pandas as pd

from fetchers import traer, fetch_datos_gob, fetch_dolar
import storage
import dashboard

RAIZ = Path(__file__).resolve().parent
CONFIG = RAIZ / "indicadores.yaml"


def _fila(serie, ind):
    return (serie.assign(indicador=ind["nombre"], bloque=ind["bloque"],
                         unidad=ind.get("unidad", ""))
            [["fecha", "indicador", "bloque", "unidad", "valor"]])


def _calcular(ind, start):
    """Series derivadas: 'suma' (ej. M1) o 'real' (ej. salario real deflactado por IPC)."""
    tipo = ind["calculo"]
    if tipo == "suma":
        partes = [fetch_datos_gob(cid, start) for cid in ind["componentes"]]
        s = partes[0].rename(columns={"valor": "v0"})[["fecha", "v0"]]
        for k, d in enumerate(partes[1:], 1):
            s = s.merge(d.rename(columns={"valor": f"v{k}"})[["fecha", f"v{k}"]],
                        on="fecha", how="inner")
        cols = [c for c in s.columns if c.startswith("v")]
        s["valor"] = s[cols].sum(axis=1)
        return s[["fecha", "valor"]]
    if tipo == "real":
        nom = fetch_datos_gob(ind["nominal_id"], start).rename(columns={"valor": "nom"})
        ipc = fetch_datos_gob(ind["deflactor_id"], start).rename(columns={"valor": "ipc"})
        s = nom.merge(ipc, on="fecha", how="inner")
        s = s[s["ipc"] > 0].sort_values("fecha")
        if s.empty:
            return s.assign(valor=[])[["fecha", "valor"]]
        s["valor"] = s["nom"] / s["ipc"]
        s["valor"] = s["valor"] / s["valor"].iloc[0] * 100   # base 100 al inicio de la serie
        return s[["fecha", "valor"]]
    if tipo == "brecha":
        # brecha = (paralelo / oficial - 1) * 100, sobre cotizaciones diarias
        alto = fetch_dolar(ind["casa_alta"], start).rename(columns={"valor": "alto"})
        base = fetch_dolar(ind["casa_base"], start).rename(columns={"valor": "base"})
        s = alto.merge(base, on="fecha", how="inner").sort_values("fecha")
        s = s[s["base"] > 0]
        s["valor"] = (s["alto"] / s["base"] - 1) * 100
        return s[["fecha", "valor"]]
    if tipo == "interanual":
        # Variación interanual: (valor_t / valor_t-12m - 1) * 100 (o -1año si frecuencia no es mensual)
        base_id = ind.get("base_id")
        if not base_id:
            raise ValueError(f"Cálculo 'interanual' requiere 'base_id' en {ind['nombre']}")
        s = fetch_datos_gob(base_id, start).sort_values("fecha").copy()
        s = s[s["valor"] > 0]
        if len(s) < 2:
            return s.assign(valor=[])[["fecha", "valor"]]
        # Crear serie lagged (12 meses antes)
        s_prev = s.rename(columns={"valor": "valor_prev"})[["fecha", "valor_prev"]].copy()
        s_prev["fecha"] = s_prev["fecha"] + pd.DateOffset(years=1)
        m = pd.merge_asof(s, s_prev, on="fecha", direction="nearest", tolerance=pd.Timedelta(days=20))
        m = m.dropna(subset=["valor_prev"])
        m = m[m["valor_prev"] > 0]
        m["valor"] = (m["valor"] / m["valor_prev"] - 1) * 100
        return m[["fecha", "valor"]].dropna().reset_index(drop=True)
    raise ValueError(f"cálculo desconocido: {tipo}")


def _avisar(nombre: str, motivo: str):
    """Advertencia visible: imprime en el log Y emite una anotación de GitHub
    Actions (aparece en el resumen del run, sin tener que abrir el log)."""
    print(f"  [ADVERTENCIA]  {nombre}: {motivo}")
    print(f"::warning title=Indicador sin datos::{nombre} — {motivo}")


def main():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    start = cfg.get("start_date")
    indicadores = cfg["indicadores"]
    filas = []
    problemas = []  # (nombre, motivo) de indicadores que no trajeron datos

    for ind in indicadores:
        nombre = ind["nombre"]
        try:
            if "calculo" in ind:
                serie = _calcular(ind, start)
            else:
                serie = traer(ind, start_date=start)
            if serie.empty:
                _avisar(nombre, "la fuente no devolvió datos (serie vacía)")
                problemas.append((nombre, "vacío"))
                continue
            filas.append(_fila(serie, ind))
            print(f"  [ok]     {nombre}  ({len(serie)} obs, ult. {serie['fecha'].max().date()})")
        except Exception as e:
            _avisar(nombre, f"error al traer/calcular la serie: {e}")
            problemas.append((nombre, f"error: {e}"))

    if problemas:
        print(f"\n{len(problemas)} indicador(es) sin datos en esta corrida:")
        for nombre, motivo in problemas:
            print(f"  - {nombre}: {motivo}")
        print("(el histórico ya guardado de esos indicadores NO se toca; se reintentará en la próxima corrida)")

    if not filas:
        print("No se trajo ningun dato.")
        return

    nuevos = pd.concat(filas, ignore_index=True)
    historico = storage.actualizar(nuevos)
    print(f"\nHistorico total: {len(historico)} filas, "
          f"{historico['indicador'].nunique()} indicadores.")
    dashboard.generar(historico, indicadores)
    print("Listo -> data/series_largo.csv, data/series_ancho.csv, docs/index.html")


if __name__ == "__main__":
    main()

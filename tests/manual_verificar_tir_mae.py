"""Verificación MANUAL de la convención de la TIR (PENDIENTES #28). Usa red: NO es parte de la suite
(`python -m unittest discover tests` sólo levanta test*.py).

Correr un día hábil con el mercado ya operado (primera vez: miércoles 11/11/2026, después de las 17 h):

    python tests/manual_verificar_tir_mae.py

Qué hace: baja el snapshot del MAE (emisiones/flujofondoscotiz/H), que trae JUNTOS el precio, la TIR y la
duración modificada que calcula el propio MAE para AL30/GD30/GD35, y recalcula la TIR y la MD con las funciones
del monitor (fuentes_mercados.tir_efectiva / duracion_modificada) a partir de ESE MISMO precio y del flujo del
MAE. Con el precio del MAE no hay ruido de precio: si la convención es la misma, coinciden a la centésima.
Prueba también variantes (liquidación T+0/T+2, base 360, capitalización semestral, precio + cupón corrido) para
decir cuál reproduce al MAE si la elegida no lo hace.

Criterio (decisión de Pedro del 08/11/2026): la convención queda verificada si la variante del monitor
(efectiva anual, ACT/365, T+1, precio tal cual) da |TIR monitor − TIR MAE| <= 0,01 pp y |MD monitor − MD MAE|
<= 0,01 años en los tres bonos que tengan precio ese día. Entonces se saca el "Dato en revisión" de las tres
TIR, la curva y el spread. Si no, se muestra la variante que sí coincide (decisión de Pedro).
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import calendario_indec  # noqa: E402
import fetchers  # noqa: E402
import fuentes_mercados as fm  # noqa: E402

BONOS = ["AL30", "GD30", "GD35"]
TOL_TIR, TOL_MD = 0.01, 0.01


def _tir_variante(precio, liq, flujos, base=365, semestral=False):
    fl = [(f, cf) for f, cf in flujos if f > liq]
    t = [(f - liq).days / base for f, _ in fl]
    cf = [c for _, c in fl]

    def exceso(y):
        if semestral:
            return sum(c / (1 + y / 2) ** (2 * ti) for c, ti in zip(cf, t)) - precio
        return sum(c / (1 + y) ** ti for c, ti in zip(cf, t)) - precio

    a, b = -0.99, 10.0
    for _ in range(200):
        m = (a + b) / 2
        a, b = (m, b) if exceso(m) > 0 else (a, m)
    return (a + b) / 2 * 100


def _corrido(ff, liq):
    """Cupón corrido por 100 de VN original (ACT/ACT del período), desde el flujo del MAE."""
    det = sorted(ff["detalle"], key=lambda x: x["fechaPago"])
    sig = next(x for x in det if pd.Timestamp(x["fechaPago"][:10]) > liq)
    f_sig = pd.Timestamp(sig["fechaPago"][:10])
    meses = round((pd.Timestamp(det[1]["fechaPago"][:10]) - pd.Timestamp(det[0]["fechaPago"][:10])).days / 30.44)
    f_ant = f_sig - pd.DateOffset(months=meses)
    return float(sig["renta"]) * (liq - f_ant).days / (f_sig - f_ant).days


def main():
    hoy = fetchers.hoy_ar()
    nh = calendario_indec.feriados(calendario_indec.cargar_config())
    if not calendario_indec.es_habil(hoy.date(), nh):
        print(f"Hoy ({hoy:%d/%m/%Y}) no es día hábil: el snapshot del MAE viene vacío. Correrlo un día hábil.")
        return 2
    datos = fetchers._get(f"{fetchers._MAE_BASE}/emisiones/flujofondoscotiz/H").json()
    por_ticker = {x.get("especie"): x for x in datos if isinstance(x, dict)}
    liq = {n: pd.Timestamp(calendario_indec.sumar_dias_habiles(hoy.date(), n, nh)) for n in (1, 2)}
    liq[0] = hoy
    ok_todos, evaluados = True, 0
    for b in BONOS:
        x = por_ticker.get(b)
        if not x or not x.get("precio"):
            print(f"{b}: el MAE no informa precio hoy (no operó): no se evalúa.")
            continue
        precio_crudo = float(x["precio"])
        precio = precio_crudo * 100 if precio_crudo < 5 else precio_crudo   # por 1 de VN -> por 100
        if precio > 300:
            print(f"{b}: precio {precio_crudo} del MAE parece en pesos: no se puede comparar en dólares.")
            continue
        ff = fetchers.fetch_mae_flujofondos_ticker(b) or x
        flujos = fm.flujos_bono(ff)
        tir_mae, md_mae = float(x["tir"]), float(x["md"])
        if abs(tir_mae) < 1:   # por si el MAE la informa como fracción
            tir_mae *= 100
        tir_mon = fm.tir_efectiva(precio, liq[1], flujos)
        md_mon = fm.duracion_modificada(tir_mon, liq[1], flujos)
        variantes = {
            "monitor: efectiva ACT/365, T+1, precio tal cual": tir_mon,
            "efectiva ACT/365, T+0": _tir_variante(precio, liq[0], flujos),
            "efectiva ACT/365, T+2": _tir_variante(precio, liq[2], flujos),
            "efectiva ACT/360, T+1": _tir_variante(precio, liq[1], flujos, base=360),
            "semestral ACT/365, T+1": _tir_variante(precio, liq[1], flujos, semestral=True),
            "efectiva ACT/365, T+1, precio + corrido": _tir_variante(precio + _corrido(ff, liq[1]), liq[1], flujos),
        }
        evaluados += 1
        print(f"\n{b}: precio MAE {precio_crudo} -> {precio:.4f} por 100 de VN · TIR MAE {tir_mae:.4f}% · MD MAE {md_mae:.4f}")
        for nombre, v in variantes.items():
            marca = "  <- coincide" if abs(v - tir_mae) <= TOL_TIR else ""
            print(f"   {nombre:45s} {v:8.4f}%  (dif {v - tir_mae:+.4f} pp){marca}")
        print(f"   MD monitor {md_mon:.4f} (dif {md_mon - md_mae:+.4f} años)")
        ok = abs(tir_mon - tir_mae) <= TOL_TIR and abs(md_mon - md_mae) <= TOL_MD
        ok_todos &= ok
    if not evaluados:
        print("\nNingún bono con precio en el MAE: repetir otro día hábil.")
        return 2
    print("\nRESULTADO:", "convención VERIFICADA (sacar 'Dato en revisión', PENDIENTES #28)" if ok_todos
          else "la convención del monitor NO reproduce al MAE: ver qué variante coincide (decisión de Pedro)")
    return 0 if ok_todos else 1


if __name__ == "__main__":
    sys.exit(main())

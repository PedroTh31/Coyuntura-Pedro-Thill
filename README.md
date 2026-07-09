# Monitor de coyuntura · Argentina

Trae automáticamente indicadores de coyuntura (precios, dólar, actividad, monetario,
fiscal, social), guarda la **serie histórica** en CSV y genera un **dashboard** con
gráficos de nivel e interanual. Pensado para correr solo, una vez por semana.

## Qué trae "de fábrica"
Estos indicadores funcionan sin configurar nada:
inflación mensual e interanual, IPC nivel general, dólar oficial / blue / MEP / CCL,
riesgo país y EMAE. El resto (M1/M2/M3, reservas, tasas, resultado fiscal,
recaudación, desempleo, salarios…) se agregan pegando el `id` de la serie en el config
(ver más abajo). Es un renglón por indicador.

## Fuentes (todas gratis, sin API key)
| Fuente | Qué aporta |
|---|---|
| `apis.datos.gob.ar/series` | +30.000 series oficiales: IPC, EMAE, agregados monetarios, fiscal, empleo |
| `api.argentinadatos.com` | inflación, riesgo país, dólar histórico por casa |

## Instalación
```bash
pip install -r requirements.txt
python run.py
```
Esto crea:
- `data/series_largo.csv` — formato tidy (para trabajar en Python/R)
- `data/series_ancho.csv` — una columna por indicador (para abrir en Excel)
- `output/index.html` — el dashboard (abrilo en el navegador)

Cada corrida vuelve a bajar la historia completa y la mezcla con lo guardado **sin
perder ni duplicar** datos viejos.

## Cómo agregar indicadores
1. Buscá el id de la serie:
   ```bash
   python src/buscar_series.py "reservas internacionales"
   python src/buscar_series.py "M2 privado"
   ```
2. Copiá el id de la primera columna.
3. Pegalo en `config/indicadores.yaml` (hay bloques ya preparados y comentados
   con el término de búsqueda sugerido para cada variable de la lista).

Estructura de un indicador:
```yaml
  - nombre: "Reservas internacionales brutas"
    bloque: monetario_financiero      # real | monetario_financiero | fiscal | social | precios
    fuente: datos_gob
    id: "PEGAR_ID_ACA"
    unidad: "millones de USD"
    graficos: [nivel, interanual]     # nivel y/o interanual
```

## Automatización (corre solo, sin prender la compu)
El proyecto incluye `.github/workflows/coyuntura.yml`, que usa **GitHub Actions**:
1. Subí esta carpeta a un repositorio de GitHub.
2. En **Settings → Actions → General**, dejá activado "Read and write permissions".
3. Listo: cada lunes 09:00 (hora ARG) corre solo, actualiza los CSV y el dashboard,
   y commitea los cambios. También podés dispararlo a mano desde la pestaña **Actions**.

Como el histórico vive en el repo, la serie va creciendo semana a semana sola.
Si querés ver el dashboard como página web, activá **GitHub Pages** apuntando a `/output`.

## Correr localmente en vez de en la nube
Si preferís correrlo vos, simplemente ejecutá `python run.py` cuando quieras
(o programalo con `cron` en Linux/Mac o el Programador de tareas en Windows).

## Estructura
```
coyuntura/
├── config/indicadores.yaml   # ← lo único que editás normalmente
├── src/
│   ├── fetchers.py           # baja datos de cada fuente
│   ├── buscar_series.py      # encontrar ids de datos.gob.ar
│   ├── storage.py            # guarda/mergea el histórico
│   └── dashboard.py          # gráficos + HTML
├── run.py                    # corre todo
├── data/                     # CSVs históricos (se versionan)
├── output/                   # dashboard.html + gráficos
└── .github/workflows/        # corrida automática semanal
```

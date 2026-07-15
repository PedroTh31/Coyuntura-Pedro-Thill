# Monitor de coyuntura · Argentina

Trae automáticamente indicadores de coyuntura (precios, dólar, actividad, monetario,
externo, social), guarda la **serie histórica** en CSV y publica un **dashboard**
interactivo (Chart.js, GitHub Pages) con gráficos de nivel. Corre solo, a diario,
vía GitHub Actions.

## Qué trae "de fábrica"
Precios (IPC mensual/interanual), dólar oficial/blue/MEP/CCL, brecha cambiaria,
tipo de cambio real, riesgo país, reservas (BCRA), agregados monetarios (base, M1,
M2, M3), tasas (BADLAR, política monetaria), crédito, EMAE general + semáforo por
16 sectores, IPI manufacturero, sector externo (expo/impo desagregado), desempleo,
salario real. El detalle completo de cada indicador vive en `indicadores.yaml`.

## Fuentes (todas gratis, sin API key)
| Fuente | Qué aporta |
|---|---|
| `apis.datos.gob.ar/series` | +30.000 series oficiales: IPC, EMAE, agregados monetarios, empleo, comercio exterior |
| `api.argentinadatos.com` | inflación, riesgo país, dólar histórico por casa |
| `api.bcra.gob.ar` | reservas internacionales diarias y otras variables monetarias del BCRA |

## Instalación
```bash
pip install -r requirements.txt
python run.py
```
Esto crea/actualiza:
- `data/series_largo.csv` — formato tidy (para trabajar en Python/R)
- `data/series_ancho.csv` — una columna por indicador (para abrir en Excel)
- `docs/index.html` — el dashboard (lo publica GitHub Pages apuntando a `/docs`)

Cada corrida vuelve a bajar la historia completa y la mezcla con lo guardado **sin
perder ni duplicar** datos viejos (merge idempotente, ver `storage.py`).

## Cómo agregar indicadores
1. Buscá el id de la serie:
   ```bash
   python buscar_series.py "reservas internacionales"
   python buscar_series.py "M2 privado"
   ```
2. Copiá el id de la primera columna.
3. Agregá un renglón en `indicadores.yaml`.

Estructura mínima de un indicador:
```yaml
  - {nombre: "Reservas internacionales brutas", bloque: monetario_financiero, grupo: "Reservas", fuente: datos_gob, id: "PEGAR_ID_ACA", unidad: "millones de USD"}
```
`bloque` es uno de: `precios | monetario_financiero | real | externo | social | fiscal`.
Ver `CLAUDE.md` para el resto de los campos soportados (`calculo`, `vista`, `tabla`,
`semaforo`, `desde`, `nota`, etc.).

## Automatización (corre solo, sin prender la compu)
El proyecto usa **GitHub Actions**:
- `.github/workflows/coyuntura.yml` — corre **a diario** (12:00 UTC), actualiza los
  CSV y el dashboard, y commitea los cambios. También se puede disparar a mano
  desde la pestaña **Actions**.
- `.github/workflows/email_semanal.yml` — manda un mail resumen los lunes y jueves
  (indicadores clave + noticias). Necesita los secrets `GMAIL_USER`,
  `GMAIL_APP_PASSWORD` y opcionalmente `MAIL_TO`.

En **Settings → Actions → General** hay que dejar activado "Read and write
permissions" para que el workflow pueda commitear.

Como el histórico vive en el repo, la serie va creciendo día a día sola.
El dashboard se sirve con **GitHub Pages** apuntando a `/docs`.

## Correr localmente en vez de en la nube
Si preferís correrlo vos, simplemente ejecutá `python run.py` cuando quieras
(o programalo con `cron` en Linux/Mac o el Programador de tareas en Windows).

## Estructura
```
coyuntura/
├── indicadores.yaml   # ← lo único que se edita normalmente
├── run.py             # orquestador: corre todo
├── fetchers.py        # baja datos de cada fuente
├── buscar_series.py   # encontrar ids de datos.gob.ar
├── storage.py         # guarda/mergea el histórico (merge idempotente)
├── dashboard.py        # gráficos (Chart.js) + HTML
├── enviar_mail.py     # resumen semanal por mail
├── data/               # CSVs históricos (se versionan)
├── docs/               # dashboard publicado por GitHub Pages
└── .github/workflows/  # corrida diaria + mail semanal
```

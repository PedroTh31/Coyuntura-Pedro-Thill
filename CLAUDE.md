# CLAUDE.md — Monitor de Coyuntura Argentina

Contexto para trabajar este proyecto. Leelo antes de tocar nada.

## Qué es
Un monitor de coyuntura macroeconómica argentina, **totalmente automatizado y gratuito**.
Baja datos de APIs públicas, guarda una serie histórica, publica un **dashboard web
interactivo** (GitHub Pages) y manda un **mail** con indicadores + noticias.

## Arquitectura (no cambiar sin motivo)
- `run.py` — orquestador. Lee `indicadores.yaml`, baja/calcula cada serie, mergea el
  histórico y regenera el dashboard.
- `fetchers.py` — funciones por fuente. Todas devuelven un DataFrame `fecha | valor`.
- `storage.py` — guarda `data/series_largo.csv` y `data/series_ancho.csv` con **merge
  idempotente** (nunca pierde ni duplica datos viejos).
- `dashboard.py` — genera `docs/index.html`. Los gráficos son **interactivos (Chart.js)**,
  NO imágenes. Cada indicador es una celda: tarjeta arriba + gráfico debajo.
- `enviar_mail.py` — resumen semanal (indicadores + noticias arg/intl) por Gmail SMTP.
- `indicadores.yaml` — **el único archivo que se edita normalmente**. Define cada serie.
- `.github/workflows/` — `coyuntura.yml` corre el pipeline a diario; `email_semanal.yml`
  manda el mail lunes y jueves.
- `docs/` — salida publicada por GitHub Pages. `data/` — CSVs históricos versionados.

## Fuentes de datos y cómo se declaran en indicadores.yaml
- `fuente: datos_gob` + `id: "..."` → apis.datos.gob.ar/series (IPC, EMAE, monetarias,
  fiscal, empleo, comercio exterior). Es el backbone.
- `fuente: bcra` + `id_variable: N` → api.bcra.gob.ar (reservas diarias, etc.).
- `fuente: argentinadatos` + `endpoint: "..."` → api.argentinadatos.com (inflación, riesgo país).
- `fuente: dolar` + `casa: ...` → cotizaciones de dólar por casa (ArgentinaDatos).
- `fuente: rem_bcra` + `variable: "..."` + `referencia: "..."` → Relevamiento de Expectativas de
  Mercado (BCRA), a partir del único Excel histórico que publica el BCRA en una URL fija. Arma la
  serie de "expectativa a un mes vista, siempre la encuesta más reciente disponible para cada
  mes": para cada encuesta se queda con el pronóstico cuyo Período es el mes inmediato siguiente
  al de la encuesta, indexado por ese Período (no por la fecha de la encuesta), normalizado a fin
  de mes. `variable`/`referencia` deben coincidir exactamente con las columnas "Variable"/
  "Referencia" de la hoja "Base de Datos Completa" del Excel (ej. "Precios minoristas (IPC nivel
  general; INDEC)" / "var. % mensual"). El Excel (~1,5 MB) se cachea en `data/_cache_rem.csv`
  (todas las variables de una sola descarga) y sólo se vuelve a bajar si la caché tiene más de
  `REM_FRESCURA_DIAS` (7) días — el BCRA lo actualiza una vez por mes, no hace falta pegarle todos
  los días.
- `calculo: suma` + `componentes: [id1, id2]` → suma de series (ej. M1).
- `calculo: real` + `nominal_id` + `deflactor_id` → deflacta por IPC (ej. salario real).
- `calculo: brecha` + `casa_alta` + `casa_base` → (alta/base − 1)·100 (brecha cambiaria).
- `calculo: interanual` + `base_id` → variación % interanual de una serie de datos_gob.
- `calculo: mensual` + `base_id` → variación % mes a mes de una serie de datos_gob (nivel → tasa).
- `calculo: variacion_real_mensual` + `nominal_id` + `deflactor_id` + `media_movil` (opcional,
  meses) → deflacta por IPC, variación % mes a mes, con media móvil opcional.
- `calculo: reservas_ajustadas` (sin parámetros propios) → reservas brutas (BCRA, diario) menos
  swap de monedas con el PBOC (China) menos posición con organismos internacionales (FMI+BIS+
  otros, Balance Semanal del BCRA). NO es "reservas netas" (esa fórmula de mercado tiene 4
  componentes: encajes en USD, swap China, BIS aislado y repos a 1 año; acá sólo 2 de esos 4
  tienen fuente pública estable, ver la `nota` del indicador). El swap sale de la sección II.2 de
  la planilla mensual SDDS/NEDD del BCRA (`fetch_bcra_swap_china`, PDF con nombre predecible
  `temp{MM}{AA}.pdf`, cacheado por mes de forma permanente ya que los meses publicados no
  cambian) y sólo tiene datos desde dic-2022. Los organismos internacionales salen del Excel
  único "Serie Anual de Balances Semanales" (`fetch_bcra_organismos_internacionales`, cacheado
  como el REM).
- `vista: reservas_combo` → gráfico combinado (barras variación + línea stock).
- `vista: overlay` + `series: ["Nombre indicador 1", "Nombre indicador 2", ...]` → líneas
  superpuestas de varios indicadores YA definidos (mismo nombre que su `nombre:`), un solo eje,
  leyenda para prender/apagar cada serie. La tarjeta resume con la ÚLTIMA serie de la lista.
- `vista: incidencia_stack` + `series: [...]` → barras apiladas de incidencia mensual (variación %
  × `peso_nacional` de cada indicador referenciado) sobre un total (ej. divisiones del IPC).
- `vista: burbujas` + `sectores: [{emae: "...", empleo: "..."}, ...]` → gráfico de burbujas
  (Chart.js `bubble`): eje X = variación % interanual del primer indicador de cada par, eje Y =
  variación % interanual del segundo, tamaño = % que representa sobre el total del segundo
  indicador al último período común. Si las frecuencias no coinciden (ej. EMAE mensual vs.
  empleo trimestral), el más frecuente se remuestrea al calendario del menos frecuente antes de
  comparar — documentarlo en la `nota`. Sin botones de filtro (es una foto de un período, no una
  serie temporal); usa anti-colisión de etiquetas en JS (prioriza burbujas grandes, omite la
  etiqueta de las que chocan con una ya puesta — esas quedan identificables sólo por tooltip).
- `calculo: combinado` + `componentes: [{id, peso}, ...]` + `rebase_fecha` (opcional) +
  `media_movil` (opcional, meses) → promedio ponderado de varios índices de nivel (los pesos se
  renormalizan solos, no hace falta que sumen 1), con rebase y/o media móvil. Ej.: EMAE
  Urbano/No urbano agrupando sectores.
- `barras: true` → un indicador normal (una sola serie) se grafica en barras en vez de línea.
- `peso_nacional: N` → ponderador fijo (0-1) de un indicador para `vista: incidencia_stack`.
  Documentar SIEMPRE la fuente y fecha base del ponderador en la `nota`.
- `solo_componente: true` → el indicador se trae y guarda en el histórico normalmente, pero no
  genera tarjeta/gráfico propio: sólo alimenta un `vista: overlay`, `incidencia_stack` o
  `burbujas` que lo referencia.
- `semaforo: true` → alimenta la tabla-semáforo del EMAE (no hace gráfico de línea).
- `tabla: "Nombre"` → va a una tabla de valores (comercio exterior desagregado).
- `desde: "AAAA-MM-DD"` → desde cuándo se ve ese gráfico (default 2024).
- `grupo: "..."` → subtítulo bajo el que se agrupa en el dashboard.
- `factor: N` → multiplica el valor crudo de la fuente por N antes de guardarlo (ej. `factor:
  100` cuando la fuente publica una tasa como fracción 0-1 pese a declararla "Porcentaje").
  Usar siempre esto en vez de parchear el número a mano en el código.
- `marca_fecha: true` → si la serie lleva más de `UMBRAL_DISCONTINUADA_DIAS` sin datos
  nuevos, el dashboard muestra un badge dinámico "Sin datos nuevos desde MM/AAAA" (se
  recalcula cada corrida; desaparece solo si la fuente retoma la publicación). También
  excluye al indicador del chequeo de frescura de `run.py` (ya avisa por otra vía).
- `rezago_normal_dias: N` → para series con un rezago de publicación estructural conocido
  (ej. el TCR multilateral depende del IPC de varios países); pone un piso al umbral del
  chequeo de frescura para no repetir la misma alerta todos los días.
- `nota: "..."` → aclaración metodológica; se muestra como asterisco bajo el gráfico y en el
  pie de la página. Obligatoria en toda serie calculada, estimada, proxy o rascada de Excel,
  o con `factor` aplicado.

## REGLAS DURAS (no negociables)
1. **NUNCA inventar IDs de series.** Antes de agregar un indicador de datos.gob.ar,
   verificar el ID en la ficha oficial del dataset (página `datos.gob.ar/dataset/.../archivo/...`,
   sección "Campos de este recurso"). Si no se puede verificar, NO se agrega: se avisa.
2. **Todo dinámico.** Gráficos SIEMPRE con Chart.js (interactivos, con tooltip al hover).
   Prohibido volver a imágenes estáticas (matplotlib/PNG).
3. **No romper la automatización.** El pipeline tiene que seguir corriendo solo en GitHub
   Actions. Probar `python run.py` localmente antes de cada commit.
4. **Calcular sí, inventar no.** Muchos datos (reservas netas, compras spot del BCRA,
   morosidad, consumo por rubro, proyecciones REM) NO están en APIs limpias: viven en
   Excel/PDF. Ante uno de esos: primero buscar API; si no hay, está bien calcularlo, estimarlo
   o rascar la fuente oficial, PERO con método legítimo basado en datos reales y **documentado
   con una `nota`** (asterisco bajo el gráfico + entrada en el pie de la página). Nunca
   inventar números sin base.
5. **Merge idempotente:** no tocar la lógica de `storage.py` que preserva el histórico.

## Estado actual (ya implementado)
Precios (inflación mensual/interanual, IPC nivel general, incidencia por división de consumo,
inflación efectiva vs. esperada REM); Dólar (oficial/blue/MEP/CCL); Brecha cambiaria; Tipo de
cambio real (diario, 116.4_TCRZE_2015_D_36_4); Riesgo país; Reservas (BCRA diario, combo,
compras netas de divisas por contraparte); Agregados (base, M1 calculado, M2, M3); Tasas
(BADLAR, política); Crédito (préstamos al sector privado, variación % real mensual, por tipo de
deudor Familias/Empresas, morosidad por tipo de banco); EMAE general + semáforo por 16 sectores +
EMAE Urbano vs. No urbano (ponderado por VAB) + burbujas actividad×empleo por sector (SIPA); IPI
manufacturero (453.1_SERIE_ORIGNAL_0_0_14_46); Sector externo (expo/impo/saldo + tablas de
desagregado por rubro y por uso + exportaciones a principales destinos); Social (desempleo,
salario real, tasa de informalidad laboral, salario real por tipo de empleo); Consumo (venta de
vehículos 0km al mercado interno, proxy de patentamientos).

## Pendientes / a mejorar
Ver el prompt de tareas. En general: filtros de años por gráfico, más desagregados, y series que
todavía no tienen fuente confiable identificada: patentamientos exactos (ACARA, sin datos
abiertos), turismo, escrituras, ISAC, depósitos.

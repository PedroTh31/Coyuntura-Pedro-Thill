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
- `calculo: suma` + `componentes: [id1, id2]` → suma de series (ej. M1).
- `calculo: real` + `nominal_id` + `deflactor_id` → deflacta por IPC (ej. salario real).
- `calculo: brecha` + `casa_alta` + `casa_base` → (alta/base − 1)·100 (brecha cambiaria).
- `calculo: interanual` + `base_id` → variación % interanual de una serie de datos_gob.
- `calculo: mensual` + `base_id` → variación % mes a mes de una serie de datos_gob (nivel → tasa).
- `vista: reservas_combo` → gráfico combinado (barras variación + línea stock).
- `vista: overlay` + `series: ["Nombre indicador 1", "Nombre indicador 2", ...]` → líneas
  superpuestas de varios indicadores YA definidos (mismo nombre que su `nombre:`), un solo eje,
  leyenda para prender/apagar cada serie. La tarjeta resume con la ÚLTIMA serie de la lista.
- `vista: incidencia_stack` + `series: [...]` → barras apiladas de incidencia mensual (variación %
  × `peso_nacional` de cada indicador referenciado) sobre un total (ej. divisiones del IPC).
- `barras: true` → un indicador normal (una sola serie) se grafica en barras en vez de línea.
- `peso_nacional: N` → ponderador fijo (0-1) de un indicador para `vista: incidencia_stack`.
  Documentar SIEMPRE la fuente y fecha base del ponderador en la `nota`.
- `solo_componente: true` → el indicador se trae y guarda en el histórico normalmente, pero no
  genera tarjeta/gráfico propio: sólo alimenta un `vista: overlay` o `vista: incidencia_stack`
  que lo referencia en `series`.
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
Precios (inflación mensual/interanual, IPC nivel general); Dólar (oficial/blue/MEP/CCL);
Brecha cambiaria; Tipo de cambio real (mensual, 116.3_TCRMA_0_M_36); Riesgo país; Reservas
(BCRA diario, combo); Agregados (base, M1 calculado, M2, M3); Tasas (BADLAR, política);
Crédito (préstamos al sector privado, 91.1_PEFPC_0_0_35); EMAE general + semáforo por 16
sectores; IPI manufacturero (453.1_SERIE_ORIGNAL_0_0_14_46); Sector externo (expo/impo/saldo
74.3_* + tablas de desagregado por rubro y por uso); Social (desempleo 45.2_ECTDT_0_T_33,
salario real).

## Pendientes / a mejorar
Ver el prompt de tareas. En general: filtros de años por gráfico, estética MinEco, más
desagregados, y varias series que hay que rastrear (ISAC, depósitos, IPC por categoría,
empleo/salarios por tipo, morosidad, proyecciones).

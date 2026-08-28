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
- `enviar_mail.py` — resumen diario (lun-vie, indicadores + noticias arg/intl) por Gmail SMTP.
- `indicadores.yaml` — **el único archivo que se edita normalmente**. Define cada serie.
- `.github/workflows/` — `coyuntura.yml` corre el pipeline a diario; `email_diario.yml`
  manda el mail de lunes a viernes a las 8am hora Argentina (GitHub Actions no garantiza el
  minuto exacto de disparo de un cron; puede llegar con demora en horas pico).
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
- `calculo: resta` + `minuendo_id` + `sustraendo_id` → resta de dos series de datos_gob (ej.
  balance comercial energético = exportaciones de combustibles y energía menos importaciones
  de combustibles y lubricantes).
- `calculo: ratio` + `numerador_id` + `denominador_id` → cociente de dos series de datos_gob,
  sin rebase ni indexar (el valor crudo del cociente es la unidad que importa, ej. capacidad de
  compra = salario en pesos ÷ costo de una canasta en pesos = "canastas que compra un salario").
- `calculo: real` + `nominal_id` + `deflactor_id` → deflacta por IPC (ej. salario real).
- `calculo: brecha` + `casa_alta` + `casa_base` → (alta/base − 1)·100 (brecha cambiaria).
- `calculo: interanual` + `base_id` → variación % interanual de una serie de datos_gob.
- `calculo: acumulado_12m` + `base_id` → suma móvil de los últimos 12 meses de una serie de
  datos_gob (ej. resultado fiscal acumulado, para comparar con series de otra frecuencia). A
  diferencia de `interanual`, no filtra valores ≤ 0: series como el resultado fiscal son
  negativas en meses de déficit sin que eso sea un dato inválido.
- `calculo: mensual` + `base_id` → variación % mes a mes de una serie de datos_gob (nivel → tasa).
- `calculo: deuda_pbi` + `pbi_id` (sin parámetros propios de deuda, usa `fuente: deuda_bruta`
  internamente) → deuda pública bruta (USD, mensual) ÷ PBI nominal (pesos, trimestral, id en
  `pbi_id`) convertido a USD con el tipo de cambio oficial PROMEDIO de cada trimestre
  (decisión de Pedro: promedio, no cierre, mismo criterio que comparaciones internacionales
  tipo FMI), expresado en %. No es un cálculo genérico como `ratio`: mezcla 3 fuentes de
  frecuencias distintas (mensual/trimestral/diaria) con una conversión de moneda de por
  medio, específico para este ratio.
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
- `fuente: bcra_morosidad_lineas` + `serie: "..."` → morosidad (cartera irregular, %) de
  Familias por línea de crédito, a partir del Anexo estadístico (Excel) del Informe sobre
  Bancos mensual del BCRA (bcra.gob.ar/informe-sobre-bancos/), hoja "Calidad de Cartera (por
  líneas)", sección fija "2. Familias - Total" (`fetch_bcra_morosidad_lineas` en
  fetchers.py). `serie` debe ser uno de `MOROSIDAD_LINEAS_SERIES`: "Cartera irregular total",
  "Personales" o "Tarjetas de crédito". No está en datos.gob.ar (dataset 332 sólo desagrega
  por tipo de banco, no por tipo de deudor/línea). Cacheado como el REM/organismos
  internacionales (máximo 1 descarga por semana).
- `fuente: deuda_bruta` (sin parámetros propios) → deuda bruta de la Administración Central
  (Secretaría de Finanzas, Ministerio de Economía), boletín mensual, hoja "A.1", fila "A-
  DEUDA BRUTA ( I + II + III)" (`fetch_deuda_bruta` en fetchers.py). No está en datos.gob.ar
  con datos vigentes (la única serie limpia, 161.1_TL_DEUDRAL_0_0_28, es sólo deuda EXTERNA y
  está discontinuada desde abr-2024). El nombre del Excel cambia cada mes (no es un patrón de
  URL predecible): se scrapea la página de descarga para encontrar el link vigente. Los
  últimos 1-4 meses marcados como provisorios por la fuente ("(*)") se excluyen. Cacheado
  como el REM/organismos internacionales/morosidad por líneas (máximo 1 descarga por semana).
- `vista: reservas_combo` → gráfico combinado (barras variación + línea stock).
- `vista: balance_cambiario` + `series: [indicador_barras, indicador_linea]` → combo de UN
  indicador ya existente como barras (eje izquierdo) + UN indicador ya existente como línea
  (eje derecho), ambos resampleados a fin de mes antes de graficar. Pensado originalmente para
  compras netas de divisas + stock de reservas, pero el mecanismo es genérico.
- `vista: combo_barras_linea` + `barras: [{serie: "...", signo: 1|-1}, ...]` (1 o 2) +
  `linea: "..."` (opcional `unidad_linea` si la línea usa otra unidad que las barras) → combo
  genérico de 1-2 indicadores ya existentes como barras (eje izquierdo) + 1 indicador ya
  existente como línea (eje derecho), dos ejes, con leyenda (a diferencia de `balance_cambiario`,
  que es siempre 1 barra + 1 línea sin leyenda). `signo: -1` invierte el signo SOLO para el
  gráfico (ej. mostrar un gasto como resta visual sobre una barra positiva, misma idea que
  `comercio_espejo` con las importaciones) sin tocar el dato guardado en el histórico. Todo se
  resamplea a fin de mes antes de unir fechas: necesario cuando barras y línea tienen frecuencias
  distintas (ej. resultado fiscal mensual + riesgo país diario) — unir fechas crudas sin
  resamplear deja un eje categórico dominado por la frecuencia más alta, con las barras de la
  frecuencia más baja reducidas a casi un pixel de ancho.
- `vista: comercio_espejo` + `series: [exportaciones, importaciones, saldo]` → gráfico espejo
  (mirror/diverging bars): exportaciones barras positivas arriba, importaciones barras negativas
  abajo (mismo valor de la fuente, sólo se invierte el signo para el gráfico), saldo comercial
  superpuesto como línea. Convención: exportaciones = divisas que "entran", arriba.
- `vista: overlay` + `series: ["Nombre indicador 1", "Nombre indicador 2", ...]` → líneas
  superpuestas de varios indicadores YA definidos (mismo nombre que su `nombre:`), un solo eje,
  leyenda para prender/apagar cada serie. La tarjeta resume con la ÚLTIMA serie de la lista.
  `grande: true` → tarjeta/gráfico más grandes (mismo tamaño que usan las burbujas), útil cuando
  varias líneas superpuestas quedan difíciles de distinguir en el tamaño chico estándar.
  `radio_punto: N` → dibuja un marcador de punto de radio N px en cada dato (por defecto 0, sin
  puntos, sólo la línea) — ayuda a distinguir series que están muy pegadas entre sí.
  `marcar_cruce_maximo: true` → marca con una línea vertical punteada (◆, con tooltip) la fecha
  en que la serie que termina liderando pasó a ser la más alta de forma DEFINITIVA (sin volver a
  perder el primer puesto). Se calcula solo en cada corrida (no una fecha fija); útil cuando el
  cruce entre líneas es el dato más importante del gráfico pero pasa en un ángulo demasiado
  cerrado para notarlo a simple vista.
  `escala_log: true` → eje Y logarítmico en vez de lineal, para overlays donde las series difieren
  en varios órdenes de magnitud (ej. Base monetaria vs. M3): a diferencia de rebasar a índice 100,
  preserva la relación de magnitud real entre las series mientras hace visibles los movimientos
  relativos de todas a la vez.
- `vista: incidencia_stack` + `series: [...]` → barras apiladas de incidencia mensual (variación %
  × `peso_nacional` de cada indicador referenciado) sobre un total (ej. divisiones del IPC).
  `top_n: N` (opcional) → en vez de apilar todas las series, muestra sólo las N de mayor
  `peso_nacional` (recalculado solo, no una lista fija) más una capa "Resto" con la suma del
  resto — con muchas categorías apiladas (ej. 12 divisiones del IPC) cada franja individual queda
  demasiado angosta para distinguirla a simple vista.
- `vista: sectores_bar` + `sectores: [{emae: "...", empleo: "..."}, ...]` → barras categóricas
  (Chart.js `bar`): eje X = sector (una columna por sector, ordenadas de mayor a menor % que
  representa sobre el total de `empleo` al último período común), eje Y = variación %
  interanual de `emae`. El empleo sólo define el ORDEN de las columnas, no un eje propio
  (decisión de diseño: mantener el cruce actividad×empleo en dos ejes reintroduciría el
  problema de superposición que tenía la versión anterior de burbujas). Barras coloreadas por
  signo (verde/rojo), mismo criterio que los combos de barra+línea. Si las frecuencias no
  coinciden (ej. EMAE mensual vs. empleo trimestral), el más frecuente se remuestrea al
  calendario del menos frecuente antes de comparar — documentarlo en la `nota`. Sin botones de
  filtro de rango de fecha (es una foto de un período, no una serie temporal). Reemplaza a una
  versión anterior en burbujas (eje X/Y = actividad/empleo, tamaño = peso de empleo): con sólo
  ~15 sectores, el cluster central quedaba amontonado en el centro del cuadrante y necesitaba
  ejes recortados con la cerca de Tukey (Q3 + 1,5×RIC) más un toggle "Vista completa"/"Zoom al
  cluster" para que el grupo central no quedara ilegible — con una columna por sector no hay
  superposición posible, así que ninguno de los dos mecanismos hace falta.
- `calculo: combinado` + `componentes: [{id, peso}, ...]` + `rebase_fecha` (opcional) +
  `media_movil` (opcional, meses) → promedio ponderado de varios índices de nivel (los pesos se
  renormalizan solos, no hace falta que sumen 1), con rebase y/o media móvil. Ej.: EMAE
  Urbano/No urbano agrupando sectores.
- `barras: true` → un indicador normal (una sola serie) se grafica en barras en vez de línea.
  También funciona en `vista: overlay` (varias series): en vez de líneas superpuestas, barras
  agrupadas por fecha (una barra por serie, no apiladas) -- útil cuando las series son
  variaciones % mensuales de categorías comparables (ej. Núcleo/Regulados/Estacionales), donde
  el patrón visual estándar para esa lectura es de barras, no de líneas.
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
- `sube_es_bueno: true` → la flecha de variación se pinta verde cuando el indicador SUBE y
  roja cuando baja (ej. EMAE, reservas, salario real). Por defecto (sin este flag) es al
  revés: verde si baja, roja si sube (ej. inflación, dólar). Mismo criterio en dashboard.py y
  enviar_mail.py (leen el flag del mismo yaml, una sola fuente de verdad). No es una decisión
  técnica: para cualquier indicador donde "subir" no tenga un signo obvio (agregados
  monetarios, tasas, crédito, depósitos nominales, TCR), preguntarle a Pedro antes de
  marcarlo — no resolver el juicio económico por cuenta propia.
- `neutral: true` → la flecha de variación se muestra sin pintar (gris, misma clase que "sin
  cambio significativo"), para indicadores donde ni `sube_es_bueno: true` ni el default rojo
  aplican con claridad (ej. Base monetaria/M1/M2/M3, BADLAR, préstamos, depósitos bancarios,
  TCR multilateral — decisión de Pedro en cada caso, ver punto anterior). Se lee del mismo
  yaml en dashboard.py y enviar_mail.py.
- `nota: "..."` → aclaración metodológica; se muestra como asterisco bajo el gráfico y en el
  pie de la página. Obligatoria en toda serie calculada, estimada, proxy o rascada de Excel,
  o con `factor` aplicado.
- `subtitulo: "..."` → aclaración corta (una línea) visible directamente debajo del nombre de
  la tarjeta, sin tener que abrir la nota al pie. Usar cuando el nombre solo no alcanza para
  distinguir un indicador de otros parecidos (ej. el grupo "Reservas", donde varios gráficos
  con nombres similares se confundían entre sí antes de agregarlo).

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
Precios (inflación mensual/interanual, IPC nivel general, incidencia por división de consumo);
Dólar (oficial/blue/MEP/CCL); Brecha cambiaria; Tipo de
cambio real (diario, 116.4_TCRZE_2015_D_36_4); Riesgo país; Reservas (BCRA diario, combo,
compras netas de divisas por contraparte); Agregados (base, M1 calculado, M2, M3); Tasas
(BADLAR); Crédito (préstamos al sector privado, variación % real mensual, por tipo de
deudor Familias/Empresas, morosidad por tipo de banco y por línea dentro de Familias,
depósitos privado vs. público); EMAE general + semáforo por 16 sectores +
EMAE Urbano vs. No urbano (ponderado por VAB) + actividad por sector en barras ordenadas por
peso de empleo (SIPA); IPI manufacturero (453.1_SERIE_ORIGNAL_0_0_14_46); Sector externo
(expo/impo/saldo en gráfico espejo + tablas de desagregado por rubro y por uso); Social
(desempleo, salario real, tasa de informalidad laboral, salario real por tipo de empleo,
capacidad de compra RIPTE/CBT); Fiscal (resultado primario y financiero del Sector Público
Nacional, superávit gemelos fiscal/comercial, resultado primario acumulado 12 meses vs. riesgo
país, resultado primario vs. intereses de deuda, deuda pública bruta, PBI nominal trimestral,
deuda/PBI vs. tipo de cambio real).

## Pendientes / a mejorar
Ver el prompt de tareas. En general: filtros de años por gráfico, más desagregados, y series que
todavía no tienen fuente confiable identificada: patentamientos exactos (ACARA, sin datos
abiertos), turismo, escrituras, ISAC, depósitos.

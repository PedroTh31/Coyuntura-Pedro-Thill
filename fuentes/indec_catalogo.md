# Catálogo de la API del INDEC

Generado el 05/11/2026 a partir de la respuesta real de la API (`GET https://api.indec.gob.ar/v1/`, spec OpenAPI 3.1 "Catálogo API-INDEC") con el token de Pedro. Spec crudo: `fuentes/indec_catalogo.json`. Perfil completo (combinaciones de series con rango y filas): `fuentes/indec_catalogo_perfil.json`.

## Confirmado contra la respuesta real

- **Base:** `https://api.indec.gob.ar/v1/` (campo `servers` del spec).
- **Autenticación:** `Authorization: Bearer <token>` (JWT). Sin token, los endpoints de datos devuelven 401.
- **Estilo PostgREST:** `select`, `order`, `limit`, `offset` y filtros `eq.` `neq.` `gt.` `gte.` `lt.` `lte.` `like.` `ilike.` `in.(...)` `is.`.
- **Paginación:** **máximo 1000 filas por respuesta**, aunque `limit` sea mayor. Hay que ordenar por la **clave completa** de cada tabla (abajo, por tabla); si no, las filas empatadas pueden repetirse o faltar.
- **Total de filas:** header `Prefer: count=exact` → `Content-Range: inicio-fin/total`; status `206` si la respuesta es parcial. Validado: en las 14 tablas bajadas completas, filas recibidas = total.
- **Errores:** JSON con `code`, `message`, `details`, `hint`. `400` filtro mal formado, `401` token faltante o inválido, `403` sin permisos.
- **Razón de nulo:** cada columna numérica viene acompañada de `<columna>_null` con el signo convencional del INDEC cuando no hay valor (`*` provisorio, `**` preliminar, `e` estimado, `///` no corresponde, `...` no disponible, `s` secreto estadístico, etc.).
- **Aviso de la propia API:** las variaciones calculadas con los datos de la API pueden diferir de las publicadas en los informes técnicos por redondeo.
- **Token:** JWT con campos `exp`, `iat`, `jti`, `role`, `sub`. `exp` = 04/05/2027 13:11 UTC.

## Resumen: 19 tablas

| Tabla | Área INDEC | Descripción | Filas | Rango | Perfil de categorías |
|---|---|---|---:|---|---|
| `ipi_manufacturero` | Dirección de Estadísticas Mineras, Manufactureras, Energéticas y de la Construcción | Índice de producción industrial manufacturero | 41.344 | 201601 → 202608 | completa |
| `ipi_minero` | Dirección de Estadísticas Mineras, Manufactureras, Energéticas y de la Construcción | Índice de producción industrial minero | 17.632 | 201701 → 202608 | completa |
| `estimaciones_poblacion_departamento_2022_2035` | Dirección de Estadísticas Poblacionales | Estimaciones de población por departamento y sexo | 14.784 | 2022 → 2035 | completa |
| `proyecciones_poblacion_jurisdiccion_2022_2040` | Dirección de Estadísticas Poblacionales | Proyecciones de población por jurisdicción, sexo y edad | 19.152 | 2022 → 2040 | completa |
| `proyecciones_poblacion_nacional_2022_2040` | Dirección de Estadísticas Poblacionales | Proyecciones nacionales de población por sexo y edad | 3.838 | 2022 → 2040 | completa |
| `ipc_nacional` | Dirección de Índices de Precios de Consumo | Índice de Precios al Consumidor (IPC) | 234.198 | 201604 → 202609 | 1.º y último período |
| `valorizacion_canastas_cba_cbt` | Dirección de Índices de Precios de Consumo | Valorización de las canastas básicas (CBA y CBT) | 1.638 | 201604 → 202609 | completa |
| `indice_salarios` | Dirección de Índices de Precios de la Producción | Índice de salarios | 3.406 | 201510 → 202608 | completa |
| `icc_precios_construccion` | Dirección de Índices de Precios de la Producción | Índice del costo de la construcción | 14.017 | 201511 → 202609 | completa |
| `redeterminacion_precios_contratos_obras_publicas` | Dirección de Índices de Precios de la Producción | Redeterminación de precios de obras públicas | 236.192 | 201510 → 202609 | 1.º y último período |
| `sipm_precios_mayoristas` | Dirección de Índices de Precios de la Producción | Sistema de índices de precios mayoristas | 234.260 | 201512 → 202609 | 1.º y último período |
| `estimador-mensual-de-actividad-economica-nivel-general` | Dirección Nacional de Cuentas Nacionales | Estimador mensual de actividad económica. Nivel general | 1.632 | 200401 → 202608 | completa |
| `estimador-mensual-de-actividad-economica-sectores` | Dirección Nacional de Cuentas Nacionales | Estimador mensual de actividad económica. Sectores | 8.512 | 200401 → 202608 | completa |
| `pobreza_eph` | Dirección Nacional de Estadísticas de Condiciones de Vida | Incidencia de la pobreza y la indigencia (EPH) | 20 | 20162S → 20261S | completa |
| `mercado_trabajo_eph` | Dirección Nacional de Estadísticas de Condiciones de Vida | Principales tasas del mercado de trabajo (EPH) | 41 | 20162T → 20262T | completa |
| `canasta-crianza` | Dirección Nacional de Estadísticas de Condiciones de Vida | Valorización de la canasta de crianza | 81 | 202001 → 202609 | completa |
| `comercio_exterior_nomenclaturas` | Dirección Nacional de Estadísticas del Sector Externo y Cuentas Internacionales | Códigos y denominaciones de comercio exterior | 325 | — | completa |
| `comercio_exterior_exportacion_bienes` | Dirección Nacional de Estadísticas del Sector Externo y Cuentas Internacionales | Exportaciones de bienes por rubros y países de destino | 779.536 | 198601 → 202609 | 1.º y último período |
| `comercio_exterior_importacion_bienes` | Dirección Nacional de Estadísticas del Sector Externo y Cuentas Internacionales | Importaciones de bienes por uso económico y país de origen | 390.315 | 198601 → 202609 | 1.º y último período |

**Nota sobre el perfil:** las 5 tablas de más de 50.000 filas (IPC, precios mayoristas, redeterminación de obra pública, exportaciones e importaciones) **no** se bajaron completas: el rango temporal sale de `order` ascendente/descendente sobre toda la tabla, pero los valores distintos de las columnas categóricas salen sólo de las filas del primer y del último período. Una categoría que exista sólo en períodos intermedios podría no aparecer listada.

## Detalle por tabla

### `ipi_manufacturero`

Índice de producción industrial manufacturero. Área: Dirección de Estadísticas Mineras, Manufactureras, Energéticas y de la Construcción.

- **Filas:** 41.344 · **Rango (periodo):** 201601 → 202608
- **Clave de orden (para paginar):** `periodo,indicador,cuadro_web,codigo_CLaNAE_2004,descripcion,serie,tipo_de_indicador`
- **Base del perfil de categorías:** tabla completa

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `periodo` | string | Período de referencia del dato, expresado en formato AAAAMM para meses |
| `anio` | number | Año correspondiente al período de referencia del dato |
| `mes` | number | Número del mes correspondiente al período de referencia. Utiliza valores comprendidos entre 1 (enero) y 12 (diciembre) |
| `indicador` | string | Nombre del indicador estadístico |
| `cuadro_web` | string | Número del cuadro estadístico publicado en el sitio web del INDEC al que corresponde el dato |
| `codigo_CLaNAE_2004` | string | Código de Clasificación Nacional de Actividades Económicas 2004  |
| `descripcion` | string | Denominación de la categoría correspondiente al código informado |
| `serie` | string | Tipo de serie estadística: original, desestacionalizada o tendencia-ciclo |
| `tipo_de_indicador` | string | Tipo de cálculo o presentación del indicador, como índice, variación intermensual, variación interanual, variación acumulada, incidencia o peso promedio |
| `unidad_de_medida` | string | Unidad en la que se expresa el valor del indicador |
| `valor` | numérico (sin tipo en el spec) | Valor del indicador para el período y las categorías informadas. |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `indicador` — 1 valores: `IPI manufacturero` (41344)
- `cuadro_web` — 5 valores: `Cuadro 2` (10880), `Cuadro 3` (10880), `Cuadro 4` (10880), `Cuadro 5` (4352), `Cuadro 6` (4352)
- `codigo_CLaNAE_2004` — 82 valores: `23200` (1536), `15` (896), `16` (896), `17` (896), `18-19` (896), `20-22` (896), `23` (896), `24` (896), `25` (896), `26` (896), `27` (896), `28` (896), `29` (896), `30-33` (896), `34` (896), `35` (896), `36-38` (896), `D` (896), `15111` (384), `15112` (384), `15113` (384), `15120/330/499` (384), `15130` (384), `15140` (384), `15200` (384), `15311/12/13/20` (384), `15411/12/41/42` (384), `15420/30` (384), `15491/2/3` (384), `15510/29/30/41/42/49` (384), `15521` (384), `16001` (384), `16009` (384), `17111/2` (384), `17113` (384), `17114/15/20` (384), `17210/20/30/90` (384), `18110/120/401/402/900` (384), `19110/20` (384), `19201/2/3/4` (384) … y 42 más (lista completa en el perfil JSON)
- `descripcion` — 84 valores: `Otro equipo de transporte` (1280), `Alimentos y bebidas` (896), `Productos de tabaco` (896), `Productos textiles` (896), `Prendas de vestir, cuero y calzado` (896), `Madera, papel, edición e impresión` (896), `Refinación del petróleo, coque y combustible nuclear` (896), `Sustancias y productos químicos` (896), `Productos de caucho y plástico` (896), `Productos minerales no metálicos` (896), `Industrias metálicas básicas` (896), `Productos de metal` (896), `Maquinaria y equipo` (896), `Otros equipos, aparatos e instrumentos` (896), `Vehículos automotores, carrocerías, remolques y autopartes` (896), `Muebles y colchones, y otras industrias manufactureras` (896), `IPI Manufacturero - Nivel general` (896), `Carne vacuna` (384), `Carne aviar` (384), `Fiambres y embutidos` (384), `Otros productos alimenticios` (384), `Preparación de frutas, hortalizas y legumbres` (384), `Molienda de oleaginosas` (384), `Productos lácteos` (384), `Molienda de cereales` (384), `Galletitas, productos de panadería y pastas` (384), `Azúcar, productos de confitería y chocolate` (384), `Yerba mate, té y café` (384), `Gaseosas, aguas, sodas, cervezas, jugos para diluir, sidras y bebidas espirituosas` (384), `Vino` (384), `Preparación de hojas de tabaco` (384), `Cigarrillos` (384), `Preparación de fibras de uso textil` (384), `Hilados de algodón` (384), `Tejidos y acabado de productos textiles` (384), `Otros productos textiles` (384), `Prendas de vestir` (384), `Curtido y artículos de cuero, excepto prendas` (384), `Calzado y sus partes` (384), `Madera y productos de madera y corcho, excepto muebles` (384) … y 44 más (lista completa en el perfil JSON)
- `serie` — 3 valores: `Serie original` (32640), `Serie desestacionalizada` (4352), `Serie tendencia-ciclo` (4352)
- `tipo_de_indicador` — 4 valores: `Índice` (15232), `Variación interanual` (10880), `Variación acumulada interanual` (10880), `Variación intermensual` (4352)
- `unidad_de_medida` — 2 valores: `%` (26112), `Numero índice` (15232)

**Razón de nulo observada:** `valor_null`: `///` (2080), `-` (36), `s` (42)

**Series (323), agrupadas por cuadro:**

| cuadro_web | serie | tipo_de_indicador | desde | hasta | n.º de aperturas |
|---|---|---|---|---|---:|
| Cuadro 2 | Serie original | Índice | 201601 | 202608 | 85 |
| Cuadro 3 | Serie original | Variación interanual | 201601 | 202608 | 85 |
| Cuadro 4 | Serie original | Variación acumulada interanual | 201601 | 202608 | 85 |
| Cuadro 5 | Serie desestacionalizada | Variación intermensual | 201601 | 202608 | 17 |
| Cuadro 5 | Serie desestacionalizada | Índice | 201601 | 202608 | 17 |
| Cuadro 6 | Serie tendencia-ciclo | Variación intermensual | 201601 | 202608 | 17 |
| Cuadro 6 | Serie tendencia-ciclo | Índice | 201601 | 202608 | 17 |

### `ipi_minero`

Índice de producción industrial minero. Área: Dirección de Estadísticas Mineras, Manufactureras, Energéticas y de la Construcción.

- **Filas:** 17.632 · **Rango (periodo):** 201701 → 202608
- **Clave de orden (para paginar):** `periodo,anio,mes,indicador,cuadro_web,codigo_ClaNAE_2010,codigo_CPC_2_1,serie,descripcion,tipo_de_indicador,unidad_de_medida`
- **Base del perfil de categorías:** tabla completa

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `periodo` | string | Período de referencia del dato, expresado en formato AAAAMM para meses |
| `anio` | number | Año correspondiente al período de referencia del dato |
| `mes` | number | Número del mes correspondiente al período de referencia. Utiliza valores comprendidos entre 1 (enero) y 12 (diciembre) |
| `indicador` | string | Nombre del indicador estadístico |
| `cuadro_web` | string | Número del cuadro estadístico publicado en el sitio web del INDEC al que corresponde el dato |
| `codigo_ClaNAE_2010` | string | Código ClaNAE 2010 |
| `codigo_CPC_2_1` | string | Código CPC 2.1 |
| `serie` | string | Tipo de serie estadística: original, desestacionalizada o tendencia-ciclo |
| `descripcion` | string | Denominación de la categoría correspondiente al código informado |
| `tipo_de_indicador` | string | Tipo de cálculo o presentación del indicador, como índice, variación intermensual, variación interanual, variación acumulada, incidencia o precio promedio |
| `unidad_de_medida` | string | Unidad en la que se expresa el valor del indicador |
| `valor` | numérico (sin tipo en el spec) | Valor del indicador para el período y las categorías informadas |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `indicador` — 1 valores: `IPI Minero` (17632)
- `cuadro_web` — 7 valores: `Cuadro 2` (5452), `Cuadro 3` (5452), `Cuadro 4` (5452), `Cuadro 1` (464), `Cuadro 5` (348), `Cuadro 6` (348), `Cuadro 7` (116)
- `codigo_ClaNAE_2010` — 16 valores: `05.100 y 08.920/90` (2436), `08.130` (2436), `08.912` (1856), `08.110` (1740), `08.140` (1740), `08.120` (1392), `08.930` (1392), `B` (812), `06.100` (696), `06.200` (696), `07.291` (696), `05.100 y 08` (348), `06 y 09.1` (348), `07.10 y 07.29` (348), `07.100 y 07.299` (348), `09.100` (348)
- `codigo_CPC_2_1` — 48 valores: `-` (812), `12010` (696), `12020` (696), `110, 151/2/3/4 y 161/2/3` (348), `11010/50, 15130/320 y 16321/22/91/92/93/99` (348), `1101004, 1632103/105/106/202 y 1639101/102/304` (348), `1105001` (348), `1513001 y 1639202/3` (348), `1532010` (348), `1632108/9201` (348), `1639302/906` (348), `12010/20 y 86221` (348), `14100 y 14210/41/42/90` (348), `1410001, 1421001 y 1429005/06/12/99` (348), `1424101/201` (348), `1424203` (348), `15120/30 y 16330` (348), `15120011/12/22/31/32, 15130032/82 y 1513005` (348), `1513002 y 15130021/3` (348), `1513004` (348), `1633001` (348), `15210/20` (348), `1521001` (348), `1522001/04/99` (348), `1522002` (348), `15120/220/311/312/320` (348), `1512004, 1522005 y 1532011` (348), `1531101` (348), `1531201/2` (348), `1531203` (348), `1532001` (348), `1532008` (348), `15401/2` (348), `1540101/201` (348), `1540102` (348), `1540204` (348), `1540205/7` (348), `16193` (348), `16193/4/5/6 y 16399` (348), `1619401` (348) … y 8 más (lista completa en el perfil JSON)
- `serie` — 3 valores: `Serie Original` (17168), `Serie Desestacionalizada` (232), `Serie Tendencia-Ciclo` (232)
- `descripcion` — 52 valores: `Nivel General - IPI Minero` (812), `Petróleo crudo` (464), `Gas natural` (464), `Extracción de minerales no metalíferos y rocas de aplicación` (348), `Extracción y aglomeración de carbón, de turba y explotación de minas y canteras n.c.p.` (348), `Resto (incluye carbón térmico, ágata, cristal de roca, rodocrosita, abrasivos naturales, talco, mica en láminas u hojas y baritina -incluye uso petrolero-)` (348), `Turba` (348), `Puzolana, feldespato potásico (microclino, ortosa) y feldespato sódico (albita)` (348), `Suelo seleccionado y/o estabilizado para relleno` (348), `Cuarzo amatista y cuarzo` (348), `Diatomita y perlita` (348), `Extracción de petróleo crudo y gas natural y servicios de apoyo` (348), `Extracción de minerales metalíferos` (348), `Resto ( incluye hierro, cobre, plomo, cinc, molibdeno y otros minerales metalíferos no ferrosos y sus concentrados)` (348), `Plata y oro y sus concentrados` (348), `Bullón Dorado , Doré ` (348), `Extracción de rocas ornamentales` (348), `Resto (incluye mármol, travertino, areniscas y pórfido en bochones o escallas, bloques o aserrado en placas cuadradas o rectangulares y rocas de cuarcita)` (348), `Granito` (348), `Piedra laja` (348), `Dolomita cruda, excepto para uso de cal o cemento` (348), `Extracción de piedra caliza y yeso` (348), `Yeso` (348), `Roca o piedra caliza, conchilla y piedras o rocas calcáreas para la producción de cal y/o cemento` (348), `Clínker` (348), `Extracción de arenas, canto rodado y triturados pétreos` (348), `Resto ( incluye roca o piedra caliza para construcción, dolomita para la producción de cal y cemento y áridos sin clasificar)` (348), `Arena común para construcción` (348), `Arenas industriales y arenas y gravas silíceas` (348), `Arenas de fractura (fracking)` (348), `Rocas para triturados pétreos sin clasificar` (348), `Canto rodado, granza y/o ripio` (348), `Extracción de arcilla y caolín` (348), `Caolín y bentonita` (348), `Arcilla común (cerámicas, ferruginosas, misceláneas)` (348), `Arcillas plásticas` (348), `Zeolita natural (no sintetizado) y limo arcilloso para ladrillos y cerámicas rojas` (348), `Carbonato de litio y otros minerales de litio` (348), `Extracción de minerales para la fabricación de productos químicos` (348), `Calcita/carbonato de calcio` (348) … y 12 más (lista completa en el perfil JSON)
- `tipo_de_indicador` — 5 valores: `Índice` (5684), `Variación interanual` (5452), `Variación acumulada interanual` (5452), `Unidades físicas` (812), `Variación intermensual` (232)
- `unidad_de_medida` — 5 valores: `%` (11136), `Número índice` (5684), `miles de m³` (348), `millones de m³` (348), `toneladas` (116)

**Razón de nulo observada:** `valor_null`: `///` (1132), `s` (511)

**Series (152), agrupadas por cuadro:**

| cuadro_web | serie | tipo_de_indicador | desde | hasta | n.º de aperturas |
|---|---|---|---|---|---:|
| Cuadro 1 | Serie Desestacionalizada | Variación intermensual | 201701 | 202608 | 1 |
| Cuadro 1 | Serie Desestacionalizada | Índice | 201701 | 202608 | 1 |
| Cuadro 1 | Serie Tendencia-Ciclo | Variación intermensual | 201701 | 202608 | 1 |
| Cuadro 1 | Serie Tendencia-Ciclo | Índice | 201701 | 202608 | 1 |
| Cuadro 2 | Serie Original | Índice | 201701 | 202608 | 47 |
| Cuadro 3 | Serie Original | Variación interanual | 201701 | 202608 | 47 |
| Cuadro 4 | Serie Original | Variación acumulada interanual | 201701 | 202608 | 47 |
| Cuadro 5 | Serie Original | Unidades físicas | 201701 | 202608 | 3 |
| Cuadro 6 | Serie Original | Unidades físicas | 201701 | 202608 | 3 |
| Cuadro 7 | Serie Original | Unidades físicas | 201701 | 202608 | 1 |

### `estimaciones_poblacion_departamento_2022_2035`

Estimaciones de población por departamento y sexo. Área: Dirección de Estadísticas Poblacionales.

- **Filas:** 14.784 · **Rango (fecha):** 2022 → 2035
- **Clave de orden (para paginar):** `departamento_cod,sexo_cod,fecha`
- **Base del perfil de categorías:** tabla completa

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `jurisdiccion_cod` | string | Código de dos posiciones que identifica a la jurisdicción de la República Argentina |
| `jurisdiccion_nom` | string | Nombre de la jurisdicción de la República Argentina |
| `departamento_cod` | string | Código de cinco posiciones que identifica al departamento, partido o comuna. Las dos primeras corresponden a la jurisdicción y las tres restantes al departamento, partido o comuna |
| `departamento_nom` | string | Nombre del departamento, partido o comuna |
| `rmba` | string | Indica si la jurisdicción, el departamento o el partido pertenece a la Región Metropolitana de Buenos Aires (RMBA) |
| `sexo_cod` | string | Código que identifica el sexo registrado al nacer |
| `sexo_nom` | string | Categoría de sexo registrado al nacer |
| `poblacion` | numérico (sin tipo en el spec) | Cantidad de habitantes estimada (2022) o proyectada (2023-2040) para la fecha de referencia |
| `fecha` | string | Año correspondiente a la estimación o proyección de población, referida al 1 de julio |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `jurisdiccion_cod` — 24 valores: `06` (3780), `86` (756), `14` (728), `18` (700), `22` (700), `66` (644), `42` (616), `70` (532), `82` (532), `46` (504), `50` (504), `30` (476), `54` (476), `90` (476), `10` (448), `38` (448), `58` (448), `02` (420), `26` (420), `62` (364), `34` (252), `74` (252), `78` (196), `94` (112)
- `jurisdiccion_nom` — 24 valores: `Buenos Aires` (3780), `Santiago del Estero` (756), `Córdoba` (728), `Corrientes` (700), `Chaco` (700), `Salta` (644), `La Pampa` (616), `San Juan` (532), `Santa Fe` (532), `La Rioja` (504), `Mendoza` (504), `Entre Ríos` (476), `Misiones` (476), `Tucumán` (476), `Catamarca` (448), `Jujuy` (448), `Neuquén` (448), `CABA` (420), `Chubut` (420), `Río Negro` (364), `Formosa` (252), `San Luis` (252), `Santa Cruz` (196), `Tierra del Fuego` (112)
- `departamento_cod` — 528 valores: `02007` (28), `02014` (28), `02021` (28), `02028` (28), `02035` (28), `02042` (28), `02049` (28), `02056` (28), `02063` (28), `02070` (28), `02077` (28), `02084` (28), `02091` (28), `02098` (28), `02105` (28), `06007` (28), `06014` (28), `06021` (28), `06028` (28), `06035` (28), `06042` (28), `06049` (28), `06056` (28), `06063` (28), `06070` (28), `06077` (28), `06084` (28), `06091` (28), `06098` (28), `06105` (28), `06112` (28), `06119` (28), `06126` (28), `06134` (28), `06140` (28), `06147` (28), `06154` (28), `06161` (28), `06168` (28), `06175` (28) … y 488 más (lista completa en el perfil JSON)
- `departamento_nom` — 446 valores: `Capital` (308), `9 de Julio` (140), `Rivadavia` (140), `25 de Mayo` (140), `San Martín` (140), `Avellaneda` (84), `Colón` (84), `Chacabuco` (84), `General Alvear` (84), `General Belgrano` (84), `General San Martín` (84), `Junín` (84), `Maipú` (84), `San Pedro` (84), `La Paz` (84), `San Javier` (84), `Libertador General San Martín` (84), `Sarmiento` (84), `Belgrano` (84), `Adolfo Alsina` (56), `Almirante Brown` (56), `Ayacucho` (56), `Coronel Pringles` (56), `Florentino Ameghino` (56), `General Paz` (56), `Ituzaingó` (56), `Leandro N. Alem` (56), `Mercedes` (56), `Moreno` (56), `Pellegrini` (56), `San Fernando` (56), `San Miguel` (56), `Santa María` (56), `Santa Rosa` (56), `General Roca` (56), `Minas` (56), `San Justo` (56), `Concepción` (56), `Lavalle` (56), `Bermejo` (56) … y 406 más (lista completa en el perfil JSON)
- `rmba` — 2 valores: `0` (13272), `1` (1512)
- `sexo_cod` — 2 valores: `1` (7392), `2` (7392)
- `sexo_nom` — 2 valores: `Mujer` (7392), `Varon` (7392)

### `proyecciones_poblacion_jurisdiccion_2022_2040`

Proyecciones de población por jurisdicción, sexo y edad. Área: Dirección de Estadísticas Poblacionales.

- **Filas:** 19.152 · **Rango (fecha):** 2022 → 2040
- **Clave de orden (para paginar):** `jurisdiccion_cod,sexo_cod,edad_cod,fecha`
- **Base del perfil de categorías:** tabla completa

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `jurisdiccion_cod` | string | Código de dos posiciones que identifica a la jurisdicción de la República Argentina |
| `jurisdiccion_nom` | string | Nombre de la jurisdicción de la República Argentina |
| `sexo_cod` | string | Código que identifica el sexo registrado al nacer |
| `sexo_nom` | string | Categoría de sexo registrado al nacer |
| `edad_cod` | string | Código que identifica al grupo quinquenal de edad |
| `edad_nom` | string | Intervalo de edad de cinco años correspondiente al código informado |
| `poblacion` | numérico (sin tipo en el spec) | Cantidad de habitantes estimada (2022) o proyectada (2023-2040) para la fecha de referencia |
| `fecha` | string | Año correspondiente a la estimación o proyección de población, referida al 1 de julio |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `jurisdiccion_cod` — 24 valores: `02` (798), `06` (798), `10` (798), `14` (798), `18` (798), `22` (798), `26` (798), `30` (798), `34` (798), `38` (798), `42` (798), `46` (798), `50` (798), `54` (798), `58` (798), `62` (798), `66` (798), `70` (798), `74` (798), `78` (798), `82` (798), `86` (798), `90` (798), `94` (798)
- `jurisdiccion_nom` — 24 valores: `Ciudad Autónoma de Buenos Aires` (798), `Buenos Aires` (798), `Catamarca` (798), `Córdoba` (798), `Corrientes` (798), `Chaco` (798), `Chubut` (798), `Entre Ríos` (798), `Formosa` (798), `Jujuy` (798), `La Pampa` (798), `La Rioja` (798), `Mendoza` (798), `Misiones` (798), `Neuquén` (798), `Río Negro` (798), `Salta` (798), `San Juan` (798), `San Luis` (798), `Santa Cruz` (798), `Santa Fe` (798), `Santiago del Estero` (798), `Tucumán` (798), `Tierra del Fuego, Antártida e Islas del Atlántico Sur` (798)
- `sexo_cod` — 2 valores: `1` (9576), `2` (9576)
- `sexo_nom` — 2 valores: `Mujer` (9576), `Varon` (9576)
- `edad_cod` — 21 valores: `0` (912), `10` (912), `100` (912), `15` (912), `20` (912), `25` (912), `30` (912), `35` (912), `40` (912), `45` (912), `5` (912), `50` (912), `55` (912), `60` (912), `65` (912), `70` (912), `75` (912), `80` (912), `85` (912), `90` (912), `95` (912)
- `edad_nom` — 21 valores: `0 a 4 años` (912), `10 a 14 años` (912), `100 y más años` (912), `15 a 19 años` (912), `20 a 24 años` (912), `25 a 29 años` (912), `30 a 34 años` (912), `35 a 39 años` (912), `40 a 44 años` (912), `45 a 49 años` (912), `5 a 9 años` (912), `50 a 54 años` (912), `55 a 59 años` (912), `60 a 64 años` (912), `65 a 69 años` (912), `70 a 74 años` (912), `75 a 79 años` (912), `80 a 84 años` (912), `85 a 89 años` (912), `90 a 94 años` (912), `95 a 99 años` (912)

### `proyecciones_poblacion_nacional_2022_2040`

Proyecciones nacionales de población por sexo y edad. Área: Dirección de Estadísticas Poblacionales.

- **Filas:** 3.838 · **Rango (fecha):** 2022 → 2040
- **Clave de orden (para paginar):** `edad,sexo_cod,fecha`
- **Base del perfil de categorías:** tabla completa

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `edad` | number | Edad de las personas, expresada en años cumplidos |
| `sexo_cod` | string | Código que identifica al sexo registrado al nacer |
| `sexo_nom` | string | Categoría de sexo registrado al nacer |
| `poblacion` | numérico (sin tipo en el spec) | Cantidad de habitantes estimada (2022) o proyectada (2023-2040) para la fecha de referencia |
| `fecha` | number | Año correspondiente a la estimación o proyección de población, referida al 1 de julio |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `sexo_cod` — 2 valores: `1` (1919), `2` (1919)
- `sexo_nom` — 2 valores: `Mujer` (1919), `Varon` (1919)

### `ipc_nacional`

Índice de Precios al Consumidor (IPC). Área: Dirección de Índices de Precios de Consumo.

- **Filas:** 234.198 · **Rango (periodo):** 201604 → 202609
- **Clave de orden (para paginar):** `clasificador,nivel,codigo,descripcion,periodo,anio,mes,indicador,tipo_de_indicador,tipo_de_indicador_descripcion,region,unidad_de_medida`
- **Base del perfil de categorías:** solo filas de los períodos 201604 y 202609 (tabla de 234198 filas)

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `clasificador` | string | Clasificador utilizado para organizar y codificar las categorías del dato |
| `nivel` | string | Nivel de desagregación de la categoría dentro de la estructura del clasificador |
| `codigo` | string | Código asignado a la categoría de acuerdo con el clasificador utilizado |
| `descripcion` | string | Denominación de la categoría correspondiente al código informado |
| `periodo` | string | Período de referencia del dato, expresado en formato AAAAMM (meses) |
| `anio` | number | Año correspondiente al período de referencia del dato |
| `mes` | number | Número del mes correspondiente al período de referencia. Utiliza valores comprendidos entre 1 (enero) y 12 (diciembre) |
| `indicador` | string | Nombre del indicador estadístico |
| `tipo_de_indicador` | string | Tipo de cálculo o presentación del indicador, como índice, variación intermensual, variación interanual, variación acumulada, incidencia o precio promedio  |
| `tipo_de_indicador_descripcion` | string | Descripción del tipo de indicador |
| `region` | string | Región estadística a la que corresponde el dato |
| `unidad_de_medida` | string | Unidad en la que se expresa el valor del indicador |
| `valor` | numérico (sin tipo en el spec) | Valor del indicador para el período y las categorías informadas |
| `observaciones` | numérico (sin tipo en el spec) | Notas necesarias para el valor informado |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `clasificador` — 4 valores: `COICOP Argentina 2019` (1834), `Estacional, Núcleo y Regulados` (147), `Bienes y servicios` (98), `IPC` (28)
- `nivel` — 6 valores: `Grupo` (770), `División` (588), `Clase` (288), `Categoría` (245), `Producto` (188), `Nivel General` (28)
- `codigo` — 109 valores: `B` (49), `S` (49), `01` (49), `02` (49), `03` (49), `04` (49), `05` (49), `06` (49), `07` (49), `08` (49), `09` (49), `10` (49), `11` (49), `12` (49), `E` (49), `N` (49), `R` (49), `01.1` (42), `01.2` (42), `02.1` (42), `02.2` (42), `03.1` (42), `03.2` (42), `04.1` (42), `04.5` (42), `05.6` (42), `06.1` (42), `07.1` (42), `07.2` (42), `07.3` (42), `08.3` (42), `09.4` (42), `09.5` (42), `11.1` (42), `12.1` (42), `0` (28), `01.1.1` (24), `01.1.2` (24), `01.1.4` (24), `01.1.5` (24) … y 69 más (lista completa en el perfil JSON)
- `descripcion` — 109 valores: `Bienes` (49), `Servicios` (49), `Alimentos y bebidas no alcohólicas` (49), `Bebidas alcohólicas y tabaco` (49), `Prendas de vestir y calzado` (49), `Vivienda, agua, electricidad, gas y otros combustibles` (49), `Equipamiento y mantenimiento del hogar` (49), `Salud` (49), `Transporte` (49), `Comunicación` (49), `Recreación y cultura` (49), `Educación` (49), `Restaurantes y hoteles` (49), `Bienes y servicios varios` (49), `Estacional` (49), `Núcleo` (49), `Regulados` (49), `Alimentos` (42), `Bebidas no alcohólicas` (42), `Bebidas alcohólicas` (42), `Tabaco` (42), `Prendas de vestir y materiales` (42), `Calzado` (42), `Alquiler de la vivienda y gastos conexos` (42), `Electricidad, gas y otros combustibles` (42), `Bienes y servicios para la conservación del hogar` (42), `Productos medicinales, artefactos y equipos para la salud` (42), `Adquisición de vehículos` (42), `Funcionamiento de equipos de transporte personal` (42), `Transporte público` (42), `Servicios de telefonía e internet` (42), `Servicios recreativos y culturales` (42), `Periódicos, diarios, revistas, libros y artículos de papelería` (42), `Restaurantes y comidas fuera del hogar` (42), `Cuidado personal` (42), `Nivel general` (28), `Pan y cereales` (24), `Carnes y derivados` (24), `Leche, productos lácteos y huevos` (24), `Aceites, grasas y manteca` (24) … y 69 más (lista completa en el perfil JSON)
- `indicador` — 1 valores: `IPC base Dic16=100` (2107)
- `tipo_de_indicador` — 8 valores: `Indice` (308), `v_acum` (308), `v_ia` (308), `v_m` (308), `Incidencia_acum` (229), `Incidencia_ia` (229), `Incidencia_m` (229), `Precio promedio` (188)
- `tipo_de_indicador_descripcion` — 32 valores: `Nivel del período, base Diciembre 2016 = 100` (308), `Variación porcentual acumulada desde diciembre del año anterior` (308), `Variación porcentual respecto del mismo período del año anterior` (308), `Variación porcentual respecto del período anterior` (308), `Incidencia en la variación acumulada del nivel general de la region desde diciembre del año anterior` (229), `Incidencia en la variación del nivel general de la region respecto del mismo período del año anterior` (229), `Incidencia en la variación del nivel general de la region del período` (229), `Valor por kg` (89), `Valor por 500 g` (13), `Valor por Litro` (11), `Valor por 1,5 litros` (9), `Valor por Docena` (7), `Valor por 750 cc` (7), `Valor por 1.000 cc` (7), `Valor por 125 g` (7), `Valor por 800 g` (4), `Valor por 200 g` (4), `Valor por 390 g` (2), `Valor por 250 g` (2), `Valor por 150 g` (2), `Valor por Env. 4 u` (2), `Valor por Env. 6 u` (2), `Valor por 195 cc` (2), `Valor por 400 g` (2), `Valor por Bot. 1,5 litros` (2), `Valor por Lata 220 g` (2), `Valor por Lata 230 g` (2), `Valor por 8 porciones` (2), `Valor por 100 g` (2), `Valor por 10 u` (2), `Valor por 400 cc` (2), `Valor por 150 cc` (2)
- `region` — 7 valores: `GBA` (429), `Cuyo` (311), `Noreste` (311), `Noroeste` (311), `Pampeana` (311), `Patagonia` (311), `Nacional` (123)
- `unidad_de_medida` — 4 valores: `Porcentaje` (924), `Puntos porcentuales` (687), `Unidad` (308), `Pesos argentinos` (188)
- `observaciones`: 25 textos distintos además de vacío (ej.: "Esta Variedad está comprendida dentro del Producto cuyo código de COICOP Argentina 2019 es  01.1.1.1.05-Pan tipo francés fresco en piezas (m")

**Razón de nulo observada:** `valor_null`: `///` (60)

**Rango de series puntuales del IPC** (consulta filtrada sobre la tabla completa):

| region | clasificador | nivel | codigo | tipo_de_indicador | desde | hasta | filas | último valor |
|---|---|---|---|---|---|---|---:|---:|
| Nacional | IPC | Nivel General | 0 | Indice | 201612 | 202609 | 118 | 12514.1508 |
| Nacional | IPC | Nivel General | 0 | v_m | 201701 | 202609 | 117 | 1.9 |
| Nacional | COICOP Argentina 2019 | División | 01 | Indice | 201612 | 202609 | 118 | 13384.1945 |
| Nacional | COICOP Argentina 2019 | División | 01 | v_m | 201701 | 202609 | 117 | 2.0 |
| Nacional | Estacional, Núcleo y Regulados | Categoría | N | Indice | 201612 | 202609 | 118 | 12654.4322 |
| Nacional | Estacional, Núcleo y Regulados | Categoría | N | v_m | 201701 | 202609 | 117 | 1.7 |
| Nacional | Bienes y servicios | Categoría | B | Indice | 201612 | 202609 | 118 | 12233.3055 |
| Nacional | Bienes y servicios | Categoría | B | v_m | 201701 | 202609 | 117 | 1.7 |
| GBA | IPC | Nivel General | 0 | Indice | 201612 | 202609 | 118 | 12523.1733 |
| GBA | IPC | Nivel General | 0 | v_m | 201701 | 202609 | 117 | 2.0 |
| GBA | COICOP Argentina 2019 | División | 01 | Indice | 201612 | 202609 | 118 | 13494.1371 |
| GBA | COICOP Argentina 2019 | División | 01 | v_m | 201701 | 202609 | 117 | 2.2 |
| GBA | Estacional, Núcleo y Regulados | Categoría | N | Indice | 201612 | 202609 | 118 | 12707.2287 |
| GBA | Estacional, Núcleo y Regulados | Categoría | N | v_m | 201701 | 202609 | 117 | 1.8 |
| GBA | Bienes y servicios | Categoría | B | Indice | 201612 | 202609 | 118 | 12279.4125 |
| GBA | Bienes y servicios | Categoría | B | v_m | 201701 | 202609 | 117 | 2.0 |

Estructura del último período (202609): la región `Nacional` tiene Nivel general, las 12 divisiones COICOP, Estacional/Núcleo/Regulados y Bienes/Servicios (índice, variaciones e incidencias). Grupos, clases y productos COICOP están sólo por región (no `Nacional`). Los precios promedio (`Precio promedio`) son por región; en 201604 la tabla sólo tiene esos precios promedio de GBA, los índices arrancan en 201612.

### `valorizacion_canastas_cba_cbt`

Valorización de las canastas básicas (CBA y CBT). Área: Dirección de Índices de Precios de Consumo.

- **Filas:** 1.638 · **Rango (periodo):** 201604 → 202609
- **Clave de orden (para paginar):** `clasificador,nivel,codigo,descripcion,periodo,anio,mes,indicador,tipo_de_indicador,tipo_de_indicador_descripcion,region,unidad_de_medida`
- **Base del perfil de categorías:** tabla completa

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `clasificador` | string | Clasificador utilizado para organizar y codificar las categorías del dato |
| `nivel` | string | Nivel de desagregación de la categoría dentro de la estructura del clasificador |
| `codigo` | string | Código asignado a la categoría de acuerdo con el clasificador utilizado |
| `descripcion` | string | Denominación de la categoría correspondiente al código informado |
| `periodo` | string | Período de referencia del dato, expresado en formato AAAAMM (meses) |
| `anio` | number | Año correspondiente al período de referencia del dato |
| `mes` | number | Número del mes correspondiente al período de referencia. Utiliza valores comprendidos entre 1 (enero) y 12 (diciembre) |
| `indicador` | string | Nombre del indicador estadístico |
| `tipo_de_indicador` | string | Tipo de cálculo o presentación del indicador, como índice, variación intermensual, variación interanual, variación acumulada, incidencia o precio promedio |
| `tipo_de_indicador_descripcion` | string | Descripción del tipo de indicador |
| `region` | string | Región estadística a la que corresponde el dato |
| `unidad_de_medida` | string | Unidad en la que se expresa el valor del indicador |
| `valor` | numérico (sin tipo en el spec) | Valor del indicador para el período y las categorías informadas |
| `observaciones` | numérico (sin tipo en el spec) | Notas necesarias para el valor informado |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `clasificador` — 1 valores: `CBA y CBT` (1638)
- `nivel` — 2 valores: `Adulto equivalente` (882), `Hogar` (756)
- `codigo` — 9 valores: `CBA` (378), `CBT` (378), `ICE` (126), `CBA H1` (126), `CBA H2` (126), `CBA H3` (126), `CBT H1` (126), `CBT H2` (126), `CBT H3` (126)
- `descripcion` — 9 valores: `Canasta Basica Alimentaria` (378), `Canasta Basica Total` (378), `Inversa del coeficiente de Engel` (126), `Canasta Basica Alimentaria, Hogar 1` (126), `Canasta Basica Alimentaria, Hogar 2` (126), `Canasta Basica Alimentaria, Hogar 3` (126), `Canasta Basica Total, Hogar 1` (126), `Canasta Basica Total, Hogar 2` (126), `Canasta Basica Total, Hogar 3` (126)
- `indicador` — 1 valores: `Canasta` (1638)
- `tipo_de_indicador` — 8 valores: `v_ia` (252), `v_m` (252), `Hogar 1` (252), `Hogar 2` (252), `Hogar 3` (252), `CBA` (126), `CBT` (126), `ICE` (126)
- `tipo_de_indicador_descripcion` — 7 valores: `Valores mensuales por adulto equivalente, expresados en pesos` (252), `Variación porcentual respecto del mismo período del año anterior` (252), `Variación porcentual respecto del período anterior` (252), `Valores mensuales del Hogar de tres integrantes, compuesto por una mujer de 35 años, su hijo de 18 años y su madre de 61 años, expresados en pesos` (252), `Valores mensuales del Hogar de cuatro integrantes, compuesto por un varón de 35 años, una mujer de 31 años, un hijo de 6 años y una hija de 8 años, expresados en pesos` (252), `Valores mensuales del Hogar de cinco integrantes, constituido por una pareja de un varón y una mujer, ambos de 30 años, y tres hijos de 5, 3 y 1 año, expresados en pesos` (252), `Proporcion de gastos totales sobre gastos alimentarios` (126)
- `region` — 1 valores: `GBA` (1638)
- `unidad_de_medida` — 3 valores: `Pesos argentinos` (1008), `Porcentaje` (504), `Unidad` (126)
- `observaciones`: 0 textos distintos además de vacío

**Razón de nulo observada:** `valor_null`: `///` (26)

**Series (13):**

| clasificador | nivel | codigo | descripcion | indicador | tipo_de_indicador | tipo_de_indicador_descripcion | region | unidad_de_medida | desde | hasta | filas |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CBA y CBT | Adulto equivalente | CBA | Canasta Basica Alimentaria | Canasta | CBA | Valores mensuales por adulto equivalente, expresados en pesos | GBA | Pesos argentinos | 201604 | 202609 | 126 |
| CBA y CBT | Adulto equivalente | CBA | Canasta Basica Alimentaria | Canasta | v_ia | Variación porcentual respecto del mismo período del año anterior | GBA | Porcentaje | 201604 | 202609 | 126 |
| CBA y CBT | Adulto equivalente | CBA | Canasta Basica Alimentaria | Canasta | v_m | Variación porcentual respecto del período anterior | GBA | Porcentaje | 201604 | 202609 | 126 |
| CBA y CBT | Adulto equivalente | CBT | Canasta Basica Total | Canasta | CBT | Valores mensuales por adulto equivalente, expresados en pesos | GBA | Pesos argentinos | 201604 | 202609 | 126 |
| CBA y CBT | Adulto equivalente | CBT | Canasta Basica Total | Canasta | v_ia | Variación porcentual respecto del mismo período del año anterior | GBA | Porcentaje | 201604 | 202609 | 126 |
| CBA y CBT | Adulto equivalente | CBT | Canasta Basica Total | Canasta | v_m | Variación porcentual respecto del período anterior | GBA | Porcentaje | 201604 | 202609 | 126 |
| CBA y CBT | Adulto equivalente | ICE | Inversa del coeficiente de Engel | Canasta | ICE | Proporcion de gastos totales sobre gastos alimentarios | GBA | Unidad | 201604 | 202609 | 126 |
| CBA y CBT | Hogar | CBA H1 | Canasta Basica Alimentaria, Hogar 1 | Canasta | Hogar 1 | Valores mensuales del Hogar de tres integrantes, compuesto por una mujer de 35 años, su hijo de 18 años y su madre de 61 años, expresados en pesos | GBA | Pesos argentinos | 201604 | 202609 | 126 |
| CBA y CBT | Hogar | CBA H2 | Canasta Basica Alimentaria, Hogar 2 | Canasta | Hogar 2 | Valores mensuales del Hogar de cuatro integrantes, compuesto por un varón de 35 años, una mujer de 31 años, un hijo de 6 años y una hija de 8 años, expresados en pesos | GBA | Pesos argentinos | 201604 | 202609 | 126 |
| CBA y CBT | Hogar | CBA H3 | Canasta Basica Alimentaria, Hogar 3 | Canasta | Hogar 3 | Valores mensuales del Hogar de cinco integrantes, constituido por una pareja de un varón y una mujer, ambos de 30 años, y tres hijos de 5, 3 y 1 año, expresados en pesos | GBA | Pesos argentinos | 201604 | 202609 | 126 |
| CBA y CBT | Hogar | CBT H1 | Canasta Basica Total, Hogar 1 | Canasta | Hogar 1 | Valores mensuales del Hogar de tres integrantes, compuesto por una mujer de 35 años, su hijo de 18 años y su madre de 61 años, expresados en pesos | GBA | Pesos argentinos | 201604 | 202609 | 126 |
| CBA y CBT | Hogar | CBT H2 | Canasta Basica Total, Hogar 2 | Canasta | Hogar 2 | Valores mensuales del Hogar de cuatro integrantes, compuesto por un varón de 35 años, una mujer de 31 años, un hijo de 6 años y una hija de 8 años, expresados en pesos | GBA | Pesos argentinos | 201604 | 202609 | 126 |
| CBA y CBT | Hogar | CBT H3 | Canasta Basica Total, Hogar 3 | Canasta | Hogar 3 | Valores mensuales del Hogar de cinco integrantes, constituido por una pareja de un varón y una mujer, ambos de 30 años, y tres hijos de 5, 3 y 1 año, expresados en pesos | GBA | Pesos argentinos | 201604 | 202609 | 126 |

### `indice_salarios`

Índice de salarios. Área: Dirección de Índices de Precios de la Producción.

- **Filas:** 3.406 · **Rango (periodo):** 201510 → 202608
- **Clave de orden (para paginar):** `clasificador,nivel,codigo,descripcion,periodo,anio,mes,indicador,tipo_de_indicador,tipo_de_indicador_descripcion,unidad_de_medida`
- **Base del perfil de categorías:** tabla completa

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `clasificador` | string | Clasificador utilizado para organizar y codificar las categorías del dato |
| `nivel` | string | Nivel de desagregación de la categoría dentro de la estructura del clasificador |
| `codigo` | string | Código asignado a la categoría de acuerdo con el clasificador utilizado |
| `descripcion` | string | Denominación de la categoría correspondiente al código informado |
| `periodo` | string | Período de referencia del dato, expresado en formato AAAAMM (meses) |
| `anio` | number | Año correspondiente al período de referencia del dato |
| `mes` | number | Número del mes correspondiente al período de referencia. Utiliza valores comprendidos entre 1 (enero) y 12 (diciembre) |
| `indicador` | string | Nombre del indicador estadístico |
| `tipo_de_indicador` | string | Tipo de cálculo o presentación del indicador, como índice, variación intermensual, variación interanual, variación acumulada, incidencia o precio promedio |
| `tipo_de_indicador_descripcion` | string | Descripción del tipo de indicador |
| `unidad_de_medida` | string | Unidad en la que se expresa el valor del indicador |
| `valor` | numérico (sin tipo en el spec) | Valor del indicador para el período y las categorías informadas |
| `observaciones` | numérico (sin tipo en el spec) | Notas necesarias para el valor informado  |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `clasificador` — 1 valores: `IS 2001` (3406)
- `nivel` — 4 valores: `1` (1048), `2` (1048), `3` (786), `0` (524)
- `codigo` — 7 valores: `0` (524), `100` (524), `200` (524), `110` (524), `120` (524), `121` (393), `122` (393)
- `descripcion` — 7 valores: `Nivel general` (524), `Total registrado` (524), `Total no registrado` (524), `Sector privado registrado` (524), `Sector público` (524), `Subsector público nacional` (393), `Subsector público provincial` (393)
- `indicador` — 1 valores: `Índice de salarios (IS)` (3406)
- `tipo_de_indicador` — 4 valores: `v_acum` (917), `v_ia` (917), `v_m` (917), `Indice` (655)
- `tipo_de_indicador_descripcion` — 4 valores: `Variación porcentual acumulada desde diciembre del año anterior` (917), `Variación porcentual respecto del mismo período del año anterior` (917), `Variación porcentual respecto del período anterior` (917), `Nivel del período, base octubre 2016=100` (655)
- `unidad_de_medida` — 2 valores: `Porcentaje` (2751), `Unidad` (655)
- `observaciones`: 0 textos distintos además de vacío

**Razón de nulo observada:** `valor_null`: `///` (648)

**Series (26):**

| clasificador | nivel | codigo | descripcion | indicador | tipo_de_indicador | tipo_de_indicador_descripcion | unidad_de_medida | desde | hasta | filas |
|---|---|---|---|---|---|---|---|---|---|---|
| IS 2001 | 0 | 0 | Nivel general | Índice de salarios (IS) | Indice | Nivel del período, base octubre 2016=100 | Unidad | 201510 | 202608 | 131 |
| IS 2001 | 0 | 0 | Nivel general | Índice de salarios (IS) | v_acum | Variación porcentual acumulada desde diciembre del año anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 0 | 0 | Nivel general | Índice de salarios (IS) | v_ia | Variación porcentual respecto del mismo período del año anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 0 | 0 | Nivel general | Índice de salarios (IS) | v_m | Variación porcentual respecto del período anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 1 | 100 | Total registrado | Índice de salarios (IS) | Indice | Nivel del período, base octubre 2016=100 | Unidad | 201510 | 202608 | 131 |
| IS 2001 | 1 | 100 | Total registrado | Índice de salarios (IS) | v_acum | Variación porcentual acumulada desde diciembre del año anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 1 | 100 | Total registrado | Índice de salarios (IS) | v_ia | Variación porcentual respecto del mismo período del año anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 1 | 100 | Total registrado | Índice de salarios (IS) | v_m | Variación porcentual respecto del período anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 1 | 200 | Total no registrado | Índice de salarios (IS) | Indice | Nivel del período, base octubre 2016=100 | Unidad | 201510 | 202608 | 131 |
| IS 2001 | 1 | 200 | Total no registrado | Índice de salarios (IS) | v_acum | Variación porcentual acumulada desde diciembre del año anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 1 | 200 | Total no registrado | Índice de salarios (IS) | v_ia | Variación porcentual respecto del mismo período del año anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 1 | 200 | Total no registrado | Índice de salarios (IS) | v_m | Variación porcentual respecto del período anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 2 | 110 | Sector privado registrado | Índice de salarios (IS) | Indice | Nivel del período, base octubre 2016=100 | Unidad | 201510 | 202608 | 131 |
| IS 2001 | 2 | 110 | Sector privado registrado | Índice de salarios (IS) | v_acum | Variación porcentual acumulada desde diciembre del año anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 2 | 110 | Sector privado registrado | Índice de salarios (IS) | v_ia | Variación porcentual respecto del mismo período del año anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 2 | 110 | Sector privado registrado | Índice de salarios (IS) | v_m | Variación porcentual respecto del período anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 2 | 120 | Sector público | Índice de salarios (IS) | Indice | Nivel del período, base octubre 2016=100 | Unidad | 201510 | 202608 | 131 |
| IS 2001 | 2 | 120 | Sector público | Índice de salarios (IS) | v_acum | Variación porcentual acumulada desde diciembre del año anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 2 | 120 | Sector público | Índice de salarios (IS) | v_ia | Variación porcentual respecto del mismo período del año anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 2 | 120 | Sector público | Índice de salarios (IS) | v_m | Variación porcentual respecto del período anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 3 | 121 | Subsector público nacional | Índice de salarios (IS) | v_acum | Variación porcentual acumulada desde diciembre del año anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 3 | 121 | Subsector público nacional | Índice de salarios (IS) | v_ia | Variación porcentual respecto del mismo período del año anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 3 | 121 | Subsector público nacional | Índice de salarios (IS) | v_m | Variación porcentual respecto del período anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 3 | 122 | Subsector público provincial | Índice de salarios (IS) | v_acum | Variación porcentual acumulada desde diciembre del año anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 3 | 122 | Subsector público provincial | Índice de salarios (IS) | v_ia | Variación porcentual respecto del mismo período del año anterior | Porcentaje | 201510 | 202608 | 131 |
| IS 2001 | 3 | 122 | Subsector público provincial | Índice de salarios (IS) | v_m | Variación porcentual respecto del período anterior | Porcentaje | 201510 | 202608 | 131 |

### `icc_precios_construccion`

Índice del costo de la construcción. Área: Dirección de Índices de Precios de la Producción.

- **Filas:** 14.017 · **Rango (periodo):** 201511 → 202609
- **Clave de orden (para paginar):** `indicador,codigo_apertura,codigo_CPC_1,clasificador,nivel,descripcion,periodo,anio,mes,tipo_de_indicador,tipo_de_indicador_descripcion,region,unidad_de_medida`
- **Base del perfil de categorías:** tabla completa

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `indicador` | string | Nombre del indicador estadístico |
| `codigo_apertura` | string | Código que identifica el nivel de apertura o desagregación del dato |
| `codigo_CPC_1` | string | Código de la Clasificación Central Provisional de Productos (CPC) elaborada por la Organización de las Naciones Unidas.  |
| `clasificador` | string | Clasificador utilizado para organizar y codificar las categorías del dato |
| `nivel` | string | Nivel de desagregación de la categoría dentro de la estructura del clasificador |
| `descripcion` | string | Denominación de la categoría correspondiente al código informado |
| `periodo` | string | Período de referencia del dato, expresado en formato AAAAMM (meses) |
| `anio` | number | Año correspondiente al período de referencia del dato |
| `mes` | number | Número del mes correspondiente al período de referencia. Utiliza valores comprendidos entre 1 (enero) y 12 (diciembre) |
| `tipo_de_indicador` | string | Tipo de cálculo o presentación del indicador, como índice, variación intermensual, variación interanual, variación acumulada, incidencia o precio promedio |
| `tipo_de_indicador_descripcion` | string | Descripción del tipo de indicador |
| `region` | string | Región estadística a la que corresponde el dato |
| `unidad_de_medida` | string | Unidad en la que se expresa el valor del indicador |
| `valor` | numérico (sin tipo en el spec) | Valor del indicador para el período y las categorías informadas |
| `observaciones` | numérico (sin tipo en el spec) | Notas necesarias para el valor informado  |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `indicador` — 1 valores: `ICC` (14017)
- `codigo_apertura` — 29 valores: `01` (655), `02` (655), `03` (655), `0` (524), `IT-01` (524), `IT-02` (524), `IT-03` (524), `IT-04` (524), `IT-05` (524), `IT-06` (524), `IT-07` (524), `IT-08` (524), `IT-09` (524), `IT-10` (524), `IT-11` (524), `IT-12` (524), `IT-13` (524), `01-15310-11` (393), `01-37350-11` (393), `01-37440-11` (393), `01-41242-11` (393), `02-01` (393), `02-02` (393), `03-51800-11` (393), `03-51800-21` (393), `03-71233-11` (393), `03-71240-11` (393), `03-74110-11` (393), `03-83107-1` (393)
- `codigo_CPC_1` — 11 valores: `-` (10087), `15310-11` (393), `37350-11` (393), `37440-11` (393), `41242-11` (393), `51800-11` (393), `51800-21` (393), `71233-11` (393), `71240-11` (393), `74110-11` (393), `83107-1` (393)
- `clasificador` — 2 valores: `ICC 93` (10087), `ICC 93-CPC` (3930)
- `nivel` — 5 valores: `Ítems` (6812), `Producto` (3930), `Capitulo` (1965), `Grupo` (786), `Nivel general` (524)
- `descripcion` — 29 valores: `Materiales` (655), `Mano de obra` (655), `Gastos generales` (655), `Nivel general` (524), `Movimiento de tierra` (524), `Estructura` (524), `Albañilería` (524), `Yesería` (524), `Instalación sanitaria y contraincendios` (524), `Instalación de gas` (524), `Instalación eléctrica` (524), `Carpintería metálica y herrería` (524), `Carpintería de madera` (524), `Ascensores` (524), `Vidrios` (524), `Pintura` (524), `Otros trabajos y gastos` (524), `Arena fina` (393), `Ladrillo cerámico hueco` (393), `Cemento portland normal, en bolsa` (393), `Acero aletado conformado, en barra` (393), `Mano de obra asalariada` (393), `Subcontratos de mano de obra` (393), `Alquiler de pala cargadora` (393), `Alquiler de retroexcavadora` (393), `Alquiler de camioneta` (393), `Alquiler de camión volcador` (393), `Alquiler de volquete` (393), `Alquiler de andamios` (393)
- `tipo_de_indicador` — 5 valores: `v_acum` (3799), `v_ia` (3799), `v_m` (3799), `Indice` (2227), `incidencia` (393)
- `tipo_de_indicador_descripcion` — 5 valores: `Variación porcentual acumulada desde diciembre del año anterior` (3799), `Variación porcentual respecto del mismo período del año anterior` (3799), `Variación porcentual respecto del período anterior` (3799), `Nivel del período, base 1993, ene-22=100` (2227), `Incidencia en la variación mensual del Nivel General` (393)
- `region` — 1 valores: `GBA` (14017)
- `unidad_de_medida` — 3 valores: `Porcentaje` (11397), `Unidad` (2227), `Puntos porcentuales` (393)
- `observaciones`: 1 textos distintos además de vacío (ej.: "* Dato provisorio")

**Razón de nulo observada:** `valor_null`: `///` (394)

### `redeterminacion_precios_contratos_obras_publicas`

Redeterminación de precios de obras públicas. Área: Dirección de Índices de Precios de la Producción.

- **Filas:** 236.192 · **Rango (periodo):** 201510 → 202609
- **Clave de orden (para paginar):** `indicador,operativo,inciso,descripcion_inciso,codigo_apertura,clasificador,nivel,descripcion,origen,periodo,anio,mes,tipo_de_indicador,tipo_de_indicador_descripcion,region,unidad_de_medida`
- **Base del perfil de categorías:** solo filas de los períodos 201510 y 202609 (tabla de 236192 filas)

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `indicador` | string | Nombre del indicador estadístico |
| `operativo` | string | Operativo estadístico del que proviene el dato |
| `inciso` | string | Código o denominación abreviada del inciso correspondiente al artículo 15 del Decreto 1295/2002 |
| `descripcion_inciso` | string | Denominación del inciso correspondiente al artículo 15 del Decreto 1295/2002 |
| `codigo_apertura` | string | Código que identifica el nivel de apertura o desagregación del dato |
| `codigo_CPC_1` | numérico (sin tipo en el spec) | Código de la Clasificación Central Provisional de Productos (CPC) elaborada por la Organización de las Naciones Unidas. |
| `codigo_CIUU_3` | numérico (sin tipo en el spec) | Código de la Clasificación Industrial Internacional Uniforme (CIIU), revisión 3 |
| `clasificador` | string | Clasificador utilizado para organizar y codificar las categorías del dato |
| `nivel` | string | Nivel de desagregación de la categoría dentro de la estructura del clasificador |
| `descripcion` | string | Denominación de la categoría correspondiente al código informado |
| `origen` | string | Origen nacional o importado del producto de referencia |
| `periodo` | string | Período de referencia del dato, expresado en formato AAAAMM (meses) |
| `anio` | number | Año correspondiente al período de referencia del dato |
| `mes` | number | Número del mes correspondiente al período de referencia. Utiliza valores comprendidos entre 1 (enero) y 12 (diciembre) |
| `tipo_de_indicador` | string | Tipo de cálculo o presentación del indicador, como índice, variación intermensual, variación interanual, variación acumulada, incidencia o precio promedio |
| `tipo_de_indicador_descripcion` | string | Descripción del tipo de indicador |
| `region` | string | Región estadística a la que corresponde el dato |
| `unidad_de_medida` | string | Unidad en la que se expresa el valor del indicador |
| `valor` | numérico (sin tipo en el spec) | Valor del indicador para el período y las categorías informadas |
| `observaciones` | numérico (sin tipo en el spec) | Notas necesarias para el valor informado |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `indicador` — 1 valores: `Obra pública` (2896)
- `operativo` — 2 valores: `ICC` (2192), `IPIB (SIPM)` (704)
- `inciso` — 22 valores: `-` (2752), `a` (8), `b` (8), `c` (8), `d` (8), `f` (8), `g` (8), `h` (8), `m` (8), `n` (8), `p` (8), `q` (8), `r` (8), `s` (8), `u` (8), `v` (8), `e` (4), `i` (4), `j` (4), `k` (4), `t` (4), `w` (4)
- `descripcion_inciso` — 22 valores: `-` (2752), `Mano de obra` (8), `Albañilería` (8), `Pisos y revestimientos` (8), `Carpinterías` (8), `Andamios` (8), `Artefactos de iluminación y cableado` (8), `Caños de PVC para instalaciones varias` (8), `Aceros - Hierro aletado` (8), `Cemento` (8), `Gastos generales` (8), `Arena` (8), `Artefactos para baño y grifería` (8), `Hormigón` (8), `Válvulas de bronce` (8), `Electrobombas` (8), `Productos químicos` (4), `Motores eléctricos y equipos de aire acondicionado` (4), `Equipo - Amortización de equipo` (4), `Asfaltos, combustibles y lubricantes` (4), `Medidores de caudal` (4), `Membrana impermeabilizante` (4)
- `codigo_apertura` — 450 valores: `01-15320-11` (8), `01-15400-11` (8), `01-15400-21` (8), `01-27230-11` (8), `01-31100-11` (8), `01-31210-11` (8), `01-31210-21` (8), `01-31210-22` (8), `01-31210-31` (8), `01-31210-32` (8), `01-31210-33` (8), `01-31210-41` (8), `01-31600-11` (8), `01-31600-12` (8), `01-31600-21` (8), `01-31600-22` (8), `01-31600-23` (8), `01-31600-31` (8), `01-31600-32` (8), `01-31600-33` (8), `01-31600-41` (8), `01-31600-42` (8), `01-31600-51` (8), `01-31600-53` (8), `01-31600-6` (8), `01-31600-61` (8), `01-31600-62` (8), `01-31600-63` (8), `01-31600-7` (8), `01-31600-71` (8), `01-31600-72` (8), `01-31600-73` (8), `01-31600-81` (8), `01-34720-11` (8), `01-35110-11` (8), `01-35110-12` (8), `01-35110-21` (8), `01-35110-22` (8), `01-35110-31` (8), `01-35110-32` (8) … y 410 más (lista completa en el perfil JSON)
- `codigo_CPC_1` — 400 valores: `None` (260), `15320-11` (8), `15400-11` (8), `15400-21` (8), `27230-11` (8), `31100-11` (8), `31210-11` (8), `31210-21` (8), `31210-22` (8), `31210-31` (8), `31210-32` (8), `31210-33` (8), `31210-41` (8), `31600-11` (8), `31600-12` (8), `31600-21` (8), `31600-22` (8), `31600-23` (8), `31600-31` (8), `31600-32` (8), `31600-33` (8), `31600-41` (8), `31600-42` (8), `31600-51` (8), `31600-53` (8), `31600-6` (8), `31600-61` (8), `31600-62` (8), `31600-63` (8), `31600-7` (8), `31600-71` (8), `31600-72` (8), `31600-73` (8), `31600-81` (8), `34720-11` (8), `35110-11` (8), `35110-12` (8), `35110-21` (8), `35110-22` (8), `35110-31` (8) … y 360 más (lista completa en el perfil JSON)
- `codigo_CIUU_3` — 53 valores: `None` (2196), `2413` (48), `2710` (44), `2520` (36), `2922` (36), `2320` (32), `2720` (32), `2899` (32), `1410` (24), `3410` (24), `2422` (20), `2610` (20), `2699` (20), `2511` (16), `2693` (16), `2695` (16), `2811` (16), `2893` (16), `2913` (16), `2924` (16), `3110` (16), `2021` (12), `2022` (12), `2519` (12), `2692` (12), `3430` (12), `1110` (8), `2010` (8), `2101` (8), `2411` (8), `2429` (8), `2691` (8), `2694` (8), `2912` (8), `3120` (8), `2221` (4), `2731` (4), `2813` (4), `291` (4), `2911` (4) … y 13 más (lista completa en el perfil JSON)
- `clasificador` — 4 valores: `ICC 93-CPC` (2080), `CIIU3-CPC` (556), `CIIU3` (148), `ICC 93` (112)
- `nivel` — 8 valores: `Producto` (2656), `Subclase` (100), `Ítems` (40), `Grupo` (28), `Subgrupo` (24), `Capitulo` (16), `Clase` (16), `División` (16)
- `descripcion` — 447 valores: `Instalación eléctrica` (16), `Yesería` (16), `Canto rodado natural` (8), `Arcilla expandida` (8), `Tosca` (8), `Alfombra de pelo cortado de material sintético, con colocación` (8), `Tirante sin cepillar` (8), `Tabla con una cara cepillada para encofrado` (8), `Machimbre con una cara cepillada` (8), `Tirante cepillado` (8), `Piso de entablonado, con colocación` (8), `Piso de parqué, con colocación` (8), `Zócalo de madera` (8), `Listón yesero` (8), `Cortina de enrollar regulable de madera` (8), `Cortina de enrollar común de madera` (8), `Puerta placa de madera, de calidad superior` (8), `Puerta placa de madera, de calidad media` (8), `Puerta placa de madera, de calidad inferior` (8), `Puerta de entrada de madera con tableros, de calidad superior` (8), `Puerta de entrada de madera con tableros, de calidad media` (8), `Puerta de entrada de madera con tableros, de calidad inferior` (8), `Puerta balcón corrediza de madera` (8), `Ventana corrediza de madera` (8), `Frente de placard de madera, de calidad superior` (8), `Frente de placard de madera, de calidad inferior` (8), `Cajonera para placard (incluye: Cajonera para placard de calidad inferior, media y superior)` (8), `Cajonera para placard, de calidad superior` (8), `Cajonera para placard, de calidad media` (8), `Cajonera para placard, de calidad inferior` (8), `Estantes y divisiones para placard (incluye: Estantes y divisiones para placard de calidad inferior, media y superior)` (8), `Estantes y divisiones para placard, de calidad superior` (8), `Estantes y divisiones para placard, de calidad media` (8), `Estantes y divisiones para placard, de calidad inferior` (8), `Portón levadizo de madera` (8), `Poliestireno expandido en placas` (8), `Enduído plástico al agua para exteriores` (8), `Enduído plástico al agua para interiores` (8), `Esmalte sintético brillante` (8), `Esmalte sintético semimate` (8) … y 407 más (lista completa en el perfil JSON)
- `origen` — 3 valores: `-` (2192), `Nacional` (596), `Importado` (108)
- `tipo_de_indicador` — 4 valores: `Indice` (724), `v_acum` (724), `v_ia` (724), `v_m` (724)
- `tipo_de_indicador_descripcion` — 5 valores: `Variación porcentual acumulada desde diciembre del año anterior` (724), `Variación porcentual respecto del mismo período del año anterior` (724), `Variación porcentual respecto del período anterior` (724), `Nivel del período, base 1993, oct-15=100` (548), `Nivel del período, base 1993, dic-15=100` (176)
- `region` — 2 valores: `GBA` (2192), `Total del país` (704)
- `unidad_de_medida` — 2 valores: `Porcentaje` (2172), `Unidad` (724)
- `observaciones`: 20 textos distintos además de vacío (ej.: "* Dato provisorio")

**Razón de nulo observada:** `valor_null`: `///` (774), `s` (201)

### `sipm_precios_mayoristas`

Sistema de índices de precios mayoristas. Área: Dirección de Índices de Precios de la Producción.

- **Filas:** 234.260 · **Rango (periodo):** 201512 → 202609
- **Clave de orden (para paginar):** `operativo,indicador,clasificador,nivel,codigo_apertura,descripcion,periodo,anio,mes,tipo_de_indicador,tipo_de_indicador_descripcion,region,unidad_de_medida`
- **Base del perfil de categorías:** solo filas de los períodos 201512 y 202609 (tabla de 234260 filas)

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `operativo` | string | Operativo estadístico del que proviene el dato |
| `indicador` | string | Nombre del indicador estadístico |
| `clasificador` | string | Clasificador utilizado para organizar y codificar las categorías del dato |
| `nivel` | string | Nivel de desagregación de la categoría dentro de la estructura del clasificador |
| `codigo_apertura` | string | Código que identifica el nivel de apertura o desagregación del dato |
| `descripcion` | string | Denominación de la categoría correspondiente al código informado |
| `periodo` | string | Período de referencia del dato, expresado en formato AAAAMM (meses) |
| `anio` | number | Año correspondiente al período de referencia del dato |
| `mes` | number | Número del mes correspondiente al período de referencia. Utiliza valores comprendidos entre 1 (enero) y 12 (diciembre) |
| `tipo_de_indicador` | string | Tipo de cálculo o presentación del indicador, como índice, variación intermensual, variación interanual, variación acumulada, incidencia o precio promedio |
| `tipo_de_indicador_descripcion` | string | Descripción del tipo de indicador |
| `region` | string | Región estadística a la que corresponde el dato |
| `unidad_de_medida` | string | Unidad en la que se expresa el valor del indicador |
| `valor` | numérico (sin tipo en el spec) | Valor del indicador para el período y las categorías informadas |
| `observaciones` | numérico (sin tipo en el spec) | Notas necesarias para el valor informado |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `operativo` — 1 valores: `SIPM` (3604)
- `indicador` — 3 valores: `IPIB` (1208), `IPIM` (1208), `IPP` (1188)
- `clasificador` — 2 valores: `CIIU3` (3480), `SIPM 93` (124)
- `nivel` — 7 valores: `Clase` (1512), `Grupo` (1008), `División` (780), `Categoría de Tabulación` (150), `Sector` (80), `Origen` (50), `Nivel general` (24)
- `codigo_apertura` — 142 valores: `A` (30), `B` (30), `C` (30), `D` (30), `E` (30), `01` (30), `05` (30), `11` (30), `14` (30), `15` (30), `16` (30), `17` (30), `18` (30), `19` (30), `20` (30), `21` (30), `22` (30), `23` (30), `24` (30), `25` (30), `26` (30), `27` (30), `28` (30), `29` (30), `31` (30), `32` (30), `33` (30), `34` (30), `35` (30), `36` (30), `40` (30), `2` (30), `N` (30), `1` (30), `0111` (24), `0112` (24), `0113` (24), `0121` (24), `0122` (24), `1511` (24) … y 102 más (lista completa en el perfil JSON)
- `descripcion` — 135 valores: `Productos agropecuarios` (60), `Productos pesqueros` (60), `Energía eléctrica` (60), `Otros medios de transporte` (54), `Sustancias químicas básicas` (48), `Otros productos químicos` (48), `Productos importados` (40), `Productos minerales` (30), `Productos manufacturados` (30), `Petróleo crudo y gas natural` (30), `Productos minerales no metalíferos` (30), `Alimentos y bebidas` (30), `Tabaco` (30), `Productos textiles` (30), `Prendas de materiales textiles` (30), `Cuero, artículos de marroquinería y calzado` (30), `Madera y productos de madera excepto muebles` (30), `Papel y productos de papel` (30), `Impresiones y reproducción de grabaciones` (30), `Productos refinados del petróleo` (30), `Sustancias y productos químicos` (30), `Productos de caucho y plástico` (30), `Productos de minerales no metálicos` (30), `Productos metálicos básicos` (30), `Productos metálicos excepto máquinas y equipos` (30), `Máquinas y equipos` (30), `Máquinas y aparatos eléctricos` (30), `Equipos y aparatos de radio y televisión` (30), `Equipos para medicina e instrumentos de medición` (30), `Vehículos automotores, carrocerías y repuestos` (30), `Muebles y otros productos industriales` (30), `Industria Manufacturera y Energía Eléctrica` (30), `Productos nacionales` (30), `Primarios` (30), `Cereales y oleaginosas` (24), `Hortalizas y legumbres` (24), `Frutas` (24), `Ganado vacuno y leche` (24), `Ganado porcino y productos de granja` (24), `Productos cárnicos` (24) … y 95 más (lista completa en el perfil JSON)
- `tipo_de_indicador` — 5 valores: `Indice` (848), `v_acum` (848), `v_ia` (848), `v_m` (848), `incidencia` (212)
- `tipo_de_indicador_descripcion` — 5 valores: `Nivel del período, base 1993, dic-15=100` (848), `Variación porcentual acumulada desde diciembre del año anterior` (848), `Variación porcentual respecto del mismo período del año anterior` (848), `Variación porcentual respecto del período anterior` (848), `Incidencia en la variación porcentual mensual del nivel general` (212)
- `region` — 1 valores: `Total del país` (3604)
- `unidad_de_medida` — 3 valores: `Porcentaje` (2544), `Unidad` (848), `Puntos porcentuales` (212)
- `observaciones`: 1 textos distintos además de vacío (ej.: "* Dato provisorio")

**Razón de nulo observada:** `valor_null`: `///` (1378)

### `estimador-mensual-de-actividad-economica-nivel-general`

Estimador mensual de actividad económica. Nivel general. Área: Dirección Nacional de Cuentas Nacionales.

- **Filas:** 1.632 · **Rango (periodo):** 200401 → 202608
- **Clave de orden (para paginar):** `tipo_de_indicador_descripcion,anio,mes,periodo,tipo_de_indicador`
- **Base del perfil de categorías:** tabla completa

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `tipo_de_indicador_descripcion` | string | Descripción del tipo de indicador |
| `anio` | number | Año correspondiente al período de referencia del dato |
| `mes` | number | Número del mes correspondiente al período de referencia. Utiliza valores comprendidos entre 1 (enero) y 12 (diciembre) |
| `periodo` | string | Período de referencia del dato, expresado en formato AAAAMM (meses) |
| `tipo_de_indicador` | string | Tipo de cálculo o presentación del indicador, como índice, variación intermensual, variación interanual, variación acumulada, incidencia o peso promedio |
| `valor` | numérico (sin tipo en el spec) | Valor del indicador para el período y las categorías informadas |
| `observaciones` | numérico (sin tipo en el spec) | Notas necesarias para el valor informado |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `tipo_de_indicador_descripcion` — 6 valores: `Var % interanual serie original` (272), `Var % mensual serie desestacionalizada` (272), `Var % mensual serie tendencia-ciclo` (272), `Índice serie desestacionalizada` (272), `Índice serie original` (272), `Índice serie tendencia-ciclo` (272)
- `tipo_de_indicador` — 2 valores: `Variación porcentual` (816), `Índice base 2004=100` (816)
- `observaciones`: 0 textos distintos además de vacío

**Razón de nulo observada:** `valor_null`: `///` (14)

**Series (6):**

| tipo_de_indicador_descripcion | tipo_de_indicador | desde | hasta | filas |
|---|---|---|---|---|
| Var % interanual serie original | Variación porcentual | 200401 | 202608 | 272 |
| Var % mensual serie desestacionalizada | Variación porcentual | 200401 | 202608 | 272 |
| Var % mensual serie tendencia-ciclo | Variación porcentual | 200401 | 202608 | 272 |
| Índice serie desestacionalizada | Índice base 2004=100 | 200401 | 202608 | 272 |
| Índice serie original | Índice base 2004=100 | 200401 | 202608 | 272 |
| Índice serie tendencia-ciclo | Índice base 2004=100 | 200401 | 202608 | 272 |

### `estimador-mensual-de-actividad-economica-sectores`

Estimador mensual de actividad económica. Sectores. Área: Dirección Nacional de Cuentas Nacionales.

- **Filas:** 8.512 · **Rango (periodo):** 200401 → 202608
- **Clave de orden (para paginar):** `anio,mes,codigo,descripcion,periodo,tipo_de_indicador`
- **Base del perfil de categorías:** tabla completa

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `anio` | number | Año correspondiente al período de referencia del dato |
| `mes` | number | Número del mes correspondiente al período de referencia. Utiliza valores comprendidos entre 1 (enero) y 12 (diciembre) |
| `codigo` | string | Código letra de la Clasificación nacional de actividades económicas 2004 (ClaNAE04) |
| `descripcion` | string | Denominación de la categoría correspondiente al código informado |
| `periodo` | string | Período de referencia del dato, expresado en formato AAAAMM (meses) |
| `tipo_de_indicador` | string | Tipo de cálculo o presentación del indicador, como índice, variación intermensual, variación interanual, variación acumulada, incidencia o peso promedio |
| `valor` | numérico (sin tipo en el spec) | Valor del indicador para el período y las categorías informadas |
| `observaciones` | numérico (sin tipo en el spec) | Notas necesarias para el valor informado |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `codigo` — 16 valores: `A` (532), `B` (532), `C` (532), `D` (532), `E` (532), `F` (532), `G` (532), `H` (532), `I` (532), `J` (532), `K` (532), `L` (532), `M` (532), `N` (532), `O` (532), `T_S` (532)
- `descripcion` — 16 valores: `Agricultura, ganadería, caza y silvicultura` (532), `Pesca` (532), `Explotación de minas y canteras` (532), `Industria manufacturera` (532), `Electricidad, gas y agua` (532), `Construcción` (532), `Comercio mayorista, minorista y reparaciones` (532), `Hoteles y restaurantes` (532), `Transporte y comunicaciones` (532), `Intermediación financiera` (532), `Actividades inmobiliarias, empresariales y de alquiler` (532), `Administración pública y defensa; planes de seguridad social de afiliación obligatoria` (532), `Enseñanza` (532), `Servicios sociales y de salud` (532), `Otras actividades de servicios comunitarios, sociales y personales` (532), `Impuestos netos de subsidios` (532)
- `tipo_de_indicador` — 2 valores: `Índice base 2004=100` (4352), `Variación porcentual interanual` (4160)
- `observaciones`: 0 textos distintos además de vacío

**Series (32):**

| codigo | descripcion | tipo_de_indicador | desde | hasta | filas |
|---|---|---|---|---|---|
| A | Agricultura, ganadería, caza y silvicultura | Variación porcentual interanual | 200501 | 202608 | 260 |
| A | Agricultura, ganadería, caza y silvicultura | Índice base 2004=100 | 200401 | 202608 | 272 |
| B | Pesca | Variación porcentual interanual | 200501 | 202608 | 260 |
| B | Pesca | Índice base 2004=100 | 200401 | 202608 | 272 |
| C | Explotación de minas y canteras | Variación porcentual interanual | 200501 | 202608 | 260 |
| C | Explotación de minas y canteras | Índice base 2004=100 | 200401 | 202608 | 272 |
| D | Industria manufacturera | Variación porcentual interanual | 200501 | 202608 | 260 |
| D | Industria manufacturera | Índice base 2004=100 | 200401 | 202608 | 272 |
| E | Electricidad, gas y agua | Variación porcentual interanual | 200501 | 202608 | 260 |
| E | Electricidad, gas y agua | Índice base 2004=100 | 200401 | 202608 | 272 |
| F | Construcción | Variación porcentual interanual | 200501 | 202608 | 260 |
| F | Construcción | Índice base 2004=100 | 200401 | 202608 | 272 |
| G | Comercio mayorista, minorista y reparaciones | Variación porcentual interanual | 200501 | 202608 | 260 |
| G | Comercio mayorista, minorista y reparaciones | Índice base 2004=100 | 200401 | 202608 | 272 |
| H | Hoteles y restaurantes | Variación porcentual interanual | 200501 | 202608 | 260 |
| H | Hoteles y restaurantes | Índice base 2004=100 | 200401 | 202608 | 272 |
| I | Transporte y comunicaciones | Variación porcentual interanual | 200501 | 202608 | 260 |
| I | Transporte y comunicaciones | Índice base 2004=100 | 200401 | 202608 | 272 |
| J | Intermediación financiera | Variación porcentual interanual | 200501 | 202608 | 260 |
| J | Intermediación financiera | Índice base 2004=100 | 200401 | 202608 | 272 |
| K | Actividades inmobiliarias, empresariales y de alquiler | Variación porcentual interanual | 200501 | 202608 | 260 |
| K | Actividades inmobiliarias, empresariales y de alquiler | Índice base 2004=100 | 200401 | 202608 | 272 |
| L | Administración pública y defensa; planes de seguridad social de afiliación obligatoria | Variación porcentual interanual | 200501 | 202608 | 260 |
| L | Administración pública y defensa; planes de seguridad social de afiliación obligatoria | Índice base 2004=100 | 200401 | 202608 | 272 |
| M | Enseñanza | Variación porcentual interanual | 200501 | 202608 | 260 |
| M | Enseñanza | Índice base 2004=100 | 200401 | 202608 | 272 |
| N | Servicios sociales y de salud | Variación porcentual interanual | 200501 | 202608 | 260 |
| N | Servicios sociales y de salud | Índice base 2004=100 | 200401 | 202608 | 272 |
| O | Otras actividades de servicios comunitarios, sociales y personales | Variación porcentual interanual | 200501 | 202608 | 260 |
| O | Otras actividades de servicios comunitarios, sociales y personales | Índice base 2004=100 | 200401 | 202608 | 272 |
| T_S | Impuestos netos de subsidios | Variación porcentual interanual | 200501 | 202608 | 260 |
| T_S | Impuestos netos de subsidios | Índice base 2004=100 | 200401 | 202608 | 272 |

### `pobreza_eph`

Incidencia de la pobreza y la indigencia (EPH). Área: Dirección Nacional de Estadísticas de Condiciones de Vida.

- **Filas:** 20 · **Rango (periodo):** 20162S → 20261S
- **Clave de orden (para paginar):** `area_geografica_nom,periodo`
- **Base del perfil de categorías:** tabla completa

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `area_geografica_nom` | string | Denominación del área geográfica a la que corresponde el dato. |
| `area_geografica_cod` | numérico (sin tipo en el spec) | Código que identifica el área geográfica a la que corresponde el dato. Ver diseño de registros y estructura para las bases preliminares (hogares y personas) de EPH en https://www.indec.gob.ar/indec/web/Institucional-Indec-BasesDeDatos . |
| `periodo` | string | Período de referencia del dato, expresado en formato AAAANS (número de semestre)   |
| `anio` | number | Año correspondiente al período de referencia del dato. |
| `semestre` | number | Número del semestre correspondiente al año de referencia. Utiliza los valores 1 (primer semestre) y 2 (segundo semestre). |
| `tasa_pobreza_hogares` | numérico (sin tipo en el spec) | Porcentaje de hogares cuyos ingresos se encuentran por debajo de su respectiva línea de pobreza en relación con el total de hogares. |
| `tasa_pobreza_personas` | numérico (sin tipo en el spec) | Porcentaje de personas que habitan en hogares cuyos ingresos se encuentran por debajo de su respectiva línea de pobreza en relación con el total de personas. |
| `tasa_indigencia_hogares` | numérico (sin tipo en el spec) | Porcentaje de hogares cuyos ingresos se encuentran por debajo de su respectiva línea de indigencia en relación con el total de hogares. |
| `tasa_indigencia_personas` | numérico (sin tipo en el spec) | Porcentaje de personas que habitan en hogares cuyos ingresos se encuentran por debajo de su respectiva línea de indigencia en relación con el total de personas. |
| `observaciones` | numérico (sin tipo en el spec) | Notas vinculadas a los valores informados. |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `area_geografica_nom` — 1 valores: `T_31_A` (20)
- `area_geografica_cod` — 1 valores: `None` (20)
- `observaciones`: 3 textos distintos además de vacío (ej.: "Los resultados del segundo semestre de 2019 no incluyen el aglomerado Gran Resistencia.")

**Series (1):**

| area_geografica_nom | area_geografica_cod | desde | hasta | filas |
|---|---|---|---|---|
| T_31_A | None | 20162S | 20261S | 20 |

### `mercado_trabajo_eph`

Principales tasas del mercado de trabajo (EPH). Área: Dirección Nacional de Estadísticas de Condiciones de Vida.

- **Filas:** 41 · **Rango (periodo):** 20162T → 20262T
- **Clave de orden (para paginar):** `area_geografica_nom,periodo`
- **Base del perfil de categorías:** tabla completa

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `area_geografica_nom` | string | Denominación del área geográfica a la que corresponde el dato. |
| `area_geografica_cod` | numérico (sin tipo en el spec) | Código que identifica el área geográfica a la que corresponde el dato. Ver diseño de registros y estructura para las bases preliminares (hogares y personas) de EPH en https://www.indec.gob.ar/indec/web/Institucional-Indec-BasesDeDatos . |
| `periodo` | string | Período de referencia del dato, expresado en formato AAAANT (número de trimestre que utiliza valores comprendidos entre 1 Y 4). |
| `anio` | number | Año correspondiente al período de referencia del dato. |
| `trimestre` | number | Número del trimestre correspondiente al año de referencia. Utiliza valores comprendidos entre 1 (primer trimestre) y 4 (cuarto trimestre). |
| `tasa_de_actividad` | numérico (sin tipo en el spec) | Porcentaje de la población económicamente activa con respecto a la población total de referencia. |
| `tasa_de_empleo` | numérico (sin tipo en el spec) | Porcentaje de la población ocupada con respecto a la población total de referencia. |
| `tasa_de_empleo_formal` | numérico (sin tipo en el spec) | Porcentaje de la población ocupada con empleo formal con respecto a la población total de referencia. |
| `tasa_de_empleo_informal` | numérico (sin tipo en el spec) | Porcentaje de la población ocupada con empleo informal con respecto a la población total de referencia. |
| `tasa_de_desocupacion` | numérico (sin tipo en el spec) | Porcentaje de la población desocupada con respecto a la población económicamente activa. |
| `tasa_de_ocupacion_demandante` | numérico (sin tipo en el spec) | Porcentaje de la población ocupada que busca activamente otra ocupación con respecto a la población económicamente activa. |
| `tasa_de_subocupacion` | numérico (sin tipo en el spec) | Porcentaje de la población subocupada con respecto a la población económicamente activa. |
| `tasa_de_subocupacion_demandante` | numérico (sin tipo en el spec) | Porcentaje de la población subocupada que busca activamente otra ocupación con respecto a la población económicamente activa. |
| `tasa_de_subocupacion_no_demandante` | numérico (sin tipo en el spec) | Porcentaje de la población subocupada que busca activamente otra ocupación con respecto a la población económicamente activa. |
| `observaciones` | numérico (sin tipo en el spec) | Notas vinculadas a los valores informados.  |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `area_geografica_nom` — 1 valores: `T_31_A` (41)
- `area_geografica_cod` — 1 valores: `None` (41)
- `observaciones`: 4 textos distintos además de vacío (ej.: "Los resultados del tercer trimestre de 2019 no incluyen el aglomerado Gran Resistencia.")

**Series (1):**

| area_geografica_nom | area_geografica_cod | desde | hasta | filas |
|---|---|---|---|---|
| T_31_A | None | 20162T | 20262T | 41 |

### `canasta-crianza`

Valorización de la canasta de crianza. Área: Dirección Nacional de Estadísticas de Condiciones de Vida.

- **Filas:** 81 · **Rango (Periodo):** 202001 → 202609
- **Clave de orden (para paginar):** `Periodo`
- **Base del perfil de categorías:** tabla completa

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `anio` | number | Año correspondiente al período de referencia del dato |
| `Mes` | number | Número del mes correspondiente al período de referencia. Utiliza valores comprendidos entre 1 (enero) y 12 (diciembre) |
| `Periodo` | string | Período de referencia del dato, expresado en formato AAAAMM (meses) |
| `bys_men1` | numérico (sin tipo en el spec) | Costo mensual de los bienes y servicios incluidos en la canasta de crianza para menores de 1 año, expresado en pesos argentinos |
| `cuid_men1` | numérico (sin tipo en el spec) | Valorización mensual del tiempo de cuidado requerido para menores de 1 año, expresado en pesos argentinos |
| `tot_men1` | numérico (sin tipo en el spec) | Valor mensual total de la canasta de crianza para menores de 1 año, expresado en pesos argentinos |
| `bys_1a3` | numérico (sin tipo en el spec) | Costo mensual de los bienes y servicios incluidos en la canasta de crianza para niñas y niños de 1 a 3 años, expresado en pesos argentinos |
| `cuid_1a3` | numérico (sin tipo en el spec) | Valorización mensual del tiempo de cuidado requerido para niñas y niños de 1 a 3 años, expresado en pesos argentinos |
| `tot_1a3` | numérico (sin tipo en el spec) | Valor mensual total de la canasta de crianza para niñas y niños de 1 a 3 años, expresado en pesos argentinos |
| `bys_4a5` | numérico (sin tipo en el spec) | Costo mensual de los bienes y servicios incluidos en la canasta de crianza para niñas y niños de 4 a 5 años, expresado en pesos argentinos |
| `cuid_4a5` | numérico (sin tipo en el spec) | Valorización mensual del tiempo de cuidado requerido para niñas y niños de 4 a 5 años, expresado en pesos argentinos |
| `tot_4a5` | numérico (sin tipo en el spec) | Valor mensual total de la canasta de crianza para niñas y niños de 4 a 5 años, expresado en pesos argentinos |
| `bys_6a12` | numérico (sin tipo en el spec) | Costo mensual de los bienes y servicios incluidos en la canasta de crianza para niñas, niños y adolescentes de 6 a 12 años, expresado en pesos argentinos |
| `cuid_6a12` | numérico (sin tipo en el spec) | Valorización mensual del tiempo de cuidado requerido para niñas, niños y adolescentes de 6 a 12 años, expresado en pesos argentinos |
| `tot_6a12` | numérico (sin tipo en el spec) | Valor mensual total de la canasta de crianza para niñas, niños y adolescentes de 6 a 12 años, expresado en pesos argentinos |

### `comercio_exterior_nomenclaturas`

Códigos y denominaciones de comercio exterior. Área: Dirección Nacional de Estadísticas del Sector Externo y Cuentas Internacionales.

- **Filas:** 325
- **Clave de orden (para paginar):** `nombre_columna,codigo`
- **Base del perfil de categorías:** tabla completa

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `nombre_columna` | string | Nombre de la columna de los servicios de datos de comercio exterior en la que se utiliza el código |
| `codigo` | string | Código utilizado en la columna indicada de los servicios de datos de comercio exterior |
| `codigo_descripcion` | string | Denominación correspondiente al código informado |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `nombre_columna` — 5 valores: `pais_cod` (240), `subrubro_cod` (50), `gce_cod` (20), `uso_economico_cod` (8), `rubro_cod` (7)
- `codigo` — 315 valores: `111` (2), `210` (2), `310` (2), `XXX` (2), `1` (2), `2` (2), `3` (2), `4` (2), `9` (2), `X` (2), `000` (1), `112` (1), `121` (1), `122` (1), `220` (1), `320` (1), `410` (1), `420` (1), `510` (1), `521` (1), `522` (1), `530` (1), `610` (1), `620` (1), `630` (1), `700` (1), `AD` (1), `AE` (1), `AF` (1), `AG` (1), `AL` (1), `AM` (1), `AN` (1), `AO` (1), `AR` (1), `AT` (1), `AU` (1), `AW` (1), `AZ` (1), `BA` (1) … y 275 más (lista completa en el perfil JSON)
- `codigo_descripcion` — 323 valores: `DESCONOCIDO` (3), `Muestras` (1), `Alimentos y bebidas básicos fundamentalmente para la industria` (1), `Alimentos y bebidas básicos fundalmentalmente para el hogar` (1), `Alimentos y bebidas elaborados fundalmentalmente para la industria` (1), `Alimentos y bebidas elaborados fundalmentalmente para el hogar` (1), `Suministros industiales básicos no especificados en otras partidas` (1), `Suministros industiales elaborados no especificados en otras partidas` (1), `Combustibles y lubricantes básicos` (1), `Combustibles y lubricantes elaborados` (1), `Bienes de capital excluido equipos de transporte` (1), `Piezas y accesorios para bienes de capital` (1), `Vehiculos automotores de pasajeros` (1), `Equipos de transporte industriales` (1), `Equipos de transporte no industriales` (1), `Piezas y accesorios para equipos de transporte` (1), `Artículos de consumo duraderos no especificados en otra partida ` (1), `Artículos de consumo semiduraderos no especificados en otra partida ` (1), `Artículos de consumo no duraderos no especificados en otra partida` (1), `Bienes no especificados en otras partidas` (1), `Desconocido` (1), `Andorra` (1), `Emiratos Árabes Unidos` (1), `Afganistán` (1), `Antigua Y Barbuda` (1), `Albania` (1), `Armenia` (1), `Antillas Holandesas (territorio vinculado a Países Bajos)` (1), `Angola` (1), `Argentina` (1), `Austria` (1), `Australia` (1), `Aruba` (1), `Azerbaiyán` (1), `Bosnia y Herzegovina` (1), `Barbados` (1), `Bangladesh` (1), `Bélgica` (1), `Burkina Faso` (1), `Bulgaria` (1) … y 283 más (lista completa en el perfil JSON)

**Códigos por columna:**

- `gce_cod` (20): `000` = Muestras; `111` = Alimentos y bebidas básicos fundamentalmente para la industria; `112` = Alimentos y bebidas básicos fundalmentalmente para el hogar; `121` = Alimentos y bebidas elaborados fundalmentalmente para la industria; `122` = Alimentos y bebidas elaborados fundalmentalmente para el hogar; `210` = Suministros industiales básicos no especificados en otras partidas; `220` = Suministros industiales elaborados no especificados en otras partidas; `310` = Combustibles y lubricantes básicos; `320` = Combustibles y lubricantes elaborados; `410` = Bienes de capital excluido equipos de transporte; `420` = Piezas y accesorios para bienes de capital; `510` = Vehiculos automotores de pasajeros; `521` = Equipos de transporte industriales; `522` = Equipos de transporte no industriales; `530` = Piezas y accesorios para equipos de transporte; `610` = Artículos de consumo duraderos no especificados en otra partida ; `620` = Artículos de consumo semiduraderos no especificados en otra partida ; `630` = Artículos de consumo no duraderos no especificados en otra partida; `700` = Bienes no especificados en otras partidas; `XXX` = Desconocido
- `pais_cod` (240 códigos; lista completa en el perfil JSON)
- `rubro_cod` (7): `1` = PRODUCTOS PRIMARIOS; `2` = MANUFACTURAS DE ORIGEN AGROPECUARIO (MOA); `3` = MANUFACTURAS DE ORIGEN INDUSTRIAL (MOI); `4` = COMBUSTIBLE Y ENERGIA; `9` = CONFIDENCIAL; `X` = DESCONOCIDO; `Z` = NO SE PUEDE ASIGNAR
- `subrubro_cod` (50): `101` = Animales Vivos; `102` = Pescados y mariscos sin elaborar; `103` = Miel; `104` = Hortalizas y legumbres sin elaborar; `105` = Frutas frescas; `106` = Cereales; `107` = Semillas y frutos oleaginosos; `108` = Tabaco sin elaborar; `109` = Lanas sucias; `110` = Fibras de algodón; `111` = Minerales metalíferos, escorias y cenizas; `199` = Resto de productos primarios; `201` = Carnes y sus preparados; `202` = Pescados y mariscos elaborados; `203` = Productos lácteos; `204` = Otros productos de origen animal; `205` = Frutas secas o procesadas; `206` = Café, té, yerba mate y especias; `207` = Productos de molinería y sus preparaciones; `208` = Grasas y aceites; `209` = Azúcar ,cacao y artículos de confitería; `210` = Preparados de hortalizas, legumbres y frutas; `211` = Bebidas, líquidos alcohólicos y vinagre; `212` = Residuos y desperdicios de la industria alimentaria; `213` = Extractos curtientes y tintóreos; `214` = Pieles y cueros; `215` = Lanas elaboradas; `299` = Resto de MOA; `302` = Productos químicos y conexos; `303` = Materias plásticas y sus manufacturas; `304` = Caucho y sus manufacturas; `305` = Manufacturas de cuero, marroquinería, etc.; `306` = Papel, cartón, impresos y publicaciones; `307` = Textiles y confecciones; `308` = Calzado y sus partes componentes; `309` = Manufacturas de piedra, yeso, vidrio, etc.; `310` = Piedras, metales preciosos y sus manufacturas, monedas; `311` = Metales comunes y sus manufacturas; `312` = Máquinas y aparatos, material eléctrico; `313` = Material de transporte terrestre; `314` = Vehículos de navegación aérea, marítima y fluvial; `399` = Resto de MOI; `401` = Petróleo crudo; `402` = Carburantes; `403` = Grasas y aceites lubricantes; `404` = Gas de petróleo y otros hidrocarburos gaseosos; `405` = Energía eléctrica; `499` = Resto de combustibles ; `999` = Confidencial; `XXX` = DESCONOCIDO
- `uso_economico_cod` (8): `1` = Bienes de Capital; `2` = Bienes Intermedios; `3` = Combustibles y Lubricantes; `4` = Piezas y Accesorios para Bienes de Capital; `5` = Bienes de Consumo; `6` = Vehiculos Automotores de Pasajeros; `9` = Resto; `X` = DESCONOCIDO

### `comercio_exterior_exportacion_bienes`

Exportaciones de bienes por rubros y países de destino. Área: Dirección Nacional de Estadísticas del Sector Externo y Cuentas Internacionales.

- **Filas:** 779.536 · **Rango (Periodo):** 198601 → 202609
- **Clave de orden (para paginar):** `Anio,Mes,Periodo,rubro_cod,subrubro_cod,pais_cod`
- **Base del perfil de categorías:** solo filas de los períodos 198601 y 202609 (tabla de 779536 filas)

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `Anio` | number | Año correspondiente al período de referencia del dato |
| `Mes` | number | Número del mes correspondiente al período de referencia. Utiliza valores comprendidos entre 1 (enero) y 12 (diciembre) |
| `Periodo` | string | Período de referencia del dato, expresado en formato AAAAMM (meses) |
| `rubro_cod` | string | Código que identifica el rubro al que pertenece la exportación |
| `subrubro_cod` | string | Código de tres posiciones que identifica el subrubro de exportación dentro del rubro correspondiente |
| `pais_cod` | string | Código que identifica el país de origen de las importaciones o de destino de las exportaciones |
| `valor_FOB` | numérico (sin tipo en el spec) | Valor de las exportaciones a precios FOB, expresado en dólares estadounidenses |
| `Peso_Neto` | numérico (sin tipo en el spec) | Peso neto de los bienes que componen el rubro o subrubro informado, expresado en kilogramos |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `rubro_cod` — 5 valores: `2` (1032), `3` (997), `1` (559), `4` (75), `9` (1)
- `subrubro_cod` — 50 valores: `302` (139), `312` (139), `399` (134), `201` (125), `311` (107), `211` (105), `106` (101), `107` (97), `104` (87), `299` (84), `208` (81), `102` (80), `210` (77), `212` (76), `303` (75), `304` (68), `306` (68), `214` (66), `307` (65), `203` (64), `213` (60), `313` (60), `309` (55), `207` (51), `206` (49), `105` (47), `199` (47), `204` (42), `305` (41), `209` (39), `215` (38), `205` (37), `202` (34), `101` (31), `499` (26), `108` (25), `103` (21), `402` (19), `308` (18), `310` (16) … y 10 más (lista completa en el perfil JSON)
- `pais_cod` — 176 valores: `US` (79), `UY` (78), `BR` (72), `CL` (72), `ES` (64), `PE` (61), `PY` (60), `IT` (59), `CO` (58), `BO` (57), `NL` (56), `CA` (53), `FR` (49), `JP` (46), `MX` (46), `EC` (42), `BE` (40), `VE` (40), `CR` (40), `PA` (38), `XR` (37), `AU` (36), `CN` (36), `DO` (36), `DE` (33), `PR` (32), `IL` (32), `MY` (29), `TW` (28), `SG` (28), `CH` (27), `GT` (27), `IN` (26), `SV` (26), `KR` (25), `GB` (25), `ZA` (25), `HN` (24), `NZ` (24), `TH` (24) … y 136 más (lista completa en el perfil JSON)

**Razón de nulo observada:** `valor_FOB_null`: `s` (992); `Peso_Neto_null`: `s` (992)

### `comercio_exterior_importacion_bienes`

Importaciones de bienes por uso económico y país de origen. Área: Dirección Nacional de Estadísticas del Sector Externo y Cuentas Internacionales.

- **Filas:** 390.315 · **Rango (Periodo):** 198601 → 202609
- **Clave de orden (para paginar):** `Anio,Mes,Periodo,uso_economico_cod,gce_cod,pais_cod`
- **Base del perfil de categorías:** solo filas de los períodos 198601 y 202609 (tabla de 390315 filas)

| Columna | Tipo | Descripción (del spec) |
|---|---|---|
| `Anio` | number | Año correspondiente al período de referencia del dato |
| `Mes` | number | Número del mes correspondiente al período de referencia. Utiliza valores comprendidos entre 1 (enero) y 12 (diciembre) |
| `Periodo` | string | Período de referencia del dato, expresado en formato AAAAMM (meses) |
| `uso_economico_cod` | string | Código que identifica el uso económico de las importaciones |
| `gce_cod` | string | Código que identifica la gran categoría económica dentro del uso económico de importación correspondiente |
| `pais_cod` | string | Código que identifica el país de origen de las importaciones o de destino de las exportaciones |
| `valor_CIF` | numérico (sin tipo en el spec) | Valor de las importaciones a precios CIF, expresado en dólares estadounidenses |
| `peso_neto` | numérico (sin tipo en el spec) | Peso neto de los bienes que componen el uso económico o categoría económica informada, expresado en kilogramos |

**Valores distintos de las columnas categóricas** (entre paréntesis, filas con ese valor):

- `uso_economico_cod` — 7 valores: `5` (458), `2` (336), `4` (231), `1` (161), `9` (80), `3` (54), `6` (22)
- `gce_cod` — 20 valores: `220` (158), `420` (131), `410` (127), `620` (119), `630` (115), `530` (100), `210` (88), `610` (80), `700` (79), `122` (67), `112` (49), `121` (48), `111` (42), `320` (39), `521` (34), `522` (28), `510` (22), `310` (8), `322` (7), `999` (1)
- `pais_cod` — 138 valores: `US` (35), `BR` (30), `JP` (29), `ES` (28), `CL` (27), `FR` (27), `NL` (27), `IT` (26), `BE` (25), `CA` (25), `UY` (25), `CH` (24), `TW` (24), `MX` (23), `AT` (22), `KR` (22), `CN` (21), `CO` (21), `XR` (21), `DK` (20), `PE` (20), `EC` (19), `SE` (19), `PY` (19), `GB` (19), `AU` (18), `IN` (18), `SG` (18), `DE` (17), `ID` (16), `HU` (16), `NZ` (15), `PT` (15), `IL` (15), `MY` (15), `TH` (15), `FI` (14), `PL` (14), `AR` (14), `TR` (14) … y 98 más (lista completa en el perfil JSON)

## Observaciones para A3 (hechos del catálogo, sin mapear todavía)

- **EMAE nivel general** trae índice y variación de las tres series (original, desestacionalizada y tendencia-ciclo), 2004-01 → 2026-08.
- **EMAE por sectores** trae sólo serie original (índice base 2004 y variación interanual), sin desestacionalizar: 15 letras ClaNAE + `T_S` (impuestos netos de subsidios).
- **IPC:** las variaciones (`v_m`, `v_ia`, `v_acum`) vienen **redondeadas a 1 decimal**, igual que el informe técnico; el índice viene con 4 decimales. Recalcular la variación desde el índice puede diferir en ±0,1 pp (lo advierte la propia API).
- **EPH** (`mercado_trabajo_eph`, `pobreza_eph`): un único área geográfica, `T_31_A` (total 31 aglomerados urbanos), con `area_geografica_cod` vacío. Tasa de empleo formal/informal disponible desde el 4T-2023 (según la propia `observaciones`). Último dato marcado "Dato provisorio".
- **Índice de salarios:** el índice (nivel) existe para nivel general, registrado, no registrado, privado registrado y público; los subsectores público nacional/provincial sólo traen variaciones.
- **Canastas CBA/CBT:** sólo región GBA (por adulto equivalente y por 3 tipos de hogar).
- **Comercio exterior:** exportaciones por rubro/subrubro/país (FOB) e importaciones por uso económico/GCE/país (CIF), en dólares y kg, desde 1986. No hay una columna de total. **Ojo:** en exportaciones de 202609 hay 992 filas con el valor oculto por secreto estadístico (`valor_FOB_null = s`; en 198601, ninguna), así que sumar filas **no** reproduce el total publicado.
- **Códigos sin nomenclatura:** en los datos aparecen códigos que no están en `comercio_exterior_nomenclaturas`: importaciones `gce_cod` `322` y `999`; exportaciones `subrubro_cod` `216` (revisado sólo en el primer y el último período).
- **No están en la API** (quedan en datos.gob.ar o en su fuente actual): cuentas nacionales trimestrales (PBI), balanza de pagos, tipo de cambio real, ISAC, IPI construcción, encuestas de supermercados/autoservicios, turismo, RIPTE y todo lo que no es del INDEC (BCRA, Secretaría de Hacienda, SIPA).

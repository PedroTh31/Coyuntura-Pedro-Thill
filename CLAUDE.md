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
- `dashboard.py` — genera `docs/index.html` (pestaña macro) Y `docs/financiera.html`
  (pestaña financiera): es el MISMO módulo, `generar(historico, config_indicadores,
  archivo_salida=, extra_html=, extra_charts=, nav_extra=, titulo_pagina=)` es genérico -- se
  lo llama dos veces desde `run.py`, una por página, cada vez con la lista de indicadores que
  corresponde (`indicadores` o `indicadores_financiera` de `indicadores.yaml`). Un `bloque`
  (ver `ORDEN_BLOQUES`) sin tarjetas para la lista que se le pasó en esa llamada simplemente no
  imprime sección -- por eso agregar el bloque `mercados` (financiera) a las mismas listas
  module-level (`ORDEN_BLOQUES`/`TITULO_BLOQUE`/`ACENTO`/`ORDEN_GRUPOS`) que usa `index.html`
  no contamina la página macro. **Reclasificar un indicador de una página a la otra significa
  MOVER su entrada de lista en indicadores.yaml (de `indicadores` a `indicadores_financiera` o
  viceversa), no sólo cambiarle el campo `bloque` en el lugar** -- bug real encontrado en Ronda
  2: retaguear sin mover dejaba la tarjeta apareciendo en las DOS páginas a la vez (la de
  origen seguía viéndolo porque el bloque nuevo también estaba en `ORDEN_BLOQUES`), mientras
  que la de destino nunca lo veía (su `generar()` sólo itera la lista que se le pasó). Los
  gráficos son **interactivos (Chart.js)**, NO imágenes. Cada indicador es una celda: tarjeta
  arriba + gráfico debajo. `extra_html={bloque: html}` inyecta HTML crudo que no sale del
  pipeline fecha/valor estándar (tablas snapshot, ej. acciones/CEDEARs más operados, ver
  `tabla_acciones()`). `extra_charts=[{card:{...}, serie_js:{...}, nota:"..."}, ...]` inyecta
  tarjetas+gráficos armados FUERA del loop yaml-driven (run.py los arma con datos fetched
  aparte, ej. "muro de vencimientos" con `kind: "muro"` -- barras AGRUPADAS, no apiladas, ver
  `muroOpts` en el JS embebido -- o el gráfico de dólar futuro con `kind: "bar"` reusado tal
  cual); `generar()` les asigna el índice `i` y registra la `nota` con el mismo sistema de
  asterisco numerado que cualquier indicador normal. `nav_extra` es el link cruzado entre
  páginas ("Financiera →" / "← Macro").
- `enviar_mail.py` — resumen diario (lun-vie, indicadores + noticias arg/intl) por Gmail SMTP.
  El filtro de noticias decide en `evaluar_ar`/`evaluar_intl` (devuelven entra + regla que
  decidió); cada envío real deja `data/noticias_log.jsonl` (una línea por nota evaluada, últimos
  14 días). **Antes de tocar keywords:** convertir el ejemplo real que lo justifica en un test de
  `tests/test_noticias.py` (`python -m unittest discover tests`), y que pasen todos los demás.
- `indicadores.yaml` — **el único archivo que se edita normalmente**. Define cada serie, en
  dos listas top-level: `indicadores` (macro, `docs/index.html`) e `indicadores_financiera`
  (`docs/financiera.html`).
- `.github/workflows/` — `coyuntura.yml` corre el pipeline a diario (06:30 AR) y
  `email_diario.yml` manda el mail de lunes a viernes (07:00 AR). **El disparo principal de
  los dos es externo** (cron-job.org → API `workflow_dispatch`, configurado por Pedro el
  05/11/2026; paso a paso en `docs_internos/DISPARO_EXTERNO.md`; el PAT nunca va al repo): el
  `schedule` de GitHub arrancaba con 4-9,5 h de demora (medido oct-nov 2026) y quedó sólo como
  respaldo (09:53 y 11:47 UTC = 06:53 y 08:47 AR). **Vencimientos:** PAT de GitHub
  05/11/2027; token de la API del INDEC 04/05/2027 (campo `exp` del token, 180 días; lo lee
  `fuentes_indec.py` para avisar 30 días antes). Secrets de Actions que necesita la API del
  INDEC: `INDEC_API_TOKEN` (secret) e `INDEC_TOKEN_FECHA` (variable, informativa).
  Datos y envío están separados: `run.py` escribe al final `data/ultima_corrida.json` (fecha/hora AR + estado por fuente); el mail NO corre `run.py`
  salvo como fallback si ese archivo no es de hoy (con warning en el log y una línea "Datos
  actualizados al momento del envío" en el mail). Guardia anti-duplicado:
  `data/mail_enviado.json` (si es de hoy, no se reenvía) + `concurrency: mail-diario`.
  `python enviar_mail.py --estado` muestra el estado sin mandar; `--dry-run` arma el HTML en
  `_mail_preview.html` sin enviar ni registrar.
- `docs/` — salida publicada por GitHub Pages (`index.html` + `financiera.html`). `data/` —
  CSVs históricos versionados, compartidos por las dos páginas (un solo `historico`, cada
  indicador tageado con su propio `bloque`).

- `fuentes_mercados.py` — bloque MAE (08/11/2026): cauciones del histórico de cierre del MAE (`mae_caucion`),
  UST del Tesoro con respaldo H.15 (`tesoro_ust`), último dato válido de los extras de run.py (muro, dólar
  futuro) en `data/extras_ultimo.json` y alertas a Pedro (máx. 1 mail por corrida; primer día y semanal; estado
  en `data/mercados_estado.json`; resumen en la clave `mercados` de `ultima_corrida.json`). **Extras vacíos**
  (`run._extras_con_respaldo`): la card se arma con el último dato válido, el sello marca su antigüedad
  (frecuencia diaria), aviso "La fuente no devolvió datos en esta corrida" y alerta; un extra nuevo de run.py
  -> pasarlo por ahí. Tests: `tests/test_fuentes_mercados.py`. Bloque TIR (08/11/2026, #28): TIR/MD de bonos
  (`byma_bono`, `serie_bono`, cierres de BYMA + flujo del MAE, sólo días posteriores al último pago) y spread
  contra el Treasury interpolado a la duración (`spread_duracion`); tests en `tests/test_tir_bonos.py`; verificación
  manual de la convención contra el MAE en `tests/manual_verificar_tir_mae.py` (con red, fuera de la suite).

- `fuentes_indec.py` — API del INDEC (api.indec.gob.ar/v1, beta, PostgREST, token JWT en
  `INDEC_API_TOKEN`, local en `.env` gitignoreado; **el token nunca se imprime ni va a
  logs/HTML/JSON/commits**). `ResolverIndec` intenta la API y, ante error o resultado vacío,
  cae al fallback (datos.gob.ar o ArgentinaDatos) con un `::warning` en el log; tras un
  401/403 el resto de la corrida va directo al fallback. Fetcher de bajo nivel:
  `fetch_indec_tabla`/`fetch_indec_api` en fetchers.py (paginación de a 1000 filas ordenando
  por la clave completa de la tabla, valida filas == `Content-Range`, reintenta 429/5xx).
  `cerrar_corrida()` actualiza `data/indec_estado.json` (rachas de fallback, última fuente por
  indicador, últimas 30 corridas) y manda alertas SOLO a pedrothill31@gmail.com (máx. 1 mail
  por corrida, desde coyuntura.yml): falla de autenticación (1/día), token a ≤30 días de
  vencer (semanal), fallback > 3 corridas seguidas (semanal por serie), una serie de fallback
  de datos.gob con 0 filas (semanal). El dashboard agrega a la nota "Fuente: INDEC (API…)" o
  "Fuente: INDEC vía …" según la fuente realmente usada, y un pie visible "Fuente: INDEC" bajo
  cada gráfico con datos del INDEC (atribución). Cada tabla de la nota enlaza a su ficha
  `api.indec.gob.ar/datasets/<tabla>` (verificada; un slug inexistente da "Dataset no
  encontrado" con HTTP 200), y el encabezado "fuentes: …" de cada página sale de
  `dashboard.fuentes_de_pagina()` (fuentes efectivamente usadas, no lista fija; un `fuente:` o
  `calculo:` nuevo con otra fuente → sumarlo a `ETIQUETA_FUENTE`/`FUENTES_CALCULO`). Catálogo de la API y equivalencias
  verificadas: `fuentes/indec_catalogo.md`, `fuentes/indec_equivalencias.md`. Tests sin red:
  `tests/test_indec_api.py`, `tests/test_fuentes_indec.py`.

- **Calendario de publicaciones** (Bloque B de `PROMPT_ronda_macro_indec.md`):
  - `calendario.yaml` guarda SÓLO lo estable: qué publicación del INDEC alimenta qué indicadores
    (`titulo_regex` con grupo `periodo`, `frecuencia`, `meses_siguientes_alerta`) y los feriados.
    Las FECHAS no van ahí: se bajan en cada corrida. Un indicador va asociado a una publicación
    sólo si esa publicación es la que agrega su período nuevo (el componente de mayor rezago,
    verificado con datos); si no, "sin calendario oficial", nunca una fecha estimada (decisión de
    Pedro). Así quedan préstamos real, adelantos/transferencias en pesos constantes (BCRA + IPC: la
    regla no se cumple) y capacidad de compra (RIPTE).
  - Fuente: calendario oficial https://www.indec.gob.ar/indec/web/Calendario-Fecha-0, que arma
    cada mes con `/Calendario/FiltrosCalendario/mes/{Mes}-{AAAA}/0` (`Mes` con mayúscula inicial,
    ej. "Noviembre-2026"): endpoint NO documentado que devuelve HTML. `calendario_indec.py` lo
    parsea y falla ruidosamente (`CalendarioFormatoError`) ante cualquier formato desconocido o 0
    publicaciones en el mes actual y los 2 siguientes; nunca devuelve silencio. El servidor
    rechaza navegadores headless (HTTP 500) pero acepta `requests` (también desde GitHub Actions,
    probado el 07/11/2026).
  - Caché: `data/calendario_indec.json`, por mes. Si un mes falla, se usa su último caché válido,
    marcado como tal (`fuente: cache`); una descarga fallida nunca pisa un caché válido.
  - `verificar_calendario.py` corre en `coyuntura.yml` después de `run.py` (`continue-on-error`,
    nunca corta el pipeline) y avisa SOLO a Pedro, máx. 1 mail por corrida, con el mismo
    mecanismo que las alertas del INDEC (estado en `data/calendario_estado.json`). Diario: falla de
    descarga/formato, título que matchea dos patrones, error al bajar feriados. Semanal:
    publicación sin fecha en su ventana (mes actual + `meses_siguientes_alerta`: 1 mensuales, 3
    trimestrales; posible cambio de título), feriados del yaml distintos de los oficiales, feriado
    "especial" oficial sin evaluar, año oficial ya publicado que el yaml tiene como provisorio,
    falta el año siguiente en diciembre.
  - Feriados (criterio de Pedro): un día es no hábil si en él NO operan el INDEC, el BCRA y BYMA.
    Cuentan los nacionales (inamovibles, trasladables, turísticos) y los "especiales" que la norma
    extiende a esos organismos (ej. 10/11/2026, Decreto 1103/2026 + Com. "A" 8487 del BCRA +
    calendario de BYMA); NO cuentan los días no laborables religiosos ni los feriados de otras
    jurisdicciones (los evaluados y descartados van en `especiales_descartados`, con el motivo).
    Fuente oficial verificable sin navegador: el JSON que carga argentina.gob.ar/feriados,
    `https://www.argentina.gob.ar/sites/default/files/holidays-{AAAA}-es.json` (404 mientras el año
    no está publicado; un año sin publicar va como `verificado: false`, desde ArgentinaDatos).
  - Tests sin red: `tests/test_calendario_indec.py`, `tests/test_verificar_calendario.py`.

- `frescura.py` — línea de frescura bajo el valor de cada card (Bloque B2, sólo `index.html`;
  `run.py` le pasa `frescura_ctx` a `dashboard.generar`): período del último dato, estado y próximo
  dato. Con calendario (indicador en `calendario.yaml`): "✓ al día · próximo DD/MM, 16 h", "X
  publicado el DD/MM, entra en la próxima actualización" (margen: publicación + 1 día hábil) o "⚠
  atrasado · X se publicó el DD/MM" (para eso `calendario.yaml` baja también `meses_atras` meses
  anteriores). Sin calendario: "próximo: sin calendario oficial"; diarias: "próximo DD/MM
  (estimado)" (próximo día hábil). Rezago grave (franja "⏸ … sin datos nuevos hace N meses"): días
  desde el CIERRE del período > 90 (trimestrales 90 + 92; piso `rezago_normal_dias`), N = meses
  completos desde ese cierre. **Diarias: a los 10 días hábiles sin datos** (`UMBRAL_DIARIAS_HABILES`,
  mismo piso; bloque MAE, 08/11/2026). **Frecuencia** (`frecuencia_de`): campo opcional `frecuencia:
  diaria|mensual|trimestral` del yaml > fuente (`FUENTES_DIARIAS`/`CALCULOS_DIARIOS`: mae_*, tesoro_ust,
  byma, byma_bono, dolar, spread_bono_ust, brecha) > separación de las fechas, SÓLO con 2 puntos o más (con uno se
  muestra la fecha, nunca se adivina el período; #24). Una fuente diaria nueva -> sumarla a esos sets. Cards con varias series: si alguna está frenada y otra no, la franja
  nombra la frenada. Colores: grises + `principal_2` "al día", NUNCA el `negativo` (bordó, es el de los negativos del
  Bloque C). Ojo: el chequeo de frescura de `run.py` (alertas) mide desde la fecha cruda del dato,
  no desde el cierre. Tests: `tests/test_frescura.py`.

- **Calendario y avisos en el mail diario** (Bloque B3, diseño aprobado por Pedro el 07/11/2026):
  - `agenda.py` (funciones puras) arma en `run.py`, después del dashboard macro, la clave `agenda` de
    `data/ultima_corrida.json`: `calendario` (hoy / esta semana = hoy + 4 días hábiles, o los 5
    siguientes si hoy no es hábil / próxima, feriado, primer día hábil de la semana, estado de la
    caché: `ok`, `cache_vieja` si un mes de la ventana se bajó hace más de 7 días, `no_disponible`),
    `publicaciones` (por publicación de `calendario.yaml`: período del dashboard, estado del B2 y
    bloque "Dato nuevo" según `apertura`), `atrasados` (uno por publicación) y `graves` (deduplicados
    por serie). Las líneas salen de `ctx.registro`, que llena `dashboard._linea_frescura`, con la
    misma redacción del dashboard (`frescura.texto_linea`). El mail (`mail_agenda.py`) NO recalcula
    nada; si la agenda no es de hoy, muestra "Calendario del INDEC no disponible hoy".
  - Orden del mail: Dato nuevo → Hoy se publica → Esta semana → Indicadores → Datos demorados →
    noticias. Sólo publicaciones del INDEC; sólo la pestaña macro; sin fila del REM (pendiente #10).
  - "Dato nuevo": abre el PRIMER mail en que el período del dashboard supera a
    `periodos_anunciados` de `data/mail_enviado.json` (lo commitea `email_diario.yml`; se escribe sólo
    tras un envío exitoso, nunca en `--dry-run`). Sin esa clave se inicializa sin anunciar.
    `apertura` en `calendario.yaml`: sólo series que el dashboard ya calcula.
  - Frecuencias (D1): atrasado en el mail todos los días (máx. 3 + "y N más") y aviso a Pedro semanal
    por publicación (`agenda.avisar_atrasados`, estado en `data/frescura_estado.json`); rezago grave en
    el mail el primer día hábil de la semana y el día en que una serie entra (`graves_vistos`), sin
    aviso aparte.
  - `verificar_calendario.py` corre ANTES de `run.py` en `coyuntura.yml` (`continue-on-error`).
  - Colores de las secciones nuevas: `tema.py` (paleta del Bloque C; el Bloque 2 de
    `PROMPT_mail_v3.md` debería leer de ahí). Tests: `tests/test_agenda.py`, `tests/test_mail_agenda.py`.

- **Organización del sitio** (Bloque E, diseño aprobado por Pedro el 07/11/2026; etapas E1 calendario →
  E2 home → E3 temas → E4 series → E5 identidad). **Bloque E CERRADO el 08/11/2026** (las 5 etapas en
  producción). Estructura final del sitio (GitHub Pages, `docs/`): `/` home, `/calendario/`, 8 temas
  (`/<slug>/`, orden y contenido en el bloque `temas:` de indicadores.yaml), `/serie/<slug>/` (59 páginas),
  `/acerca/`; `financiera.html` y las anclas viejas (`#precios`, …) redirigen. Lo pendiente de diseño y
  contenido que salió del bloque está en `docs_internos/PENDIENTES.md` (sección "Contenido": C1
  descripciones, C2 negativos en combos de dos barras; "Bloques futuros": F1 agenda ampliada). Etapas:
  - E1: `pagina_calendario.py` genera `docs/calendario/index.html` (run.py, `_generar_calendario`, después de
    `agenda.armar`; nunca corta el pipeline). Hoy / Esta semana (misma ventana que el mail,
    `agenda.fin_ventana`), estado de cada publicación de `calendario.yaml` (línea del B2 + próxima fecha,
    `agenda.proximas`), el mes con pestañas (anterior, actual y 2 siguientes, `agenda.armar_meses`: estados
    `incorporado`/`publicado`/`atrasado`/`proximo`), datos demorados y series sin calendario
    (`agenda.sin_calendario`). Las publicaciones del INDEC que el monitor no usa van ocultas detrás de un
    checkbox (D6). Sin agenda: "Calendario del INDEC no disponible hoy". Nada estimado.
  - `sitio.py`: armazón común de las páginas nuevas (cabecera, nav, pie, CSS base desde tema.py), `slug()` de
    las cards (D7, `slug:` opcional en el yaml), `nav_sitio()` (Inicio · Calendario · 8 temas), `pie_sitio()`
    (inicio del proyecto + link al commit 730dd39, Acerca, LinkedIn y el mail OFUSCADO: va invertido en dos
    partes y lo arma el JS al hacer click; nunca escribir la dirección completa en un HTML).
  - E2: `temas.py` + bloque `temas:` de indicadores.yaml (cada ítem = nombre de card, `tabla:`, "Semáforo
    del EMAE" o los extras de run.py; cada card en UN solo tema, sin las `solo_referencia`). run.py
    (`_generar_temas`) llama a `dashboard.generar(..., tema=, temas_nav=, raiz="../")` una vez por tema ->
    `docs/<slug>/index.html`. Card nueva
    sin tema: sale en "Sin tema asignado" del tema de su bloque + `::warning` (y falla tests/test_temas.py).
    `con_titulares` acepta el conjunto de nombres macro (titulares sólo en esas). Frescura en todas las cards
    (D4), pero la agenda del mail usa `run._ctx_solo(ctx, indicadores)`: el registro SÓLO de las macro, en el
    orden del yaml (el mail queda idéntico). `pagina_home.py`: `docs/index.html` (franja Hoy/Esta semana de
    la agenda, 9 datos clave del bloque `home:` del yaml con valor/variación de la MISMA card de su tema y
    frescura + mini Chart.js SÓLO de la serie que la resume (decisión de Pedro); EMAE con las funciones de card sin registrarse en la
    agenda; temas con 2 titulares; datos demorados; redirección de las anclas viejas `#precios`… a su tema,
    `sitio.REDIRECCION_ANCLAS`) y `docs/acerca/index.html`.
  - E3: la página de tema lleva cards COMPACTAS (`dashboard._card_compacta`: toda la card es un `<a>` a
    `../serie/<slug>/`, asterisco como texto, mini Chart.js sin ejes de `_mini_card`/`_mini_extra`: últimos 12
    meses de una diaria, 24 datos de una mensual, 8 de una trimestral; overlay con todas sus series, espejo,
    incidencia apilada 13 meses, sectores; combos con rezago/evento: "Gráfico completo en la página de la
    serie") y una bajada (`_bajada_tema`: series, al día, sin datos nuevos, próxima publicación de la caché,
    nunca estimada). Sólo los minis van embebidos (la página ya no carga las series completas). Cada card
    tiene `docs/serie/<slug>/index.html` (`_escribir_series`: la card completa de siempre + su nota como *1;
    E4 le suma próximo dato, contexto y últimos datos). Los datos clave de la home linkean a su serie.
    `financiera.html` es una redirección a `mercados/` (`pagina_home.generar_redireccion`).
  - E4: la página de serie lleva miga, kicker (tema), titular, `descripcion:` del yaml (si falta, `subtitulo`),
    valor/variación/frescura, caja "Próximo dato" (`_proximo_dato`: fecha de la caché del calendario,
    "todavía sin fecha" o "sin calendario oficial"; nunca estimada salvo la línea de las diarias del B2),
    el gráfico completo (`_card_cell(solo_grafico=True)`), "Último dato, en contexto" (las mismas filas del
    "Dato nuevo" del mail, `agenda.armar_apertura`, sin recalcular), "Últimos 13 datos" (`_tabla_ultimos`:
    la serie resumen + hasta 3 más de la card CON SU MISMA FRECUENCIA; también es la vista accesible del
    gráfico), la nota completa y "También en <tema>". El encabezado "fuentes:" de cada serie es el de esa
    serie, no el de todo el tema. `pagina_serie: <slug de tema>` en un `solo_componente` le da página de
    serie sin card en el tema (hoy: EMAE general, con `titular_regla: direccion`, sujeto "El EMAE").
    Agenda: cada publicación lleva `url` (`agenda.url_serie`: la card cuya serie resumen es esa; si no, la
    primera card que la dibuja; si no, su `pagina_serie`); el "Dato nuevo" del mail linkea ahí y cae al
    `#ancla` si no hay `url`. El link de "Datos demorados" del mail va a `calendario/#demorados`.
  - Decisiones tomadas en el bloque (ya implementadas): 9 datos clave en la home (los 8 propuestos + EMAE,
    que tiene página de serie pero no card de tema; `titular_regla: direccion`, sujeto "El EMAE", en E4);
    tasas bancarias en "Dinero y crédito", cauciones y CER en "Mercados" (D8 opción A); riesgo país en
    Mercados, PBI nominal en Actividad; URLs `/serie/<slug>/`; mapeo de temas en un bloque `temas:` de
    indicadores.yaml; financiera.html pasa a redirigir a `/mercados/`; anclas viejas (`#precios`, ...)
    redirigidas desde la home. Pie y Acerca: "Proyecto iniciado el 9 de julio de 2026"
    con link al primer commit (730dd39); contacto por mail (ofuscado, nunca completo en el HTML) y LinkedIn.
  - E5 (identidad A+B+C, elegida por Pedro): A = cabecera, títulos de página y titulares en serif del sistema
    (`fuente_titulares` de tema.py, Georgia/Times; kickers, valores y datos siguen en sans); B = rampa
    protagonista ciruela (`principal_1..3`, `principal_contexto`; antes `azul_*`, renombrado en tema.py, las
    variables CSS `--principal-*`, el JS y mail_agenda.py), banda ciruela en cabecera y pie; C = la frescura
    como sello: estampilla en cada card del tema (`frescura.html_sello`, la misma línea del B2 partida en
    período/estado/resto: borde lleno al día o publicado, punteado atrasado, gris con fondo rezago grave,
    gris claro sin calendario o diaria; la línea completa sigue en la página de la serie y la franja ⏸ en la
    card) y estampillas de fecha (`sitio.tile`) en la franja Hoy/Esta semana de la home y en el calendario.
    Todo el CSS de identidad está en `sitio.CSS_IDENTIDAD`, al final del `<style>` de todas las páginas (sitio.pagina
    y la plantilla de dashboard.py). Mail: botón "Ver el dashboard completo" = `principal_1`, "Leer nota" =
    `principal_2`, texto = `texto`, gris de variación nula = `texto_3`, desde tema.py; el verde/rojo de la
    variación de los indicadores queda para el Bloque 2 de PROMPT_mail_v3.md. Tests: `tests/test_identidad_e5.py`.
- **Estética del dashboard** (Bloque C, diseño aprobado por Pedro el 07/11/2026; mismo estilo en las dos
  páginas):
  - Colores y tipografía SÓLO de `tema.py` (`TEMA`): el CSS (variables `--principal-1`, …) y el JS (`TEMA`,
    `Chart.defaults` + plugins globales `etiquetasDirectas`, `tramoSinDatos`, `lineaCero`) se generan desde
    ahí. Ningún gráfico se estiliza por separado; la jerarquía la da el orden: protagonista `principal_1`,
    luego `principal_2`, `principal_3` (punteado), contexto `principal_contexto` (ciruela desde E5). En un overlay la protagonista es la
    ÚLTIMA serie de `series:` (la que resume la card). `ACENTO`/`AZUL_ENLACE` quedan sólo por compatibilidad.
  - `negativo` = SÓLO valores negativos (D2): bordó medio #A3505C desde el 09/11/2026 (decisión B de Pedro en el
    bloque de identidad visual; antes arena #C9A66B). Los textos dicen "bordó" vía `tema.NOMBRE_COLOR`. La variación bajo el valor va en gris azulado, sin
    juicio (D3): `sube_es_bueno`/`neutral` ya no pintan la card del dashboard (el mail los sigue usando
    hasta su Bloque 2).
  - Sin leyendas de Chart.js: etiquetas directas al final de cada serie + leyenda en prosa sobre el
    gráfico (`.cdesc`, la arma el JS con los colores reales). Campo opcional `etiqueta: "..."` en el yaml
    = texto corto de la etiqueta directa (si no hay y el nombre es largo, va sólo el valor).
  - Decimales según la unidad y pp para tasas (D4, `titulares.decimales`/`decDe` en JS). Fuente del
    sistema (Helvetica Neue/Helvetica/Arial), sin Google Fonts (D6).
  - Selector "Vista: desde mmm-aa · 6M · 1A · 5A · Máx · Rango…" (D5): la vista inicial es el `desde`.
  - Serie con franja ⏸ (rezago grave del B2): el eje sigue hasta hoy con nulls y el tramo sin datos va
    sombreado (D9, `_extender_hasta_hoy`). máx/mín van en el pie, junto a la fuente y el asterisco (D11).
  - La línea de frescura del B2 (`.cf`) NO se toca.
- **Identidad visual** (09/11/2026, decisiones de Pedro): paleta azul marino (`principal_1..3`, `principal_contexto` en
  tema.py; principal_3 = #7696C2 llega a 3:1 y su etiqueta directa va en principal_2; texto_3 = #677987, 4,5:1). Los
  textos que nombran un color salen de `tema.NOMBRE_COLOR` (nunca "bordó"/"azul" escritos a mano). Firma "por Pedro
  Thill" en la cabecera de todas las páginas (`sitio.firma`) y bloque de autor en /acerca/. Anclas: `[id] {
  scroll-margin-top }` en `sitio.CSS_IDENTIDAD` (la barra de navegación es sticky). **Escala de 5A/Máx**
  (`dashboard.escala_larga`): las series con `nominal_pesos: true` o `escala_log_largo: true` (dólares, depósitos,
  M2/M3) en niveles positivos pasan a escala logarítmica en 5A y Máx, con rótulo "escala logarítmica"; con negativos
  o ceros (resultado fiscal) la card no ofrece Máx. La vista inicial no cambia. Tests: `tests/test_identidad_visual.py`.
- `titulares.py` (funciones puras, tests en `tests/test_titulares.py`) — titular por reglas de cada card
  de la pestaña macro (sólo macro, D1; `generar(con_titulares=True)` desde run.py) y la variación bajo el
  valor, que compara contra lo mismo que el titular (D13). Campos del yaml: `titular_regla:
  direccion|signo|saldo|aporte`, `titular_sujeto` (con artículo: define género/número del verbo),
  `titular_formato` (ej. `"USD {} M"`), `titular` (texto fijo, override). Sin regla, en rezago grave o sin
  dato de comparación, la card muestra el nombre. Períodos: trimestrales siempre con año ("2.º trimestre
  de 2026"); mensuales con año sólo si no es el año en curso.
  - `comparar:` política por defecto (D7): las diarias contra el dato anterior; las mensuales y
    trimestrales (ninguna serie del dashboard está desestacionalizada, verificado en la metadata de
    datos.gob.ar) contra el MISMO período del año anterior, tanto la dirección como la racha, y sin
    "Máximo/Mínimo desde" (D12). **Excepción explícita en el yaml** con `comparar: anterior`: inflación
    mensual y núcleo/regulados/estacionales (decisión de Pedro del 07/11/2026: es como se comunica el
    dato, "La inflación mensual sube a 1,9% en septiembre"), más las series que ya son una variación
    interanual o una tasa real (inflación interanual, tasa real). Nunca hardcodear la excepción en el código.
  - Incidencia del IPC: `top_n: 3` + Resto (D8); titular `aporte` con la división de mayor aporte.
  - Rachas ("n.º mes seguido"), decisiones de Pedro: desde 3 períodos. Las de DIRECCIÓN (suba/baja, por
    encima/debajo del año anterior) se omiten si pasan de 24 (`MAX_RACHA`) y en series nominales en pesos,
    marcadas en el yaml con `nominal_pesos: true` (hoy: base monetaria, préstamos al sector privado, PBI
    nominal, resultado fiscal; el dólar no, es un tipo de cambio). Las de SIGNO (superávit, déficit, tasa
    negativa) van siempre: sin tope y también en pesos. Una serie nueva en pesos corrientes con titular
    → marcarla.
  - `titular:` con el mismo texto que el `nombre` = la card muestra sólo el nombre (sin antetítulo), y
    `ocultar_variacion: true` saca la variación bajo el valor. Se usan para no publicar un titular ni una
    variación sobre un dato dudoso mientras se revisa (base monetaria, PENDIENTES #14).
  - `unidad_linea:` en `vista: balance_cambiario` = unidad de la línea, que es también la del valor de la
    card (ej. reservas en millones de USD, con las barras de compras netas en millones de $).

## Fuentes de datos y cómo se declaran en indicadores.yaml
- `fuente: datos_gob` + `id: "..."` → apis.datos.gob.ar/series (IPC, EMAE, monetarias,
  fiscal, empleo, comercio exterior). Es el backbone. **Fallback al CSV de distribución**
  (`fuentes_datos_gob.py`, decisión de Pedro del 08/11/2026, #21 de PENDIENTES): toda serie de datos.gob.ar
  (directa, componente de `calculo:` o fallback de una del INDEC) se compara con el CSV de distribución del
  mismo catálogo (`downloadURL` y título del campo de la metadata) y se usa el CSV si la API devuelve 0
  filas, menos filas que su `time_index_size`, si los últimos 12 períodos comunes difieren más de 1% (la
  mayor diferencia sobre el promedio de |CSV| en la ventana) o si el CSV tiene períodos más nuevos que la
  API. **Guarda anti-RIPTE:** si el período más nuevo del CSV repite EXACTAMENTE el valor del anterior, ese
  período no se usa (si era el único motivo, queda la API) y sale alerta semanal (clave
  `datos_gob_csv_descartados` de `ultima_corrida.json`). **Coherencia por card** (`grupos_por_card` +
  `ResolverDatosGob.preparar`, antes del loop de run.py): si un id cae al CSV, los demás ids de la MISMA
  distribución que dibuja la misma card (combos, espejos, overlays, tablas, componentes de `calculo:`)
  también usan el CSV; nada de mezclar API y CSV en un gráfico. La guarda no salta si la API publica ese
  mismo período con el mismo valor. Alertas a Pedro sólo por 0 filas, historia cortada, diferencia >
  tolerancia y la guarda; el disparador 4 y la coherencia quedan en `datos_gob_csv`, la racha y la nota. La API puede tener la metadata al día y aun
  así devolver vacío, historia cortada o valores erróneos (base monetaria jun-2026). Cada uso: clave
  `datos_gob_csv` de `data/ultima_corrida.json`, racha en `data/datos_gob_estado.json`, alerta a Pedro el
  primer día y semanal (máx. 1 mail por corrida) y la nota de la serie agrega "Datos vía CSV de
  distribución de datos.gob.ar". `fallback_csv_excluir:` (top-level del yaml) = ids que nunca lo usan (hoy
  ninguno: el RIPTE, cuyo CSV traía ago-2026 con el valor de jun-2026, pasó a `fuente: trabajo_ripte`). Tests: `tests/test_fuentes_datos_gob.py`.
- `equivalencias_indec:` (top-level del yaml) → mapa `id de datos.gob → {tabla, filtros,
  columna?, variaciones?}` de la API del INDEC, cada uno verificado contra el catálogo real
  (`fuentes/indec_equivalencias.md`; regla dura #1 vale igual: nada se agrega sin verificar).
  Cualquier `_dg(id)` de run.py (series directas y componentes de `calculo:`) con equivalencia
  va primero a la API. `variaciones: {mensual: v_m, interanual: v_ia}` → `calculo:
  mensual`/`interanual` sobre ese id usa la variación PUBLICADA por el INDEC (no la recalcula
  desde el índice; si la API falla, la recalcula desde datos.gob como antes).
- `fuente_primaria: indec_api` + `fuente_fallback: datos_gob_ar|argentinadatos` → serie
  directa del INDEC. Con `datos_gob_ar` usa la equivalencia de su `id`; con `argentinadatos`
  declara `indec: {tabla, filtros}` propio + `endpoint` del fallback. `factor_fallback: N` →
  factor que se aplica SÓLO si se usó el fallback (ej. desempleo: la API publica %, datos.gob
  fracción). `fecha_fin_mes: true` → normaliza las fechas a fin de mes (convención histórica
  de esa serie en el CSV, ej. inflación mensual de ArgentinaDatos). Empalme: `storage` pisa
  fechas repetidas con el dato nuevo y conserva las que la API no tiene (ej. inflación
  mensual GBA 2017-ene/may y desempleo hasta 3T-2015 quedan de la fuente vieja, documentado
  en la nota). Ojo: si un día se usa el fallback, vuelve a pisar con el dato viejo.
- Comercio exterior, PBI, ISAC, supermercados y turismo siguen en datos.gob.ar (la API no
  publica totales de comex ni esas series).
- `fuente: bcra` + `id_variable: N` → api.bcra.gob.ar (reservas diarias, etc.).
  Con `agregacion_mensual: promedio_corridos|promedio_habiles|fin_de_mes` la serie diaria se trae
  COMPLETA desde `start_date` (`fetch_bcra_historia`, en ventanas de 4 años; `fetch_bcra` no se toca) y se
  mensualiza (`agregar_mensual`, sin el mes en curso). `promedio_corridos` (fines de semana y feriados
  arrastran el último hábil) es el "promedio mensual" que publica datos.gob.ar: 0,000% de diferencia en
  base monetaria (idVariable 15, desde el 08/11/2026) y 0,001% en M2 (idVariable 109, "M2 " de
  Series.xlsm, desde el 08/11/2026) en 24 meses.
- `fuente: argentinadatos` + `endpoint: "..."` → api.argentinadatos.com (inflación, riesgo país).
- `fuente: dolar` + `casa: ...` → cotizaciones de dólar por casa (ArgentinaDatos).
- `fuente: byma` + `symbol: "..."` → índices históricos de BYMA (open.bymadata.com.ar,
  `fetch_byma_indice` en fetchers.py; `symbol: "M"` = S&P MERVAL, `"G"` = BURCAP), serie diaria
  completa en un solo request. El certificado de BYMA tiene una CA intermedia fuera del bundle
  estándar de certifi: el fetcher pide con `verify=False` (conexión sigue siendo TLS, sólo se
  salta la validación de cadena), mismo criterio que las librerías públicas de BYMA
  (`pyhomebroker`, `bymadata`).
- **Fechas y snapshots (bloque MAE, 08/11/2026):** el runner de Actions está en UTC; para "hoy" usar
  `fetchers.hoy_ar()` (fecha de Argentina), NUNCA `pd.Timestamp.today()`/`date.today()`/`datetime.now()` sin
  zona. Un snapshot del día se fecha con la fecha que informe la fuente (`fetchers.fecha_snapshot_mae`) o, si no
  la trae, con `hoy_ar()`, y run.py descarta los puntos de fines de semana y feriados de las fuentes
  snapshot (`run.FUENTES_SNAPSHOT`/`CALCULOS_SNAPSHOT`, `run.solo_habiles`). Un 0 de un snapshot del MAE es "sin
  operaciones", no un dato.
- `fuente: mae_bono` + `ticker: "..."` + `campo: tir|md` (opcional `letra`, default "H") →
  TIR o duración modificada de un bono hard-dollar, Mercado Abierto Electrónico
  (`fetch_mae_bono_campo`/`fetch_mae_flujofondos` en fetchers.py, endpoint
  `emisiones/flujofondoscotiz/{letra}`, no documentado oficialmente por el MAE, `letra: "H"` =
  bonos hard-dollar step-up tipo AL30/GD30/GD35, `"B"` = BOPREAL). Snapshot del día, SIN
  endpoint histórico ni fecha propia: la serie sólo acumula un punto por corrida, sin backfill posible. Viene
  vacío fines de semana y feriados, y también días hábiles si el bono no operó en el MAE. **Ya no lo usa ningún
  indicador** (desde el 08/11/2026 las TIR salen de `byma_bono`); sirve como referencia y para la verificación
  de la convención (`tests/manual_verificar_tir_mae.py`).
- `fuente: byma_bono` + `ticker: "..."` + `campo: tir|md` + `desde_historia` → TIR (% anual) o duración
  modificada (años) calculadas por el monitor (`fuentes_mercados.serie_bono`, #28, decisión de Pedro del
  08/11/2026): TIR efectiva anual, ACT/365, liquidación T+1 hábil, precio = cierre (`c`) de BYMA de
  "<ticker>D 24HS" tal cual (sin cupón corrido; sólo responde 24HS), flujos del MAE por 100 de VN original
  (`emisiones/flujofondos/{ticker}`, `cashFlow`); MD = Macaulay / (1 + TIR). **BYMA ajusta hacia atrás sus
  cierres en cada pago** (verificado: sin caída de precio en los pagos de jul-2025/ene-2026/jul-2026; GD30 a 49,3
  en BYMA y 73 en el MAE el 03/12/2024): sólo se calculan los días POSTERIORES al último pago
  (`ultimo_pago`: el pago listado con fecha <= hoy o, si el MAE ya lo sacó, el primero futuro menos el período),
  así que las filas anteriores a un pago, ya guardadas, no se recalculan nunca (test del reajuste en
  `tests/test_tir_bonos.py`). Historia desde el 10/07/2026 (primer hábil después del pago del 09/07: el 13/07).
  BYMA gratis sólo da 2 años móviles. **Las tres TIR, la curva y el spread siguen EN REVISIÓN** hasta verificar la
  convención contra el snapshot del MAE (precio + TIR + MD juntos) con `python tests/manual_verificar_tir_mae.py`
  un día hábil (PENDIENTES #28).
- **Muro de vencimientos:** `fetch_mae_flujofondos_ticker(ticker)` (endpoint `emisiones/flujofondos/{ticker}`,
  el de la ficha del título): `detalle[]` con fechaPago, amortizacion (% del VN ORIGINAL), renta, cashFlow y
  valor residual. No depende de que el bono cotice (responde fines de semana).
- `fuente: mae_resumen` + `tipo: "..."` + `ticker: "..."` + `campo` (opcional, default
  "ultimo") → un campo de un instrumento puntual del resumen del MAE (`"RF"` = renta fija, `"DDF"` = dólar
  futuro, `"FOR"` = forwards). Snapshot del día, mismas limitaciones que `mae_bono`. Ya no se usa para las
  cauciones (ver `mae_caucion`).
- `fuente: mae_caucion` + `ticker: "CAARS"|"CAUSD"` + `desde_historia` → caución del MAE desde el histórico de
  cierre (`fuentes_mercados.serie_caucion`, endpoint `mercado/titulo/historicocauciones?oTitulo={"fechaDesde",
  "fechaHasta"}`, el que usa marketdata.mae.com.ar; ventanas de 3 meses: con un año da 400), hasta el día hábil
  anterior que informa `mercado/fechahabilanterior`. Por día: `tasaPP` (promedio ponderado) del plazo MÁS CORTO
  operado (001 de lunes a jueves, 003 los viernes, 004-006 antes de feriados); tasa o monto 0 = sin dato (el
  `ultimo` del cierre es siempre 0, #13). Historia: pesos desde ene-2024, dólares desde el 02/07/2025 (primer
  día del histórico del MAE). Umbral (`filtrar_monto_minimo`): si el monto del plazo más corto es < 5% de la
  mediana de los 20 días hábiles previos, el día queda sin dato, sin sustituto (decisión de Pedro, #13). Otros endpoints históricos
  del MAE sin clave, verificados: `mercado/titulo/historicorentafija` (+ `/detalle?oTitulo={"fecha"}`, precios
  por operación, sin TIR). La API oficial con clave (`api.mae.com.ar/MarketData/v1`) no se usa.
- `fuente: tesoro_ust` + `plazo: "10 Yr"` → rendimiento del Treasury (`fuentes_mercados.serie_ust`): CSV de la
  curva par del Tesoro de EE.UU. (`daily-treasury-rates.csv/{año}/all?type=daily_treasury_yield_curve`, un
  archivo por año) y, si falla, el H.15 de la Fed (`Output.aspx?rel=H15&series=bf17364827e38702b42a58cf8eaa3f78`,
  `from` y `to` juntos con las barras sin codificar) con alerta a Pedro; si fallan los dos, queda el histórico,
  con alerta. Mismos números que el DGS10 de FRED (verificado en 5.673 fechas). **FRED se sacó**: Akamai retiene
  la conexión desde GitHub Actions (nunca funcionó ahí, #8).
- `calculo: spread_bono_ust` + `ticker_bono: "..."` + `ust_plazos: ["6 Mo", "1 Yr", "2 Yr", "3 Yr"]` +
  `desde_historia` → (TIR del bono vía `byma_bono` − Treasury interpolado lineal en plazo a la MD del bono) × 100,
  en puntos básicos (`fuentes_mercados.spread_duracion`, decisión de Pedro del 08/11/2026, #8/#28). Cada plazo
  sale de `tesoro_ust` (CSV del Tesoro, respaldo H.15: `H15_SERIE` tiene los ids verificados de 6 Mo/1/2/3/10 Yr; el "UST 10Y
  (Treasury)" del yaml se sacó el 09/11/2026 y sus filas quedan huérfanas, #25);
  `pd.merge_asof` hacia atrás con tolerancia de 5 días (el Tesoro publica con el calendario de EE.UU.); una MD
  fuera del rango de los plazos usa el extremo, sin extrapolar. Card "Spread GD30 vs. Treasury de igual
  duración" (antes "Spread soberano GD30 vs. UST10Y (proxy)", contra el 10 años; `slug_anterior` redirige la
  URL vieja). Nunca llamarlo "riesgo país" a secas: no es el EMBI+. EN REVISIÓN junto con la TIR (#28).
- `solo_referencia: true` → el indicador NO se fetchea (run.py lo saltea en el loop): reusa el
  dato que otro indicador de la MISMA corrida ya trajo con el mismo `nombre` (mismo `historico`
  compartido), sólo le agrega una tarjeta propia bajo su propio `bloque`/`grupo`. Pensado para
  mostrar el mismo indicador macro (ej. Dólar oficial, TAMAR) también en `indicadores_financiera`
  sin duplicar el fetch ni las filas del CSV.
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
  sin rebase ni indexar (el valor crudo del cociente es la unidad que importa, ej. RIPTE medido en
  canastas = salario en pesos ÷ costo de una canasta en pesos = "canastas que compra un salario").
  Cualquiera de los dos lados puede ser una fuente propia en vez de un id: `numerador: {fuente: ...}`
  (se trae con `fetchers.traer`; hoy `{fuente: trabajo_ripte}`).
- `calculo: real` + `nominal_id` + `deflactor_id` → deflacta por IPC (ej. salario real). Por
  defecto rebasa a índice 100 al inicio de la serie. Con `base_fecha: "AAAA-MM-01"` devuelve
  en cambio PESOS CONSTANTES de ese mes (nominal × IPC(base) / IPC(t)), ej. Adelantos
  Transitorios / Transferencia de Utilidades. Mes base FIJO a propósito: la `nota` y la
  `unidad` lo nombran ("millones de $ de ago-2026"), así que moverlo implica actualizar
  también esos textos. Falla explícitamente si el IPC no tiene dato en `base_fecha`. Con el
  IPC 148.3_INIVELNAL_DICI_M_26 la serie real arranca en dic-2016 (inicio de ese IPC).
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
- `calculo: tasa_real_expost` + `tasa_id_variable` + `ipc_base_id` → tasa nominal del BCRA
  (diaria, resampleada a fin de mes) menos inflación interanual (datos_gob, mensual, calculada
  con la misma lógica que `calculo: interanual`), en puntos porcentuales. EX-POST (mide contra
  la inflación YA ocurrida, no la esperada) -- la variante ex-ante necesitaría inflación
  esperada del REM, no implementada por esta vía.
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
- `fuente: trabajo_ripte` (sin parámetros) → RIPTE en pesos corrientes de la Secretaría de Trabajo
  (`fuentes_trabajo.py`, decisión de Pedro del 08/11/2026; sin fallback a datos.gob.ar, cuyo
  158.1_REPTE_0_0_5 dejó de devolver datos). Página
  https://www.argentina.gob.ar/trabajo/seguridadsocial/ripte: encabezado "Publicación <Mes> <Año>", valor
  destacado, PDF con la serie completa desde jul-1994 (nombre que cambia sin patrón en cada publicación: se
  toma el link de la página, que hoy viene como `href="blank:#/sites/..."`) y tabla HTML de los últimos 20
  meses. Controles que hacen fallar ruidosamente (nunca serie vacía): cada línea del PDF con un monto se
  tiene que leer (pdfplumber deja mes y año en la línea; pdftotext no), meses consecutivos desde jul-1994
  ($ 874,87), índice = monto / 874,87 × 100, variación % fila por fila, último mes = encabezado = título del
  PDF, último monto = destacado y los 20 meses de la tabla iguales al PDF. Escalón: si el PDF falla y la
  tabla pasa sus controles (meses consecutivos, variación fila por fila, último mes = encabezado), se usan
  las filas de la tabla (el merge conserva lo anterior) + alerta; si fallan los dos, `RipteError` ->
  `problemas` + alerta, histórico intacto. En cada corrida se baja la página; el PDF sólo si cambió su link
  o el mes respecto de `data/_cache_ripte.csv`/`_cache_ripte_meta.json` (sólo un PDF validado pisa la
  caché). Estado (racha sin PDF, avisos) en la clave `estado` del mismo meta; alerta a Pedro el primer día y
  semanal; resumen en `trabajo_ripte` de `ultima_corrida.json`. Sin calendario oficial (la página dice
  "hasta 45 días de finalizado el período": plazo, no fecha). Tests: `tests/test_trabajo_ripte.py`
  (fixtures en `tests/fixtures/ripte_*`).
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
- `vista: combo_2lineas` + `linea_izq: "..."` + `linea_der: "..."` + `unidad_izq`/`unidad_der`
  → combo de DOS indicadores ya existentes, ambos como línea, cada uno en su propio eje --
  para cuando ninguno de los dos tiene sentido como barra y sus magnitudes no son comparables
  en un eje compartido (ej. un índice base 100 vs. un nivel concreto en otra unidad; a
  diferencia de `overlay`, que comparte un solo eje y sólo sirve si las series son de magnitud
  parecida). Mismo resampleo a fin de mes que `combo_barras_linea` por si las frecuencias
  difieren.
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
  con burbuja (Chart.js `bar` + plugin propio `burbujaSectorPlugin`): eje X = sector (una
  columna por sector, ordenadas por el VALOR de `emae` de menor a mayor -- no por `empleo`),
  eje Y = variación % interanual de `emae`. Burbuja dibujada en la punta de cada columna: %
  que representa `empleo` sobre el total al último período común (radio ~ raíz cuadrada del %,
  para que sea el ÁREA la que quede proporcional al peso, no el radio) -- referencia visual:
  slide de MAP LATAM. El empleo ya no define el orden del eje (a diferencia de una versión
  anterior de este mismo mecanismo), sólo el tamaño de la burbuja. Barras coloreadas por signo
  (verde/rojo), mismo criterio que los combos de barra+línea. Si las frecuencias no coinciden
  (ej. EMAE mensual vs. empleo trimestral), el más frecuente se remuestrea al calendario del
  menos frecuente antes de comparar — documentarlo en la `nota`. Sin botones de filtro de rango
  de fecha (es una foto de un período, no una serie temporal). Reemplaza a una versión anterior
  en burbujas de dos ejes continuos (eje X/Y = actividad/empleo, tamaño = peso de empleo): con
  sólo ~15 sectores, el cluster central quedaba amontonado en el centro del cuadrante y
  necesitaba ejes recortados con la cerca de Tukey (Q3 + 1,5×RIC) más un toggle "Vista
  completa"/"Zoom al cluster" para que el grupo central no quedara ilegible — con una columna
  por sector no hay superposición posible, así que ninguno de los dos mecanismos hace falta.
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
- `rebase_vista: true` en un `vista: overlay` → las series se guardan en NIVELES y `dashboard.rebase_vista`
  las rebasa a 100 al dibujar, en el primer mes del `desde` de la card (decirlo en la `nota` y la
  `unidad`). Preferirlo a `rebase_100`: un valor guardado ya rebasado depende de la primera fila que
  devolvió la fuente, y si una corrida trae historia parcial el merge mezcla bases (pasó con M1/M2/M3,
  #23 de PENDIENTES). `reconstruir_series.py` borra (con backup fuera de data/) todas las filas de un
  indicador para que la corrida siguiente lo reescriba desde una sola fuente: única excepción al merge
  idempotente, sólo con OK de Pedro. Con `--solo-no-habiles` borra sólo las filas fechadas en fines de
  semana y feriados (snapshots sin historia en la fuente, bloque MAE).
- `cortar_comun: true` en un `vista: overlay` → la card y el gráfico llegan sólo hasta el último período
  que tienen TODAS sus series (`dashboard.cortar_comun`, sobre la copia del histórico de la página; lo
  guardado no se toca). Para series que sólo dibuja ese overlay (`solo_componente`): ej. M2 del BCRA va un
  mes adelante de M3 de datos.gob.ar.
- `rebase_100: true` → rebasa la serie a 100 en su primer valor disponible antes de guardarla
  (aplica sobre el resultado de cualquier `fuente:`/`calculo:`, es un paso genérico, no un
  cálculo propio). Para cuando un indicador sólo tiene sentido combinado en un `vista: overlay`
  con otros de magnitud muy distinta (ej. M1/M2/M3: M3 es varias veces más grande que M1 en
  pesos, así que mostrarlos en niveles absolutos aplastaría a los más chicos contra el eje).
- `marca_fecha: true` → si la serie lleva más de `UMBRAL_DISCONTINUADA_DIAS` sin datos
  nuevos, el dashboard muestra un badge dinámico "Sin datos nuevos desde MM/AAAA" (se
  recalcula cada corrida; desaparece solo si la fuente retoma la publicación). También
  excluye al indicador del chequeo de frescura de `run.py` (ya avisa por otra vía).
- `sin_alerta_rezago: true` → excluye la serie del chequeo de frescura de `run.py` (alertas de rezago), SIN
  badge (a diferencia de `marca_fecha`). Para una serie en revisión cuyo atraso ya se conoce. NO se ata al
  `aviso` (decisión de Pedro: apagaría también la alerta del S&P MERVAL). Hoy: sólo el spread GD30.
- `slug_anterior: "..."` → al renombrar una card, run.py escribe `docs/serie/<slug viejo>/index.html` como
  redirección a la página nueva (`pagina_home.generar_redireccion`, igual que `financiera.html`), y la página de
  su tema manda `#<slug viejo>` a `#<slug nuevo>` (`sitio.js_anclas`, el mismo script de las anclas viejas de la
  home).
- `sin_valor` (en la card que arma run.py, no en el yaml) → la card no muestra valor ni unidad (muro de
  vencimientos: un gráfico por año no tiene valor único; opción A de Pedro, 08/11/2026).
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
  aplican con claridad (ej. Base monetaria/M1/M2/M3, TAMAR, préstamos, depósitos bancarios,
  TCR multilateral — decisión de Pedro en cada caso, ver punto anterior). Se lee del mismo
  yaml en dashboard.py y enviar_mail.py.
- `nota: "..."` → aclaración metodológica; se muestra como asterisco bajo el gráfico y en el
  pie de la página. Obligatoria en toda serie calculada, estimada, proxy o rascada de Excel,
  o con `factor` aplicado.
- `aviso: "..."` → línea visible (franja gris del B2) en la card, tanto en la página de tema como en la
  de la serie, para un dato EN REVISIÓN que no se corrige (regla dura #4). Genérico: va junto con
  `ocultar_variacion: true` mientras esté abierto el pendiente. Hoy: S&P MERVAL ("Dato en revisión: posible
  cambio de escala en la fuente desde el 19/10/2026", PENDIENTES #12). Sacar los dos campos al cerrarlo.
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

## Reglas de trabajo con git
- **Antes de cualquier push**, correr `git fetch` + `git log origin/main..HEAD` y mostrarle a Pedro TODOS los
  commits que van a subir (hash, mensaje completo y `--stat`). Si hay alguno que no es el de la ronda actual,
  frenar y preguntar antes de pushear.
- Nunca `pull --rebase` + push en el mismo paso sin ese chequeo: un rebase puede arrastrar commits locales
  viejos que nunca se aprobaron para subir. Pasó el 08/11/2026: el commit de la ronda anterior (fd5d1f5,
  fallback al CSV de datos.gob.ar) estaba sólo en local y salió junto con el del RIPTE. Pedro decidió dejarlo.
- Commit y push, sólo con el OK explícito de Pedro para cada uno.

## Estado actual (ya implementado)
Precios (inflación mensual/interanual, IPC nivel general, incidencia por división de consumo);
Dólar (oficial/blue/MEP/CCL); Brecha cambiaria; Tipo de
cambio real (diario, 116.4_TCRZE_2015_D_36_4); Riesgo país; Reservas (BCRA diario, combo,
compras netas de divisas por contraparte); Agregados monetarios (base monetaria; M2 y M3 en
un overlay rebasado a 100 al dibujar; el M1 quedó definido en el yaml pero fuera del gráfico desde el
08/11/2026, su definición está en revisión, PENDIENTES #23); Tasas (TAMAR total bancos, reemplaza a BADLAR); Crédito (préstamos
al sector privado, variación % real mensual, por tipo de
deudor Familias/Empresas; tasa de interés real ex-post (TAMAR - inflación interanual, opción A,
ex-ante con REM pendiente de confirmación de Pedro); semáforo del EMAE por 16 sectores +
actividad por sector en barras con burbuja de empleo (puestos asalariados registrados de la Cuenta de
Generación del Ingreso del INDEC, no SIPA), ordenadas por variación de actividad -- EMAE general, EMAE Urbano vs. No urbano e IPI manufacturero se sacaron del dashboard
a pedido de Pedro (siguen en indicadores.yaml donde hace falta, ver `solo_componente`); Sector
externo (expo/impo/saldo en gráfico espejo + tablas de desagregado por rubro y por uso); Social
(desempleo, tasa de informalidad laboral, salario real por tipo de empleo, salario real
combinado con capacidad de compra RIPTE/CBT en un combo de dos ejes); Fiscal (resultado
primario y financiero del Sector Público Nacional, superávit gemelos fiscal/comercial,
resultado primario acumulado 12 meses vs. riesgo país, resultado primario vs. intereses de
deuda, deuda pública bruta, PBI nominal trimestral, deuda/PBI vs. tipo de cambio real,
asistencia monetaria del BCRA al Tesoro -- Adelantos Transitorios + Transferencia de
Utilidades, ubicación en Fiscal y sin normalizar por PBI/Base Monetaria pendientes de
confirmación de Pedro). Depósitos y morosidad se reclasificaron a la pestaña financiera (ver
más abajo), ya no están en `docs/index.html`.

**Pestaña financiera** (`docs/financiera.html`, Rondas 1-2 de `PROMPT_pestana_financiera.md`):
página separada con nav cruzado hacia/desde la macro. FX/brechas y TAMAR (total bancos, 135)
referenciados desde la pestaña macro (`solo_referencia`, mismo dato, sin refetch); CER (BCRA,
idVariable 30); S&P MERVAL (BYMA, serie histórica diaria); TAMAR bancos privados (idVariable
44, variante que referencian los bonos duales) y BADLAR (idVariable 7), plazo fijo a 30 días,
cauciones pesos/USD (MAE, histórico de cierre, plazo más corto del día); curva de rendimientos
AL30/GD30/GD35 (EN REVISIÓN, #28; TIR en el tiempo calculada con cierres de BYMA + flujo del MAE, no
snapshot puntual -- el pedido original de un gráfico X=duración/Y=TIR se cambió por una serie
temporal de las 3 TIR, ver la nota del indicador); spread GD30 vs. Treasury de igual duración (EN REVISIÓN,
NO es el EMBI+ oficial); muro de vencimientos de AL30/GD30/GD35 (barras agrupadas por año, % del
valor nominal de cada bono, vía el flujo de fondos del MAE); depósitos y morosidad
RECLASIFICADOS desde la macro (ver la nota sobre mover vs. retaguear en Arquitectura), con
nuevo corte de depósitos por moneda (pesos/USD, privado/público); acciones y CEDEARs más
operados (tablas, ranking por monto vía data912, recalculado en cada corrida); dólar futuro
(DDF, curva de contratos vía MAE, gráfico de barras -- reemplazó a la tabla de Ronda 1).
Universo de renta fija acotado a AL30/GD30/GD35 por decisión de Pedro (no todo el set
disponible en el MAE). Canje MEP/CCL (`calculo: brecha` sobre CCL/MEP en vez de CCL/oficial).
Pendiente de rondas siguientes (ver `PROMPT_pestana_financiera (1).md` sección 8):
LECAPs/BONCAPs/ONs en la curva de rendimientos, fiscal dentro de esta misma pestaña,
combinadas (tasa real vs. EMAE, TAMAR vs. CER ex-post, etc.), divisas internacionales, FED,
licitaciones, panel líder completo (20 símbolos) más allá del ranking por volumen actual.

## Pendientes / a mejorar
Ver el prompt de tareas. En general: filtros de años por gráfico, más desagregados, y series que
todavía no tienen fuente confiable identificada: patentamientos exactos (ACARA, sin datos
abiertos), turismo, escrituras, ISAC.

**Token del INDEC (para `PROMPT_ronda_macro_indec.md`):** el prompt (punto A5) asume que el
token vence a los 12 meses de `INDEC_TOKEN_FECHA`, pero vence a los **180 días** (el actual,
el 04/05/2027, según el campo `exp` del propio token). Al implementar el aviso de
vencimiento, conviene leer `exp` del token en vez de calcular un plazo fijo; confirmarlo con
Pedro antes.

**Filtro de noticias — ejemplos marcados por Pedro para la próxima ronda (NO tocados todavía):**
- Zona horaria de las notas (PENDIENTES #29): `published_parsed` (UTC) se compara contra un límite en hora AR.
- NO va en Internacional (2026-11-05, BBC Mundo, feeds.bbci.co.uk/mundo/rss.xml). Pasa
  `evaluar_intl` por `"ee.uu"` en la bajada (KW_INTERNACIONAL); no es economía. Convertirlo en
  test de `tests/test_noticias.py` antes de ajustar nada. Texto textual:
  - título: `"Soy morra, cis y hetero, pero creo que es mejor tener menos novios y más amigas"`
  - bajada: `La escritora mexicana y ganadora del Premio Biblioteca Breve 2026, conversa con BBC
    Mundo sobre su obra y cómo es vivir al lado de la frontera con EE.UU.`
- Decisión de Pedro: "De la Espriella adapta a Colombia el modelo de Milei de gabelas
  tributarias a inversionistas" SÍ puede entrar en Argentina (pasa por "milei"); no es un error.

**Hallazgos de `PROMPT_ronda_canje_y_macro.md` sin implementar (reportados, no forzados):**
- **Historia larga de reservas**: `api.bcra.gob.ar` v4.0 SÍ soporta paginación real encadenando
  `hasta` = (mínima fecha del batch anterior − 1 día) -- confirmado en vivo, historia real de
  reservas (idVariable 1) al menos desde 2014-05-07, muy por encima de la ventana de ~2 años
  que trae `fetch_bcra()` hoy (diseño propio, no una limitación real de la API). NO migrado:
  `fetch_bcra()` alimenta reservas Y "Reservas ajustadas" (notas *7/*10 de index.html, que
  documentan la ventana deslizante actual) -- cualquier cambio necesita confirmación de Pedro
  antes de tocar el fetcher en producción.
- **Calendario de licitaciones del Tesoro**: el único endpoint de licitaciones del MAE
  confirmado en vivo (`mercado/licitaciones`) no tiene campo de monto y mezcla eventos
  municipales/corporativos (ONs)/nacionales sin filtro -- no alcanza para "próxima fecha +
  monto que vence". Pendiente encontrar una fuente mejor (ej. calendario propio de la
  Secretaría de Finanzas, posible candidato a scrapear tipo `deuda_bruta`).

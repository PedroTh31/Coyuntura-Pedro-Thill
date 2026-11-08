# Pendientes

Cola priorizada por Pedro. El orden es el suyo: no se reordena ni se arranca un ítem sin que lo pida.

## Cola (en orden de prioridad)

1. **Capacidad de compra del salario (RIPTE / CBT) vacía en producción** — anotado el 07/11/2026.
   - Síntoma: el indicador sale vacío en todas las corridas; el histórico quedó en jul-2026.
   - Causa identificada (sin diagnosticar a fondo): el RIPTE `158.1_REPTE_0_0_5` devuelve 0
     filas en datos.gob.ar. No es una serie del INDEC (no tiene que ver con el Bloque A). La CBT
     (`150.1_CSTA_BATAL_0_D_20`) sí trae datos.
   - A hacer: diagnosticar (¿serie discontinuada, id cambiado, fuente alternativa?) y, mientras
     tanto, que el gráfico avise al lector que el dato está frenado.
   - **Resuelto el 08/11/2026:** el RIPTE sale de la Secretaría de
     Trabajo (`fuente: trabajo_ripte`, `fuentes_trabajo.py`: PDF con la historia completa + tabla de la
     página como control y como escalón de respaldo). La serie se renombró "RIPTE medido en canastas
     básicas (CBT, GBA)" (la card combo "Salario real y capacidad de compra" no cambia, ni su slug) y llega
     a ago-2026. La CBT estaba sana (API del INDEC, hasta sep-2026): la causa era sólo el RIPTE. Las 124
     filas viejas con el nombre "Capacidad de compra del salario (RIPTE / CBT)" se borraron con
     `reconstruir_series.py` (OK de Pedro; backup en el Escritorio, `backup_datos/`). Las otras huérfanas, en
     el #25.

2. **Series con fallback vacío en la alerta de autenticación del INDEC** — anotado el 07/11/2026.
   - Hoy: `11.3_TAC_2004_M_60`, `11.3_VMATC_2004_M_12`, `146.3_IRECREANAL_DICI_M_31`,
     `146.3_IRESTAUNAL_DICI_M_33` (su fallback de datos.gob.ar devuelve 0 filas).
   - Problema: si la API del INDEC falla, son las únicas series que se quedan sin datos, pero no
     aparecen en la lista de "series afectadas" de la alerta de autenticación
     (`ResolverIndec.terminar(ok=False)` no las registra porque terminan vacías). El aviso
     semanal de "fallback vacío" sí las nombra, por separado.
   - A hacer: incluirlas en la alerta de autenticación.
   - Ver también el #27 (unificar los mails de alerta).

3. **Adelantos transitorios y Transferencia de utilidades congelados en may-2026** — anotado el
   07/11/2026.
   - Síntoma: `331.1_OTRAS_OPERIOS__58` (adelantos) y `331.1_OTRAS_OPERDES__39` (transferencia de
     utilidades) no tienen datos posteriores a may-2026 en datos.gob.ar (190 días de rezago el
     07/11/2026). Arrastran a sus versiones en pesos constantes y al gráfico "Asistencia monetaria
     del BCRA al Tesoro".
   - A hacer: buscar una fuente alternativa verificada (por ejemplo, series del BCRA directo; regla
     dura #1: nada sin verificar). Mientras tanto, la etiqueta de frescura del Bloque B2 tiene que
     mostrar ese rezago con claridad.

4. **Comercio exterior atrasado** — anotado el 07/11/2026.
   - Síntoma: datos.gob.ar no levantó septiembre de 2026 del ICA (el INDEC lo publicó el 19/10). La
     línea de frescura del Bloque B2 lo marca "⚠ atrasado" en exportaciones, importaciones, saldo,
     balance energético y los gráficos que los usan.
   - A hacer: revisar una fuente alternativa verificada (regla dura #1).
   - **RESUELTO el 08/11/2026** (decisión C de Pedro, 4.º disparador del fallback del #21): el CSV de
     distribución del ICA ya trae sep-2026, así que exportaciones, importaciones, saldo, balance energético
     y el desagregado por rubro y por uso salen del CSV (coherencia por card: nada de mezclar API y CSV en un
     gráfico). Corrida local del 08/11: todas hasta sep-26, sello "al día" con próximo dato el 19/11. Si la
     API vuelve a ponerse al día, el disparador deja de saltar solo.

5. **TCR multilateral y compras netas de divisas frenados** — anotado el 07/11/2026.
   - TCR multilateral (`116.4_TCRZE_2015_D_36_4`): último dato 28/01/2026, ~10 meses, contra un
     rezago normal documentado de 210 días.
   - Compras netas de divisas del BCRA (total y por contraparte): último dato may-2026.
   - A hacer: diagnosticar (¿serie discontinuada, id cambiado, fuente alternativa?).

6. **Morosidad frenada (las 6 series de la pestaña financiera)** — anotado el 07/11/2026.
   - Familias total / Personales / Tarjetas de crédito (Excel del Informe sobre Bancos del BCRA,
     `fetch_bcra_morosidad_lineas`): último dato may-2026.
   - Sistema financiero / bancos privados / bancos públicos (datos.gob.ar, dataset 332.2): último
     dato abr-2026.
   - Causa no verificada. A hacer: diagnosticar (¿el BCRA no publicó anexos nuevos, cambió el link o
     el formato? ¿dataset 332.2 discontinuado?).

7. **Reservas ajustadas frenada en jun-2026** — anotado el 07/11/2026.
   - Toma la fecha más vieja de sus componentes (reservas brutas, swap con China de la planilla
     SDDS mensual del BCRA, organismos internacionales del Balance Semanal). Causa no verificada
     (¿falta la planilla SDDS de julio?). A hacer: diagnosticar qué componente la frena.

8. **Spread soberano GD30 vs. UST10Y frenado en 01/09/2026** — anotado el 07/11/2026.
   - Serie diaria (TIR del GD30 del MAE − DGS10 de FRED). Causa no verificada (¿falla la TIR del
     GD30 en el MAE o el cruce con FRED?). A hacer: diagnosticar.
   - **Causa (08/11/2026):** FRED da timeout desde GitHub Actions (`Read timed out. (read timeout=30)` contra
     `fred.stlouisfed.org/graph/fredgraph.csv`, en todas las corridas del bot registradas en
     `ultima_corrida.json` desde el 04/11/2026); desde la máquina local responde. Último dato del UST 10Y
     guardado: 03/09/2026. Se trata en el bloque del MAE.
   - **Bloque MAE (08/11/2026):** FRED nunca respondió desde Actions (la primera corrida con el indicador, el
     03/09, ya dio timeout; los datos del 01/09 y del 03/09 son de corridas locales). Está detrás de Akamai Bot
     Manager, que retiene la conexión sin contestar (no es rate limit ni 403). **Resuelto en el código:** el UST
     10Y sale del CSV del Tesoro de EE.UU. (curva par, columna "10 Yr", año por año desde 2004) con respaldo en
     el H.15 de la Fed (alerta a Pedro si entra el respaldo o si fallan los dos); FRED se sacó. Las 5.673 fechas
     guardadas de FRED coinciden exactamente con el Tesoro y con el H.15. **Falta verificar** que el Tesoro
     responda desde Actions: la prueba es la primera corrida del bot (no se creó repo de diagnóstico, decisión de
     Pedro).
   - **El spread sigue frenado y queda EN REVISIÓN** (titular fijo, sin variación, aviso "Dato en revisión"),
     porque depende de la TIR del GD30 del MAE (ver #28). Al resolver la TIR, el spread se calcula contra el
     Treasury **interpolado a la duration del GD30** con los plazos de 1, 2 y 3 años del mismo CSV del Tesoro
     (columnas "1 Yr", "2 Yr", "3 Yr"; `fuentes_mercados.H15_SERIE` ya tiene sus ids del H.15), no contra el de
     10 años (decisión de Pedro del 08/11/2026).

9. **La pestaña financiera no tiene línea de frescura** — anotado el 07/11/2026. **CERRADO el 08/11/2026:**
   lo resolvió el Bloque E2 (D4: frescura en todas las cards de todos los temas). Verificado en `docs/`
   generado: `mercados/` 7/7 cards con sello y `dinero-y-credito/` 15/15 (morosidad con franja ⏸ "sin datos
   nuevos hace 5/6 meses"); el spread GD30 lleva sello "sep-26 · sin calendario oficial" y no tiene franja
   porque su atraso (68 días al 08/11) todavía no pasa el umbral de 90. Texto original:
   - El Bloque B2 la dejó fuera de la ronda (sólo `index.html`). Consecuencia: los gráficos frenados
     de la financiera (morosidad, spread GD30) no le avisan nada al lector.
   - A hacer: extender la línea a `financiera.html` (en `run.py`, pasarle `frescura_ctx` también a
     la segunda llamada a `dashboard.generar`) cuando se decida.

10. **Mediana del REM en el "Dato nuevo" del IPC (mail diario)** — anotado el 07/11/2026 (decisión de
    Pedro: fuera del Bloque B3).
    - Hoy el IPC abre el mail sin fila del REM. El Excel histórico del BCRA (el que baja
      `fetch_rem_variable`) llegaba el 07/11/2026 sólo hasta la encuesta de fines de agosto, aunque el
      REM de octubre ya se había publicado (~05/11). Además, `data/_cache_rem.csv` es del 23/07: ningún
      indicador activo usa el REM, así que nadie la refresca.
    - A hacer: investigar si el BCRA publica cada encuesta del REM con una URL verificable (regla dura
      #1: no adivinarla) y refrescar la caché desde `run.py`. Recién ahí entra la fila del REM en la
      apertura del IPC (`calendario.yaml`, `apertura` de `ipc`), con la regla que defina Pedro (D2 del
      diseño del B3: la encuesta más reciente publicada antes del IPC que tenga pronóstico para ese mes).

11. **Reenvío del mail si falla el push de `data/mail_enviado.json`** — anotado el 07/11/2026.
    Riesgo aceptado por Pedro (ya existía desde el Bloque 1 de `PROMPT_mail_v3.md`).
    - Si fallan los 3 intentos de `pull --rebase` + push del último paso de `email_diario.yml`, el
      mail ya salió pero `mail_enviado.json` no queda en `main`. El workflow termina en rojo
      (`::error::No se pudo pushear data/mail_enviado.json`) y el disparo de respaldo de las 08:47
      reenvía el mail completo. Desde el Bloque B3, además, repite el "Dato nuevo" (tampoco quedó
      guardado `periodos_anunciados`) y vuelve a mostrar las series que entraron en rezago grave
      ese día (`graves_vistos`).
    - Mientras tanto: si el workflow del mail termina en rojo por ese error, revisar a mano antes de
      las 08:47 (o cancelar esa corrida de respaldo).
    - Ver también el #27 (unificar los mails de alerta).

12. **S&P MERVAL: corte de escala el 19/10/2026** — anotado el 07/11/2026 (visto en el Bloque C, no
    arreglado a pedido de Pedro).
    - En `data/series_largo.csv` la serie (BYMA, `symbol: "M"`) viene en ~2,8-3,0 millones de puntos
      hasta el 15/10/2026 y desde el 19/10/2026 en ~84.000-92.000 (último: 84.093,11 el 06/11). El
      cociente entre un día y el anterior en el corte es 0,034 (≈ 1/29), sin ningún otro salto así en
      la serie (desde 02/09/2024).
    - Se ve en la card de la pestaña financiera (antes y después del rediseño): la línea cae a casi 0.
    - Pendiente: confirmar en BYMA si cambió la base/divisor del índice o la unidad del endpoint, y
      decidir con Pedro cómo empalmar (no reescalar a mano sin una fuente que lo documente).

13. **Cauciones: valor 0,00 en un día con dato** — anotado el 07/11/2026 (visto en el Bloque C, no
    arreglado).
    - Caución en dólares (1 día): último dato 0,00 % TNA el 05/11/2026 (los días previos entre 0,90 y
      1,20). Es el valor que muestra la card.
    - Caución en pesos (1 día): 0,0 % TNA el 05/11/2026, entre 26,0 (04/11) y 30,0 (06/11).
    - Parece un snapshot del MAE tomado sin operaciones (campo `ultimo` en 0) que se guarda como dato
      real. Pendiente: tratar 0 como sin dato en `mae_resumen` (o usar otro campo), con un test.
    - **CERRADO el 08/11/2026 (bloque MAE):** el 0 venía del MAE (el campo `ultimo` del cierre es siempre 0; la
      tasa está en `ultimaTasa`/`tasaPP`). Las cauciones pasaron a `fuente: mae_caucion` (fuentes_mercados.py):
      histórico de cierre `mercado/titulo/historicocauciones` hasta el día hábil anterior que informa el MAE,
      tasa promedio ponderada (`tasaPP`) del plazo más corto operado del día (1 día hábil), tasa o monto 0 = sin
      dato (tests en tests/test_fuentes_mercados.py; `mae_resumen` también descarta el 0). Serie reconstruida
      desde ene-2024 (pesos; dólares desde el 02/07/2025, primer día del histórico del MAE) con
      reconstruir_series.py, backup en Desktop\backup_datos\cauciones_2026-11-08.csv.
    - Umbral de monto (decisión de Pedro del 08/11/2026, `fuentes_mercados.filtrar_monto_minimo`): si el monto del
      plazo más corto del día es menor al 5% de la mediana de los 20 días hábiles previos (misma moneda), ese día
      queda SIN DATO; no se lo sustituye por otro plazo. Desde ene-2024 pasa UN solo día: 05/11/2026 en pesos,
      plazo 001 con $12.932 MM (0,5% de la mediana, ~$2,96 billones; el grueso se operó a 006). En dólares,
      ningún día. Test con ese caso en tests/test_fuentes_mercados.py; dicho en la nota de las dos cauciones.
      **#13 cerrado completo.**

14. **Base monetaria: la serie cae a la mitad en jun-2026** — anotado el 07/11/2026 (visto en el Bloque
    C). **CERRADO el 08/11/2026:** pasa al BCRA (idVariable 15, promedio de días corridos, historia completa;
    0,000% de diferencia con el CSV de datos.gob.ar en 24 meses); se sacaron `titular:` fijo y
    `ocultar_variacion`.
    - `90.1_BMT_0_0_20` (datos.gob.ar, "millones de $") en `data/series_largo.csv`: 41.399.340 en
      may-2026 y 18.185.780 en jun-2026 (−56% en un mes); después 21.504.650 (jul) y 22.520.769 (ago).
      Ningún movimiento parecido en el resto de la serie. Con el titular por reglas salía "La base
      monetaria de agosto está 48,1% por debajo de la de un año antes": parece un corte de la fuente
      (cambio de definición o de escala), no un dato económico.
    - Mientras tanto la card lleva `titular: "Base monetaria"` en el yaml (decisión de Pedro: no se
      publica un titular sobre un posible corte de la fuente). Al resolverlo, sacar ese override.
    - Pendiente: revisar la metadata y las notas de la serie en datos.gob.ar y en el BCRA y decidir con
      Pedro cómo empalmar.
    - **Causa encontrada el 08/11/2026** (diagnóstico del #21): no es un corte de la fuente. La API de
      datos.gob.ar devuelve valores erróneos desde jun-2026 (18.185.776 en jun), mientras que el CSV de
      distribución del mismo dataset (90.1) y el BCRA (API v4, idVariable 15, promedio mensual) dan 43,3
      billones en jun, 45,6 en jul y 46,4 en ago, sin ningún salto. Lo mismo pasa con el circulante
      (`90.1_BMCMP_0_0_44`, componente de M1). Se resuelve junto con el #23.

15. **Tramo sin datos más angosto que el tiempo real en series frenadas** — anotado el 07/11/2026.
    - El sombreado del Bloque C (D9) se dibuja sobre el eje de categorías de Chart.js: cada dato ocupa
      el mismo ancho aunque las fechas no estén equiespaciadas. En el TCR multilateral (frenado el
      28/01/2026) los ~9 meses sin datos se ven más angostos que 9 meses de historia, porque la serie
      vieja tiene más puntos por mes que los días hábiles que se agregan hasta hoy.
    - No se arregla en el Bloque C (decisión de Pedro). Opción a evaluar: eje de tiempo real
      (`type: 'time'`, necesita un adaptador de fechas para Chart.js) o rellenar con la misma
      frecuencia que la historia.

16. **Dólar futuro: contrato "nov/2026" duplicado con valor 3** — anotado el 07/11/2026 (visto en el
    Bloque C, no arreglado).
    - En la curva DDF del MAE (`_ddf_chart` en run.py) aparecen dos contratos rotulados "nov/2026": uno
      en 1.570 y otro con último = 3 (barra casi invisible; el pie de la card dice "mín. 3").
    - Pendiente: ver qué ticker es (posible contrato de otro tipo o sin operaciones con un precio no
      comparable) y filtrarlo con un criterio documentado, con un test.

17. **Convertir los depósitos en moneda extranjera (idVariable 104) a USD** — anotado el 07/11/2026.
    - El BCRA publica la 104 "En millones de ARS", moneda extranjera: dólares VALUADOS EN PESOS. Desde el
      Bloque C se rotula así ("millones de $ (dólares valuados en pesos)"), sin convertir.
    - ⚠️ DECISIÓN PEDRO: con qué tipo de cambio convertir (ej. A3500/oficial del mismo día, que es el
      que usa el BCRA para valuar). Recién con eso se agrega la conversión, documentada en la nota.

18. **Escala de la metadata del BCRA en depósitos (981, 209, 229)** — anotado el 07/11/2026.
    - La API de Estadísticas Monetarias v4.0 dice "En miles de ARS" para 981 (total privado), 209 y 229
      (sector público, pesos y moneda extranjera), y "En millones de ARS" para 100 y 104.
    - Al 31/08/2026: 100 (126.016.828) + 104 (61.719.152) = 187.735.980 ≈ 981 (187.655.774, 0,04% de
      diferencia): la 981 está en la MISMA escala que 100/104 (millones), no en miles.
    - La 229 (3.050.621 al 31/08) no se pudo confirmar con una suma así: si fueran millones de ARS serían
      ~USD 2.000 M (plausible); si fueran miles, ~USD 2 M. Su `unidad` en el yaml (componente interno,
      "millones de USD") sigue sin corregir hasta confirmarlo.
    - Desde el Bloque C las cards de depósitos en pesos con `factor: 0.001` se rotulan "miles de millones
      de $" (coherente con millones × 0,001). Pendiente: confirmar con el BCRA y, si corresponde, revisar
      el factor de la 209.

19. **Compras netas de divisas por contraparte: escala del valor de la card (−2.372.091 millones de $)**
    — anotado el 07/11/2026 (visto en la propuesta del Bloque E, no arreglado).
    - La card resume con la última serie del overlay (Tesoro Nacional, 331.1_COMPRAS_NENAL__39): may-26 =
      −2.372.091. La metadata oficial de datos.gob.ar (consultada el 07/11/2026) dice "En millones de
      pesos", dataset "Factores de explicación de Base Monetaria. Datos mensuales" (efecto en pesos de las
      compras, no dólares). Las tres series son coherentes entre sí: total = privado + Tesoro (ene-26:
      1.676.371 − 4.030.000 = −2.353.629).
    - Lo que hay que revisar: (a) el máximo histórico de la serie del Tesoro es 395.901 y en 2026 aparecen
      −4.030.000 y −2.372.091 (10 veces más): ¿es la inflación y el tipo de cambio, o la fuente cambió de
      escala? Comparar con la planilla de factores de explicación del BCRA; (b) dic-25 = 0 en las tres
      series y abr-26 = 0 en el Tesoro: ¿cero real o dato faltante?; (c) cómo mostrarlo en la card: un
      número de 7 cifras en millones de pesos no se lee (opciones: billones de $, o convertir a USD con el
      tipo de cambio del mes, documentado en la nota).
    - Nada se cambia hasta revisarlo (regla dura #4: no corregir a ojo).

20. **Muro de vencimientos (AL30/GD30/GD35): desaparece cuando el MAE no devuelve bonos** — anotado el
    07/11/2026 (visto en E2, no arreglado).
    - El 07/11/2026 `fetch_mae_flujofondos("H")` (endpoint `emisiones/flujofondoscotiz/H`, no documentado)
      devuelve 0 bonos: `run._muro_vencimientos()` da None y la card no se genera. Ya falta en el sitio
      publicado desde la corrida de la mañana del 07/11 (commit e2f1202). Revisar si el endpoint cambió o si
      es algo del fin de semana; el ítem sigue asignado a Mercados en `temas:` y vuelve solo si el MAE responde.
    - Criterio general (decisión de Pedro): una card NO debería desaparecer cuando la fuente devuelve 0 filas.
      Tiene que quedar visible, con un aviso del tipo "la fuente no devolvió datos hoy" (mismo criterio que
      la línea de frescura del B2), para el muro y para cualquier otro extra o serie que hoy se saltea en
      silencio. No se resuelve en E2.
    - Agregado el 08/11/2026: las TIR de AL30, GD30 y GD35 (`fuente: mae_bono`) salen del MISMO endpoint
      (`flujofondoscotiz/H`) y también vienen vacías ("Indicador sin datos" en las corridas del 06/11 y del
      08/11; GD35 trajo dato el 06/11). Últimos datos en el CSV: AL30 y GD30 05/11, GD35 06/11. Probable misma
      causa que el muro, sin verificar. Arrastra al spread GD30 vs. UST10Y (#8).
    - **CERRADO el 08/11/2026 (bloque MAE):** el muro sale de `emisiones/flujofondos/{ticker}` (flujo de fondos
      de cada bono, no depende de que cotice; responde también fines de semana). Criterio general implementado
      para los extras de run.py (muro y dólar futuro, `run._extras_con_respaldo`): el último dato válido se
      guarda en `data/extras_ultimo.json`; si la fuente viene vacía la card se arma con ese dato, el sello marca
      su antigüedad (frecuencia diaria), lleva el aviso "La fuente no devolvió datos en esta corrida" y sale la
      alerta a Pedro (primer día y semanal, `data/mercados_estado.json`). Si nunca hubo dato, no hay card pero sí
      alerta. Las series del yaml ya mantenían su último dato (sin cambios). Las TIR siguen en el #28.

21. **Series de datos.gob.ar que devuelven 0 filas en cada corrida** — anotado el 08/11/2026 (revisión de
    los avisos "Indicador sin datos" de E4, no arreglado).
    - Aparecen en las corridas de producción del 06/11 y del 08/11 y en las locales de E1 a E4. El histórico
      no se pierde (merge idempotente), pero no entra ningún dato nuevo. Último dato en el CSV:
      - `90.1_AMTM2_0_0_31` M2 (agregado total): ago-2026.
      - `324.1_H_HOTELES_ADO__60` y `324.1_K_ACT_INMOADO__57` (puestos asalariados registrados de la Cuenta de
        Generación del Ingreso del INDEC, no SIPA; Hoteles y restaurantes /
        Inmobiliarias y empresariales, componentes del gráfico de actividad y empleo por sector): ene-2026.
      - Comercio exterior desagregado: `74.3_IEMOI_0_M_46` MOI, `74.3_IECE_0_M_35` Combustibles y energía,
        `74.3_IICL_0_M_42` Combustibles y lubricantes, `74.3_IIPABC_0_M_50` Piezas y accesorios para bienes de
        capital, y el balance comercial energético que se calcula con dos de ellas: ago-2026. No es lo mismo
        que el #4 (atraso de septiembre en los totales): acá la fuente no devuelve nada.
      - `379.9_RESULTADO_017__31_73` Resultado primario del SPN y su acumulado de 12 meses: ago-2026.
    - Causa no verificada (¿id cambiado o serie discontinuada en datos.gob.ar, falla del pedido en lote?).
      A hacer: diagnosticar id por id contra la ficha del dataset (regla dura #1).
    - **Diagnóstico del 08/11/2026:** los ids no cambiaron y las series no están discontinuadas. La API de
      datos.gob.ar tiene la metadata al día pero devuelve 0 filas (o historia cortada: `74.3_IICL_0_M_42`
      sólo 1992-01 → 2003-06), mientras que los CSV de distribución del mismo catálogo (regenerados el
      07/11/2026) traen un período más (sep-2026; 2T-2026 en el 324). Decisión de Pedro: fallback al CSV de
      distribución (salvo el RIPTE, cuyo CSV trae agosto con el valor de junio; ver el #1), M2 al BCRA
      (idVariable 109) y RIPTE desde la página de la Secretaría de Trabajo. En curso: el fallback al CSV
      está implementado (`fuentes_datos_gob.py`), con 4 disparadores (0 filas, historia cortada, últimos 12
      períodos con más de 1% de diferencia, CSV con períodos más nuevos), guarda anti-RIPTE (último período
      del CSV que repite exactamente el anterior: no se usa y alerta) y coherencia por card. M2 ya sale del
      BCRA (idVariable 109, promedio de días corridos: 0,001% de diferencia promedio con datos.gob.ar en 24
      meses). El RIPTE pasó a la Secretaría de Trabajo el 08/11/2026 (ver el #1).
    - Visto en la corrida local del 08/11/2026 la guarda cortó 2T-2026 de la tasa de
      informalidad (`52.2_ASDJ_0_0_37`, 0,379 igual que el 1T), aunque la API también publica 2T-2026 con
      0,379. Como la API está cortada (91 de 93 filas) la serie igual sale del CSV, sin ese trimestre (el
      punto guardado se conserva por el merge). **Ajustado el 08/11/2026** (decisión de Pedro): la guarda no
      salta si la API publica ese mismo período con el mismo valor. Alertas sólo por 0 filas, historia
      cortada, diferencia > tolerancia y la guarda (14 series en la corrida local del 08/11; el disparador 4 y
      la coherencia no alertan). Además, un id que entra al CSV por coherencia no pasa por la guarda (hoy:
      adelantos transitorios, ceros repetidos legítimos).

22. **Cauciones (MAE) vacías en la corrida** — anotado el 08/11/2026 (no arreglado).
    - Caución en pesos y en dólares (1 día) (`mae_resumen`, tipo `CAU`): "Indicador sin datos" en las
      corridas del 06/11 (viernes, de tarde) y del 08/11; últimos datos 06/11 (pesos) y 05/11 (dólares). Es
      un snapshot sin historia: un día vacío es un día perdido. Ver también el #13 (valor 0,00 guardado
      como dato). Causa no verificada (¿hora de la corrida respecto de la operatoria, cambio del ticker?).
    - **CERRADO el 08/11/2026 (bloque MAE):** causa verificada con los logs de Actions y el histórico del MAE: (1)
      los viernes y antes de feriados el "1 día" no es el ticker `001` sino `003`/`004`/`006`, así que nunca hubo
      viernes guardados; (2) las corridas de las 06:30 son antes de la rueda; (3) la fecha salía de la UTC del
      runner (la corrida de las 22:53 del 04/11 guardó el cierre del 04/11 como 05/11). Resuelto con el histórico
      de cierre (ver #13).

23. **Agregados monetarios (M1, M2, M3) mezclan bases de rebase** — anotado el 08/11/2026 (diagnóstico
    del #21; prioridad 1 por decisión de Pedro: es un dato falso publicado).
    - `rebase_100` rebasa sobre el primer valor que devuelve la API y el merge pisa sólo las fechas que
      vinieron. La API devolvió historia parcial o valores erróneos en distintas corridas (hoy: M2 0 filas,
      M3 sólo desde 2014-04, depósitos en cuenta corriente `90.1_DCCT_0_0_32` sólo hasta 2012-02,
      circulante con valores erróneos desde jun-2026), así que el histórico guardado quedó con varias
      bases mezcladas: M2 alterna entre dos bases (±2,7%) en 116 tramos, incluso dentro de 2026; M3 salta
      ×8,4 en abr-2014; M1 cae ~40% en jun-2026.
    - La card llevaba `aviso:` + `ocultar_variacion: true` mientras tanto; se sacaron el 08/11/2026 al quedar
      sólo M2 y M3 (ver abajo).
    - Hecho el 08/11/2026: M1/M2/M3 se guardan en niveles (millones de $) y el overlay los rebasa al dibujar
      (`rebase_vista: true`, base ene-2026 = 100); las 816 filas rebasadas se borraron con
      `reconstruir_series.py` (backup fuera del repo) y se reescriben desde datos.gob.ar (CSV de
      distribución: la API de los cuatro ids del dataset 90 está vacía, cortada o con valores erróneos).
    - M2 pasó al BCRA (idVariable 109, "M2 ", Series.xlsm, saldos diarios en millones de $; promedio de días
      corridos). M3 sigue en datos.gob.ar (vía CSV de distribución).
    - **Sigue abierto por el M1** (decisión de Pedro del 08/11/2026: se saca del overlay, que pasa a llamarse
      "Agregados monetarios (M2, M3)"; el M1 queda definido en el yaml, sin mostrarse, y no se implementa
      nada nuevo hasta decidir la definición). Diagnóstico acotado contra el M1 de datos.gob.ar
      (`174.1_AGADOS_M1_0_0_28`, hasta abr-2026), 24 meses (may-2024 a abr-2026), diferencia % de cada
      armado contra ese M1 (promedio / promedio del valor absoluto / máximo del valor absoluto):

      | Armado | Fuente | Prom. | Prom. abs. | Máx. abs. |
      |---|---|---|---|---|
      | circulante + cta. cte. "total" (definición actual) | CSV dataset 90 | −40,17 | 40,17 | 48,00 |
      | circulante + cta. cte. privada | CSV dataset 90 | −22,62 | 22,62 | 31,71 |
      | circulante + cta. cte. pública | CSV dataset 90 | −3,12 | 3,87 | 13,70 |
      | circulante + cta. cte. total, promedio | BCRA (17 + series.xlsm) | −9,12 | 9,12 | 18,48 |
      | circulante + cta. cte. privada, promedio | BCRA | −26,63 | 26,63 | 34,82 |
      | circulante + cta. cte. pública, promedio | BCRA | −42,16 | 42,16 | 49,04 |
      | circulante + cta. cte. privada, fin de mes | BCRA | −57,96 | 57,96 | 62,98 |
      | circulante + cta. cte. total, fin de mes | BCRA | −57,51 | 57,51 | 72,65 |

      Ningún armado reproduce el M1 publicado. Llama la atención que en el CSV del dataset 90 la columna de
      cuenta corriente "total" sea menor que la "privada" (hipótesis no verificada: columnas rotuladas al
      revés). Nada se cambió por esta tabla.

24. **Spread soberano GD30 vs. UST10Y: el sello dice "sin calendario oficial"** — anotado el 08/11/2026.
    - Es una serie diaria (snapshot del MAE), así que debería llevar el "próximo DD/MM (estimado)" de las
      diarias del B2. Hoy: "sep-26 · próximo: sin calendario oficial". Causa no verificada (¿se clasifica
      la frecuencia por la cantidad de puntos, que es chica porque la serie es un snapshot?).
    - **CERRADO el 08/11/2026 (bloque MAE):** con un solo punto `frescura.frecuencia()` devolvía "mensual" por
      defecto, y el rezago se contaba desde el 30/09 (sin franja ⏸). Ahora la frecuencia sale del campo
      `frecuencia:` del yaml, si no de la fuente (`frescura.FUENTES_DIARIAS`/`CALCULOS_DIARIOS`: snapshots del
      MAE, Tesoro, BYMA, dólar, spread, brecha) y sólo si no, de las fechas (con 2 puntos o más; con uno, se
      muestra la fecha y no se adivina). Las diarias pasan a franja ⏸ a los 10 días hábiles sin datos (piso
      `rezago_normal_dias`); las demás frecuencias no cambian. El spread hoy: "⏸ 01/09/26 · sin datos nuevos".

25. **Series huérfanas en el histórico** — anotado el 08/11/2026 (limpieza aparte, no tocadas).
    - Filas de `data/series_largo.csv` (y columnas de `series_ancho.csv`) con un nombre que ya no está en
      indicadores.yaml (indicadores renombrados o sacados). No se muestran ni se actualizan; sólo ocupan lugar.
      Las del RIPTE con el nombre viejo ("Capacidad de compra del salario (RIPTE / CBT)", 124 filas) se
      borraron el 08/11/2026 con `reconstruir_series.py` (backup en el Escritorio, `backup_datos/`).
    - Quedan 13 (nombre: filas, primer y último mes):

      | Serie | Filas | Desde | Hasta |
      |---|---|---|---|
      | EMAE No urbano (agro, minería y pesca) | 265 | 2004-06 | 2026-06 |
      | EMAE Urbano | 265 | 2004-06 | 2026-06 |
      | Exportaciones a Brasil | 269 | 2004-01 | 2026-05 |
      | Exportaciones a Chile | 269 | 2004-01 | 2026-05 |
      | Exportaciones a China | 269 | 2004-01 | 2026-05 |
      | Exportaciones a Estados Unidos | 269 | 2004-01 | 2026-05 |
      | Exportaciones a India | 269 | 2004-01 | 2026-05 |
      | IPC Nacional - Nivel general | 115 | 2016-12 | 2026-06 |
      | IPI manufacturero (industria) | 126 | 2016-01 | 2026-06 |
      | Inflación esperada (REM, próximo mes) | 121 | 2016-07 | 2026-07 |
      | Tasa BADLAR (mayorista) | 8.205 | 2004-01 | 2026-06 |
      | Tasa de política monetaria | 3.495 | 2015-12 | 2025-07 |
      | Venta de vehículos 0km al mercado interno | 270 | 2004-01 | 2026-06 |

    - A hacer: decidir serie por serie si se borra (con `reconstruir_series.py` y backup) o si se conserva
      como archivo (ej. EMAE Urbano/No urbano o IPI, que salieron del dashboard a pedido de Pedro).

26. **Notas de series `solo_componente` que no se publican** — anotado el 08/11/2026 (sólo diagnóstico, no
    arreglado).
    - El sitio publica sólo la `nota` de la card (`dashboard.generar` usa `ind.get("nota")` de la card que
      dibuja); la `nota` propia de una serie `solo_componente` no aparece en ninguna página. Hoy tienen nota
      propia que no se ve:
      - "Compras netas de divisas del BCRA" (card: Balance cambiario).
      - "Salario real (deflactado por IPC)" (card: Salario real y capacidad de compra).
      - "RIPTE medido en canastas básicas (CBT, GBA)" (misma card; lo esencial se copió a la nota de la card el
        08/11/2026).
      - "Resultado primario acumulado 12 meses" (card: ¿El mercado premia la mejora fiscal?).
      - "Depósitos: sector privado en dólares" y "Depósitos: sector público en dólares" (card: Depósitos en
        moneda extranjera).
      - "TIR AL30 (USD)", "TIR GD30 (USD)", "TIR GD35 (USD)" (card: Curva de rendimientos).
      - "M1 (circulante + cta. cte.)" y "UST 10Y (Treasury)": sin card que las dibuje (el M1 salió del overlay,
        #23; el UST 10Y sólo entra en el cálculo del spread soberano).
    - La nota "Datos vía CSV de distribución de datos.gob.ar" sí llega: `_ids_csv` junta los ids de la card y
      de los indicadores que referencia (en la corrida local del 08/11/2026 apareció en 17 páginas de serie,
      entre ellas Actividad y empleo por sector, Préstamos por tipo de deudor y Agregados monetarios). Sólo se
      pierde en series sin card: M1 (90.1_BMCMP_0_0_44, 90.1_DCCT_0_0_32) y Adelantos transitorios / Transferencia
      de utilidades nominales (331.1_OTRAS_OPERIOS__58, 331.1_OTRAS_OPERDES__39), cuyos datos tampoco se ven; las
      versiones en pesos constantes, que sí se dibujan, llevan la nota.
    - A hacer: decidir si la nota de una componente se suma a la de su card (y cómo, sin repetir) o si se
      revisan a mano las notas de esas cards.

27. **Cuatro mecanismos de alerta con un mail de tope cada uno** (eran tres; Mercados se sumó el 08/11/2026) — anotado el 08/11/2026 (ver también el #2 y
    el #11).
    - Hoy cada corrida puede mandar a Pedro hasta tres mails: INDEC (`fuentes_indec.cerrar_corrida`), fallback
      al CSV de datos.gob.ar (`fuentes_datos_gob.cerrar_corrida`) y RIPTE de la Secretaría de Trabajo
      (`fuentes_trabajo.cerrar_corrida`), Mercados (`fuentes_mercados.cerrar_corrida`: UST y extras vacíos,
      desde el 08/11/2026), más los del calendario (`verificar_calendario.py`) y los de frescura
      (`agenda.avisar_atrasados`), cada uno con su propio estado y su tope de 1 mail por corrida.
    - A evaluar: un solo mail por corrida con secciones, que junte los avisos que tocan ese día (cada
      mecanismo conservaría su estado y su frecuencia; sólo cambiaría el envío).
    - La alerta del fallback al CSV de datos.gob.ar incluye componentes de series que no se muestran (en la
      del 08/11/2026: 90.1_BMCMP_0_0_44 y 90.1_DCCT_0_0_32, componentes del M1, que salió del gráfico, #23).
      Evaluar excluirlas al unificar las alertas.

28. **TIR de AL30/GD30/GD35 (MAE) en revisión** — anotado el 08/11/2026 (bloque MAE, no implementado).
    - Las tres TIR, la curva de rendimientos y el spread GD30 vs. UST10Y quedan como dato en revisión
      (`titular` = nombre, `ocultar_variacion: true`, `aviso: "Dato en revisión"`). Se siguen bajando de
      `flujofondoscotiz/H` (snapshot, fechado con la fecha de Argentina; ese endpoint no informa fecha), sin
      puntos de fines de semana ni feriados (30 borrados el 08/11/2026, backup en
      Desktop\backup_datos\mae_no_habiles_2026-11-08.csv). Ojo: la corrida de las 06:30 puede seguir
      tomando el estado del día hábil anterior con la fecha de hoy (la fecha del snapshot no la informa el MAE).
    - Diagnóstico (08/11/2026): cierres diarios de BYMA (`chart/historical-series/history`, símbolo con el plazo:
      "AL30D 24HS", "GD30D 24HS", "GD35D 24HS"; sin el sufijo da `no_data`) + flujo de fondos del MAE
      (`emisiones/flujofondos/{ticker}`, `cashFlow` por 100 de VN original), liquidación T+1 hábil, TIR efectiva
      anual ACT/365. Contra las TIR guardadas del MAE en los mismos días: AL30 mediana +1,24 pp y hasta +4,15 pp
      (la del MAE salta 1,25 pp por día en la mediana; la de BYMA 0,21 pp); GD30 mediana −0,08 pp, hasta 2,66 pp;
      GD35 mediana +0,75 pp, hasta 1,48 pp. En muchos días coinciden a la centésima, así que la fórmula es la
      misma: la diferencia es el precio (el MAE toma la última operación propia, poco líquida y a veces en otra
      moneda o plazo). Tabla completa en el informe de la ronda.
    - Otra fecha mal puesta, no borrada (es día hábil): TIR GD30 del 05/11/2026 = la corrida de las 22:53 del
      04/11 (valor del 04/11).
    - A decidir: pasar las TIR a precio de cierre de BYMA + flujo de fondos (con `nota`), y después el spread
      contra el Treasury interpolado a la duration (#8).

29. **Filtro de noticias del mail diario** — anotado el 08/11/2026 (los ejemplos marcados por Pedro para la
    próxima ronda están en CLAUDE.md, "Filtro de noticias — ejemplos marcados por Pedro").
    - Zona horaria (visto en el bloque MAE, no tocado por decisión de Pedro): en `enviar_mail._recolectar`,
      `published_parsed` de los feeds viene en UTC y se compara contra `_limite()`, que está en hora argentina
      sin zona. Pueden entrar notas hasta 3 horas más viejas que la ventana (1 día; 3 los lunes; 7 en
      internacional). Arreglo posible: pasar `published_parsed` a hora argentina antes de comparar, con un
      test en tests/test_noticias.py.

## Bloques futuros (después del Bloque E; no implementar todavía)

F1. **Agenda ampliada en el calendario (internacional + BCRA)** — anotado el 08/11/2026.
    - Internacional: reuniones de política monetaria de la FED (FOMC), el BCE, el Banco de Japón y el Banco
      de Inglaterra, y datos de EE. UU. del BLS (informe de empleo, CPI).
    - BCRA: IPOM y fecha de publicación del REM (se relaciona con el #10). Verificar si el BCRA publica sus
      fechas por adelantado en una página oficial; si no, "sin fecha oficial", nunca estimada (como mucho,
      la fecha del último publicado).
    - ⚠️ DECISIÓN PEDRO: cambia el alcance del B1 (hoy sólo publicaciones que alimentan el dashboard). Va
      como sección o color aparte, sin mezclarse con las publicaciones del monitor.
    - Reglas: cada fecha con su fuente oficial y link (regla dura #1); chequeo periódico de cambios, como
      `verificar_calendario.py` (las fechas del BLS se movieron en 2025 por el cierre del gobierno de
      EE. UU.); color secundario neutro, sin juicio.
    - A definir en el diseño: si entra en el mail, si las fechas se cargan desde un archivo anual verificado
      o se descargan, y cómo se avisa si una cambia.

## Contenido (textos del sitio, no datos)

C1. **Descripciones de las páginas de serie (`descripcion:` del yaml)** — anotado el 08/11/2026 (E4,
    decisión de Pedro: opción A).
    - Hoy ninguna serie tiene `descripcion:`; la página de serie muestra el `subtitulo` cuando existe (9
      series, todos textos redactados en rondas anteriores, ninguno de metadata oficial) y nada en las 50
      restantes. "Actividad y empleo por sector" quedó sin descripción a propósito: su advertencia sobre la fuente del empleo
      pasó a la nota.
    - A hacer: redactar las descripciones (1-2 líneas por serie), indicando la fuente de cada texto
      (metadata oficial de datos.gob.ar/INDEC/BCRA o redacción propia). Las redactadas las revisa Pedro
      antes de publicar.
    - Revisar también los nombres de las cards. Caso anotado el 08/11/2026: "Salario real y capacidad de
      compra" contradice el descargo de la Secretaría de Trabajo (el RIPTE de su eje derecho es un indicador
      previsional, no una medida de la evolución de los salarios). Cambiarle el nombre cambia el slug de
      `/serie/` (hay que redirigir el viejo, como financiera.html) y los bloques `temas:` y `home:` del yaml.

C2. **Negativos en los combos de dos barras (diseño)** — anotado el 08/11/2026 (visto en E5, no tocado).
    - En `vista: combo_barras_linea` con dos barras (hoy: Superávit gemelos, Resultado primario vs. intereses de
      deuda) cada serie se pinta siempre con su tono de la rampa (`principal_3` y `principal_contexto`), también
      cuando el valor es negativo: no se cumple "arena = sólo valores negativos" (D2 del Bloque C).
    - Problema de fondo: si los negativos de las dos series van en arena, se pierde qué barra es de qué serie.
      Necesita un diseño propio (por ejemplo, arena en dos tonos, borde o textura por serie); no se resuelve
      cambiando el color.

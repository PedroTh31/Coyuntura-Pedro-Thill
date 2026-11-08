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

2. **Series con fallback vacío en la alerta de autenticación del INDEC** — anotado el 07/11/2026.
   - Hoy: `11.3_TAC_2004_M_60`, `11.3_VMATC_2004_M_12`, `146.3_IRECREANAL_DICI_M_31`,
     `146.3_IRESTAUNAL_DICI_M_33` (su fallback de datos.gob.ar devuelve 0 filas).
   - Problema: si la API del INDEC falla, son las únicas series que se quedan sin datos, pero no
     aparecen en la lista de "series afectadas" de la alerta de autenticación
     (`ResolverIndec.terminar(ok=False)` no las registra porque terminan vacías). El aviso
     semanal de "fallback vacío" sí las nombra, por separado.
   - A hacer: incluirlas en la alerta de autenticación.

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

9. **La pestaña financiera no tiene línea de frescura** — anotado el 07/11/2026.
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

14. **Base monetaria: la serie cae a la mitad en jun-2026** — anotado el 07/11/2026 (visto en el Bloque
    C, no arreglado).
    - `90.1_BMT_0_0_20` (datos.gob.ar, "millones de $") en `data/series_largo.csv`: 41.399.340 en
      may-2026 y 18.185.780 en jun-2026 (−56% en un mes); después 21.504.650 (jul) y 22.520.769 (ago).
      Ningún movimiento parecido en el resto de la serie. Con el titular por reglas salía "La base
      monetaria de agosto está 48,1% por debajo de la de un año antes": parece un corte de la fuente
      (cambio de definición o de escala), no un dato económico.
    - Mientras tanto la card lleva `titular: "Base monetaria"` en el yaml (decisión de Pedro: no se
      publica un titular sobre un posible corte de la fuente). Al resolverlo, sacar ese override.
    - Pendiente: revisar la metadata y las notas de la serie en datos.gob.ar y en el BCRA y decidir con
      Pedro cómo empalmar.

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

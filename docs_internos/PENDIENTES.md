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

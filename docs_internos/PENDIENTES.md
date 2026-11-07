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

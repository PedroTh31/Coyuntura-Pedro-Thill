# Disparo externo de los workflows (cron-job.org → GitHub Actions)

**Por qué:** el `schedule` de GitHub Actions es *best effort*. Entre el 08/10 y el 04/11/2026
el mail programado para las 08:00 arrancó todos los días con **4 a 9,5 horas de demora**. Por
eso ahora los dos workflows se disparan desde afuera, a la hora exacta, con la API
`workflow_dispatch`. El `schedule` de GitHub queda sólo como respaldo.

| Workflow | Hora (AR) | Días | Respaldo de GitHub |
|---|---|---|---|
| `coyuntura.yml` (datos) | **07:00** | todos | 09:53 UTC |
| `email_diario.yml` (mail) | **08:00** | lun a vie | 11:47 UTC (08:47 AR) |

> ⚠️ **El token (PAT) NO va al repo.** Ni en un archivo, ni en un commit, ni en un secret de
> GitHub. Vive sólo en el job de cron-job.org (y en tu gestor de contraseñas).

---

## 1. Crear el token (PAT fine-grained)

1. GitHub → foto de perfil → **Settings** → **Developer settings** → **Personal access
   tokens** → **Fine-grained tokens** → **Generate new token**.
2. **Token name:** `cron-job-coyuntura`.
3. **Expiration:** elegí una fecha concreta (por ejemplo, 1 año). Anotala abajo, en
   [Vencimiento](#vencimiento-del-token).
4. **Resource owner:** `PedroTh31`.
5. **Repository access:** *Only select repositories* → `Coyuntura-Pedro-Thill`. Ningún otro.
6. **Permissions** → *Repository permissions* → **Actions: Read and write**. Nada más
   (*Metadata: Read-only* se agrega sola y es obligatoria).
7. **Generate token** y copialo en ese momento: GitHub no lo vuelve a mostrar.

## 2. Probar el token antes de configurar nada

Desde una terminal (Git Bash o PowerShell con `curl.exe`), reemplazando `<PAT>`:

```bash
curl -i -X POST \
  -H "Authorization: Bearer <PAT>" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/PedroTh31/Coyuntura-Pedro-Thill/actions/workflows/email_diario.yml/dispatches \
  -d '{"ref":"main"}'
```

- **Esperado: `HTTP/2 204`**, sin cuerpo. En la pestaña *Actions* del repo aparece una
  corrida nueva del mail con evento `workflow_dispatch`.
  - Si el mail de hoy ya salió, esa corrida termina en verde **sin mandar** (guardia
    anti-duplicado). Es lo esperado.
- `401`: el token está mal copiado o venció.
- `403` o `404`: le falta el permiso *Actions: Read and write*, o no tiene acceso a este repo.
- `422`: el body o el `ref` están mal.

## 3. Crear los dos jobs en cron-job.org

1. Creá una cuenta gratis en https://cron-job.org.
2. En la configuración de la cuenta, poné la zona horaria **`America/Argentina/Buenos_Aires`**.
   Si el job tiene su propio campo de zona horaria, ponela también ahí.
3. Creá un cronjob nuevo con estos datos:

**Job 1: Datos 07:00**
- **URL:**
  `https://api.github.com/repos/PedroTh31/Coyuntura-Pedro-Thill/actions/workflows/coyuntura.yml/dispatches`
- **Horario:** todos los días, 07:00.
- **Método:** `POST`.
- **Headers:**
  - `Authorization: Bearer <PAT>`
  - `Accept: application/vnd.github+json`
  - `X-GitHub-Api-Version: 2022-11-28`
- **Body:** `{"ref":"main"}`

**Job 2: Mail 08:00**
- **URL:**
  `https://api.github.com/repos/PedroTh31/Coyuntura-Pedro-Thill/actions/workflows/email_diario.yml/dispatches`
- **Horario:** lunes a viernes, 08:00.
- **Método, headers y body:** iguales al Job 1.

4. Activá las notificaciones por mail de cron-job.org **cuando el job falle**. Así te enterás
   si el token vence o GitHub responde algo distinto de `204`.
5. Con el botón de ejecución de prueba de cron-job.org (si está disponible), verificá que
   responda `204` y que aparezca la corrida en *Actions*.

## 4. Qué pasa cada día

1. **07:00** cron-job.org dispara `coyuntura.yml`. Corre `run.py` (unos 6 minutos), commitea
   `data/` y `docs/`, y escribe `data/ultima_corrida.json` con la fecha, la hora y el estado
   por fuente.
2. **08:00** cron-job.org dispara `email_diario.yml`. Si ya se mandó el mail de hoy, sale sin
   mandar. Si no:
   - si `ultima_corrida.json` es de hoy, manda con los datos commiteados (el job tarda menos
     de 1 minuto);
   - si no es de hoy, corre `run.py` como **fallback** (unos 6 minutos más), deja un warning
     en el log y manda el mail con la línea "Datos actualizados al momento del envío".
3. Después de mandar, commitea `data/mail_enviado.json`. Cualquier disparo posterior del
   mismo día (el respaldo de las 08:47, uno manual) **no reenvía**.

Cada corrida deja en el log qué la disparó (`schedule` o `workflow_dispatch`) y la hora real
de envío.

## 5. Renovar el token

Cuando se acerque el vencimiento:

1. Andá a GitHub → *Fine-grained tokens* → `cron-job-coyuntura` → **Regenerate token**, o
   creá uno nuevo con los mismos permisos.
2. En cron-job.org, reemplazá el valor del header `Authorization` **en los dos jobs**.
3. Repetí la prueba del paso 2.
4. Actualizá la fecha de abajo.

### Vencimiento del token

- Token actual creado el: `____/____/______`
- **Vence el: `____/____/______`**. Ponete un recordatorio una semana antes.

Si el token vence sin que lo renueves, el mail no se corta del todo: sigue saliendo por el
respaldo de GitHub, pero con las demoras de horas de antes.

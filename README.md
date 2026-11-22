# MediBot 360 · versión Next

Plataforma de una PyME médica **ficticia** (San Francisco de Campeche) con chatbot, CRM y ERP, todo gratuito y local.

| Módulo | Qué incluye |
|---|---|
| **Recepción virtual (chatbot 3.0)** | Reglas + extracción de entidades (sin IA generativa). Entiende especialidad, especialista o preferencia («con la doctora»), fechas («mañana», «el sábado», «25/11»), rangos («después de las 11», «por la mañana»), folios y acciones («lo antes posible», «dame otra opción»). Reserva por pasos con tarjetas, fechas, horarios por especialista, resumen editable y confirmación con folio + PIN. Consulta y cancelación verificadas, solicitudes a recepción, emergencias (911) y *fallback*. |
| **CRM** | Pacientes y prospectos, embudo, fichas con historial cronológico, bandeja de solicitudes de atención humana captadas por el asistente. |
| **ERP** | Agenda semanal, citas (web, asistente y recepción), cobros y facturas simuladas, catálogo, horarios, inventario, reportes, métricas del asistente y bitácora de auditoría. |

Stack: Python 3.10+, FastAPI, Pydantic, SQLite, HTML/CSS/JavaScript nativo. Sin dependencias de pago.

## Ejecutar

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn main:app --reload
```

| Ruta | Contenido |
|---|---|
| `/` | **Consola clínica**: inicio de sesión o dashboard si ya hay sesión |
| `/sitio` | Portal público (con acceso a «Personal») |
| `/reservar` | Reservación por pasos y «Mis citas» (folio + PIN) |
| `/admin` | Redirige a `/` (compatibilidad) |
| `/docs` | Documentación de la API |

Usuarios de demostración (cambia las contraseñas con `MEDIBOT_ADMIN_PASSWORD` y `MEDIBOT_RECEPCION_PASSWORD` **antes del primer arranque**; no se muestran en la interfaz):

- `admin` / `Admin#2026demo` (acceso total)
- `recepcion` / `Recepcion#2026demo` (CRM, citas, cobros, solicitudes e inventario)

La clave que firma las sesiones se guarda en `.medibot_secret` (excluido de git) para que reiniciar el servidor no cierre las sesiones. En producción, defínela con `MEDIBOT_SECRET`.

### Datos de demostración (opcional)

```powershell
python -m scripts.seed_demo
```

Genera pacientes, citas pasadas y futuras que respetan los horarios, cobros, solicitudes a recepción y conversaciones anónimas para las métricas. Todo es ficticio.

## Consola: atajos de teclado

| Atajo | Acción |
|---|---|
| `Ctrl + K` o `/` | Paleta de comandos y búsqueda global (pacientes, folios, facturas, módulos) |
| `G` y luego una letra | Ir a un módulo: `D` resumen, `P` pacientes, `S` solicitudes, `A` agenda, `C` citas, `F` pagos, `R` reportes, `V` asistente |
| `N` | Registrar una nueva cita |
| `Esc` | Cerrar diálogos, paleta o menú móvil |

## Pruebas

```powershell
pip install -r requirements-dev.txt
python -m pytest -q tests
```

La batería cubre lenguaje natural, fechas ambiguas, cambios de intención, correcciones, disponibilidad por especialista, reservas concurrentes, validación de identidad con PIN y límite de intentos, cancelaciones, emergencias, estado manipulado, bandeja de recepción, métricas, búsqueda y exportaciones.

## Seguridad y privacidad

- **Servidor:** decide la validación (fechas, horarios, especialistas, duplicados con índice único y transacción) y revalida en cada mensaje el estado que envía el chat.
- **PIN:** consultar o cancelar exige folio y PIN de 6 dígitos guardado con hash PBKDF2. Hay límite de 5 intentos por folio y por cliente, y el mensaje de error no revela si la cita existe.
- **Personal:** contraseñas con PBKDF2, sesión firmada en cookie `HttpOnly`/`SameSite=Strict`, bloqueo por intentos y cabeceras CSP y `X-Frame-Options`.
- **Chat:** el navegador guarda solo el estado del flujo y un historial con alias, teléfono y PIN enmascarados. Las métricas usan un identificador aleatorio y frases no comprendidas sin números ni correos.
- **Seguridad médica:** el asistente no diagnostica, no receta y deriva emergencias al 911. Precios, especialistas, horarios y políticas salen de la base de datos y de `app/config.py`.
- **Simulación:** pagos y facturas son simulados. Usa solo alias y datos ficticios. Para producción faltarían HTTPS, aviso de privacidad, respaldos y evaluación legal.
- **Sin aprendizaje automático:** el asistente funciona con reglas. Las métricas sirven para que el equipo ajuste vocabulario y flujos.

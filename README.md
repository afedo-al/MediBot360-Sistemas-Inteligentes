# MediBot 360

Plataforma web para una clínica médica **ficticia** en San Francisco de Campeche que integra tres productos sobre una misma base de datos:

- **Recepción virtual (chatbot):** agenda, consulta y cancela citas conversando en lenguaje natural.
- **CRM:** pacientes, prospectos, embudo de seguimiento y bandeja de solicitudes de atención humana.
- **ERP:** agenda, cobros simulados, catálogo, horarios, inventario, reportes y auditoría.

Proyecto académico de la asignatura *Sistemas Inteligentes* (Facultad de Ingeniería, Universidad Autónoma de Campeche). Todo el contenido médico, profesional, económico y personal es ficticio.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)
![Tests](https://img.shields.io/badge/pruebas-41%20aprobadas-12936B)
![Licencia](https://img.shields.io/badge/uso-acad%C3%A9mico-3766E8)

---

## Contenido

1. [Características](#características)
2. [Arquitectura](#arquitectura)
3. [Instalación](#instalación)
4. [Uso](#uso)
5. [Chatbot](#chatbot)
6. [Seguridad y privacidad](#seguridad-y-privacidad)
7. [API](#api)
8. [Pruebas](#pruebas)
9. [Estructura del proyecto](#estructura-del-proyecto)
10. [Alcance y limitaciones](#alcance-y-limitaciones)

---

## Características

### Recepción virtual
- Comprende frases como «quiero cardiología el viernes después de las 11» o «prefiero con la doctora».
- Extrae especialidad, especialista, fecha, hora, rango horario y folio.
- Reserva por pasos con tarjetas, fechas y horarios por especialista, resumen editable y confirmación con folio y PIN.
- Permite regresar, corregir, cambiar de tema y cancelar el proceso sin cerrar la conversación.
- Deriva emergencias al 911 y **no diagnostica ni receta**.

### CRM
- Pacientes y prospectos con ficha e historial cronológico.
- Embudo: prospecto → contactado → cliente → inactivo.
- Bandeja de solicitudes captadas por el asistente.

### ERP
- Agenda semanal y citas de tres canales: sitio web, asistente y recepción.
- Cobros y facturas **simulados**, catálogo de servicios y especialistas, horarios, inventario con alertas de bajo stock.
- Reportes con gráficas, exportación a CSV y bitácora de auditoría.
- Métricas del asistente: conversión, abandono por etapa y frases no comprendidas.

### Experiencia
- Interfaz clara, responsiva y accesible (teclado, lectores de pantalla y «reducir movimiento»).
- Paleta de comandos con búsqueda global (`Ctrl + K`) y atajos de teclado.

## Arquitectura

| Capa | Tecnología |
|---|---|
| API y servidor | FastAPI, Pydantic, Uvicorn |
| Persistencia | SQLite |
| Interfaz | HTML, CSS y JavaScript nativos, sin dependencias externas |
| Pruebas | pytest, TestClient |

El asistente, la web y el panel comparten las mismas reglas de negocio (`app/services.py`): validación de fechas, disponibilidad por especialista y reserva atómica con índice único, por lo que no existen dos sistemas de reservación.

## Instalación

Requisitos: Python 3.10 o superior.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Datos de demostración opcionales (pacientes, citas, cobros y conversaciones ficticias):

```powershell
python -m scripts.seed_demo
```

## Uso

| Ruta | Contenido |
|---|---|
| `/` | Consola clínica: inicio de sesión o panel si ya hay sesión |
| `/sitio` | Portal público |
| `/reservar` | Reservación por pasos y «Mis citas» (folio + PIN) |
| `/docs` | Documentación interactiva de la API |

### Credenciales de demostración

Se crean en el primer arranque y son **solo para pruebas locales**. Cámbialas con variables de entorno antes de iniciar por primera vez.

| Usuario | Contraseña por defecto | Variable | Permisos |
|---|---|---|---|
| `admin` | `Admin#2026demo` | `MEDIBOT_ADMIN_PASSWORD` | Total |
| `recepcion` | `Recepcion#2026demo` | `MEDIBOT_RECEPCION_PASSWORD` | CRM, citas, cobros, solicitudes e inventario |

### Variables de entorno

| Variable | Descripción |
|---|---|
| `MEDIBOT_DB` | Ruta de la base SQLite (por defecto `medibot.db`) |
| `MEDIBOT_SECRET` | Clave de firma de sesiones; si no existe se genera en `.medibot_secret` |
| `MEDIBOT_ADMIN_PASSWORD` | Contraseña inicial de `admin` |
| `MEDIBOT_RECEPCION_PASSWORD` | Contraseña inicial de `recepcion` |

### Atajos de la consola

| Atajo | Acción |
|---|---|
| `Ctrl + K` o `/` | Paleta de comandos y búsqueda global |
| `G` y una letra | Ir a un módulo (`D` resumen, `P` pacientes, `S` solicitudes, `A` agenda, `C` citas, `F` pagos, `R` reportes, `V` asistente) |
| `N` | Nueva cita en recepción |
| `Esc` | Cerrar diálogo, paleta o menú |

## Chatbot

Motor basado en reglas, sin IA generativa ni servicios externos:

1. **Normalización** del texto (minúsculas, sin acentos).
2. **Extracción de entidades:** especialidad, especialista, fecha, hora, rango horario, folio y acciones. Distingue «mañana» (fecha) de «por la mañana» (periodo).
3. **Intención** por reglas priorizadas; emergencias y salud tienen prioridad.
4. **Máquina de estados** para reserva, consulta, cancelación verificada y solicitud de atención humana. El servidor revalida en cada mensaje el estado enviado por el navegador.
5. **Respuesta** con texto breve y componentes interactivos.

Precios, especialistas, horarios y políticas se consultan en la base de datos y en `app/config.py`; el asistente no los inventa.

**Métricas operativas** (sin datos clínicos): intenciones, conversión a reserva, abandono por etapa, solicitudes a recepción, consultas, cancelaciones y errores de disponibilidad. El asistente **no aprende automáticamente**: las métricas permiten ajustar vocabulario y flujos.

## Seguridad y privacidad

- **Verificación de citas:** folio y PIN de 6 dígitos, guardado con hash PBKDF2. Límite de 5 intentos por folio y por cliente. El error es el mismo exista o no la cita.
- **Personal:** contraseñas con PBKDF2, sesión firmada en cookie `HttpOnly` y `SameSite=Strict`, bloqueo por intentos y cabeceras CSP y `X-Frame-Options`.
- **Validación en el servidor:** fechas, horarios, especialistas, estados y entradas con Pydantic.
- **Privacidad del chat:** el navegador no guarda alias, teléfono ni PIN. Las métricas usan identificadores aleatorios y frases sin números ni correos.
- **Exportaciones:** CSV protegido contra inyección de fórmulas.
- **Roles:** `admin` y `recepcion`, con auditoría de acciones.

## API

La API completa está en `/docs`. Endpoints públicos principales:

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/specialties` | Especialidades, precios y especialistas |
| `GET` | `/api/slots` | Horarios libres (`detailed=true` por especialista) |
| `GET` | `/api/next-available` | Próximo horario por especialidad |
| `POST` | `/api/appointments` | Crea la cita y devuelve folio y PIN |
| `GET` | `/api/appointments/{folio}?pin=` | Consulta verificada |
| `POST` | `/api/appointments/{folio}/cancel` | Cancelación verificada |
| `POST` | `/api/chat` | Conversación con el asistente |

Los endpoints `/api/admin/*` requieren sesión.

## Pruebas

```powershell
pip install -r requirements-dev.txt
python -m pytest -q tests
```

Cubren lenguaje natural, fechas ambiguas, cambios de intención, correcciones, disponibilidad por especialista, reservas concurrentes, verificación con PIN, cancelaciones, emergencias, estado manipulado, bandeja de recepción, métricas, búsqueda y exportaciones.

## Estructura del proyecto

```
MediBot360/
├── main.py              # Rutas y API
├── app/
│   ├── chatbot.py       # Motor conversacional
│   ├── services.py      # Reglas de negocio compartidas
│   ├── db.py            # Esquema SQLite y datos iniciales
│   ├── security.py      # Hashes y firmas
│   └── config.py        # Datos institucionales de la clínica
├── templates/           # index.html, reservar.html, admin.html
├── static/
│   ├── css/style.css    # Sistema de diseño
│   └── js/              # chat, admin, reservar, home, common
├── scripts/seed_demo.py # Datos de demostración
└── tests/               # Pruebas automáticas
```

## Alcance y limitaciones

Es un prototipo académico. Los pagos y facturas son simulados y los datos son ficticios; no registres información personal ni clínica real. Un despliegue real requeriría HTTPS, aviso de privacidad, respaldos, control de acceso ampliado y evaluación de la legislación mexicana aplicable.

## Autor

Alfredo J. Cruz Miss · Sistemas Inteligentes · Universidad Autónoma de Campeche.

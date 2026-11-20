# MediBot 360

Plataforma de coordinación de servicios médicos desarrollada como proyecto académico.

## Descripción

MediBot 360 simula una empresa de servicios médicos en San Francisco de Campeche, México.
Integra una página pública, reservaciones, chatbot, CRM, ERP y dashboard administrativo.

No realiza diagnósticos médicos ni procesa pagos reales.

## Tecnologías

- Python y FastAPI
- SQLite
- Jinja2
- HTML, CSS y JavaScript
- Chart.js
- pytest y HTTPX

## Módulos

| Módulo | Qué incluye | Dónde |
|---|---|---|
| Portal público (catálogo) | Servicios con precios y profesionales, proceso de reserva, formulario de contacto | `/sitio`, `/reservar` |
| Chatbot | Reglas con 11 intenciones: servicios y precios, horarios libres y equipo (datos reales de la base), reservar, consultar y cancelar con verificación, contacto, emergencias y despedida | Widget en `/sitio` |
| CRM | Clientes con estado (prospecto, activo, inactivo), origen (sitio web, chatbot, contacto, administración), filtros, historial de interacciones y exportación CSV | `/admin/clientes` |
| ERP | Reservaciones, catálogo, horarios, pagos simulados con reembolso, inventario con movimientos, calendario, reportes y exportación CSV | `/admin/*` |
| Reportes | Ingresos, citas por especialidad, captación de clientes, intenciones del chatbot e inventario | `/admin/reportes` |

### Cómo se conectan

1. El visitante conversa con el **chatbot** o llena el **formulario de contacto**.
2. Cada conversación y cada mensaje de contacto se registran en el **CRM** (`interactions`); el formulario crea un prospecto.
3. Al reservar, el prospecto pasa a cliente activo y la cita entra al **ERP** (agenda, calendario, cobro simulado y reportes).

## Costo de las herramientas

Todo el software es gratuito y de código abierto; no se usan servicios de pago.

| Componente | Uso | Licencia |
|---|---|---|
| Python | Lenguaje del servidor | PSF (libre) |
| FastAPI + Uvicorn | API y servidor web | MIT / BSD |
| SQLite | Base de datos local | Dominio público |
| Jinja2 | Plantillas HTML | BSD |
| Chart.js | Gráficas | MIT |
| pytest + HTTPX | Pruebas automáticas | MIT / BSD |

Un despliegue en Internet sí podría generar gastos de alojamiento y dominio.

## Instalación

1. Instalar Python compatible.
2. Crear y activar un entorno virtual.
3. Instalar dependencias:

```powershell
python -m pip install -r requirements-dev.txt
```

4. Crear `.env` a partir de `.env.example`.
5. Crear el administrador:

```powershell
python create_admin.py
```

6. Iniciar el servidor:

```powershell
python -m uvicorn main:app --reload
```

## Acceso

- Sitio público: http://127.0.0.1:8000/
- Panel administrativo: http://127.0.0.1:8000/admin
- Documentación: http://127.0.0.1:8000/docs

## Pruebas

```powershell
python -m pytest tests/ -v
```

## Seguridad

- Sesiones administrativas con cookies HttpOnly.
- Contraseñas protegidas mediante PBKDF2.
- Protección de origen en operaciones administrativas.
- Límites básicos de intentos.
- Encabezados HTTP de protección del navegador.
- Transacciones SQLite en operaciones críticas.

## Alcance

Todos los datos son ficticios. El proyecto es académico y demostrativo.
No sustituye un expediente clínico, no proporciona diagnósticos y no procesa pagos reales.

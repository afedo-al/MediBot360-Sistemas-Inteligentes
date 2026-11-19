# MediBot 360

Plataforma web para coordinar servicios médicos, gestionar reservaciones y dar seguimiento a clientes desde un panel administrativo.

## Funcionalidades

- Página pública con especialidades, profesionales y disponibilidad.
- Reservación de citas con folio único.
- Validación de fechas, disponibilidad y días no permitidos.
- Panel administrativo protegido por sesión.
- CRM de clientes con búsqueda, edición, historial e interacciones.
- ERP de reservaciones con filtros por texto, estado y fecha.
- Cancelación transaccional de citas y liberación automática de horarios.
- Reprogramación de citas conservando el folio y validando la especialidad.
- Catálogo administrativo de especialidades y profesionales.
- Activación y desactivación protegida ante citas confirmadas pendientes.
- Registro de cancelaciones en el historial del CRM.
- Persistencia local con SQLite.

## Stack tecnológico

- Python 3.13+
- FastAPI
- Jinja2
- SQLite
- HTML, CSS y JavaScript vanilla
- Uvicorn

## Requisitos

- Python 3.13 o superior
- `pip`

## Instalación

```powershell
git clone https://github.com/afedo-al/MediBot360-Sistemas-Inteligentes.git
cd MediBot360
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Crea un archivo `.env` en la raíz:

```env
MEDIBOT_SESSION_SECRET=tu-clave-secreta-larga
```

## Ejecución

```powershell
python -m uvicorn main:app --reload
```

La aplicación estará disponible en:

- Sitio público: <http://127.0.0.1:8000>
- Reservaciones: <http://127.0.0.1:8000/reservar>
- Panel administrativo: <http://127.0.0.1:8000/admin>
- CRM: <http://127.0.0.1:8000/admin/clientes>
- ERP: <http://127.0.0.1:8000/admin/reservaciones>
- Catálogo: <http://127.0.0.1:8000/admin/catalogo>

## Usuario administrador

Para crear o actualizar un administrador:

```powershell
python create_admin.py
```

El script solicita las credenciales de forma interactiva. No incluyas `.env`, la base de datos ni credenciales en el repositorio.

## Estructura principal

```text
MediBot360/
├── app/                  # Base de datos, modelos y seguridad
├── database/             # SQLite local, excluida de Git
├── static/               # CSS y JavaScript del sitio
├── templates/            # Plantillas Jinja2
├── create_admin.py       # Alta de administradores
├── main.py               # Aplicación FastAPI y endpoints
├── requirements.txt      # Dependencias
└── .env                  # Configuración local, no versionada
```

## Validación

```powershell
python -m py_compile main.py
```

## Seguridad y datos

Este proyecto está preparado como aplicación académica/prototipo. Usa una clave de sesión segura en producción, protege el archivo `.env`, configura HTTPS y utiliza una base de datos administrada antes de desplegarlo públicamente.

## Licencia

Proyecto académico de MediBot 360. Añade la licencia que corresponda antes de distribuirlo públicamente.

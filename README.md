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

- Sitio público y reservaciones.
- Chatbot basado en reglas.
- CRM de clientes e interacciones.
- ERP de horarios, pagos simulados y recursos.
- Dashboard con indicadores y gráficas.

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

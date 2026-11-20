"""
MediBot 360 - Empaquetado académico.

Genera un ZIP local con el código fuente.
NO incluye .env, bases SQLite ni contraseñas.
"""

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT.parent / "MediBot360_Entrega_Academica.zip"

EXCLUDED_DIRECTORIES = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".vscode", ".idea",
    "node_modules", "dist", "build", "backups"
}
EXCLUDED_NAMES = {
    ".env", ".DS_Store", "Thumbs.db", "desktop.ini"
}
EXCLUDED_EXTENSIONS = {
    ".db", ".sqlite", ".sqlite3", ".pyc", ".pyo", ".log",
    ".bak", ".zip", ".pem", ".key", ".p12", ".pfx"
}


def allowed(relative: Path) -> bool:
    if any(part in EXCLUDED_DIRECTORIES for part in relative.parts[:-1]):
        return False

    filename = relative.name
    if filename in EXCLUDED_NAMES:
        return False
    if filename.startswith(".env"):
        return filename == ".env.example"
    if relative.suffix.lower() in EXCLUDED_EXTENSIONS:
        return False
    if filename.endswith((".db-shm", ".db-wal", ".db-journal")):
        return False
    return True


def create_package():
    if OUTPUT.exists():
        raise SystemExit(
            "Ya existe el paquete de entrega. "
            "Renómbralo o retíralo antes de repetir."
        )

    included = 0
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED) as archive:
        for source in sorted(ROOT.rglob("*")):
            if not source.is_file() or source.is_symlink():
                continue
            relative = source.relative_to(ROOT)
            if not allowed(relative):
                continue
            archive.write(
                source,
                arcname=(Path("MediBot360") / relative).as_posix()
            )
            included += 1

    with ZipFile(OUTPUT) as archive:
        names = set(archive.namelist())
        required = {
            "MediBot360/main.py",
            "MediBot360/requirements.txt",
            "MediBot360/README.md",
            "MediBot360/.env.example",
            "MediBot360/app/database.py"
        }
        if not required.issubset(names):
            OUTPUT.unlink(missing_ok=True)
            raise SystemExit(
                "Faltan archivos esenciales. "
                "El paquete fue descartado."
            )
        if archive.testzip() is not None:
            OUTPUT.unlink(missing_ok=True)
            raise SystemExit("Se detectó un error en el ZIP.")

    print()
    print("PAQUETE ACADEMICO GENERADO")
    print("-" * 40)
    print(f"Archivos incluidos: {included}")
    print(f"Ubicación: {OUTPUT}")
    print()
    print(
        "No se incluyeron bases SQLite, "
        "entornos virtuales ni archivos .env."
    )


if __name__ == "__main__":
    create_package()

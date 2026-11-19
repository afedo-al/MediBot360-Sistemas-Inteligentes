from getpass import getpass

from app.database import get_db
from app.models import initialize_database
from app.security import hash_password


def create_admin():
    print("\n================================")
    print("       MEDIBOT 360")
    print("   CREAR ADMINISTRADOR")
    print("================================\n")

    username = input("Nombre de usuario: ").strip().lower()
    if len(username) < 3:
        print("El usuario debe tener al menos 3 caracteres.")
        return

    password = getpass("Contraseña: ")
    if len(password) < 12:
        print("La contraseña debe tener al menos 12 caracteres.")
        return

    confirmation = getpass("Confirma la contraseña: ")
    if password != confirmation:
        print("Las contraseñas no coinciden.")
        return

    password_hash = hash_password(password)
    initialize_database()

    with get_db() as db:
        existing = db.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if existing:
            db.execute(
                "UPDATE users SET password_hash = ?, role = 'admin' WHERE id = ?",
                (password_hash, existing["id"])
            )
            print("\nAdministrador actualizado correctamente.")
        else:
            db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
                (username, password_hash)
            )
            print("\nAdministrador creado correctamente.")

    print("\nYa puedes iniciar sesión en MediBot 360.")


if __name__ == "__main__":
    create_admin()

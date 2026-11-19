document.addEventListener("DOMContentLoaded", () => {

    const loginForm = document.getElementById("login-form");

    const loginButton = document.getElementById("login-button");

    const loginFeedback = document.getElementById("login-feedback");

    const logoutButton = document.getElementById("logout-button");

    // INICIAR SESIÓN

    if (loginForm) {

        loginForm.addEventListener("submit", async event => {

            event.preventDefault();

            loginFeedback.hidden = true;

            loginButton.disabled = true;

            loginButton.textContent = "Verificando acceso...";

            const username = document.getElementById("username").value.trim();

            const password = document.getElementById("password").value;

            try {

                const response = await fetch("/api/auth/login", {

                    method: "POST",

                    headers: {
                        "Content-Type": "application/json"
                    },

                    body: JSON.stringify({
                        username,
                        password
                    })

                });

                const result = await response.json();

                if (!response.ok) {

                    throw new Error(
                        result.detail || "No fue posible iniciar sesión."
                    );

                }

                window.location.assign("/admin");

            } catch (error) {

                loginFeedback.textContent = error.message;

                loginFeedback.hidden = false;

                loginButton.disabled = false;

                loginButton.textContent = "Iniciar sesión →";

            }

        });

    }

    // CERRAR SESIÓN

    if (logoutButton) {

        logoutButton.addEventListener("click", async () => {

            logoutButton.disabled = true;

            logoutButton.textContent = "Cerrando sesión...";

            try {

                await fetch("/api/auth/logout", {
                    method: "POST"
                });

            } finally {

                window.location.replace("/admin/login");

            }

        });

    }

});
document.addEventListener("DOMContentLoaded", () => {
    console.log("MediBot 360 iniciado correctamente.");

    loadSpecialties();
    initializeContactForm();
});

async function loadProfessionalNames(specialtyId) {
    try {
        const response = await fetch(`/api/professionals/${encodeURIComponent(specialtyId)}`);

        if (!response.ok) return [];

        const result = await response.json();

        return (result.data || []).map(item => item.full_name);
    } catch (error) {
        return [];
    }
}

async function loadSpecialties() {
    const container = document.getElementById("specialties-container");

    if (!container) return;

    try {
        const response = await fetch("/api/specialties");

        if (!response.ok) {
            throw new Error("No se pudieron obtener las especialidades.");
        }

        const result = await response.json();

        container.innerHTML = "";

        if (result.data.length === 0) {
            container.textContent = "No hay especialidades disponibles.";
            return;
        }

        const teams = await Promise.all(
            result.data.map(specialty => loadProfessionalNames(specialty.id))
        );

        result.data.forEach((specialty, index) => {
            const card = document.createElement("article");
            card.className = "service-card";

            const icon = document.createElement("span");
            icon.className = "service-icon";
            icon.textContent = "✚";

            const title = document.createElement("h3");
            title.textContent = specialty.name;

            const description = document.createElement("p");
            description.textContent = specialty.description;

            const team = document.createElement("small");
            team.className = "service-team";
            team.textContent = teams[index].length
                ? `Atiende: ${teams[index].join(", ")}`
                : "Equipo por confirmar";

            const price = document.createElement("strong");
            price.className = "service-price";
            price.textContent = `$${Number(specialty.price).toFixed(2)} MXN`;

            const button = document.createElement("a");
            button.className = "service-button";
            button.href = `/reservar?specialty_id=${encodeURIComponent(specialty.id)}`;
            button.textContent = "Solicitar cita";

            card.append(icon, title, description, team, price, button);
            container.appendChild(card);
        });
    } catch (error) {
        console.error("Error:", error);
        container.textContent =
            "No fue posible cargar las especialidades. Intenta nuevamente.";
    }
}

function initializeContactForm() {
    const form = document.getElementById("contact-form");

    if (!form) return;

    const status = document.getElementById("contact-status");
    const submit = document.getElementById("contact-submit");

    function show(message, type) {
        status.textContent = message;
        status.className = `contact-status ${type}`;
    }

    form.addEventListener("submit", async event => {
        event.preventDefault();

        if (!form.checkValidity()) {
            form.reportValidity();
            return;
        }

        const data = new FormData(form);

        submit.disabled = true;
        show("Enviando mensaje...", "info");

        try {
            const response = await fetch("/api/contact", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    full_name: data.get("full_name"),
                    email: data.get("email"),
                    phone: data.get("phone") || null,
                    message: data.get("message")
                })
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(
                    typeof result.detail === "string"
                        ? result.detail
                        : "Revisa los datos del formulario."
                );
            }

            form.reset();
            show(result.message, "success");
        } catch (error) {
            show(error.message, "error");
        } finally {
            submit.disabled = false;
        }
    });
}

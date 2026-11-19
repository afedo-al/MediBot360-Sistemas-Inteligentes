
document.addEventListener("DOMContentLoaded", () => {
    console.log("MediBot 360 iniciado correctamente.");

    loadSpecialties();
});

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

        result.data.forEach(specialty => {
            const card = document.createElement("article");
            card.className = "service-card";

            const icon = document.createElement("span");
            icon.className = "service-icon";
            icon.textContent = "✚";

            const title = document.createElement("h3");
            title.textContent = specialty.name;

            const description = document.createElement("p");
            description.textContent = specialty.description;

            const price = document.createElement("strong");
            price.className = "service-price";
            price.textContent = `$${Number(specialty.price).toFixed(2)} MXN`;

            const button = document.createElement("a");
            button.className = "service-button";
            button.href = `/reservar?specialty_id=${encodeURIComponent(specialty.id)}`;
            button.textContent = "Solicitar cita";

            card.append(icon, title, description, price, button);
            container.appendChild(card);
        });
    } catch (error) {
        console.error("Error:", error);
        container.textContent =
            "No fue posible cargar las especialidades. Intenta nuevamente.";
    }
}

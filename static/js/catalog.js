(function () {
    const state = { specialties: [], professionals: [] };
    const $ = (id) => document.getElementById(id);
    const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    }[character]));

    function showFeedback(message, error = false) {
        const element = $("catalog-feedback");
        element.textContent = message;
        element.className = `catalog-feedback ${error ? "error" : "success"}`;
    }

    async function request(url, options = {}) {
        const response = await fetch(url, {
            headers: { "Content-Type": "application/json" },
            ...options
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || "No se pudo completar la operación.");
        return payload;
    }

    function renderSpecialties() {
        $("specialties-list").innerHTML = state.specialties.length
            ? state.specialties.map((item) => `
                <article class="catalog-item ${item.active ? "" : "inactive"}">
                    <div><strong>${escapeHTML(item.name)}</strong><span>${escapeHTML(item.description || "Sin descripción")}</span><small>$${Number(item.price).toFixed(2)} · ${item.professionals_count} profesional(es)</small></div>
                    <div class="catalog-item-actions"><span class="catalog-status">${item.active ? "Activa" : "Inactiva"}</span><button type="button" class="catalog-edit" data-specialty="${item.id}">Editar</button></div>
                </article>`).join("")
            : '<p class="catalog-empty">Todavía no hay especialidades.</p>';
    }

    function renderProfessionals() {
        $("professionals-list").innerHTML = state.professionals.length
            ? state.professionals.map((item) => `
                <article class="catalog-item ${item.active ? "" : "inactive"}">
                    <div><strong>${escapeHTML(item.full_name)}</strong><span>${escapeHTML(item.specialty_name)}</span><small>${escapeHTML(item.email || "Sin correo")}</small></div>
                    <div class="catalog-item-actions"><span class="catalog-status">${item.active ? "Activo" : "Inactivo"}</span><button type="button" class="catalog-edit" data-professional="${item.id}">Editar</button></div>
                </article>`).join("")
            : '<p class="catalog-empty">Todavía no hay profesionales.</p>';
    }

    function populateSpecialties() {
        $("professional-specialty").innerHTML = state.specialties.map((item) =>
            `<option value="${item.id}">${escapeHTML(item.name)}${item.active ? "" : " (inactiva)"}</option>`
        ).join("");
    }

    function resetForm(type) {
        const form = $(`${type}-form`);
        form.reset();
        $(`${type}-id`).value = "";
        $(`${type}-active`).checked = true;
        closeModal(type);
    }

    function openModal(type, editing) {
        const modal = $(`${type}-modal`);
        const form = $(`${type}-form`);
        const title = $(`${type}-modal-title`);
        title.textContent = `${editing ? "Editar" : "Nueva"} ${type === "specialty" ? "especialidad" : "profesional"}`;
        modal.hidden = false;
        document.body.classList.add("modal-open");
        form.querySelector("input:not([type='hidden'])").focus();
    }

    function closeModal(type) {
        $(`${type}-modal`).hidden = true;
        if ($("specialty-modal").hidden && $("professional-modal").hidden) {
            document.body.classList.remove("modal-open");
        }
    }

    function editSpecialty(id) {
        const item = state.specialties.find((entry) => entry.id === id);
        if (!item) return;
        $("specialty-id").value = item.id;
        $("specialty-name").value = item.name;
        $("specialty-price").value = item.price;
        $("specialty-description").value = item.description || "";
        $("specialty-active").checked = Boolean(item.active);
        openModal("specialty", true);
    }

    function editProfessional(id) {
        const item = state.professionals.find((entry) => entry.id === id);
        if (!item) return;
        $("professional-id").value = item.id;
        $("professional-name").value = item.full_name;
        $("professional-email").value = item.email || "";
        $("professional-specialty").value = item.specialty_id;
        $("professional-active").checked = Boolean(item.active);
        openModal("professional", true);
    }

    async function load() {
        try {
            const [specialties, professionals] = await Promise.all([
                request("/api/admin/specialties"),
                request("/api/admin/professionals")
            ]);
            state.specialties = specialties.data;
            state.professionals = professionals.data;
            populateSpecialties();
            renderSpecialties();
            renderProfessionals();
        } catch (error) {
            showFeedback(error.message, true);
        }
    }

    $("specialty-new").addEventListener("click", () => {
        resetForm("specialty");
        openModal("specialty", false);
    });
    $("professional-new").addEventListener("click", () => {
        resetForm("professional");
        populateSpecialties();
        openModal("professional", false);
    });
    document.addEventListener("click", (event) => {
        const specialty = event.target.closest("[data-specialty]");
        const professional = event.target.closest("[data-professional]");
        const cancel = event.target.closest("[data-catalog-cancel]");
        const close = event.target.closest("[data-catalog-close]");
        if (specialty) editSpecialty(Number(specialty.dataset.specialty));
        if (professional) editProfessional(Number(professional.dataset.professional));
        if (cancel) resetForm(cancel.dataset.catalogCancel);
        if (close) closeModal(close.dataset.catalogClose);
    });
    $("specialty-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const id = $("specialty-id").value;
        try {
            await request(id ? `/api/admin/specialties/${id}` : "/api/admin/specialties", {
                method: id ? "PUT" : "POST",
                body: JSON.stringify({
                    name: $("specialty-name").value,
                    description: $("specialty-description").value,
                    price: Number($("specialty-price").value),
                    active: $("specialty-active").checked
                })
            });
            resetForm("specialty");
            showFeedback("Especialidad guardada correctamente.");
            await load();
        } catch (error) { showFeedback(error.message, true); }
    });
    $("professional-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const id = $("professional-id").value;
        try {
            await request(id ? `/api/admin/professionals/${id}` : "/api/admin/professionals", {
                method: id ? "PUT" : "POST",
                body: JSON.stringify({
                    full_name: $("professional-name").value,
                    email: $("professional-email").value || null,
                    specialty_id: Number($("professional-specialty").value),
                    active: $("professional-active").checked
                })
            });
            resetForm("professional");
            showFeedback("Profesional guardado correctamente.");
            await load();
        } catch (error) { showFeedback(error.message, true); }
    });
    $("specialty-form-slot").appendChild($("specialty-form"));
    $("professional-form-slot").appendChild($("professional-form"));
    ["specialty", "professional"].forEach((type) => {
        const modal = $(`${type}-modal`);
        modal.addEventListener("click", (event) => {
            if (event.target === modal) closeModal(type);
        });
    });
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        if (!$("specialty-modal").hidden) closeModal("specialty");
        if (!$("professional-modal").hidden) closeModal("professional");
    });
    load();
})();

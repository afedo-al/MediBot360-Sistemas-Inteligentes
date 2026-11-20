document.addEventListener("DOMContentLoaded", () => {
    initializeCustomerDirectory();
    initializeCustomerProfile();
    initializeLogout();
});

function escapeHTML(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;").replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function showFeedback(element, message, type) {
    if (!element) return;
    element.textContent = message;
    element.className = `crm-feedback ${type}`;
    element.hidden = false;
}

async function initializeCustomerDirectory() {
    const table = document.getElementById("customers-table");
    const searchInput = document.getElementById("customer-search");
    const statusFilter = document.getElementById("customer-status-filter");
    const sourceFilter = document.getElementById("customer-source-filter");
    const exportLink = document.getElementById("customer-export");
    if (!table || !searchInput) return;

    const STATUS = {
        lead: ["lead", "Prospecto"],
        active: ["active", "Activo"],
        inactive: ["inactive", "Inactivo"]
    };
    const SOURCE = {
        web: "Sitio web",
        chatbot: "Chatbot",
        contacto: "Formulario de contacto",
        admin: "Administración"
    };

    function buildQuery() {
        const params = new URLSearchParams();
        if (searchInput.value.trim()) params.set("search", searchInput.value.trim());
        if (statusFilter && statusFilter.value) params.set("status", statusFilter.value);
        if (sourceFilter && sourceFilter.value) params.set("source", sourceFilter.value);
        return params.toString();
    }

    async function loadCustomers() {
        const query = buildQuery();
        if (exportLink) exportLink.href = "/api/admin/export/customers.csv" + (query ? "?" + query : "");
        table.innerHTML = '<tr><td colspan="7" class="empty-table">Buscando clientes...</td></tr>';
        try {
            const response = await fetch("/api/admin/customers" + (query ? "?" + query : ""));
            if (response.status === 401) {
                window.location.replace("/admin/login");
                return;
            }
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || "Error al consultar los clientes.");
            const customers = result.data || [];
            renderCustomers(customers);
            updateCustomerStatistics(customers);
        } catch (error) {
            table.innerHTML = `<tr><td colspan="7" class="empty-table">${escapeHTML(error.message)}</td></tr>`;
        }
    }

    function renderCustomers(customers) {
        const results = document.getElementById("crm-results");
        if (!customers.length) {
            table.innerHTML = '<tr><td colspan="7" class="empty-table">No se encontraron clientes.</td></tr>';
            results.textContent = "0 clientes encontrados";
            return;
        }
        table.innerHTML = customers.map(customer => {
            const [cls, text] = STATUS[customer.status] || STATUS.inactive;
            return `<tr>
                <td><div class="crm-customer-cell"><div class="crm-customer-avatar">${escapeHTML(customer.full_name.charAt(0).toUpperCase())}</div><div class="crm-customer-name"><strong>${escapeHTML(customer.full_name)}</strong><span>Cliente #${customer.id}</span></div></div></td>
                <td><div class="crm-contact"><span>${escapeHTML(customer.email || "Sin correo")}</span><small>${escapeHTML(customer.phone || "Sin teléfono")}</small></div></td>
                <td><span class="crm-source">${escapeHTML(SOURCE[customer.source] || customer.source)}</span></td>
                <td>${customer.appointments_count}</td><td>${escapeHTML(customer.created_at)}</td>
                <td><span class="crm-status ${cls}">${text}</span></td>
                <td><a href="/admin/clientes/${customer.id}" class="crm-action-link">Ver perfil →</a></td>
            </tr>`;
        }).join("");
        results.textContent = `${customers.length} cliente(s) encontrado(s)`;
    }

    function updateCustomerStatistics(customers) {
        document.getElementById("crm-total").textContent = customers.length;
        document.getElementById("crm-active").textContent = customers.filter(item => item.status === "active").length;
        const leads = document.getElementById("crm-leads");
        if (leads) leads.textContent = customers.filter(item => item.status === "lead").length;
        document.getElementById("crm-inactive").textContent = customers.filter(item => item.status === "inactive").length;
    }

    let searchTimeout;
    searchInput.addEventListener("input", () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(loadCustomers, 200);
    });
    [statusFilter, sourceFilter].forEach(select => {
        if (select) select.addEventListener("change", loadCustomers);
    });
    await loadCustomers();
}

function initializeCustomerProfile() {
    const editForm = document.getElementById("customer-edit-form");
    if (editForm) {
        editForm.addEventListener("submit", async event => {
            event.preventDefault();
            const button = document.getElementById("customer-save-button");
            const feedback = document.getElementById("customer-edit-feedback");
            const payload = {
                full_name: document.getElementById("customer-name").value.trim(),
                email: document.getElementById("customer-email").value.trim(),
                phone: document.getElementById("customer-phone").value.trim(),
                status: document.getElementById("customer-status").value
            };
            button.disabled = true;
            button.textContent = "Guardando...";
            try {
                const response = await fetch(`/api/admin/customers/${editForm.dataset.customerId}`, {
                    method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
                });
                const result = await response.json();
                if (response.status === 401) { window.location.replace("/admin/login"); return; }
                if (!response.ok) throw new Error(result.detail || "No fue posible guardar.");
                showFeedback(feedback, result.message, "success");
                document.querySelector(".customer-profile-identity h2").textContent = payload.full_name;
                document.querySelector(".customer-large-avatar").textContent = payload.full_name.charAt(0).toUpperCase();
                const badge = document.querySelector(".customer-status");
                badge.textContent = {active: "Activo", lead: "Prospecto"}[payload.status] || "Inactivo";
                badge.className = `customer-status ${payload.status}`;
            } catch (error) {
                showFeedback(feedback, error.message, "error");
            } finally {
                button.disabled = false;
                button.textContent = "Guardar cambios";
            }
        });
    }

    const interactionForm = document.getElementById("interaction-form");
    if (interactionForm) {
        interactionForm.addEventListener("submit", async event => {
            event.preventDefault();
            const button = document.getElementById("interaction-save-button");
            const feedback = document.getElementById("interaction-feedback");
            const input = document.getElementById("interaction-message");
            const message = input.value.trim();
            if (message.length < 2) return;
            button.disabled = true;
            button.textContent = "Registrando...";
            try {
                const response = await fetch(`/api/admin/customers/${interactionForm.dataset.customerId}/interactions`, {
                    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({message})
                });
                const result = await response.json();
                if (response.status === 401) { window.location.replace("/admin/login"); return; }
                if (!response.ok) throw new Error(result.detail || "Error al registrar.");
                showFeedback(feedback, result.message, "success");
                input.value = "";
                setTimeout(() => window.location.reload(), 500);
            } catch (error) {
                showFeedback(feedback, error.message, "error");
            } finally {
                button.disabled = false;
                button.textContent = "Registrar seguimiento";
            }
        });
    }
}

function initializeLogout() {
    const button = document.getElementById("logout-button");
    if (!button) return;
    button.addEventListener("click", async () => {
        button.disabled = true;
        button.textContent = "Cerrando sesión...";
        try { await fetch("/api/auth/logout", {method: "POST"}); }
        finally { window.location.replace("/admin/login"); }
    });
}

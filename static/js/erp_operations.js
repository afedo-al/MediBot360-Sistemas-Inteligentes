document.addEventListener("DOMContentLoaded", () => {
    const $ = id => document.getElementById(id);
    const money = value => new Intl.NumberFormat("es-MX", {
        style: "currency",
        currency: "MXN"
    }).format(Number(value || 0));
    let financeRecords = [];
    let paymentResolver = null;

    function settlePaymentConfirmation(value) {
        $("ops-payment-modal").hidden = true;
        document.body.classList.remove("modal-open");
        const resolve = paymentResolver;
        paymentResolver = null;
        if (resolve) resolve(value);
    }

    function requestPaymentConfirmation(message, operation) {
        if (paymentResolver) settlePaymentConfirmation(false);

        const isPayment = operation === "collect";
        $("ops-payment-icon").textContent = isPayment ? "✓" : "↩";
        $("ops-payment-icon").className =
            `ops-payment-icon ${isPayment ? "collect" : "refund"}`;
        $("ops-payment-title").textContent =
            isPayment ? "Registrar pago simulado" : "Registrar devolución";
        $("ops-payment-message").textContent = message;
        $("ops-payment-confirm").textContent =
            isPayment ? "Registrar pago" : "Registrar devolución";
        $("ops-payment-modal").hidden = false;
        document.body.classList.add("modal-open");
        $("ops-payment-confirm").focus();

        return new Promise(resolve => {
            paymentResolver = resolve;
        });
    }

    $("ops-payment-cancel").addEventListener("click", () => {
        settlePaymentConfirmation(false);
    });
    $("ops-payment-confirm").addEventListener("click", () => {
        settlePaymentConfirmation(true);
    });
    $("ops-payment-modal").addEventListener("click", event => {
        if (event.target === $("ops-payment-modal")) {
            settlePaymentConfirmation(false);
        }
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && !$("ops-payment-modal").hidden) {
            settlePaymentConfirmation(false);
        }
    });

    async function api(url, options = {}) {
        const response = await fetch(url, options);
        if (response.status === 401) {
            window.location.replace("/admin/login");
            throw new Error("Sesión expirada.");
        }
        const result = await response.json();
        if (!response.ok) {
            throw new Error(
                typeof result.detail === "string"
                    ? result.detail
                    : "No se pudo completar la operación."
            );
        }
        return result;
    }

    function cell(row, value) {
        const td = row.insertCell();
        td.textContent = value ?? "—";
        return td;
    }

    function actionButton(text, handler, secondary = false) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = secondary
            ? "ops-small-button secondary"
            : "ops-small-button";
        button.textContent = text;
        button.addEventListener("click", handler);
        return button;
    }

    function message(id, text, error = false) {
        const element = $(id);
        element.textContent = text;
        element.className = error
            ? "ops-message error"
            : "ops-message success";
    }

    function badge(row, text, kind) {
        const td = row.insertCell();
        const label = document.createElement("span");
        label.className = `ops-badge ${kind}`;
        label.textContent = text;
        td.appendChild(label);
    }

    function renderFinance() {
        const tbody = $("fin-table");
        tbody.replaceChildren();
        const search = $("fin-search").value.trim().toLowerCase();
        const records = financeRecords.filter(item =>
            item.folio.toLowerCase().includes(search)
            || item.customer_name.toLowerCase().includes(search)
        );

        if (!records.length) {
            const row = tbody.insertRow();
            const td = cell(row, "No se encontraron reservaciones.");
            td.colSpan = 7;
            td.className = "empty-table";
            return;
        }

        records.forEach(item => {
            const row = tbody.insertRow();
            cell(row, item.folio);
            cell(row, item.customer_name);
            cell(row, item.specialty_name);
            cell(row, money(item.agreed_price));
            badge(
                row,
                item.appointment_status === "confirmed" ? "Confirmada" : "Cancelada",
                item.appointment_status === "confirmed" ? "positive" : "neutral"
            );

            const states = {
                unpaid: ["Sin pagar", "neutral"],
                pending: ["Pendiente", "warning"],
                paid: ["Pagado", "positive"],
                refunded: ["Devuelto", "warning"]
            };
            const current = states[item.payment_status]
                || [item.payment_status, "neutral"];
            badge(row, current[0], current[1]);

            const actions = row.insertCell();
            if (
                item.appointment_status === "confirmed"
                && ["unpaid", "pending"].includes(item.payment_status)
            ) {
                actions.appendChild(actionButton(
                    "Registrar pago",
                    () => changePayment(item, "collect")
                ));
            } else if (item.payment_status === "paid") {
                actions.appendChild(actionButton(
                    "Devolución",
                    () => changePayment(item, "refund"),
                    true
                ));
            } else {
                actions.textContent = "—";
            }
        });
    }

    async function loadFinance() {
        const result = await api("/api/admin/finance");
        financeRecords = result.data || [];
        $("fin-appointments").textContent = result.stats.appointments;
        $("fin-paid").textContent = money(result.stats.paid_total);
        $("fin-pending").textContent = money(result.stats.pending_total);
        $("fin-refunded").textContent = money(result.stats.refunded_total);
        renderFinance();
        message("fin-message", `${financeRecords.length} reservación(es).`);
    }

    async function changePayment(item, operation) {
        const isPayment = operation === "collect";
        const prompt = isPayment
            ? `¿Registrar el pago SIMULADO de ${money(item.agreed_price)} para el folio ${item.folio}?`
            : `¿Registrar la devolución SIMULADA del folio ${item.folio}?`;
        const confirmed = await requestPaymentConfirmation(prompt, operation);
        if (!confirmed) return;

        try {
            const result = await api(
                `/api/admin/payments/${item.appointment_id}/${operation}`,
                { method: "POST" }
            );
            await loadFinance();
            message("fin-message", result.message);
        } catch (error) {
            message("fin-message", error.message, true);
        }
    }

    $("fin-search").addEventListener("input", renderFinance);

    function resetResourceForm() {
        $("resource-form").reset();
        $("resource-id").value = "";
        $("resource-quantity").disabled = false;
        $("resource-quantity").value = "0";
        $("resource-form-title").textContent = "Nuevo recurso";
        $("resource-save").textContent = "Guardar recurso";
    }

    function editResource(resource) {
        $("resource-id").value = resource.id;
        $("resource-name").value = resource.name;
        $("resource-description").value = resource.description || "";
        $("resource-quantity").value = resource.quantity;
        $("resource-quantity").disabled = true;
        $("resource-status").value = resource.status;
        $("resource-form-title").textContent = "Editar recurso";
        $("resource-save").textContent = "Actualizar recurso";
        $("resource-name").scrollIntoView({ behavior: "smooth", block: "center" });
        $("resource-name").focus();
    }

    function openAdjustment(resource) {
        $("resource-adjust-form").reset();
        $("resource-adjust-id").value = resource.id;
        $("resource-adjust-name").textContent =
            `${resource.name} · Existencia actual: ${resource.quantity}`;
        $("resource-adjust-panel").hidden = false;
        message("resource-adjust-message", "");
        $("resource-adjust-panel").scrollIntoView({
            behavior: "smooth",
            block: "center"
        });
    }

    function closeAdjustment() {
        $("resource-adjust-form").reset();
        $("resource-adjust-panel").hidden = true;
        $("resource-adjust-id").value = "";
    }

    async function loadResources() {
        const result = await api("/api/admin/resources");
        const resources = result.data || [];
        $("resource-total").textContent =
            `${resources.length} recurso(s) registrados`;

        const tbody = $("resource-table");
        tbody.replaceChildren();
        if (!resources.length) {
            const td = cell(tbody.insertRow(), "Todavía no hay recursos.");
            td.colSpan = 4;
        }

        resources.forEach(resource => {
            const row = tbody.insertRow();
            cell(row, resource.name);
            cell(row, resource.quantity);
            badge(
                row,
                resource.status === "available" ? "Disponible" : "No disponible",
                resource.status === "available" ? "positive" : "neutral"
            );
            const actions = row.insertCell();
            actions.append(
                actionButton("Editar", () => editResource(resource)),
                actionButton(
                    "Ajustar",
                    () => openAdjustment(resource),
                    true
                )
            );
        });

        const movementsBody = $("resource-movements");
        movementsBody.replaceChildren();
        const movements = result.movements || [];
        if (!movements.length) {
            const td = cell(
                movementsBody.insertRow(),
                "No existen movimientos registrados."
            );
            td.colSpan = 5;
        }
        movements.forEach(item => {
            const row = movementsBody.insertRow();
            cell(row, item.created_at);
            cell(row, item.resource_name);
            const delta = Number(item.quantity_change);
            cell(row, delta > 0 ? `+${delta}` : String(delta));
            cell(row, item.reason);
            cell(row, item.username || "Sistema");
        });
    }

    $("resource-form").addEventListener("submit", async event => {
        event.preventDefault();
        if (!event.currentTarget.reportValidity()) return;

        const id = $("resource-id").value;
        const button = $("resource-save");
        const payload = {
            name: $("resource-name").value.trim(),
            description: $("resource-description").value.trim(),
            status: $("resource-status").value
        };
        if (!id) {
            payload.quantity = Number($("resource-quantity").value);
        }
        button.disabled = true;

        try {
            const result = await api(
                id
                    ? `/api/admin/resources/${id}`
                    : "/api/admin/resources",
                {
                    method: id ? "PUT" : "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                }
            );
            resetResourceForm();
            await loadResources();
            message("resource-message", result.message);
        } catch (error) {
            message("resource-message", error.message, true);
        } finally {
            button.disabled = false;
        }
    });

    $("resource-adjust-form").addEventListener("submit", async event => {
        event.preventDefault();
        if (!event.currentTarget.reportValidity()) return;

        const id = $("resource-adjust-id").value;
        const button = $("resource-adjust-save");
        button.disabled = true;

        try {
            const result = await api(
                `/api/admin/resources/${id}/adjust`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        quantity_change: Number($("resource-delta").value),
                        reason: $("resource-reason").value.trim()
                    })
                }
            );
            closeAdjustment();
            await loadResources();
            message("resource-message", result.message);
        } catch (error) {
            message("resource-adjust-message", error.message, true);
        } finally {
            button.disabled = false;
        }
    });

    $("resource-clear").addEventListener("click", () => {
        resetResourceForm();
        message("resource-message", "");
    });
    $("resource-adjust-cancel").addEventListener("click", closeAdjustment);

    loadFinance().catch(error =>
        message("fin-message", error.message, true)
    );
    loadResources().catch(error =>
        message("resource-message", error.message, true)
    );
});

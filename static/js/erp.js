document.addEventListener("DOMContentLoaded", () => {
    const table = document.getElementById("erp-table");
    const search = document.getElementById("erp-search");
    const status = document.getElementById("erp-status");
    const dateInput = document.getElementById("erp-date");
    const clear = document.getElementById("erp-clear");
    const feedback = document.getElementById("erp-feedback");
    if (!table || !search || !status || !dateInput || !clear || !feedback) return;

    let requestNumber = 0;
    let searchTimer;

    function addCell(row, value) {
        const cell = document.createElement("td");
        cell.textContent = value ?? "—";
        row.appendChild(cell);
        return cell;
    }

    async function loadAppointments() {
        const currentRequest = ++requestNumber;
        const params = new URLSearchParams();
        if (search.value.trim()) params.set("search", search.value.trim());
        if (status.value) params.set("status", status.value);
        if (dateInput.value) params.set("appointment_date", dateInput.value);
        feedback.textContent = "Consultando reservaciones...";

        try {
            const response = await fetch(`/api/admin/appointments?${params}`);
            if (response.status === 401) {
                window.location.replace("/admin/login");
                return;
            }
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || "Error al consultar reservaciones.");
            if (currentRequest !== requestNumber) return;
            table.replaceChildren();

            if (!result.data.length) {
                const row = table.insertRow();
                const cell = addCell(row, "No se encontraron reservaciones.");
                cell.colSpan = 7;
                cell.className = "empty-table";
            }

            result.data.forEach(appointment => {
                const row = table.insertRow();
                addCell(row, appointment.folio);
                addCell(row, appointment.customer_name);
                addCell(row, appointment.specialty_name);
                addCell(row, appointment.professional_name);
                addCell(row, `${appointment.appointment_date} ${appointment.start_time}`);

                const statusCell = row.insertCell();
                const badge = document.createElement("span");
                const confirmed = appointment.status === "confirmed";
                badge.className = `status-badge ${confirmed ? "confirmed" : "cancelled"}`;
                badge.textContent = confirmed ? "Confirmada" : "Cancelada";
                statusCell.appendChild(badge);

                const actionCell = row.insertCell();
                if (confirmed) {
                    const button = document.createElement("button");
                    button.type = "button";
                    button.className = "erp-cancel-button";
                    button.textContent = "Cancelar";
                    button.addEventListener("click", () => cancelAppointment(appointment, button));
                    actionCell.appendChild(button);
                } else {
                    actionCell.textContent = "—";
                }
            });
            feedback.textContent = `${result.total} reservación(es) encontrada(s).`;
        } catch (error) {
            if (currentRequest === requestNumber) feedback.textContent = error.message;
        }
    }

    async function cancelAppointment(appointment, button) {
        if (!window.confirm(`¿Cancelar la reservación ${appointment.folio}?`)) return;
        button.disabled = true;
        button.textContent = "Cancelando...";
        try {
            const response = await fetch(`/api/admin/appointments/${appointment.id}/cancel`, {method: "POST"});
            if (response.status === 401) {
                window.location.replace("/admin/login");
                return;
            }
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || "No fue posible cancelar.");
            await loadAppointments();
            feedback.textContent = result.message;
        } catch (error) {
            feedback.textContent = error.message;
        } finally {
            button.disabled = false;
            button.textContent = "Cancelar";
        }
    }

    search.addEventListener("input", () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(loadAppointments, 250);
    });
    status.addEventListener("change", loadAppointments);
    dateInput.addEventListener("change", loadAppointments);
    clear.addEventListener("click", () => {
        search.value = "";
        status.value = "";
        dateInput.value = "";
        loadAppointments();
    });
    loadAppointments();
});

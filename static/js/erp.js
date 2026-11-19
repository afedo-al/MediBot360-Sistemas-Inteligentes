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

    const confirmationModal = document.getElementById("erp-confirm-modal");
    const confirmationMessage = document.getElementById("erp-confirm-message");
    const confirmationCancel = document.getElementById("erp-confirm-cancel");
    const confirmationAccept = document.getElementById("erp-confirm-accept");
    let confirmationResolver = null;

    function settleConfirmation(value) {
        confirmationModal.hidden = true;
        const resolve = confirmationResolver;
        confirmationResolver = null;
        if (resolve) resolve(value);
    }

    function requestConfirmation(message, acceptText) {
        if (confirmationResolver) settleConfirmation(false);
        confirmationMessage.textContent = message;
        confirmationAccept.textContent = acceptText;
        confirmationModal.hidden = false;
        confirmationAccept.focus();
        return new Promise(resolve => {
            confirmationResolver = resolve;
        });
    }

    confirmationCancel.addEventListener("click", () => settleConfirmation(false));
    confirmationAccept.addEventListener("click", () => settleConfirmation(true));
    confirmationModal.addEventListener("click", event => {
        if (event.target === confirmationModal) settleConfirmation(false);
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && !confirmationModal.hidden) {
            settleConfirmation(false);
        }
    });

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
                    const reprogramButton = document.createElement("button");
                    reprogramButton.type = "button";
                    reprogramButton.className = "erp-reschedule-button";
                    reprogramButton.textContent = "Reprogramar";
                    reprogramButton.addEventListener("click", () => openReschedule(appointment));
                    actionCell.appendChild(reprogramButton);

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
        const confirmed = await requestConfirmation(
            `¿Cancelar la reservación ${appointment.folio}? Esta acción liberará su horario.`,
            "Cancelar reservación"
        );
        if (!confirmed) return;
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

    const modal = document.getElementById("erp-reschedule-modal");
    const rescheduleForm = document.getElementById("erp-reschedule-form");
    const rescheduleProfessional = document.getElementById("erp-reschedule-professional");
    const rescheduleDate = document.getElementById("erp-reschedule-date");
    const rescheduleSchedule = document.getElementById("erp-reschedule-schedule");
    const rescheduleFeedback = document.getElementById("erp-reschedule-feedback");
    const rescheduleSubmit = document.getElementById("erp-reschedule-submit");
    const rescheduleClose = document.getElementById("erp-reschedule-close");
    let activeReschedule = null;
    let optionsRequest = 0;
    let rescheduleBusy = false;

    function localISO(days = 0) {
        const value = new Date();
        value.setDate(value.getDate() + days);
        return [
            value.getFullYear(),
            String(value.getMonth() + 1).padStart(2, "0"),
            String(value.getDate()).padStart(2, "0")
        ].join("-");
    }

    function closeReschedule() {
        if (rescheduleBusy) return;
        optionsRequest++;
        activeReschedule = null;
        modal.hidden = true;
    }

    async function openReschedule(appointment) {
        activeReschedule = appointment;
        rescheduleForm.reset();
        rescheduleProfessional.disabled = true;
        rescheduleSchedule.disabled = true;
        rescheduleSubmit.disabled = true;
        rescheduleDate.min = localISO(1);
        rescheduleDate.max = localISO(14);
        rescheduleDate.value =
            appointment.appointment_date >= rescheduleDate.min &&
            appointment.appointment_date <= rescheduleDate.max
                ? appointment.appointment_date
                : localISO(1);
        document.getElementById("erp-reschedule-current").textContent =
            `${appointment.folio} · ${appointment.customer_name} · ` +
            `${appointment.appointment_date} ${appointment.start_time} · ` +
            appointment.professional_name;
        rescheduleFeedback.textContent = "Cargando profesionales...";
        modal.hidden = false;
        rescheduleClose.focus();

        try {
            const response = await fetch(`/api/professionals/${appointment.specialty_id}`);
            if (!response.ok) throw new Error("No se pudieron consultar los profesionales.");
            const result = await response.json();
            if (activeReschedule !== appointment) return;
            rescheduleProfessional.replaceChildren(new Option("Selecciona un profesional", ""));
            (result.data || []).forEach(professional => {
                rescheduleProfessional.add(new Option(professional.full_name, professional.id));
            });
            rescheduleProfessional.value = String(appointment.professional_id);
            rescheduleProfessional.disabled = false;
            if (rescheduleProfessional.value) await loadRescheduleOptions();
        } catch (error) {
            rescheduleFeedback.textContent = error.message;
        }
    }

    async function loadRescheduleOptions() {
        const currentRequest = ++optionsRequest;
        rescheduleSchedule.replaceChildren(new Option("Consultando horarios...", ""));
        rescheduleSchedule.disabled = true;
        rescheduleSubmit.disabled = true;
        if (!activeReschedule || !rescheduleProfessional.value || !rescheduleDate.value) return;

        const selectedDate = new Date(`${rescheduleDate.value}T12:00:00`);
        if (selectedDate.getDay() === 0) {
            rescheduleFeedback.textContent = "No se permiten citas los domingos.";
            return;
        }

        const params = new URLSearchParams({
            professional_id: rescheduleProfessional.value,
            appointment_date: rescheduleDate.value
        });

        try {
            const response = await fetch(
                `/api/admin/appointments/${activeReschedule.id}/reschedule-options?${params}`
            );
            if (response.status === 401) {
                window.location.replace("/admin/login");
                return;
            }
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || "Error al consultar disponibilidad.");
            if (currentRequest !== optionsRequest) return;
            rescheduleSchedule.replaceChildren(new Option("Selecciona un horario", ""));
            const available = result.data || [];
            if (!available.length) {
                rescheduleFeedback.textContent = "No hay horarios libres para esta selección.";
                return;
            }
            available.forEach(schedule => {
                rescheduleSchedule.add(new Option(
                    `${schedule.start_time} - ${schedule.end_time}`,
                    schedule.id
                ));
            });
            rescheduleSchedule.disabled = false;
            rescheduleFeedback.textContent = `${available.length} horario(s) disponible(s).`;
        } catch (error) {
            if (currentRequest === optionsRequest) rescheduleFeedback.textContent = error.message;
        }
    }

    async function submitReschedule(event) {
        event.preventDefault();
        if (!activeReschedule || !rescheduleSchedule.value || rescheduleBusy) return;
        const confirmed = await requestConfirmation(
            `¿Confirmar la reprogramación de ${activeReschedule.folio}?`,
            "Confirmar cambio"
        );
        if (!confirmed) return;
        rescheduleBusy = true;
        rescheduleSubmit.disabled = true;
        rescheduleSubmit.textContent = "Guardando...";
        try {
            const response = await fetch(
                `/api/admin/appointments/${activeReschedule.id}/reschedule`,
                {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({schedule_id: Number(rescheduleSchedule.value)})
                }
            );
            if (response.status === 401) {
                window.location.replace("/admin/login");
                return;
            }
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || "No fue posible reprogramar la cita.");
            closeReschedule();
            await loadAppointments();
            feedback.textContent = result.message;
        } catch (error) {
            rescheduleFeedback.textContent = error.message;
        } finally {
            rescheduleBusy = false;
            rescheduleSubmit.textContent = "Confirmar cambio";
            rescheduleSubmit.disabled = !rescheduleSchedule.value;
        }
    }

    rescheduleProfessional.addEventListener("change", loadRescheduleOptions);
    rescheduleDate.addEventListener("change", loadRescheduleOptions);
    rescheduleSchedule.addEventListener("change", () => {
        rescheduleSubmit.disabled = !rescheduleSchedule.value;
    });
    rescheduleForm.addEventListener("submit", submitReschedule);
    rescheduleClose.addEventListener("click", closeReschedule);
    document.getElementById("erp-reschedule-back").addEventListener("click", closeReschedule);
    modal.addEventListener("click", event => {
        if (event.target === modal) closeReschedule();
    });
    document.addEventListener("keydown", event => {
        if (!confirmationModal.hidden) return;
        if (event.key === "Escape" && !modal.hidden) closeReschedule();
    });

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

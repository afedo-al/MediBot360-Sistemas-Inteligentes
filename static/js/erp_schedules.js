document.addEventListener("DOMContentLoaded", () => {
    const $ = id => document.getElementById(id);
    const professional = $("schedule-professional");
    const dayInput = $("schedule-date");
    const table = $("schedule-table-body");
    const status = $("schedule-day-status");
    const toggleDay = $("schedule-day-toggle");
    const feedback = $("schedule-feedback");
    const form = $("schedule-form");
    const save = $("schedule-save");
    let slots = [], closed = false, requestId = 0;

    const localDate = (offset = 0) => {
        const value = new Date();
        value.setDate(value.getDate() + offset);
        return [
            value.getFullYear(),
            String(value.getMonth() + 1).padStart(2, "0"),
            String(value.getDate()).padStart(2, "0")
        ].join("-");
    };
    const notify = (message, error = false) => {
        feedback.textContent = message;
        feedback.className = `schedule-feedback ${error ? "error" : "success"}`;
    };
    async function api(url, options = {}) {
        const response = await fetch(url, options);
        const result = await response.json();
        if (response.status === 401) {
            window.location.replace("/admin/login");
            throw new Error("La sesión expiró.");
        }
        if (!response.ok) throw new Error(result.detail || "No fue posible completar la operación.");
        return result;
    }
    function resetForm() {
        form.reset();
        $("schedule-edit-id").value = "";
        $("schedule-start").value = "09:00";
        $("schedule-end").value = "10:00";
        $("schedule-form-title").textContent = "Nuevo horario";
        save.textContent = "Guardar horario";
        save.disabled = closed;
    }
    function render() {
        table.replaceChildren();
        $("schedule-total").textContent = `${slots.length} horario(s) registrado(s)`;
        if (!slots.length) {
            const row = table.insertRow();
            row.insertCell().textContent = "No hay horarios registrados para esta fecha.";
            row.cells[0].colSpan = 5;
            row.cells[0].className = "empty-table";
            return;
        }
        slots.forEach(slot => {
            const row = table.insertRow();
            [slot.start_time, slot.end_time].forEach(value => row.insertCell().textContent = value);
            const badge = document.createElement("span");
            badge.className = `schedule-badge ${slot.status}`;
            badge.textContent = {available: "Disponible", reserved: "Reservado", blocked: "Bloqueado"}[slot.status] || slot.status;
            row.insertCell().appendChild(badge);
            row.insertCell().textContent = slot.folio || "—";
            const actions = row.insertCell();
            actions.className = "schedule-actions";
            if (slot.status === "reserved" || closed) {
                actions.textContent = "—";
                return;
            }
            const edit = document.createElement("button");
            edit.type = "button";
            edit.className = "schedule-edit";
            edit.textContent = "Editar";
            edit.onclick = () => {
                $("schedule-edit-id").value = slot.id;
                $("schedule-start").value = slot.start_time;
                $("schedule-end").value = slot.end_time;
                $("schedule-slot-status").value = slot.status;
                $("schedule-form-title").textContent = "Editar horario";
                save.textContent = "Actualizar horario";
            };
            const block = document.createElement("button");
            block.type = "button";
            block.className = "schedule-toggle";
            block.textContent = slot.status === "blocked" ? "Habilitar" : "Bloquear";
            block.onclick = () => updateSlot(slot, slot.status === "blocked" ? "available" : "blocked");
            actions.append(edit, block);
        });
    }
    async function loadDay() {
        const current = ++requestId;
        resetForm();
        if (!professional.value || !dayInput.value) return;
        try {
            const params = new URLSearchParams({professional_id: professional.value, appointment_date: dayInput.value});
            const result = await api(`/api/admin/schedule-management?${params}`);
            if (current !== requestId) return;
            slots = result.data || [];
            closed = Boolean(result.is_closed);
            status.textContent = closed ? "Día cerrado para reservaciones" : "Día abierto para reservaciones";
            toggleDay.textContent = closed ? "Reabrir día" : "Bloquear día";
            toggleDay.disabled = false;
            save.disabled = closed;
            render();
        } catch (error) {
            if (current === requestId) notify(error.message, true);
        }
    }
    async function updateSlot(slot, newStatus) {
        try {
            const result = await api(`/api/admin/manage-schedules/${slot.id}`, {
                method: "PUT", headers: {"Content-Type": "application/json"},
                body: JSON.stringify({start_time: slot.start_time, end_time: slot.end_time, status: newStatus})
            });
            await loadDay(); notify(result.message);
        } catch (error) { notify(error.message, true); }
    }
    form.onsubmit = async event => {
        event.preventDefault();
        if (closed || !form.reportValidity()) return;
        const id = $("schedule-edit-id").value;
        const payload = {start_time: $("schedule-start").value, end_time: $("schedule-end").value, status: $("schedule-slot-status").value};
        if (!id) { payload.professional_id = Number(professional.value); payload.appointment_date = dayInput.value; }
        try {
            const result = await api(id ? `/api/admin/manage-schedules/${id}` : "/api/admin/manage-schedules", {
                method: id ? "PUT" : "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
            });
            await loadDay(); notify(result.message);
        } catch (error) { notify(error.message, true); }
    };
    toggleDay.onclick = async () => {
        const next = !closed;
        if (next && !window.confirm("¿Bloquear el día completo?")) return;
        try {
            const result = await api(`/api/admin/schedule-days/${professional.value}/${dayInput.value}`, {
                method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({is_closed: next})
            });
            await loadDay(); notify(result.message);
        } catch (error) { notify(error.message, true); }
    };
    async function loadProfessionals() {
        try {
            const result = await api("/api/admin/professionals");
            professional.replaceChildren(new Option("Selecciona un profesional", ""));
            result.data.filter(person => person.active).forEach(person => professional.add(new Option(`${person.full_name} · ${person.specialty_name}`, person.id)));
            if (professional.options.length > 1) { professional.selectedIndex = 1; loadDay(); }
        } catch (error) { notify(error.message, true); }
    }
    professional.onchange = loadDay;
    dayInput.onchange = loadDay;
    $("schedule-reset").onclick = () => { resetForm(); notify(""); };
    dayInput.min = localDate(1);
    dayInput.max = localDate(14);
    dayInput.value = localDate(1);
    loadProfessionals();
});

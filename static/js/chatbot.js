document.addEventListener("DOMContentLoaded", () => {
    const $ = id => document.getElementById(id);
    const toggle = $("mb-chat-toggle");
    const panel = $("mb-chat-panel");
    const history = $("mb-chat-history");
    const actions = $("mb-chat-actions");
    const compose = $("mb-chat-compose");
    const messageInput = $("mb-chat-message");
    const booking = $("mb-chat-booking");
    const verify = $("mb-chat-verify");
    const spec = $("mb-chat-specialty");
    const pro = $("mb-chat-professional");
    const day = $("mb-chat-date");
    const slot = $("mb-chat-slot");
    const bookButton = $("mb-chat-book-submit");
    const proofButton = $("mb-chat-proof-submit");
    const bookingStatus = $("mb-chat-book-status");
    const proofStatus = $("mb-chat-proof-status");

    let initialized = false;
    let mode = null;
    let proVersion = 0;
    let slotVersion = 0;

    async function api(url, options = {}) {
        const response = await fetch(url, options);
        let data;
        try {
            data = await response.json();
        } catch {
            throw new Error("El servidor no respondió correctamente.");
        }
        if (!response.ok) {
            throw new Error(
                typeof data.detail === "string"
                    ? data.detail
                    : "Revisa los datos e intenta nuevamente."
            );
        }
        return data;
    }

    const jsonPost = (url, data) => api(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
    });

    function bubble(content, sender = "bot") {
        const item = document.createElement("div");
        item.className = `mb-chat-bubble ${sender}`;
        item.textContent = content;
        history.appendChild(item);
        history.scrollTop = history.scrollHeight;
    }

    function quickReplies(labels) {
        actions.replaceChildren();
        labels.forEach(label => {
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = label;
            button.addEventListener("click", () => sendMessage(label));
            actions.appendChild(button);
        });
    }

    function showMode(next) {
        mode = next;
        booking.hidden = next !== "booking";
        verify.hidden = next !== "lookup" && next !== "cancel";

        if (next === "lookup" || next === "cancel") {
            verify.reset();
            proofStatus.textContent = "";
            proofButton.textContent =
                next === "cancel"
                    ? "Cancelar reservación"
                    : "Consultar reservación";
        }
        if (next === "booking") startBooking();
    }

    function openPanel() {
        panel.hidden = false;
        toggle.setAttribute("aria-expanded", "true");

        if (!initialized) {
            bubble(
                "¡Hola! Soy MediBot, el asistente virtual " +
                "de demostración. Puedo mostrar servicios, " +
                "ayudarte a reservar o consultar una cita. " +
                "No doy diagnósticos médicos."
            );
            quickReplies([
                "Servicios y precios",
                "Reservar cita",
                "Consultar mi cita",
                "Cancelar mi cita"
            ]);
            initialized = true;
        }
        messageInput.focus();
    }

    function closePanel() {
        panel.hidden = true;
        toggle.setAttribute("aria-expanded", "false");
        messageInput.value = "";
        booking.reset();
        verify.reset();
        showMode(null);
        history.replaceChildren();
        actions.replaceChildren();
        initialized = false;
        toggle.focus();
    }

    toggle.addEventListener("click", () => {
        panel.hidden ? openPanel() : closePanel();
    });
    $("mb-chat-close").addEventListener("click", closePanel);

    async function sendMessage(text) {
        const value = text.trim();
        if (!value) return;
        bubble(value, "user");
        messageInput.value = "";
        $("mb-chat-send").disabled = true;

        try {
            const result = await jsonPost("/api/chat", { message: value });
            bubble(result.reply);
            quickReplies(result.options || []);
            if (result.action) showMode(result.action);
        } catch (error) {
            bubble(error.message);
        } finally {
            $("mb-chat-send").disabled = false;
        }
    }

    compose.addEventListener("submit", event => {
        event.preventDefault();
        sendMessage(messageInput.value);
    });

    function localISO(offset) {
        const d = new Date();
        d.setDate(d.getDate() + offset);
        return [
            d.getFullYear(),
            String(d.getMonth() + 1).padStart(2, "0"),
            String(d.getDate()).padStart(2, "0")
        ].join("-");
    }

    function resetSlots(hint = "Selecciona una fecha") {
        ++slotVersion;
        slot.replaceChildren(new Option(hint, ""));
        slot.disabled = true;
        bookButton.disabled = true;
    }

    function updateBookButton() {
        bookButton.disabled = !(
            spec.value
            && pro.value
            && day.value
            && slot.value
            && booking.checkValidity()
        );
    }

    async function startBooking() {
        booking.reset();
        bookingStatus.textContent = "";
        day.min = localISO(1);
        day.max = localISO(14);
        pro.disabled = true;
        day.disabled = true;
        resetSlots();
        spec.replaceChildren(
            new Option("Cargando especialidades...", "")
        );

        try {
            const result = await api("/api/specialties");
            if (mode !== "booking") return;
            spec.replaceChildren(
                new Option("Selecciona especialidad", "")
            );
            (result.data || []).forEach(item => {
                spec.add(new Option(
                    `${item.name} · $${Number(item.price).toFixed(2)} MXN`,
                    item.id
                ));
            });
        } catch (error) {
            bookingStatus.textContent = error.message;
        }
    }

    spec.addEventListener("change", async () => {
        const request = ++proVersion;
        ++slotVersion;
        pro.replaceChildren(new Option("Selecciona profesional", ""));
        pro.disabled = true;
        day.value = "";
        day.disabled = true;
        resetSlots();
        if (!spec.value) return;

        try {
            const result = await api(
                `/api/professionals/${encodeURIComponent(spec.value)}`
            );
            if (request !== proVersion || mode !== "booking") return;
            (result.data || []).forEach(item => {
                pro.add(new Option(item.full_name, item.id));
            });
            pro.disabled = false;
        } catch (error) {
            bookingStatus.textContent = error.message;
        }
    });

    pro.addEventListener("change", () => {
        day.value = "";
        day.disabled = !pro.value;
        resetSlots();
    });

    day.addEventListener("change", async () => {
        const request = ++slotVersion;
        slot.replaceChildren(
            new Option("Consultando disponibilidad...", "")
        );
        slot.disabled = true;
        updateBookButton();
        if (!day.value || !pro.value) return;

        if (
            day.value < day.min
            || day.value > day.max
            || new Date(`${day.value}T12:00:00`).getDay() === 0
        ) {
            bookingStatus.textContent =
                "Selecciona una fecha válida de lunes a sábado.";
            return;
        }

        try {
            const query = new URLSearchParams({
                professional_id: pro.value,
                appointment_date: day.value
            });
            const result = await api(`/api/schedules?${query}`);
            if (request !== slotVersion || mode !== "booking") return;

            slot.replaceChildren(
                new Option("Selecciona horario", "")
            );
            (result.data || []).forEach(item => {
                slot.add(new Option(
                    `${item.start_time} - ${item.end_time}`,
                    item.id
                ));
            });
            slot.disabled = !(result.data || []).length;
            bookingStatus.textContent = slot.disabled
                ? "No hay turnos libres para esta fecha."
                : "";
        } catch (error) {
            bookingStatus.textContent = error.message;
        }
    });

    booking.addEventListener("input", updateBookButton);
    booking.addEventListener("change", updateBookButton);

    booking.addEventListener("submit", async event => {
        event.preventDefault();
        if (!booking.reportValidity() || !slot.value) return;
        bookButton.disabled = true;

        try {
            const result = await jsonPost("/api/appointments", {
                schedule_id: Number(slot.value),
                full_name: $("mb-chat-name").value.trim(),
                email: $("mb-chat-email").value.trim(),
                phone: $("mb-chat-phone").value.trim(),
                source: "chatbot"
            });
            bubble(
                `Reservación confirmada. Tu folio es ` +
                `${result.folio}. Guárdalo para futuras consultas.`
            );
            showMode(null);
            booking.reset();
        } catch (error) {
            bookingStatus.textContent = error.message;
            if (/disponible|ocupad/i.test(error.message)) {
                day.dispatchEvent(new Event("change"));
            }
        } finally {
            updateBookButton();
        }
    });

    verify.addEventListener("submit", async event => {
        event.preventDefault();
        if (!verify.reportValidity()) return;
        const action = mode;
        if (action !== "lookup" && action !== "cancel") return;

        const folio = $("mb-chat-folio").value.trim().toUpperCase();
        if (
            action === "cancel"
            && !window.confirm(`¿Cancelar la reservación ${folio}?`)
        ) return;

        proofButton.disabled = true;
        proofStatus.textContent = "Validando datos...";

        try {
            const result = await jsonPost(
                `/api/chat/appointments/${action}`,
                {
                    folio,
                    email: $("mb-chat-proof-email").value.trim(),
                    phone: $("mb-chat-proof-phone").value.trim()
                }
            );

            if (action === "lookup") {
                const appointment = result.data;
                bubble(
                    `Folio: ${appointment.folio}\n` +
                    `Estado: ${
                        appointment.status === "confirmed"
                            ? "Confirmada"
                            : "Cancelada"
                    }\n` +
                    `Servicio: ${appointment.specialty}\n` +
                    `Profesional: ${appointment.professional}\n` +
                    `Fecha y hora: ${appointment.date}, ${appointment.time}`
                );
            } else {
                bubble(result.message);
            }
            showMode(null);
            verify.reset();
        } catch (error) {
            proofStatus.textContent = error.message;
        } finally {
            proofButton.disabled = false;
        }
    });
});

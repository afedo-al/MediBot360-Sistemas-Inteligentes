document.addEventListener("DOMContentLoaded", () => {

    const form = document.getElementById("appointment-form");

    const specialtySelect = document.getElementById("specialty");
    const professionalSelect = document.getElementById("professional");
    const dateInput = document.getElementById("appointment-date");
    const scheduleSelect = document.getElementById("schedule");

    const fullNameInput = document.getElementById("full-name");
    const emailInput = document.getElementById("email");
    const phoneInput = document.getElementById("phone");

    const selectedSpecialty = document.getElementById("selected-specialty");
    const selectedPrice = document.getElementById("selected-price");

    const scheduleHelp = document.getElementById("schedule-help");

    const submitButton = document.getElementById("submit-booking");

    const feedback = document.getElementById("form-feedback");

    const confirmationCard = document.getElementById("confirmation-card");
    const confirmationFolio = document.getElementById("confirmation-folio");
    const confirmationMessage = document.getElementById("confirmation-message");

    const copyFolioButton = document.getElementById("copy-folio");
    const newBookingButton = document.getElementById("new-booking");

    let specialties = [];
    let schedules = [];


    // Fechas locales: la disponibilidad se genera desde mañana.

    function localDateISO(daysToAdd = 0) {

        const currentDate = new Date();

        currentDate.setDate(currentDate.getDate() + daysToAdd);

        const year = currentDate.getFullYear();
        const month = String(currentDate.getMonth() + 1).padStart(2, "0");
        const day = String(currentDate.getDate()).padStart(2, "0");

        return `${year}-${month}-${day}`;
    }


    // Configuración del selector de fechas.

    dateInput.min = localDateISO(1);
    dateInput.max = localDateISO(14);


    // Mensajes del formulario.

    function showFeedback(message, type = "error") {

        feedback.textContent = message;

        feedback.className = `form-feedback ${type}`;

        feedback.hidden = false;
    }


    function hideFeedback() {

        feedback.hidden = true;

        feedback.textContent = "";

        feedback.className = "form-feedback";
    }


    // Petición reutilizable al backend.

    async function apiRequest(url, options = {}) {

        const response = await fetch(url, options);

        let result;

        try {
            result = await response.json();
        } catch {
            throw new Error("El servidor devolvió una respuesta inválida.");
        }

        if (!response.ok) {

            throw new Error(
                result.detail ||
                result.message ||
                "Ocurrió un error al comunicarse con el servidor."
            );
        }

        return result;
    }


    // Limpiar los controles dependientes.

    function resetProfessional() {

        professionalSelect.innerHTML =
            '<option value="">Primero selecciona una especialidad</option>';

        professionalSelect.disabled = true;

        resetDateAndSchedule();
    }


    function resetDateAndSchedule() {

        dateInput.value = "";

        dateInput.disabled = true;

        scheduleSelect.innerHTML =
            '<option value="">Selecciona primero un profesional y fecha</option>';

        scheduleSelect.disabled = true;

        schedules = [];

        scheduleHelp.textContent =
            "Los horarios se actualizarán según la disponibilidad.";

        updateSubmitButton();
    }


    function updateSubmitButton() {

        submitButton.disabled = !(
            specialtySelect.value &&
            professionalSelect.value &&
            dateInput.value &&
            scheduleSelect.value
        );
    }


    // 1. Cargar especialidades.

    async function loadSpecialties() {

        specialtySelect.innerHTML =
            '<option value="">Cargando especialidades...</option>';

        try {

            const result = await apiRequest("/api/specialties");

            specialties = result.data || [];

            specialtySelect.innerHTML =
                '<option value="">Selecciona una especialidad</option>';

            specialties.forEach(specialty => {

                const option = document.createElement("option");

                option.value = specialty.id;

                option.textContent = specialty.name;

                specialtySelect.appendChild(option);

            });

            if (specialties.length === 0) {

                specialtySelect.innerHTML =
                    '<option value="">No hay especialidades disponibles</option>';
            }

        } catch (error) {

            specialtySelect.innerHTML =
                '<option value="">Error al cargar especialidades</option>';

            showFeedback(error.message);
        }
    }


    // 2. Consultar profesionales según la especialidad.

    specialtySelect.addEventListener("change", async () => {

        hideFeedback();

        resetProfessional();

        const specialtyId = specialtySelect.value;

        if (!specialtyId) {

            selectedSpecialty.textContent = "Sin seleccionar";

            selectedPrice.textContent = "—";

            return;
        }

        const selected = specialties.find(
            item => String(item.id) === String(specialtyId)
        );

        if (selected) {

            selectedSpecialty.textContent = selected.name;

            selectedPrice.textContent =
                `$${Number(selected.price).toFixed(2)} MXN`;
        }

        professionalSelect.disabled = true;

        professionalSelect.innerHTML =
            '<option value="">Cargando profesionales...</option>';

        try {

            const result = await apiRequest(
                `/api/professionals/${specialtyId}`
            );

            professionalSelect.innerHTML =
                '<option value="">Selecciona un profesional</option>';

            const professionals = result.data || [];

            professionals.forEach(professional => {

                const option = document.createElement("option");

                option.value = professional.id;

                option.textContent = professional.full_name;

                professionalSelect.appendChild(option);

            });

            if (professionals.length === 0) {

                professionalSelect.innerHTML =
                    '<option value="">No hay profesionales disponibles</option>';

                showFeedback(
                    "Actualmente no hay profesionales disponibles para esta especialidad."
                );

                return;
            }

            professionalSelect.disabled = false;

        } catch (error) {

            professionalSelect.innerHTML =
                '<option value="">No se pudieron cargar los profesionales</option>';

            showFeedback(error.message);
        }

    });


    // 3. Habilitar fechas al seleccionar profesional.

    professionalSelect.addEventListener("change", () => {

        hideFeedback();

        resetDateAndSchedule();

        if (professionalSelect.value) {

            dateInput.disabled = false;

            scheduleHelp.textContent =
                "Selecciona una fecha para consultar los horarios.";
        }

        updateSubmitButton();
    });


    // 4. Consultar disponibilidad de horarios.

    async function loadSchedules() {

        hideFeedback();

        scheduleSelect.disabled = true;

        scheduleSelect.innerHTML =
            '<option value="">Consultando disponibilidad...</option>';

        schedules = [];

        const professionalId = professionalSelect.value;

        const appointmentDate = dateInput.value;

        updateSubmitButton();

        if (!professionalId || !appointmentDate) {

            scheduleSelect.innerHTML =
                '<option value="">Selecciona profesional y fecha</option>';

            return;
        }

        // Validar que la fecha esté dentro del periodo generado.

        if (
            appointmentDate < dateInput.min ||
            appointmentDate > dateInput.max
        ) {

            scheduleSelect.innerHTML =
                '<option value="">Fecha fuera del periodo disponible</option>';

            showFeedback(
                "Selecciona una fecha dentro del periodo de disponibilidad."
            );

            return;
        }

        try {

            const params = new URLSearchParams({
                professional_id: professionalId,
                appointment_date: appointmentDate
            });

            const result = await apiRequest(
                `/api/schedules?${params.toString()}`
            );

            schedules = result.data || [];

            scheduleSelect.innerHTML =
                '<option value="">Selecciona un horario</option>';

            if (schedules.length === 0) {

                scheduleSelect.innerHTML =
                    '<option value="">No hay horarios disponibles</option>';

                scheduleHelp.textContent =
                    "No se encontraron horarios para la fecha seleccionada.";

                return;
            }

            schedules.forEach(schedule => {

                const option = document.createElement("option");

                option.value = schedule.id;

                option.textContent =
                    `${schedule.start_time} - ${schedule.end_time}`;

                scheduleSelect.appendChild(option);

            });

            scheduleSelect.disabled = false;

            scheduleHelp.textContent =
                `${schedules.length} horarios disponibles para esta fecha.`;

        } catch (error) {

            scheduleSelect.innerHTML =
                '<option value="">Error al consultar horarios</option>';

            showFeedback(error.message);

        }

        updateSubmitButton();
    }


    dateInput.addEventListener("change", loadSchedules);


    scheduleSelect.addEventListener("change", () => {

        hideFeedback();

        updateSubmitButton();

    });


    // 5. Registrar una reservación.

    form.addEventListener("submit", async event => {

        event.preventDefault();

        hideFeedback();

        if (!form.checkValidity()) {

            form.reportValidity();

            return;
        }

        const selectedSchedule = schedules.find(
            item => String(item.id) === String(scheduleSelect.value)
        );

        if (!selectedSchedule) {

            showFeedback("Selecciona un horario válido.");

            return;
        }

        const payload = {

            schedule_id: Number(selectedSchedule.id),

            full_name: fullNameInput.value.trim(),

            email: emailInput.value.trim(),

            phone: phoneInput.value.trim()

        };


        submitButton.disabled = true;

        submitButton.textContent = "Procesando reservación...";


        try {

            const result = await apiRequest(
                "/api/appointments",
                {
                    method: "POST",

                    headers: {
                        "Content-Type": "application/json"
                    },

                    body: JSON.stringify(payload)
                }
            );


            if (result.success === false) {

                throw new Error(
                    result.message || "No fue posible confirmar la reservación."
                );
            }


            // Compatible con la respuesta plana y con la respuesta
            // que contiene un objeto data del backend.

            const appointment = result.data || result;

            const folio = appointment.folio;

            if (!folio) {

                throw new Error(
                    "La reservación fue procesada, pero el servidor no devolvió un folio."
                );
            }


            // Mostrar confirmación.

            confirmationFolio.textContent = folio;

            confirmationMessage.textContent =
                result.message || "Tu reservación se registró correctamente.";

            confirmationCard.hidden = false;

            showFeedback(
                "La reservación se confirmó correctamente.",
                "success"
            );

            copyFolioButton.focus();


            // Actualizar la interfaz para una nueva reservación.

            form.reset();

            specialtySelect.value = "";

            selectedSpecialty.textContent = "Sin seleccionar";

            selectedPrice.textContent = "—";

            resetProfessional();

            submitButton.textContent = "Confirmar reservación →";

        } catch (error) {

            showFeedback(error.message);

            submitButton.textContent = "Confirmar reservación →";

        } finally {

            updateSubmitButton();

            if (!submitButton.disabled) {
                submitButton.textContent = "Confirmar reservación →";
            }

        }

    });


    // 6. Copiar folio.

    copyFolioButton.addEventListener("click", async () => {

        const folio = confirmationFolio.textContent;

        try {

            await navigator.clipboard.writeText(folio);

            copyFolioButton.textContent = "¡Folio copiado!";

        } catch {

            copyFolioButton.textContent =
                "No se pudo copiar el folio";

        }

    });


    // 7. Realizar otra reservación.

    newBookingButton.addEventListener("click", () => {

        confirmationCard.hidden = true;

        hideFeedback();

        form.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });

        submitButton.textContent = "Confirmar reservación →";

        updateSubmitButton();

    });


    // 8. Cerrar la confirmación con Escape.

    document.addEventListener("keydown", (event) => {

        if (
            event.key === "Escape" &&
            !confirmationCard.hidden
        ) {
            confirmationCard.hidden = true;
        }

    });


    // Inicializar formulario y recuperar especialidad seleccionada.

    async function initializeBooking() {

        await loadSpecialties();

        const params = new URLSearchParams(window.location.search);

        const specialtyId = params.get("specialty_id");

        if (!specialtyId) return;

        const specialtyExists = specialties.some(
            specialty => String(specialty.id) === specialtyId
        );

        if (!specialtyExists) return;

        specialtySelect.value = specialtyId;

        specialtySelect.dispatchEvent(
            new Event("change")
        );

    }

    initializeBooking();

});
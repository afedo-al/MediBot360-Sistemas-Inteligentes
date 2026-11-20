document.addEventListener("DOMContentLoaded", () => {

    const $ = id => document.getElementById(id);

    const title = $("mb-cal-title");
    const grid = $("mb-cal-grid");
    const count = $("mb-cal-count");
    const professional = $("mb-cal-professional");
    const detail = $("mb-cal-detail");
    const exportBtn = $("mb-cal-export");

    if (!title || !grid || !count || !professional || !detail || !exportBtn) return;

    const monthFormat = new Intl.DateTimeFormat("es-MX", {month: "long", year: "numeric"});
    const fullFormat = new Intl.DateTimeFormat("es-MX", {
        weekday: "long", day: "numeric", month: "long", year: "numeric"
    });
    const shortFormat = new Intl.DateTimeFormat("es-MX", {day: "numeric", month: "short"});

    const pad = n => String(n).padStart(2, "0");
    const iso = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
    const monday = d => addDays(d, -((d.getDay() + 6) % 7));
    const startOfToday = () => {
        const now = new Date();
        return new Date(now.getFullYear(), now.getMonth(), now.getDate());
    };

    let cursor = startOfToday();
    let view = "month";
    let events = [];
    let requestId = 0;

    function getRange() {
        if (view === "day") return {start: cursor, end: cursor};

        if (view === "week") {
            const start = monday(cursor);
            return {start, end: addDays(start, 6)};
        }

        const start = monday(new Date(cursor.getFullYear(), cursor.getMonth(), 1));
        return {start, end: addDays(start, 41)};
    }

    function setTitle(range) {
        if (view === "day") {
            title.textContent = fullFormat.format(cursor);
        } else if (view === "week") {
            title.textContent =
                `${shortFormat.format(range.start)} — ${shortFormat.format(range.end)} ${range.end.getFullYear()}`;
        } else {
            title.textContent = monthFormat.format(cursor);
        }
    }

    function make(tag, cls, text) {
        const node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function openDetail(e) {
        detail.replaceChildren();
        detail.appendChild(make("h3", "", e.customer_name));

        const status = e.status === "confirmed" ? "Confirmada" : "Cancelada";

        [
            `Folio: ${e.folio}`,
            `Estado: ${status}`,
            `Especialidad: ${e.specialty_name}`,
            `Profesional: ${e.professional_name}`,
            `Fecha: ${e.appointment_date}`,
            `Horario: ${e.start_time} - ${e.end_time}`
        ].forEach(value => detail.appendChild(make("p", "", value)));

        const link = make("a", "mb-cal-open", "Abrir reservación en ERP →");
        link.href = `/admin/reservaciones?search=${encodeURIComponent(e.folio)}`;
        detail.appendChild(link);

        detail.hidden = false;
        detail.scrollIntoView({block: "nearest", behavior: "smooth"});
    }

    function chip(e) {
        const button = make(
            "button",
            `mb-cal-event ${e.status}`,
            `${e.start_time} · ${e.customer_name}`
        );
        button.type = "button";
        button.title = `${e.folio} · ${e.specialty_name} · ${e.professional_name}`;
        button.addEventListener("click", event => {
            event.stopPropagation();
            openDetail(e);
        });
        return button;
    }

    function render() {
        grid.replaceChildren();
        detail.hidden = true;

        const range = getRange();
        setTitle(range);

        const confirmed = events.filter(e => e.status === "confirmed").length;
        count.textContent =
            `${events.length} cita(s) en el periodo · ${confirmed} confirmada(s)`;

        grid.className = `mb-cal-grid mb-cal-view-${view}`;

        const byDate = new Map();
        events.forEach(e => {
            if (!byDate.has(e.appointment_date)) byDate.set(e.appointment_date, []);
            byDate.get(e.appointment_date).push(e);
        });

        const todayKey = iso(startOfToday());

        if (view === "month") {
            ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"].forEach(label => {
                grid.appendChild(make("div", "mb-cal-weekday", label));
            });

            for (let i = 0; i < 42; i++) {
                const d = addDays(range.start, i);
                const key = iso(d);
                const cell = make("div", "mb-cal-day");

                if (d.getMonth() !== cursor.getMonth()) cell.classList.add("muted");
                if (key === todayKey) cell.classList.add("today");

                const dateBtn = make("button", "mb-cal-day-number", String(d.getDate()));
                dateBtn.type = "button";
                dateBtn.setAttribute("aria-label", `Ver ${fullFormat.format(d)}`);
                dateBtn.addEventListener("click", () => {
                    cursor = d;
                    view = "day";
                    syncView();
                    load();
                });
                cell.appendChild(dateBtn);

                const dayEvents = byDate.get(key) || [];
                dayEvents.slice(0, 3).forEach(e => cell.appendChild(chip(e)));

                if (dayEvents.length > 3) {
                    const more = make("button", "mb-cal-more", `+${dayEvents.length - 3} más`);
                    more.type = "button";
                    more.addEventListener("click", () => {
                        cursor = d;
                        view = "day";
                        syncView();
                        load();
                    });
                    cell.appendChild(more);
                }

                grid.appendChild(cell);
            }
            return;
        }

        const total = view === "week" ? 7 : 1;

        for (let i = 0; i < total; i++) {
            const d = addDays(range.start, i);
            const key = iso(d);
            const col = make("section", "mb-cal-column");

            if (key === todayKey) col.classList.add("today");

            col.appendChild(make("h3", "", fullFormat.format(d)));

            const items = byDate.get(key) || [];

            if (!items.length) {
                col.appendChild(make("p", "mb-cal-empty", "Sin reservaciones para este día."));
            }

            items.forEach(e => col.appendChild(chip(e)));
            grid.appendChild(col);
        }
    }

    async function load() {
        const current = ++requestId;
        const range = getRange();

        count.textContent = "Cargando agenda...";
        setTitle(range);

        const params = new URLSearchParams({start: iso(range.start), end: iso(range.end)});
        if (professional.value) params.set("professional_id", professional.value);

        try {
            const response = await fetch(`/api/admin/calendar?${params}`, {cache: "no-store"});

            if (response.status === 401) {
                window.location.replace("/admin/login");
                return;
            }

            const result = await response.json();

            if (!response.ok) {
                throw new Error(
                    typeof result.detail === "string"
                        ? result.detail
                        : "No se pudo cargar la agenda."
                );
            }

            if (current !== requestId) return;

            events = result.data || [];
            render();
        } catch (error) {
            if (current === requestId) count.textContent = error.message;
        }
    }

    function syncView() {
        document.querySelectorAll("[data-cal-view]").forEach(button => {
            const active = button.dataset.calView === view;
            button.classList.toggle("active", active);
            button.setAttribute("aria-pressed", String(active));
        });
    }

    document.querySelectorAll("[data-cal-view]").forEach(button => {
        button.addEventListener("click", () => {
            view = button.dataset.calView;
            syncView();
            load();
        });
    });

    function move(direction) {
        if (view === "month") {
            cursor = new Date(cursor.getFullYear(), cursor.getMonth() + direction, 1);
        } else {
            cursor = addDays(cursor, (view === "week" ? 7 : 1) * direction);
        }
        load();
    }

    $("mb-cal-prev").addEventListener("click", () => move(-1));
    $("mb-cal-next").addEventListener("click", () => move(1));
    $("mb-cal-today").addEventListener("click", () => {
        cursor = startOfToday();
        load();
    });

    professional.addEventListener("change", load);

    exportBtn.addEventListener("click", () => {
        if (!events.length) {
            count.textContent = "No hay citas en el periodo para exportar.";
            return;
        }

        // Evita que las hojas de cálculo interpreten fórmulas.
        const safe = value => {
            let text = String(value ?? "");
            if (/^[\s]*[=+\-@]/.test(text)) text = "'" + text;
            return '"' + text.replaceAll('"', '""') + '"';
        };

        const statusLabel = s => (s === "confirmed" ? "Confirmada" : "Cancelada");

        const lines = [
            ["Folio", "Cliente", "Especialidad", "Profesional", "Fecha", "Inicio", "Fin", "Estado"],
            ...events.map(e => [
                e.folio, e.customer_name, e.specialty_name, e.professional_name,
                e.appointment_date, e.start_time, e.end_time, statusLabel(e.status)
            ])
        ];

        const csv = "﻿" + lines.map(line => line.map(safe).join(",")).join("\r\n");
        const blob = new Blob([csv], {type: "text/csv;charset=utf-8;"});
        const url = URL.createObjectURL(blob);
        const range = getRange();
        const a = document.createElement("a");

        a.href = url;
        a.download = `medibot-agenda-${iso(range.start)}_${iso(range.end)}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    });

    async function loadProfessionals() {
        try {
            const response = await fetch("/api/admin/professionals", {cache: "no-store"});

            if (response.status === 401) {
                window.location.replace("/admin/login");
                return;
            }

            if (!response.ok) throw new Error("No se pudieron cargar los profesionales.");

            const data = await response.json();

            (data.data || []).forEach(p => {
                professional.add(new Option(`${p.full_name} · ${p.specialty_name}`, String(p.id)));
            });
        } catch (error) {
            count.textContent = error.message;
        }
    }

    syncView();
    loadProfessionals().then(load);
});

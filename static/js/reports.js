document.addEventListener("DOMContentLoaded", () => {

    const $ = id => document.getElementById(id);

    const periodSelect = $("report-period");
    const rangeLabel = $("report-range");
    const kpiBox = $("report-kpis");

    if (!periodSelect || !kpiBox) return;

    const money = new Intl.NumberFormat("es-MX", {
        style: "currency", currency: "MXN"
    });

    const INTENTS = {
        emergencia: "Emergencias",
        cancelar: "Cancelar cita",
        consultar: "Consultar cita",
        reservar: "Reservar cita",
        despedida: "Despedidas",
        contacto: "Contacto",
        equipo: "Equipo médico",
        horarios: "Horarios",
        precios: "Precios y servicios",
        saludo: "Saludos",
        no_entendido: "No entendido"
    };

    const SOURCES = {
        web: "Sitio web",
        chatbot: "Chatbot",
        contacto: "Formulario de contacto",
        admin: "Administración"
    };

    const STATUSES = {
        lead: "Prospectos",
        active: "Activos",
        inactive: "Inactivos"
    };

    const STOCK = {available: "Disponible", unavailable: "No disponible"};

    let charts = {};
    let requestId = 0;

    function make(tag, text, cls) {
        const node = document.createElement(tag);
        if (text !== undefined) node.textContent = text;
        if (cls) node.className = cls;
        return node;
    }

    function fillRows(tbody, rows, emptyText, columns) {
        tbody.replaceChildren();

        if (!rows.length) {
            const tr = make("tr");
            const td = make("td", emptyText, "empty-table");
            td.colSpan = columns;
            tr.appendChild(td);
            tbody.appendChild(tr);
            return;
        }

        rows.forEach(cells => {
            const tr = make("tr");
            cells.forEach(cell => {
                const td = make("td");
                if (cell instanceof Node) td.appendChild(cell);
                else td.textContent = String(cell);
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
    }

    function renderKpis(k) {
        const items = [
            ["Citas creadas", k.appointments, `${k.confirmed} confirmadas · ${k.cancelled} canceladas`],
            ["Ingresos cobrados", money.format(k.revenue_paid), "Pagos simulados"],
            ["Por cobrar", money.format(k.receivable), "Citas confirmadas sin pago"],
            ["Reembolsos", money.format(k.revenue_refunded), "Devoluciones simuladas"],
            ["Clientes nuevos", k.new_customers, `${k.contact_requests} mensajes de contacto`],
            ["Mensajes al chatbot", k.chat_messages, "Conversaciones registradas"]
        ];

        kpiBox.replaceChildren();

        items.forEach(([name, value, note]) => {
            const card = make("article", undefined, "mb-report-kpi");
            card.append(make("span", name), make("strong", String(value)), make("small", note));
            kpiBox.appendChild(card);
        });
    }

    function drawChart(key, canvasId, labels, values, color) {
        const canvas = $(canvasId);
        if (!canvas || typeof Chart === "undefined") return;

        if (charts[key]) charts[key].destroy();

        charts[key] = new Chart(canvas, {
            type: "bar",
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: color,
                    borderRadius: 8,
                    maxBarThickness: 34
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {legend: {display: false}},
                scales: {
                    y: {beginAtZero: true, ticks: {precision: 0}},
                    x: {grid: {display: false}}
                }
            }
        });
    }

    function render(data) {
        const {period, kpis} = data;

        rangeLabel.textContent = `${period.start} al ${period.end}`;
        renderKpis(kpis);

        drawChart(
            "specialties", "chart-specialties",
            data.specialties.map(s => s.name),
            data.specialties.map(s => s.confirmed + s.cancelled),
            "#4168f5"
        );

        drawChart(
            "intents", "chart-intents",
            data.chatbot_intents.map(i => INTENTS[i.intent] || i.intent),
            data.chatbot_intents.map(i => i.total),
            "#2bb8c9"
        );

        fillRows(
            $("report-specialties"),
            data.specialties.map(s => [
                s.name, s.confirmed, s.cancelled, money.format(s.revenue)
            ]),
            "Sin datos en el periodo.", 4
        );

        fillRows(
            $("report-sources"),
            data.customers_by_source.map(s => [SOURCES[s.source] || s.source, s.total]),
            "Sin clientes nuevos en el periodo.", 2
        );

        fillRows(
            $("report-statuses"),
            data.customers_by_status.map(s => [STATUSES[s.status] || s.status, s.total]),
            "Sin clientes registrados.", 2
        );

        $("report-threshold").textContent = String(data.low_stock_threshold);

        fillRows(
            $("report-inventory"),
            data.inventory.map(r => [
                r.name,
                r.quantity,
                STOCK[r.status] || r.status,
                r.low ? make("span", "Existencias bajas", "mb-low-stock") : "—"
            ]),
            "Aún no hay recursos registrados.", 4
        );
    }

    async function load() {
        const current = ++requestId;
        rangeLabel.textContent = "Consultando...";

        try {
            const response = await fetch(
                `/api/admin/reports?days=${encodeURIComponent(periodSelect.value)}`,
                {cache: "no-store"}
            );

            if (response.status === 401) {
                window.location.replace("/admin/login");
                return;
            }

            const result = await response.json();

            if (!response.ok) {
                throw new Error(
                    typeof result.detail === "string"
                        ? result.detail
                        : "No se pudo cargar el reporte."
                );
            }

            if (current !== requestId) return;
            render(result);
        } catch (error) {
            if (current === requestId) rangeLabel.textContent = error.message;
        }
    }

    periodSelect.addEventListener("change", load);
    load();
});

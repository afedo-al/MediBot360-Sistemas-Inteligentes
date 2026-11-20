document.addEventListener("DOMContentLoaded", () => {
    const $ = id => document.getElementById(id);
    const period = $("analytics-period");
    const refreshButton = $("analytics-refresh");
    const feedback = $("analytics-feedback");

    if (!period || !refreshButton || !feedback) return;

    const charts = [];
    let requestVersion = 0;
    const money = value => new Intl.NumberFormat("es-MX", {
        style: "currency",
        currency: "MXN"
    }).format(Number(value || 0));

    function showMessage(message, error = false) {
        feedback.textContent = message;
        feedback.className = error
            ? "analytics-feedback error"
            : "analytics-feedback";
    }

    function formatDay(isoDate) {
        const parts = isoDate.split("-");
        return `${parts[2]}/${parts[1]}`;
    }

    async function getAnalytics(days) {
        const response = await fetch(
            `/api/admin/dashboard/analytics?days=${days}`,
            { cache: "no-store" }
        );
        if (response.status === 401) {
            window.location.replace("/admin/login");
            throw new Error("Sesión administrativa expirada.");
        }
        const result = await response.json();
        if (!response.ok) {
            throw new Error(
                typeof result.detail === "string"
                    ? result.detail
                    : "No fue posible consultar las estadísticas."
            );
        }
        return result;
    }

    function updateIndicators(summary) {
        $("kpi-new-customers").textContent = summary.new_customers;
        $("kpi-new-appointments").textContent = summary.new_appointments;
        $("kpi-cancelled").textContent = summary.cancelled;
        $("kpi-paid").textContent = money(summary.paid_amount);
    }

    const colors = {
        blue: "#1769e0",
        blueLight: "rgba(23, 105, 224, 0.12)",
        green: "#2caa79",
        purple: "#8c72dc",
        orange: "#e3a04b",
        text: "#687486",
        grid: "#eef1f6"
    };

    function cartesianOptions(currency = false) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 350 },
            interaction: { intersect: false, mode: "index" },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: "#182335",
                    padding: 12,
                    callbacks: currency ? {
                        label: context => money(context.parsed.y)
                    } : {}
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: {
                        color: colors.text,
                        maxTicksLimit: 8,
                        maxRotation: 0
                    },
                    border: { display: false }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: colors.grid },
                    ticks: {
                        color: colors.text,
                        ...(currency ? {
                            callback: value =>
                                "$" + Number(value).toLocaleString("es-MX")
                        } : { precision: 0 })
                    },
                    border: { display: false }
                }
            }
        };
    }

    function createChart(id, config) {
        const canvas = $(id);
        if (!canvas) return;
        charts.push(new Chart(canvas, config));
    }

    function clearCharts() {
        charts.forEach(chart => chart.destroy());
        charts.length = 0;
    }

    function drawCharts(data) {
        clearCharts();
        const dates = data.charts.dates.map(formatDay);

        createChart("chart-appointments", {
            type: "line",
            data: {
                labels: dates,
                datasets: [{
                    label: "Reservaciones",
                    data: data.charts.appointments,
                    borderColor: colors.blue,
                    backgroundColor: colors.blueLight,
                    borderWidth: 3,
                    tension: 0.35,
                    pointRadius: 2,
                    pointHoverRadius: 5,
                    fill: true
                }]
            },
            options: cartesianOptions()
        });

        createChart("chart-customers", {
            type: "bar",
            data: {
                labels: dates,
                datasets: [{
                    label: "Clientes nuevos",
                    data: data.charts.customers,
                    backgroundColor: colors.green,
                    borderRadius: 5,
                    maxBarThickness: 22
                }]
            },
            options: cartesianOptions()
        });

        const specialties = data.charts.specialties;
        createChart("chart-specialties", {
            type: "bar",
            data: {
                labels: specialties.length
                    ? specialties.map(item => item.name)
                    : ["Sin reservaciones"],
                datasets: [{
                    label: "Reservaciones",
                    data: specialties.length
                        ? specialties.map(item => item.total)
                        : [0],
                    backgroundColor: [
                        colors.blue,
                        colors.purple,
                        colors.green,
                        colors.orange,
                        "#6da9e7",
                        "#9bb0c8"
                    ],
                    borderRadius: 6,
                    maxBarThickness: 35
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: "y",
                plugins: {
                    legend: { display: false },
                    tooltip: { backgroundColor: "#182335", padding: 12 }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        grid: { color: colors.grid },
                        ticks: { precision: 0, color: colors.text }
                    },
                    y: {
                        grid: { display: false },
                        ticks: { color: colors.text }
                    }
                }
            }
        });

        createChart("chart-payments", {
            type: "line",
            data: {
                labels: dates,
                datasets: [{
                    label: "Cobros simulados vigentes",
                    data: data.charts.payments,
                    borderColor: colors.purple,
                    backgroundColor: "rgba(140, 114, 220, 0.12)",
                    borderWidth: 3,
                    tension: 0.35,
                    pointRadius: 2,
                    pointHoverRadius: 5,
                    fill: true
                }]
            },
            options: cartesianOptions(true)
        });
    }

    async function loadDashboard() {
        const currentRequest = ++requestVersion;
        refreshButton.disabled = true;
        refreshButton.textContent = "Actualizando...";
        showMessage("Consultando estadísticas de MediBot 360...");

        try {
            const result = await getAnalytics(Number(period.value));
            if (currentRequest !== requestVersion) return;
            updateIndicators(result.summary);

            if (typeof Chart === "undefined") {
                showMessage(
                    "Los indicadores se cargaron, pero Chart.js no está disponible.",
                    true
                );
                return;
            }

            drawCharts(result);
            showMessage(
                `Datos actualizados · ${result.period.start} al ` +
                `${result.period.end} · ${result.period.days} días`
            );
        } catch (error) {
            if (currentRequest === requestVersion) {
                showMessage(error.message, true);
                console.error("Dashboard MediBot 360:", error);
            }
        } finally {
            if (currentRequest === requestVersion) {
                refreshButton.disabled = false;
                refreshButton.textContent = "Actualizar";
            }
        }
    }

    period.addEventListener("change", loadDashboard);
    refreshButton.addEventListener("click", loadDashboard);
    loadDashboard();
});

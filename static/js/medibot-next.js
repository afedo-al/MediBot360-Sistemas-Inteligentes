document.addEventListener("DOMContentLoaded", () => {

    const page = document.body;
    const isAdmin = page.classList.contains("dashboard-page");

    // ===== SITIO PÚBLICO Y LOGIN =====

    if (!isAdmin) {
        document.querySelectorAll('a[href="/"]').forEach(a => {
            a.href = "/sitio";
        });

        const nav = document.querySelector(".navbar, .booking-header");

        if (nav && !nav.querySelector(".mb-public-admin")) {
            const link = document.createElement("a");
            link.href = "/admin";
            link.className = "mb-public-admin";
            link.textContent = "Panel interno";
            nav.appendChild(link);
        }

        return;
    }

    // ===== NAVEGACIÓN UNIFICADA =====

    const routes = [
        {label: "Inicio", icon: "◈", href: "/admin", match: p => p === "/admin"},
        {label: "Calendario", icon: "▦", href: "/admin/calendario", match: p => p === "/admin/calendario"},
        {label: "Reservaciones", icon: "◷", href: "/admin/reservaciones", match: p => p.startsWith("/admin/reservaciones")},
        {label: "Clientes", icon: "♙", href: "/admin/clientes", match: p => p.startsWith("/admin/clientes")},
        {label: "Especialidades y personal", icon: "✚", href: "/admin/catalogo", match: p => p.startsWith("/admin/catalogo")},
        {label: "Horarios", icon: "▤", href: "/admin/horarios", match: p => p === "/admin/horarios"},
        {label: "Pagos y recursos", icon: "◇", href: "/admin/operaciones", match: p => p === "/admin/operaciones"},
        {label: "Análisis y reportes", icon: "▥", href: "/admin/reportes", match: p => p.startsWith("/admin/reportes")},
        {label: "Ver sitio público", icon: "↗", href: "/sitio", match: () => false}
    ];

    const path = location.pathname.replace(/\/+$/, "") || "/";
    const nav = document.querySelector(".admin-navigation");

    if (nav) {
        const fragment = document.createDocumentFragment();

        routes.forEach(route => {
            const a = document.createElement("a");
            const active = route.match(path);

            a.href = route.href;
            a.className = "nav-item" + (active ? " active" : "");
            if (active) a.setAttribute("aria-current", "page");
            if (route.href === "/sitio") a.classList.add("mb-site-link");

            const symbol = document.createElement("span");
            symbol.textContent = route.icon;
            symbol.setAttribute("aria-hidden", "true");

            a.append(symbol, document.createTextNode(route.label));
            fragment.appendChild(a);
        });

        nav.replaceChildren(fragment);
    }

    const header = document.querySelector(".admin-topbar");
    if (!header) return;

    document.querySelectorAll('a[href="/"]').forEach(a => {
        a.href = "/sitio";
    });

    // ===== ACCIONES SUPERIORES =====

    const controls = document.createElement("div");
    controls.className = "mb-top-actions";

    const searchBtn = document.createElement("button");
    searchBtn.type = "button";
    searchBtn.className = "mb-icon-action mb-command-btn";
    searchBtn.textContent = "⌕  Buscar  Ctrl+K";
    searchBtn.title = "Navegación rápida (Ctrl + K)";
    searchBtn.setAttribute("aria-label", "Buscar módulo");

    const alertBtn = document.createElement("button");
    alertBtn.type = "button";
    alertBtn.className = "mb-icon-action mb-alert-btn";
    alertBtn.setAttribute("aria-expanded", "false");
    alertBtn.setAttribute("aria-label", "Centro de avisos");

    const alertLabel = document.createElement("span");
    alertLabel.textContent = "◔ Avisos";

    const alertBadge = document.createElement("span");
    alertBadge.className = "mb-alert-badge";
    alertBadge.hidden = true;

    alertBtn.append(alertLabel, alertBadge);
    controls.append(searchBtn, alertBtn);
    header.appendChild(controls);

    // ===== MENÚ RESPONSIVE =====

    const navBtn = document.createElement("button");
    navBtn.type = "button";
    navBtn.className = "mb-mobile-menu";
    navBtn.textContent = "☰";
    navBtn.setAttribute("aria-label", "Abrir navegación");
    navBtn.setAttribute("aria-expanded", "false");
    header.prepend(navBtn);

    const shade = document.createElement("button");
    shade.className = "mb-nav-shade";
    shade.type = "button";
    shade.tabIndex = -1;
    shade.setAttribute("aria-label", "Cerrar navegación");
    page.appendChild(shade);

    const setNav = open => {
        page.classList.toggle("mb-nav-open", open);
        navBtn.setAttribute("aria-expanded", String(open));
    };

    navBtn.addEventListener("click", () => setNav(!page.classList.contains("mb-nav-open")));
    shade.addEventListener("click", () => setNav(false));

    // ===== CENTRO DE AVISOS =====

    const drawer = document.createElement("section");
    drawer.className = "mb-notifications";
    drawer.hidden = true;
    drawer.setAttribute("role", "region");
    drawer.setAttribute("aria-label", "Centro de avisos");

    const drawerTitle = document.createElement("h3");
    drawerTitle.textContent = "Centro de avisos";

    const drawerItems = document.createElement("div");
    drawerItems.className = "mb-notification-items";

    drawer.append(drawerTitle, drawerItems);
    page.appendChild(drawer);

    const addNotice = (heading, text, href, tone) => {
        const a = document.createElement("a");
        a.href = href;
        a.className = "mb-notice" + (tone ? ` ${tone}` : "");

        const strong = document.createElement("strong");
        strong.textContent = heading;

        const info = document.createElement("span");
        info.textContent = text;

        a.append(strong, info);
        drawerItems.appendChild(a);
    };

    async function fetchAlerts() {
        const response = await fetch("/api/admin/overview-alerts", {cache: "no-store"});

        if (response.status === 401) {
            window.location.replace("/admin/login");
            throw new Error("Sesión expirada.");
        }

        if (!response.ok) throw new Error("No se pudieron cargar los avisos.");

        return response.json();
    }

    function updateBadge(data) {
        const total =
            data.upcoming.length +
            data.low_stock.length +
            (data.counts.unpaid ? 1 : 0);

        alertBadge.textContent = String(total);
        alertBadge.hidden = total === 0;
    }

    async function loadNotices() {
        drawerItems.replaceChildren();

        const loading = document.createElement("p");
        loading.textContent = "Consultando actividad...";
        drawerItems.appendChild(loading);

        try {
            const data = await fetchAlerts();
            updateBadge(data);
            drawerItems.replaceChildren();

            if (!data.upcoming.length && !data.low_stock.length && !data.counts.unpaid) {
                addNotice("Todo al día", "No hay avisos importantes por el momento.", "/admin");
            }

            data.upcoming.forEach(a => {
                addNotice(
                    "Cita próxima · " + a.folio,
                    `${a.appointment_date} ${a.start_time} · ${a.customer_name}`,
                    "/admin/calendario"
                );
            });

            data.low_stock.forEach(r => {
                addNotice(
                    "Existencias bajas",
                    `${r.name} · ${r.quantity} disponibles`,
                    "/admin/operaciones#recursos",
                    "warning"
                );
            });

            if (data.counts.unpaid) {
                addNotice(
                    "Pagos simulados pendientes",
                    `${data.counts.unpaid} cita(s) confirmada(s) sin pago definitivo`,
                    "/admin/operaciones#pagos",
                    "warning"
                );
            }
        } catch (error) {
            drawerItems.replaceChildren();
            const p = document.createElement("p");
            p.textContent = error.message;
            drawerItems.appendChild(p);
        }
    }

    const closeDrawer = () => {
        drawer.hidden = true;
        alertBtn.setAttribute("aria-expanded", "false");
    };

    alertBtn.addEventListener("click", async event => {
        event.stopPropagation();
        drawer.hidden = !drawer.hidden;
        alertBtn.setAttribute("aria-expanded", String(!drawer.hidden));
        if (!drawer.hidden) await loadNotices();
    });

    document.addEventListener("click", event => {
        if (!drawer.hidden && !drawer.contains(event.target)) closeDrawer();
    });

    fetchAlerts().then(updateBadge).catch(() => {});

    // ===== BUSCADOR DE MÓDULOS (CTRL + K) =====

    const modal = document.createElement("div");
    modal.className = "mb-command-overlay";
    modal.hidden = true;
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-label", "Navegación rápida");

    const box = document.createElement("section");
    box.className = "mb-command-box";

    const input = document.createElement("input");
    input.type = "search";
    input.placeholder = "Escribe el módulo que quieres abrir...";
    input.setAttribute("aria-label", "Buscar módulo");

    const results = document.createElement("div");
    results.className = "mb-command-results";

    const hint = document.createElement("p");
    hint.className = "mb-command-hint";
    hint.textContent = "Enter para abrir · Esc para cerrar";

    box.append(input, results, hint);
    modal.appendChild(box);
    page.appendChild(modal);

    const normalize = text =>
        text.toLocaleLowerCase("es").normalize("NFD").replace(/[̀-ͯ]/g, "");

    function drawCommands() {
        results.replaceChildren();
        const query = normalize(input.value.trim());

        const matches = routes.filter(route => normalize(route.label).includes(query));

        if (!matches.length) {
            const empty = document.createElement("p");
            empty.className = "mb-command-empty";
            empty.textContent = "Sin coincidencias.";
            results.appendChild(empty);
            return;
        }

        matches.forEach(route => {
            const link = document.createElement("a");
            link.href = route.href;
            link.textContent = route.icon + "  " + route.label;
            results.appendChild(link);
        });
    }

    let lastFocus = null;

    function openCommands() {
        lastFocus = document.activeElement;
        modal.hidden = false;
        input.value = "";
        drawCommands();
        input.focus();
    }

    function closeCommands() {
        if (modal.hidden) return;
        modal.hidden = true;
        if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
    }

    searchBtn.addEventListener("click", openCommands);
    input.addEventListener("input", drawCommands);

    input.addEventListener("keydown", event => {
        if (event.key === "Enter") {
            const first = results.querySelector("a");
            if (first) {
                event.preventDefault();
                window.location.assign(first.href);
            }
        }
    });

    modal.addEventListener("click", event => {
        if (event.target === modal) closeCommands();
    });

    document.addEventListener("keydown", event => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
            event.preventDefault();
            if (modal.hidden) openCommands();
            else closeCommands();
        }

        if (event.key === "Escape") {
            closeCommands();
            closeDrawer();
            setNav(false);
        }
    });
});

"use strict";
// Consola administrativa de MediBot 360: navegación, vistas CRM/ERP, paleta de comandos y gráficas SVG.
(function () {
  const $ = id => document.getElementById(id);
  const view = $("view");
  const DAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
  const STAGES = ["prospecto", "contactado", "cliente", "inactivo"];
  const STAGE_COLOR = {prospecto: "#B7791F", contactado: "#7357D9", cliente: "#3766E8", inactivo: "#D64545"};
  const STATUS_COLOR = {confirmada: "#3766E8", completada: "#12936B", cancelada: "#D64545"};
  const PALETTE = ["#3766E8", "#22B8B0", "#7357D9", "#F0A93B", "#E2667A", "#12936B", "#0EA5E9", "#A16207"];
  const CHANNEL = {web: "Sitio web", chatbot: "Asistente", recepcion: "Recepción"};
  const chan = c => CHANNEL[c] || c;
  // Módulos: vista, título, icono, tecla para «G + tecla» y si requiere rol administrador.
  const MODULES = [
    {v: "dashboard", t: "Resumen", i: "grid", k: "d"}, {v: "customers", t: "Pacientes", i: "users", k: "p"},
    {v: "requests", t: "Solicitudes", i: "inbox", k: "s"}, {v: "pipeline", t: "Embudo", i: "funnel", k: "e"},
    {v: "agenda", t: "Agenda semanal", i: "calendar", k: "a"}, {v: "appointments", t: "Citas", i: "list", k: "c"},
    {v: "payments", t: "Pagos y facturas", i: "card", k: "f"}, {v: "catalog", t: "Catálogo", i: "layers", k: "t", admin: true},
    {v: "schedules", t: "Horarios", i: "clock", k: "h", admin: true}, {v: "inventory", t: "Inventario", i: "box", k: "i"},
    {v: "reports", t: "Reportes", i: "chart", k: "r"}, {v: "assistant", t: "Asistente virtual", i: "chat", k: "v"},
    {v: "audit", t: "Auditoría", i: "shield", k: "u", admin: true},
  ];
  const TITLES = Object.fromEntries(MODULES.map(m => [m.v, m.t]));
  let me = null, current = "dashboard", chartSeq = 0, renderSeq = 0;
  const filters = {q: "", stage: "", ast: "", aq: "", week: 0, req: "pendiente", days: 30};

  // ------------------------------------------------------------ utilidades
  const isoD = d => new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10);
  const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
  const shortDay = s => new Date(s + "T12:00:00").toLocaleDateString("es-MX", {day: "numeric", month: "short"}).replace(".", "");
  const fmtDate = s => s ? new Date(s.length === 10 ? s + "T12:00:00" : s.replace(" ", "T")).toLocaleDateString("es-MX", {day: "numeric", month: "short", year: "numeric"}) : "";
  const ago = s => {
    const m = Math.round((Date.now() - new Date(s.replace(" ", "T"))) / 6e4);
    if (m < 1) return "ahora";
    if (m < 60) return `hace ${m} min`;
    if (m < 1440) return `hace ${Math.round(m / 60)} h`;
    return fmtDate(s);
  };
  const compactMoney = v => v >= 1000 ? `$${(v / 1000).toLocaleString("es-MX", {maximumFractionDigits: 1})}k` : `$${v}`;
  const badge = s => `<span class="badge ${esc(s)}">${esc(s)}</span>`;
  const who = (name, sub = "") => `<div class="who"><span class="avatar">${esc(initials(name))}</span><div><b>${esc(name)}</b>${sub ? `<small>${sub}</small>` : ""}</div></div>`;
  const head = (title, sub, actions = "") =>
    `<div class="view-head"><div><h1>${title}</h1><p>${sub}</p></div><div class="actions">${actions}</div></div>`;
  const table = (heads, rows, empty = "Sin registros por ahora.") =>
    `<div class="tbl"><table><thead><tr>${heads.map(h => `<th scope="col">${h}</th>`).join("")}</tr></thead><tbody>${
      rows.join("") || `<tr class="empty-row"><td colspan="${heads.length}">${empty}</td></tr>`}</tbody></table></div>`;
  const kpi = (ic, cls, value, label, fmt) => {
    const num = typeof value === "number";
    return `<div class="kpi"><span class="k-ico ${cls}">${icon(ic)}</span><div><span>${label}</span><b ${num ? `data-count="${value}" ${fmt ? `data-fmt="${fmt}"` : ""}` : ""}>${num ? (fmt === "money" ? money(0) : "0") : esc(value)}</b></div></div>`;
  };
  const exportBtn = (kind, label = "Exportar CSV") => `<a class="btn btn-outline" href="/api/admin/export/${kind}.csv">${icon("download")}${label}</a>`;
  const bars = (rows, fmt = v => v) => {
    if (!rows.length) return `<p class="hint" style="margin:0">Aún no hay datos.</p>`;
    const max = Math.max(1, ...rows.map(r => Number(r.value)));
    return `<div class="bars">${rows.map((r, i) => `<div class="bar"><span class="l" title="${esc(r.label)}">${esc(r.label)}</span><span class="t"><i style="width:${Math.max(2, Math.round(Number(r.value) / max * 100))}%;animation-delay:${i * 50}ms"></i></span><b>${esc(fmt(r.value))}</b></div>`).join("")}</div>`;
  };

  function toast(msg, ok = true) {
    const t = document.createElement("div");
    t.className = "toast" + (ok ? "" : " err");
    t.setAttribute("role", ok ? "status" : "alert");
    t.innerHTML = icon(ok ? "checkCircle" : "alert") + `<span>${esc(msg)}</span>`;
    $("toasts").appendChild(t);
    setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 200); }, 4200);
  }
  const guard = fn => async (...a) => {
    try { await fn(...a); } catch (e) { if (e.status === 401) return showLogin(); toast(e.message, false); }
  };
  // Etiquetas para el modo tarjeta de las tablas en móvil.
  function labelTables(root) {
    root.querySelectorAll(".tbl table").forEach(tb => {
      const heads = [...tb.querySelectorAll("thead th")].map(th => th.textContent.trim());
      tb.querySelectorAll("tbody tr").forEach(tr => [...tr.children].forEach((td, i) => { if (heads[i]) td.dataset.label = heads[i]; }));
    });
  }
  function afterRender(root = view) {
    labelTables(root);
    root.querySelectorAll("[data-count]").forEach(countUp);
    requestAnimationFrame(() => root.querySelectorAll(".seg-arc").forEach(c => c.setAttribute("stroke-dasharray", c.dataset.dash)));
  }

  // ------------------------------------------------------------ gráficas SVG
  function fillDays(rows, from, to) {
    const m = Object.fromEntries(rows.map(r => [r.label, Number(r.value)]));
    const out = [];
    for (let d = new Date(from); d <= to; d = addDays(d, 1)) out.push({label: isoD(d), value: m[isoD(d)] || 0});
    return out;
  }
  function niceMax(v) {
    if (v <= 4) return 4;
    const p = Math.pow(10, Math.floor(Math.log10(v))), n = v / p;
    return (n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
  }
  function areaChart(rows, fmt = v => v, color = "#3766E8", {W = 640, H = 230, axis = fmt} = {}) {
    if (!rows.some(r => r.value)) return `<div class="chart-empty">${icon("chart")}<span>Aún no hay datos en este periodo.</span></div>`;
    const id = "g" + (++chartSeq), P = {l: 52, r: 30, t: 16, b: 30};
    const n = rows.length, max = niceMax(Math.max(...rows.map(r => r.value)));
    const x = i => P.l + (n === 1 ? 0 : i * (W - P.l - P.r) / (n - 1));
    const y = v => P.t + (H - P.t - P.b) * (1 - v / max);
    const pts = rows.map((r, i) => [x(i), y(r.value)]);
    let len = 0;
    pts.forEach((p, i) => { if (i) len += Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]); });
    const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join("");
    const area = line + `L${x(n - 1)},${H - P.b}L${x(0)},${H - P.b}Z`;
    const grid = [0, .25, .5, .75, 1].map(f => `<line x1="${P.l}" x2="${W - P.r}" y1="${y(max * f)}" y2="${y(max * f)}" class="cg"/><text x="${P.l - 10}" y="${y(max * f) + 4}" text-anchor="end" class="ct">${esc(axis(Math.round(max * f)))}</text>`).join("");
    const every = Math.ceil(n / 7), today = isoD(new Date());
    const xl = rows.map((r, i) => i % every === 0 || i === n - 1 ? `<text x="${x(i)}" y="${H - 8}" text-anchor="middle" class="ct">${esc(shortDay(r.label))}</text>` : "").join("");
    const ti = rows.findIndex(r => r.label === today);
    const mark = ti >= 0 ? `<line x1="${x(ti)}" x2="${x(ti)}" y1="${P.t}" y2="${H - P.b}" class="ctoday"/><text x="${ti > n * .85 ? x(ti) - 4 : x(ti) + 4}" y="${P.t + 10}" text-anchor="${ti > n * .85 ? "end" : "start"}" class="ct ctoday-t">hoy</text>` : "";
    const dots = pts.map((p, i) => rows[i].value ? `<circle cx="${p[0]}" cy="${p[1]}" r="3.5" fill="#fff" stroke="${color}" stroke-width="2"><title>${esc(shortDay(rows[i].label))}: ${esc(fmt(rows[i].value))}</title></circle>` : "").join("");
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Gráfica de serie de tiempo"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".22"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>
      ${grid}${mark}<path class="area" d="${area}" fill="url(#${id})"/><path class="line" style="--len:${Math.ceil(len)}" d="${line}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>${dots}${xl}</svg>`;
  }
  function donut(rows, colors = {}, fmt = v => v, center = "Total", centerFmt = fmt) {
    const total = rows.reduce((a, r) => a + Number(r.value), 0);
    if (!total) return `<div class="chart-empty">${icon("chart")}<span>Aún no hay datos.</span></div>`;
    const R = 62, C = 2 * Math.PI * R;
    let acc = 0;
    const segs = rows.map((r, i) => {
      const len = Number(r.value) / total * C, col = colors[r.label] || PALETTE[i % PALETTE.length];
      const s = `<circle class="seg-arc" r="${R}" cx="80" cy="80" fill="none" stroke="${col}" stroke-width="20" stroke-dasharray="0 ${C.toFixed(2)}" data-dash="${Math.max(0, len - 1.5).toFixed(2)} ${(C - len + 1.5).toFixed(2)}" stroke-dashoffset="${(-acc).toFixed(2)}"><title>${esc(r.label)}: ${esc(fmt(r.value))}</title></circle>`;
      acc += len; return s;
    }).join("");
    const legend = rows.map((r, i) => `<li><i style="background:${colors[r.label] || PALETTE[i % PALETTE.length]}"></i><span>${esc(r.label)}</span><b>${esc(fmt(r.value))}</b><small>${Math.round(Number(r.value) / total * 100)}%</small></li>`).join("");
    return `<div class="donut"><svg viewBox="0 0 160 160" role="img" aria-label="Distribución"><g transform="rotate(-90 80 80)"><circle r="${R}" cx="80" cy="80" fill="none" stroke="#EEF1F6" stroke-width="20"/>${segs}</g>
      <text x="80" y="78" text-anchor="middle" class="dn-v">${esc(centerFmt(total))}</text><text x="80" y="97" text-anchor="middle" class="dn-l">${esc(center)}</text></svg><ul class="legend">${legend}</ul></div>`;
  }

  // ------------------------------------------------------------ diálogos
  const dlg = $("dlg");
  const nativeClose = HTMLDialogElement.prototype.close;
  function closeDialog(d) {
    if (!d.open || d.classList.contains("closing")) return;
    if (REDUCED) return nativeClose.call(d);
    d.classList.add("closing");
    setTimeout(() => { d.classList.remove("closing"); nativeClose.call(d); }, 170);
  }
  [dlg, $("palette")].forEach(d => {
    d.close = () => closeDialog(d);
    d.addEventListener("cancel", e => { e.preventDefault(); closeDialog(d); });
    d.addEventListener("click", e => { if (e.target === d) closeDialog(d); }); // clic fuera
  });
  function dialog(title, body, onSubmit, okLabel = "Guardar") {
    dlg.innerHTML = `<form novalidate><h2 id="dlg-title">${title}</h2>${body}<div id="dlg-msg" class="msg"></div>
      <div class="dlg-actions"><button type="button" class="btn btn-outline" data-close>${onSubmit ? "Cancelar" : "Cerrar"}</button>${onSubmit ? `<button class="btn btn-primary" data-ok>${okLabel}</button>` : ""}</div></form>`;
    const f = dlg.querySelector("form");
    dlg.querySelector("[data-close]").onclick = () => dlg.close();
    f.addEventListener("submit", async ev => {
      ev.preventDefault();
      if (!onSubmit) return;
      if (!f.checkValidity()) { f.reportValidity(); return; }
      const ok = f.querySelector("[data-ok]");
      ok.classList.add("is-loading");
      try { await onSubmit(f); dlg.close(); }
      catch (e) { if (e.status === 401) { dlg.close(); return showLogin(); } const m = $("dlg-msg"); m.className = "msg err"; m.textContent = e.message; }
      finally { ok.classList.remove("is-loading"); }
    });
    labelTables(dlg);
    dlg.showModal();
    const first = f.querySelector("input,select,textarea"); if (first) first.focus();
  }

  // ------------------------------------------------------------ acciones compartidas
  async function walkIn(preset = {}) {
    const specs = await api("/api/specialties");
    const firstDay = new Date().getDay() === 0 ? addDays(new Date(), 1) : new Date();
    dialog("Nueva cita en recepción", `
      <div class="grid-2"><div class="field"><label for="w-s">Especialidad</label><select id="w-s" name="spec">${specs.map(s => `<option value="${s.id}">${esc(s.name)} · ${money(s.price)}</option>`).join("")}</select></div>
      <div class="field"><label for="w-d">Fecha</label><input id="w-d" name="date" type="date" required min="${isoD(new Date())}" max="${isoD(addDays(new Date(), 45))}" value="${preset.date || isoD(firstDay)}"></div></div>
      <div class="field"><label for="w-t">Horario y especialista</label><select id="w-t" name="slot" required><option value="">Selecciona fecha…</option></select></div>
      <div class="grid-2"><div class="field"><label for="w-a">Paciente (alias)</label><input id="w-a" name="alias" required minlength="2" maxlength="60"></div>
      <div class="field"><label for="w-p">Teléfono</label><input id="w-p" name="phone" pattern="\\d{10}" maxlength="10" inputmode="numeric" placeholder="10 dígitos"></div></div>`,
      async f => {
        const [pid, time] = f.slot.value.split("@");
        const r = await api("/api/admin/appointments", {method: "POST", body: {specialty_id: Number(f.spec.value), date: f.date.value, time, professional_id: Number(pid), alias: f.alias.value.trim(), phone: f.phone.value.trim()}});
        setTimeout(() => dialog("Cita registrada", `
          <p>Entrega estos datos al paciente. <b>El PIN solo se muestra esta vez.</b></p>
          <div class="ticket"><small>Folio</small><b>${esc(r.code)}</b><small>PIN privado</small><b>${esc(r.pin)}</b>
          <span>${esc(r.specialty)} · ${esc(r.professional)}<br>${esc(fmtDate(r.date))} · ${esc(r.time)} h</span></div>`, null), 200);
        go(current);
      }, "Registrar cita");
    const f = dlg.querySelector("form");
    async function load() {
      const sel = f.slot;
      sel.innerHTML = `<option value="">Cargando…</option>`;
      try {
        const rows = await api(`/api/slots?specialty_id=${f.spec.value}&date=${f.date.value}&detailed=true`);
        sel.innerHTML = rows.length ? rows.map(s => `<option value="${s.professional_id}@${s.time}">${s.time} h · ${esc(s.professional)}</option>`).join("") : `<option value="">Sin horarios libres ese día</option>`;
      } catch (e) { sel.innerHTML = `<option value="">${esc(e.message)}</option>`; }
    }
    f.spec.onchange = load; f.date.onchange = load; load();
  }
  function apptDetail(a) {
    const actions = a.status === "confirmada";
    dialog(`Cita ${esc(a.code)}`, `
      <div class="detail">${who(a.alias, esc(a.phone || "Sin teléfono"))}${badge(a.status)}</div>
      <dl class="dl"><dt>Servicio</dt><dd>${esc(a.specialty)}</dd><dt>Especialista</dt><dd>${esc(a.professional)}</dd>
      <dt>Fecha</dt><dd>${esc(fmtDate(a.date))} · ${esc(a.time)} h</dd><dt>Canal</dt><dd>${esc(chan(a.channel))}</dd>
      <dt>Precio</dt><dd>${money(a.price)}</dd>${a.invoice ? `<dt>Factura</dt><dd class="mono">${esc(a.invoice)}</dd>` : ""}</dl>
      ${actions ? `<div class="dlg-inline"><button type="button" class="btn btn-primary btn-sm" data-st="completada">${icon("check")}Marcar completada</button><button type="button" class="btn btn-danger btn-sm" data-st="cancelada">Cancelar cita</button></div>` : ""}`, null);
    dlg.querySelectorAll("[data-st]").forEach(b => b.onclick = guard(async () => {
      if (b.dataset.st === "cancelada" && !confirm("¿Cancelar esta cita?")) return;
      await api(`/api/admin/appointments/${a.id}/status`, {method: "POST", body: {status: b.dataset.st}});
      dlg.close(); toast(b.dataset.st === "completada" ? "Cita completada" : "Cita cancelada"); go(current);
    }));
  }
  async function refreshBadges() {
    try {
      const d = await api("/api/admin/dashboard");
      document.querySelectorAll("[data-req]").forEach(el => { el.textContent = d.requests; el.hidden = !d.requests; });
      return d;
    } catch (_) { return null; }
  }

  // ------------------------------------------------------------ navegación
  function setNav(open) {
    $("app").classList.toggle("nav-open", open);
    $("menu-btn").setAttribute("aria-expanded", String(open));
  }
  function showLogin() {
    me = null;
    $("app").hidden = true; $("login-box").hidden = false;
    $("boot").classList.add("done");
    setTimeout(() => $("u").focus(), 50);
  }
  function showApp() {
    $("login-box").hidden = true; $("app").hidden = false;
    $("boot").classList.add("done");
    $("me-name").textContent = me.username;
    $("me-role").textContent = me.role === "admin" ? "Administrador" : "Recepción";
    $("me-av").textContent = me.username.slice(0, 2).toUpperCase();
    const td = new Date().toLocaleDateString("es-MX", {weekday: "long", day: "numeric", month: "long"});
    $("today").textContent = td[0].toUpperCase() + td.slice(1);
    document.querySelectorAll("[data-admin]").forEach(b => b.hidden = me.role !== "admin");
    const fromHash = location.hash.slice(1);
    go(fromHash in TITLES ? fromHash : current);
  }
  function allowed(v) { const m = MODULES.find(x => x.v === v); return !!(me && m && (!m.admin || me.role === "admin")); }
  async function go(v) {
    if (!me) return showLogin();
    if (!allowed(v)) v = "dashboard";
    current = v;
    history.replaceState(null, "", "#" + v);
    $("crumb").textContent = TITLES[v];
    document.title = `${TITLES[v]} · MediBot 360`;
    document.querySelectorAll(".sidebar nav button").forEach(b => {
      b.classList.toggle("on", b.dataset.v === v);
      if (b.dataset.v === v) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
    });
    setNav(false);
    const seq = ++renderSeq;
    view.classList.remove("enter");
    try {
      await views[v]();
      if (seq !== renderSeq) return;
      void view.offsetWidth; // reinicia la animación de entrada
      view.classList.add("enter");
      afterRender();
    } catch (e) {
      if (e.status === 401) return showLogin();
      view.innerHTML = `<div class="card view-error"><div class="state-box">${icon(e.status === 0 ? "wifiOff" : "alert")}<h3>No pudimos cargar «${esc(TITLES[v])}»</h3><p>${esc(e.message)}</p><button class="btn btn-primary" id="retry">${icon("refresh")}Reintentar</button></div></div>`;
      $("retry").onclick = () => go(v);
    }
    refreshBadges();
  }

  // ------------------------------------------------------------ vistas
  const views = {
    async dashboard() {
      const today = isoD(new Date());
      const [d, upcoming, rep, act] = await Promise.all([api("/api/admin/dashboard"), api("/api/admin/appointments?status=confirmada"),
                                                         api("/api/admin/reports"), api("/api/admin/activity")]);
      const todays = (await api(`/api/admin/appointments?day=${today}`)).filter(a => a.status !== "cancelada").sort((a, b) => a.time.localeCompare(b.time));
      const nextDay = upcoming.filter(a => a.date > today).sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time));
      const agendaRows = todays.length ? todays : nextDay.filter(a => nextDay.length && a.date === nextDay[0].date);
      const agendaTitle = todays.length ? "Agenda de hoy" : nextDay.length ? `Próximo día con citas · ${fmtDate(nextDay[0].date)}` : "Agenda";
      const h = new Date().getHours(), greet = h < 6 ? "Hola" : h < 12 ? "Buenos días" : h < 19 ? "Buenas tardes" : "Buenas noches";
      const nowT = new Date().toTimeString().slice(0, 5);
      const nowIdx = todays.findIndex(a => a.time >= nowT);
      const series = fillDays(rep.appointments_by_day, addDays(new Date(), -14), addDays(new Date(), 14));
      const specs = [...new Set(agendaRows.map(a => a.specialty))];
      view.innerHTML = head(`${greet}, ${esc(me.username)}`, "Centro de operaciones de la clínica.",
        `<button class="btn btn-primary" id="walk">${icon("plus")}Nueva cita</button>`) +
        `<div class="quick">
          <button data-act="walk"><span class="k-ico">${icon("plus")}</span><span>Registrar cita<small>Paciente presencial o telefónico</small></span></button>
          <button data-go="requests"><span class="k-ico warn">${icon("inbox")}</span><span>Solicitudes<small>${d.requests} pendientes de atender</small></span></button>
          <button data-go="agenda"><span class="k-ico teal">${icon("calendar")}</span><span>Agenda semanal<small>Vista por día y hora</small></span></button>
          <button data-go="assistant"><span class="k-ico violet">${icon("chat")}</span><span>Asistente virtual<small>Conversión y comprensión</small></span></button>
        </div>
        <div class="kpis">
          ${kpi("calendar", "", d.today, "Citas de hoy")}${kpi("clock", "info", d.pending, "Citas próximas")}
          ${kpi("money", "ok", d.income, "Ingresos registrados", "money")}${kpi("inbox", d.requests ? "warn" : "ok", d.requests, "Solicitudes pendientes")}
        </div>
        <div class="chart-grid wide">
          <div class="card"><div class="card-head"><div><h2>Citas por día</h2><small class="muted">Últimas 2 semanas y próximas 2</small></div><button class="btn btn-outline btn-sm" data-go="agenda">Ver agenda</button></div><div class="card-body">${areaChart(series)}</div></div>
          <div class="card"><div class="card-head"><h2>Estado de las citas</h2></div><div class="card-body">${donut(rep.appointments_by_status, STATUS_COLOR, v => v, "citas")}</div></div>
        </div>
        <div class="two-col">
          <div class="card"><div class="card-head"><div><h2>${esc(agendaTitle)}</h2><small class="muted">${agendaRows.length} citas</small></div><button class="btn btn-outline btn-sm" data-go="appointments">Ver todas</button></div>
            ${agendaRows.length ? `<ul class="day-agenda stagger">${agendaRows.map((a, i) => `<li data-i="${i}" class="${todays.length && i === nowIdx ? "now" : ""}" tabindex="0" role="button" aria-label="Cita de ${esc(a.alias)} a las ${esc(a.time)}">
              <time>${esc(a.time)}</time><div style="border-left:3px solid ${PALETTE[specs.indexOf(a.specialty) % PALETTE.length]};padding-left:12px"><b>${esc(a.alias)}</b><small>${esc(a.specialty)} · ${esc(a.professional)}</small></div>${badge(a.status)}</li>`).join("")}</ul>`
              : `<div class="state-box">${icon("calendar")}<h3>Sin citas programadas</h3><p>Registra una cita o comparte el portal de reservaciones.</p></div>`}</div>
          <div class="card"><div class="card-head"><h2>Actividad reciente</h2></div><div class="card-body">
            ${act.length ? `<ul class="timeline stagger">${act.map(x => `<li class="k-${x.kind}"><b>${x.kind === "cita" ? "Nueva cita" : x.kind === "pago" ? "Cobro registrado" : "Solicitud de contacto"}</b><small>${esc(ago(x.at))}</small><p>${esc(x.who)} · ${esc(String(x.what).replace(/(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})/, (_, d, t) => `${shortDay(d)} ${t} h`))}${x.kind === "cita" ? ` · ${esc(chan(x.extra))}` : ""}</p></li>`).join("")}</ul>`
              : `<p class="muted">Aún no hay actividad.</p>`}</div></div>
        </div>`;
      view.querySelectorAll("[data-go]").forEach(b => b.onclick = () => go(b.dataset.go));
      view.querySelectorAll("[data-act=walk], #walk").forEach(b => b.onclick = guard(() => walkIn()));
      view.querySelectorAll(".day-agenda li").forEach(li => {
        const open = () => apptDetail(agendaRows[li.dataset.i]);
        li.onclick = open;
        li.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } };
      });
    },

    async customers() {
      const rows = await api(`/api/admin/customers?q=${encodeURIComponent(filters.q)}&stage=${filters.stage}`);
      view.innerHTML = head("Pacientes y prospectos", "Seguimiento de la relación con cada paciente.",
        `${exportBtn("pacientes")}<button class="btn btn-primary" id="new">${icon("plus")}Nuevo prospecto</button>`) +
        `<div class="card"><div class="toolbar">
          <div class="search">${icon("search")}<input id="q" type="search" placeholder="Buscar por alias, teléfono o correo" value="${esc(filters.q)}" aria-label="Buscar pacientes"></div>
          <div class="tabs" role="tablist" aria-label="Etapa">${["", ...STAGES].map(s => `<button role="tab" aria-selected="${s === filters.stage}" data-stage="${s}">${s ? s[0].toUpperCase() + s.slice(1) : "Todas"}</button>`).join("")}</div>
        </div><div id="cust-body">` +
        table(["Paciente", "Contacto", "Etapa", "Origen", "Citas", ""], rows.map(c => `<tr>
          <td>${who(c.alias, "Alta " + esc(fmtDate(c.created_at)))}</td><td>${esc(c.phone || "—")}${c.email ? `<br><small>${esc(c.email)}</small>` : ""}</td>
          <td>${badge(c.stage)}</td><td>${esc(chan(c.source))}</td><td>${c.appointments}</td>
          <td><div class="acts"><button class="btn btn-outline btn-sm" data-id="${c.id}">Ver ficha</button></div></td></tr>`),
          "No se encontraron pacientes con esos filtros.") + `</div></div>`;
      let t;
      $("q").oninput = () => {
        clearTimeout(t);
        t = setTimeout(async () => {
          filters.q = $("q").value;
          const body = $("cust-body"); body.style.opacity = ".5";
          await go("customers");
          const i = $("q"); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); }
        }, 300);
      };
      view.querySelectorAll("[data-stage]").forEach(b => b.onclick = () => { filters.stage = b.dataset.stage; go("customers"); });
      $("new").onclick = () => dialog("Nuevo prospecto", `
        <div class="field"><label for="d-alias">Alias o nombre</label><input id="d-alias" name="alias" required minlength="2" maxlength="60"></div>
        <div class="grid-2"><div class="field"><label for="d-phone">Teléfono</label><input id="d-phone" name="phone" pattern="\\d{10}" maxlength="10" inputmode="numeric" placeholder="10 dígitos"></div>
        <div class="field"><label for="d-email">Correo</label><input id="d-email" name="email" type="email"></div></div>
        <div class="field"><label for="d-notes">Notas</label><textarea id="d-notes" name="notes" maxlength="500"></textarea></div>`,
        async f => { const v = Object.fromEntries(new FormData(f)); v.source = "manual"; await api("/api/admin/customers", {method: "POST", body: v}); toast("Prospecto registrado"); go("customers"); });
      view.querySelectorAll("button[data-id]").forEach(b => b.onclick = () => guard(profile)(b.dataset.id));
    },

    async requests() {
      const rows = await api(`/api/admin/requests?status=${filters.req}`);
      const seg = [["pendiente", "Pendientes"], ["atendida", "Atendidas"], ["descartada", "Descartadas"], ["", "Todas"]];
      view.innerHTML = head("Solicitudes de atención", "Personas que pidieron hablar con recepción desde el asistente virtual.") +
        `<div class="card"><div class="toolbar"><div class="tabs" role="tablist">${seg.map(([s, l]) => `<button role="tab" aria-selected="${s === filters.req}" data-rs="${s}">${l}</button>`).join("")}</div></div>
        ${rows.length ? `<div class="stagger">${rows.map(r => `<div class="inbox-item ${r.status !== "pendiente" ? "done" : ""}">
            <span class="avatar">${esc(initials(r.alias))}</span>
            <div><b>${esc(r.alias)} <span class="badge ${esc(r.status)}">${esc(r.status)}</span></b>
              <small class="muted">${esc(r.topic_label)} · ${r.phone ? esc(r.phone) : "sin teléfono"} · ${esc(ago(r.created_at))}${r.handled_by ? ` · atendida por ${esc(r.handled_by)}` : ""}</small></div>
            <div class="acts">${r.phone ? `<a class="btn btn-outline btn-sm" href="tel:${esc(r.phone)}">${icon("phone")}Llamar</a>` : ""}
              ${r.customer_id ? `<button class="btn btn-outline btn-sm" data-cid="${r.customer_id}">Ficha</button>` : ""}
              ${r.status === "pendiente" ? `<button class="btn btn-primary btn-sm" data-done="${r.id}">${icon("check")}Atendida</button><button class="btn btn-ghost btn-sm" data-drop="${r.id}">Descartar</button>` : `<button class="btn btn-ghost btn-sm" data-reopen="${r.id}">Reabrir</button>`}</div>
          </div>`).join("")}</div>`
          : `<div class="state-box">${icon("inbox")}<h3>Bandeja al día</h3><p>No hay solicitudes en esta categoría.</p></div>`}</div>`;
      view.querySelectorAll("[data-rs]").forEach(b => b.onclick = () => { filters.req = b.dataset.rs; go("requests"); });
      view.querySelectorAll("[data-cid]").forEach(b => b.onclick = () => guard(profile)(b.dataset.cid));
      const setStatus = (id, status, note = "") => api(`/api/admin/requests/${id}/status`, {method: "POST", body: {status, note}});
      view.querySelectorAll("[data-done]").forEach(b => b.onclick = () => dialog("Marcar como atendida", `
        <div class="field"><label for="r-n">Nota de seguimiento (opcional)</label><textarea id="r-n" name="note" maxlength="300" placeholder="Ej. Se agendó por teléfono"></textarea></div>
        <p class="hint">El paciente pasará a «contactado» y la nota quedará en su historial.</p>`,
        async f => { await setStatus(b.dataset.done, "atendida", f.note.value.trim()); toast("Solicitud atendida"); go("requests"); }, "Guardar"));
      view.querySelectorAll("[data-drop]").forEach(b => b.onclick = guard(async () => { await setStatus(b.dataset.drop, "descartada"); toast("Solicitud descartada"); go("requests"); }));
      view.querySelectorAll("[data-reopen]").forEach(b => b.onclick = guard(async () => { await setStatus(b.dataset.reopen, "pendiente"); toast("Solicitud reabierta"); go("requests"); }));
    },

    async pipeline() {
      const [p, rows] = await Promise.all([api("/api/admin/pipeline"), api("/api/admin/customers")]);
      const total = Object.values(p).reduce((a, b) => a + b, 0) || 1;
      view.innerHTML = head("Embudo de pacientes", "De prospecto a paciente: así avanza la relación.") +
        `<div class="pipe stagger">${STAGES.map(s => `<div class="stage" style="--c:${STAGE_COLOR[s]}">${badge(s)}<b data-count="${p[s]}">0</b><span class="pct">${Math.round(p[s] / total * 100)}% del total</span></div>`).join("")}</div>
        <div class="two-col">
          <div class="card"><div class="card-head"><h3>Prospectos por contactar</h3></div>${table(["Prospecto", "Origen", ""], rows.filter(c => c.stage === "prospecto").slice(0, 8).map(c => `<tr><td>${who(c.alias, esc(c.phone))}</td><td>${esc(chan(c.source))}</td><td><div class="acts"><button class="btn btn-outline btn-sm" data-id="${c.id}">Dar seguimiento</button></div></td></tr>`), "No hay prospectos pendientes.")}</div>
          <div class="card"><div class="card-head"><h3>¿Cómo avanza un paciente?</h3></div><div class="card-body">
            <ul class="timeline">
              <li><b>Prospecto</b><p>Llega desde el asistente («hablar con recepción») o se captura manualmente.</p></li>
              <li><b>Contactado</b><p>Recepción atiende la solicitud o registra una llamada en su ficha.</p></li>
              <li><b>Cliente</b><p>Al reservar una cita avanza automáticamente.</p></li>
              <li><b>Inactivo</b><p>Sin actividad reciente; candidato a campañas de reactivación.</p></li>
            </ul></div></div>
        </div>`;
      view.querySelectorAll("button[data-id]").forEach(b => b.onclick = () => guard(profile)(b.dataset.id));
    },

    async agenda() {
      const base = new Date().getDay() === 0 ? addDays(new Date(), 1) : new Date();
      const monday = addDays(base, -((base.getDay() + 6) % 7) + filters.week * 7);
      const days = [0, 1, 2, 3, 4, 5].map(i => isoD(addDays(monday, i)));
      const rows = (await api(`/api/admin/appointments?start=${days[0]}&end=${days[5]}`)).filter(a => a.status !== "cancelada");
      const specs = [...new Set(rows.map(a => a.specialty))].sort();
      const col = s => PALETTE[specs.indexOf(s) % PALETTE.length];
      const hs = rows.map(a => Number(a.time.slice(0, 2)));
      const hours = [];
      for (let h = Math.min(9, ...hs); h <= Math.max(16, ...hs); h++) hours.push(h);
      const today = isoD(new Date());
      const label = `${shortDay(days[0])} – ${shortDay(days[5])} ${new Date(days[5] + "T12:00").getFullYear()}`;
      const cell = (d, h) => rows.filter(a => a.date === d && Number(a.time.slice(0, 2)) === h)
        .map(a => `<button class="ev ${a.status}" style="--c:${col(a.specialty)}" data-id="${a.id}" aria-label="${esc(a.time)} ${esc(a.alias)}, ${esc(a.specialty)}"><b>${esc(a.time)}</b> ${esc(a.alias)}<small>${esc(a.specialty)} · ${esc(a.professional)}</small></button>`).join("");
      view.innerHTML = head("Agenda semanal", "Citas confirmadas y completadas por día y hora.",
        `<div class="seg"><button class="btn btn-outline btn-icon" id="wk-p" aria-label="Semana anterior">${icon("chevL")}</button><button class="btn btn-outline" id="wk-t">Hoy</button><button class="btn btn-outline btn-icon" id="wk-n" aria-label="Semana siguiente">${icon("chevR")}</button></div><button class="btn btn-primary" id="walk">${icon("plus")}Nueva cita</button>`) +
        `<div class="card"><div class="card-head"><h2>${esc(label)}</h2><span class="muted">${rows.length} citas</span></div>
        <div class="cal ${filters._swap ? "swap" : ""}" role="grid" aria-label="Agenda semanal">
          <div class="cal-corner"></div>
          ${days.map(d => { const n = rows.filter(a => a.date === d).length; const dt = new Date(d + "T12:00"); return `<div class="cal-day ${d === today ? "today" : ""}"><small>${dt.toLocaleDateString("es-MX", {weekday: "short"}).replace(".", "")}</small><b>${dt.getDate()}</b><span>${n ? n + (n === 1 ? " cita" : " citas") : "libre"}</span></div>`; }).join("")}
          ${hours.map(h => `<div class="cal-h">${String(h).padStart(2, "0")}:00</div>${days.map(d => `<div class="cal-c ${d === today ? "today" : ""} ${d < today ? "past" : ""}">${cell(d, h)}</div>`).join("")}`).join("")}
        </div>
        ${specs.length ? `<div class="cal-legend">${specs.map(s => `<span><i style="background:${col(s)}"></i>${esc(s)}</span>`).join("")}</div>` : ""}</div>`;
      filters._swap = false;
      const nav = delta => { filters.week = delta === 0 ? 0 : filters.week + delta; filters._swap = true; go("agenda"); };
      $("wk-p").onclick = () => nav(-1); $("wk-n").onclick = () => nav(1); $("wk-t").onclick = () => nav(0);
      $("walk").onclick = guard(() => walkIn());
      view.querySelectorAll(".ev").forEach(b => b.onclick = () => apptDetail(rows.find(a => a.id == b.dataset.id)));
    },

    async appointments() {
      const rows = await api(`/api/admin/appointments?status=${filters.ast}&q=${encodeURIComponent(filters.aq)}`);
      const seg = ["", "confirmada", "completada", "cancelada"];
      view.innerHTML = head("Citas", "Completa, cancela y cobra consultas del sitio, el asistente y recepción.",
        `${exportBtn("citas")}<button class="btn btn-primary" id="walk">${icon("plus")}Nueva cita</button>`) +
        `<div class="card"><div class="toolbar"><div class="search">${icon("search")}<input id="aq" type="search" placeholder="Folio, paciente o teléfono" value="${esc(filters.aq)}" aria-label="Buscar citas"></div>
        <div class="tabs" role="tablist" aria-label="Estado">${seg.map(s => `<button role="tab" aria-selected="${s === filters.ast}" data-st="${s}">${s ? s[0].toUpperCase() + s.slice(1) + "s" : "Todas"}</button>`).join("")}</div></div>` +
        table(["Folio", "Paciente", "Servicio", "Fecha", "Estado", "Canal", ""], rows.map(a => `<tr>
          <td class="mono">${esc(a.code)}</td><td>${who(a.alias, esc(a.phone))}</td>
          <td>${esc(a.specialty)}<br><small>${esc(a.professional)}</small></td>
          <td>${esc(fmtDate(a.date))}<br><small>${esc(a.time)} h</small></td><td>${badge(a.status)}</td><td>${esc(chan(a.channel))}</td>
          <td><div class="acts">${a.status === "confirmada"
            ? `<button class="btn btn-outline btn-sm" data-s="completada" data-id="${a.id}">${icon("check")}Completar</button><button class="btn btn-danger btn-sm" data-s="cancelada" data-id="${a.id}">Cancelar</button>`
            : a.status === "completada" && !a.invoice ? `<button class="btn btn-primary btn-sm" data-pay="${a.id}" data-price="${a.price}">${icon("card")}Cobrar</button>`
            : a.invoice ? `<span class="mono">${esc(a.invoice)}</span>` : ""}</div></td></tr>`), "No hay citas con este filtro.") + `</div>`;
      view.querySelectorAll("[data-st]").forEach(b => b.onclick = () => { filters.ast = b.dataset.st; go("appointments"); });
      $("walk").onclick = guard(() => walkIn());
      let t;
      $("aq").oninput = () => { clearTimeout(t); t = setTimeout(async () => { filters.aq = $("aq").value.trim(); await go("appointments"); const i = $("aq"); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }, 300); };
      view.querySelectorAll("button[data-s]").forEach(b => b.onclick = guard(async () => {
        if (b.dataset.s === "cancelada" && !confirm("¿Cancelar esta cita?")) return;
        await api(`/api/admin/appointments/${b.dataset.id}/status`, {method: "POST", body: {status: b.dataset.s}});
        toast(b.dataset.s === "completada" ? "Cita marcada como completada" : "Cita cancelada"); go("appointments");
      }));
      view.querySelectorAll("button[data-pay]").forEach(b => b.onclick = () => dialog("Registrar cobro", `
        <p>Monto de la consulta: <b>${money(b.dataset.price)}</b></p>
        <div class="field"><label for="d-m">Método de pago</label><select id="d-m" name="method"><option value="efectivo">Efectivo</option><option value="tarjeta">Tarjeta</option><option value="transferencia">Transferencia</option></select></div>
        <p class="hint">Se genera una factura simulada sin validez fiscal.</p>`,
        async f => { const r = await api(`/api/admin/appointments/${b.dataset.pay}/payment`, {method: "POST", body: {method: f.method.value}}); toast(`Factura ${r.invoice} por ${money(r.amount)}`); go("appointments"); }, "Cobrar"));
    },

    async payments() {
      const rows = await api("/api/admin/payments");
      const total = rows.reduce((a, r) => a + r.amount, 0);
      const byMethod = {};
      rows.forEach(r => byMethod[r.method] = (byMethod[r.method] || 0) + r.amount);
      const top = Object.entries(byMethod).sort((a, b) => b[1] - a[1])[0];
      view.innerHTML = head("Pagos y facturas", "Cobros registrados en recepción. Facturación simulada sin validez fiscal.", exportBtn("pagos")) +
        `<div class="kpis">${kpi("money", "ok", total, "Total cobrado", "money")}${kpi("ticket", "", rows.length, "Facturas emitidas")}
        ${kpi("chart", "info", Math.round(rows.length ? total / rows.length : 0), "Ticket promedio", "money")}${kpi("card", "violet", top ? top[0] : "—", "Método más usado")}</div>
        <div class="card">${table(["Factura", "Fecha", "Cita", "Paciente", "Método", "Monto"], rows.map(r => `<tr><td class="mono">${esc(r.invoice)}</td><td>${esc(fmtDate(r.created_at))}</td><td class="mono">${esc(r.code)}</td><td>${who(r.alias)}</td><td style="text-transform:capitalize">${esc(r.method)}</td><td><b>${money(r.amount)}</b></td></tr>`), "Aún no hay cobros. Completa una cita y regístrala desde «Citas».")}</div>`;
    },

    async catalog() {
      const c = await api("/api/admin/catalog");
      view.innerHTML = head("Catálogo", "Servicios, precios y especialistas que se muestran en el portal y el asistente.",
        `<button class="btn btn-outline" id="np">${icon("user")}Nuevo especialista</button><button class="btn btn-primary" id="ns">${icon("plus")}Nueva especialidad</button>`) +
        `<div class="card"><div class="card-head"><h3>Especialidades</h3></div>${table(["Especialidad", "Precio", "Estado", ""], c.specialties.map(s => `<tr><td><div class="who"><span class="svc-ico" style="width:36px;height:36px;margin:0">${icon(specIcon(s.name))}</span><div><b>${esc(s.name)}</b><small>${esc(s.description)}</small></div></div></td><td><b>${money(s.price)}</b></td><td>${s.active ? '<span class="badge ok">activa</span>' : '<span class="badge low">inactiva</span>'}</td><td><div class="acts"><button class="btn btn-outline btn-sm" data-es="${s.id}">Editar</button></div></td></tr>`))}</div>
        <div class="card"><div class="card-head"><h3>Especialistas</h3></div>${table(["Especialista", "Especialidad", "Estado", ""], c.professionals.map(p => `<tr><td>${who(p.name)}</td><td>${esc(p.specialty)}</td><td>${p.active ? '<span class="badge ok">activo</span>' : '<span class="badge low">inactivo</span>'}</td><td><div class="acts"><button class="btn btn-outline btn-sm" data-ep="${p.id}">Editar</button></div></td></tr>`))}</div>`;
      const specForm = s => `<div class="field"><label for="d-n">Nombre</label><input id="d-n" name="name" required minlength="2" value="${esc(s.name || "")}"></div>
        <div class="field"><label for="d-p">Precio (MXN)</label><input id="d-p" name="price" type="number" min="0" step="10" required value="${s.price ?? ""}"></div>
        <div class="field"><label for="d-d">Descripción</label><input id="d-d" name="description" maxlength="200" value="${esc(s.description || "")}"></div>
        <label class="check"><input type="checkbox" name="active" ${s.active === 0 ? "" : "checked"}> Visible en el portal</label>`;
      const specBody = f => ({name: f.name.value, price: Number(f.price.value), description: f.description.value, active: f.active.checked});
      $("ns").onclick = () => dialog("Nueva especialidad", specForm({}), async f => { await api("/api/admin/specialties", {method: "POST", body: specBody(f)}); toast("Especialidad creada"); go("catalog"); });
      view.querySelectorAll("[data-es]").forEach(b => b.onclick = () => { const s = c.specialties.find(x => x.id == b.dataset.es); dialog("Editar especialidad", specForm(s), async f => { await api(`/api/admin/specialties/${s.id}`, {method: "PUT", body: specBody(f)}); toast("Cambios guardados"); go("catalog"); }); });
      const proForm = p => `<div class="field"><label for="d-n">Nombre</label><input id="d-n" name="name" required minlength="2" value="${esc(p.name || "")}"></div>
        <div class="field"><label for="d-s">Especialidad</label><select id="d-s" name="sp">${c.specialties.map(s => `<option value="${s.id}" ${s.id === p.specialty_id ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select></div>
        <label class="check"><input type="checkbox" name="active" ${p.active === 0 ? "" : "checked"}> Activo para recibir citas</label>`;
      const proBody = f => ({name: f.name.value, specialty_id: Number(f.sp.value), active: f.active.checked});
      $("np").onclick = () => dialog("Nuevo especialista", proForm({}), async f => { await api("/api/admin/professionals", {method: "POST", body: proBody(f)}); toast("Especialista agregado. Asígnale horarios."); go("catalog"); });
      view.querySelectorAll("[data-ep]").forEach(b => b.onclick = () => { const p = c.professionals.find(x => x.id == b.dataset.ep); dialog("Editar especialista", proForm(p), async f => { await api(`/api/admin/professionals/${p.id}`, {method: "PUT", body: proBody(f)}); toast("Cambios guardados"); go("catalog"); }); });
    },

    async schedules() {
      const [rows, cat] = await Promise.all([api("/api/admin/schedules"), api("/api/admin/catalog")]);
      const byPro = {};
      rows.forEach(r => (byPro[r.professional] = byPro[r.professional] || []).push(r));
      view.innerHTML = head("Horarios", "Bloques de atención por especialista. Definen los turnos que se ofrecen en línea.",
        `<button class="btn btn-primary" id="nh">${icon("plus")}Agregar horario</button>`) +
        (Object.keys(byPro).length ? Object.entries(byPro).map(([pro, list]) => `<div class="card"><div class="card-head">${who(pro, list.length + " bloques")}</div>
          ${table(["Día", "Horario", "Duración del turno", ""], list.map(r => `<tr><td>${DAYS[r.weekday]}</td><td>${esc(r.start)} – ${esc(r.end)}</td><td>${r.slot_minutes} min</td><td><div class="acts"><button class="btn btn-danger btn-sm" data-del="${r.id}">Quitar</button></div></td></tr>`))}</div>`).join("")
          : `<div class="card"><div class="state-box">${icon("clock")}<h3>Sin horarios</h3><p>Agrega bloques para ofrecer citas en línea.</p></div></div>`);
      $("nh").onclick = () => dialog("Nuevo horario", `
        <div class="field"><label for="d-p">Especialista</label><select id="d-p" name="p">${cat.professionals.map(p => `<option value="${p.id}">${esc(p.name)} · ${esc(p.specialty)}</option>`).join("")}</select></div>
        <div class="field"><label for="d-d">Día</label><select id="d-d" name="d">${DAYS.map((d, i) => `<option value="${i}">${d}</option>`).join("")}</select></div>
        <div class="grid-3"><div class="field"><label for="d-s">Inicio</label><input id="d-s" name="s" type="time" value="09:00" required></div>
        <div class="field"><label for="d-e">Fin</label><input id="d-e" name="e" type="time" value="17:00" required></div>
        <div class="field"><label for="d-m">Turno</label><select id="d-m" name="m"><option value="30">30 min</option><option value="60" selected>60 min</option></select></div></div>`,
        async f => { await api("/api/admin/schedules", {method: "POST", body: {professional_id: Number(f.p.value), weekday: Number(f.d.value), start: f.s.value, end: f.e.value, slot_minutes: Number(f.m.value)}}); toast("Horario agregado"); go("schedules"); });
      view.querySelectorAll("[data-del]").forEach(b => b.onclick = guard(async () => { if (confirm("¿Quitar este bloque de horario?")) { await api(`/api/admin/schedules/${b.dataset.del}`, {method: "DELETE"}); toast("Horario eliminado"); go("schedules"); } }));
    },

    async inventory() {
      const rows = await api("/api/admin/inventory");
      const value = rows.reduce((a, i) => a + i.stock * i.unit_cost, 0);
      const low = rows.filter(i => i.low).length;
      view.innerHTML = head("Inventario de insumos", "Existencias de material de consulta con alertas de reabastecimiento.",
        exportBtn("inventario") + (me.role === "admin" ? `<button class="btn btn-primary" id="ni">${icon("plus")}Nuevo artículo</button>` : "")) +
        `<div class="kpis">${kpi("box", "", rows.length, "Artículos")}${kpi("money", "ok", Math.round(value), "Valor del inventario", "money")}
         ${kpi("alert", low ? "bad" : "ok", low, "Por reabastecer")}${kpi("layers", "info", rows.reduce((a, i) => a + i.stock, 0), "Unidades en almacén")}</div>
        <div class="card">${table(["Artículo", "Existencias", "Mínimo", "Costo unitario", "Estado", ""], rows.map(i => `<tr><td><b>${esc(i.name)}</b></td><td><div class="stock"><b>${i.stock}</b><span class="meter"><i class="${i.low ? "low" : ""}" style="width:${Math.min(100, Math.round(i.stock / Math.max(1, i.min_stock * 3) * 100))}%"></i></span></div></td><td>${i.min_stock}</td><td>${money(i.unit_cost)}</td><td>${i.low ? '<span class="badge low">reabastecer</span>' : '<span class="badge ok">suficiente</span>'}</td><td><div class="acts"><button class="btn btn-outline btn-sm" data-h="${i.id}">Historial</button><button class="btn btn-primary btn-sm" data-mv="${i.id}" data-n="${esc(i.name)}">Movimiento</button></div></td></tr>`))}</div>`;
      if ($("ni")) $("ni").onclick = () => dialog("Nuevo artículo", `
        <div class="field"><label for="d-n">Nombre</label><input id="d-n" name="n" required minlength="2"></div>
        <div class="grid-3"><div class="field"><label for="d-s">Existencias</label><input id="d-s" name="s" type="number" min="0" value="0"></div>
        <div class="field"><label for="d-m">Mínimo</label><input id="d-m" name="m" type="number" min="0" value="0"></div>
        <div class="field"><label for="d-c">Costo unitario</label><input id="d-c" name="c" type="number" min="0" value="0"></div></div>`,
        async f => { await api("/api/admin/inventory", {method: "POST", body: {name: f.n.value, stock: Number(f.s.value), min_stock: Number(f.m.value), unit_cost: Number(f.c.value)}}); toast("Artículo agregado"); go("inventory"); });
      view.querySelectorAll("[data-mv]").forEach(b => b.onclick = () => dialog(`Movimiento · ${esc(b.dataset.n)}`, `
        <div class="field"><label for="d-t">Tipo</label><select id="d-t" name="t"><option value="1">Entrada (compra, donación)</option><option value="-1">Salida (consumo, merma)</option></select></div>
        <div class="grid-2"><div class="field"><label for="d-q">Cantidad</label><input id="d-q" name="q" type="number" min="1" required></div>
        <div class="field"><label for="d-r">Motivo</label><input id="d-r" name="r" required minlength="2" placeholder="Compra a proveedor"></div></div>`,
        async f => { await api(`/api/admin/inventory/${b.dataset.mv}/movement`, {method: "POST", body: {delta: Number(f.t.value) * Number(f.q.value), reason: f.r.value}}); toast("Movimiento registrado"); go("inventory"); }));
      view.querySelectorAll("[data-h]").forEach(b => b.onclick = guard(async () => {
        const m = await api(`/api/admin/inventory/${b.dataset.h}/movements`);
        dialog("Historial de movimientos", table(["Fecha", "Cambio", "Motivo"], m.map(x => `<tr><td>${esc(x.created_at)}</td><td><b style="color:${x.delta > 0 ? "var(--ok)" : "var(--bad)"}">${x.delta > 0 ? "+" : ""}${x.delta}</b></td><td>${esc(x.reason)}</td></tr>`), "Sin movimientos registrados."), null);
      }));
    },

    async reports() {
      const r = await api("/api/admin/reports");
      const card = (t, body, sub = "") => `<div class="card"><div class="card-head"><div><h3>${t}</h3>${sub ? `<small class="muted">${sub}</small>` : ""}</div></div><div class="card-body">${body}</div></div>`;
      const income = fillDays(r.income_by_day, addDays(new Date(), -29), new Date());
      const total30 = income.reduce((a, x) => a + x.value, 0);
      const appts = r.appointments_by_status.reduce((a, x) => a + x.value, 0);
      const done = (r.appointments_by_status.find(x => x.label === "completada") || {}).value || 0;
      const canc = (r.appointments_by_status.find(x => x.label === "cancelada") || {}).value || 0;
      view.innerHTML = head("Reportes", "Ingresos, agenda e inventario.",
        `${exportBtn("citas", "Citas CSV")}${exportBtn("pagos", "Pagos CSV")}`) +
        `<div class="kpis">${kpi("money", "ok", total30, "Ingresos últimos 30 días", "money")}
          ${kpi("checkCircle", "info", appts ? Math.round(done / appts * 100) : 0, "Citas completadas", "pct")}
          ${kpi("x", "bad", appts ? Math.round(canc / appts * 100) : 0, "Tasa de cancelación", "pct")}
          ${kpi("calendar", "violet", appts, "Citas registradas")}</div>
        <div class="card"><div class="card-head"><div><h3>Ingresos diarios</h3><small class="muted">Últimos 30 días</small></div></div><div class="card-body">${areaChart(income, money, "#12936B", {W: 1180, H: 260, axis: compactMoney})}</div></div>
        <div class="chart-grid">${card("Ingresos por especialidad", bars(r.income_by_specialty, money))}${card("Ingresos por método de pago", donut(r.methods, {}, money, "cobrado", compactMoney))}
        ${card("Citas por estado", donut(r.appointments_by_status, STATUS_COLOR, v => v, "citas"))}${card("Citas por canal", donut(r.channels.map(x => ({...x, label: chan(x.label)})), {}, v => v, "citas"), "Sitio web, asistente o recepción")}
        ${card("Citas por especialidad", bars(r.appointments_by_specialty))}${card("Insumos con bajo stock", bars(r.low_stock))}</div>`;
    },

    async assistant() {
      const m = await api(`/api/admin/chat-metrics?days=${filters.days}`);
      const start = m.funnel[0].sessions || 1;
      const card = (t, body, sub = "") => `<div class="card"><div class="card-head"><div><h3>${t}</h3>${sub ? `<small class="muted">${sub}</small>` : ""}</div></div><div class="card-body">${body}</div></div>`;
      view.innerHTML = head("Asistente virtual", "Métricas operativas anónimas de la recepción virtual. Sin datos clínicos.",
        `<div class="tabs" role="tablist" aria-label="Periodo">${[7, 30, 90].map(d => `<button role="tab" aria-selected="${d === filters.days}" data-days="${d}">${d} días</button>`).join("")}</div>`) +
        `<div class="kpis">${kpi("chat", "", m.conversations, "Conversaciones")}${kpi("calendar", "ok", m.bookings, "Reservas por el asistente")}
          ${kpi("funnel", "info", Math.round(m.conversion), "Conversión de reservas", "pct")}${kpi("checkCircle", "teal", Math.round(m.understood), "Mensajes comprendidos", "pct")}</div>
        <div class="kpis">${kpi("inbox", "warn", m.human_requests, "Solicitudes a recepción")}${kpi("search", "violet", m.lookups, "Consultas de cita")}
          ${kpi("x", "bad", m.cancellations, "Cancelaciones completadas")}${kpi("alert", "bad", m.availability_errors, "Errores de disponibilidad")}</div>
        <div class="chart-grid">
          ${card("Embudo de reservación", `<div class="funnel">${m.funnel.map((f, i) => `<div class="funnel-row"><span>${esc(f.label)}</span><span class="t"><i style="width:${Math.max(2, Math.round(f.sessions / start * 100))}%;animation-delay:${i * 60}ms"></i></span><b>${f.sessions} <small>${Math.round(f.sessions / start * 100)}%</small></b></div>`).join("")}</div>`, "Conversaciones que alcanzaron cada etapa")}
          ${card("Abandono por etapa", bars(m.abandon), "Conversaciones que no avanzaron a la siguiente etapa")}
          ${card("Intenciones detectadas", bars(m.intents), "«otro» = mensajes no comprendidos")}
          ${card("Frases no comprendidas", m.top_fallback.length ? table(["Frase (anonimizada)", "Veces"], m.top_fallback.map(t => `<tr><td>${esc(t.label)}</td><td><b>${t.value}</b></td></tr>`)) : `<p class="muted">Sin frases pendientes de revisar.</p>`, "Úsalas para ampliar el vocabulario de las reglas")}
        </div>
        <p class="hint">El asistente funciona con reglas y no aprende automáticamente: estas métricas sirven para que el equipo ajuste vocabulario, flujos y disponibilidad.</p>`;
      view.querySelectorAll("[data-days]").forEach(b => b.onclick = () => { filters.days = Number(b.dataset.days); go("assistant"); });
    },

    async audit() {
      const rows = await api("/api/admin/audit");
      view.innerHTML = head("Bitácora de auditoría", "Registro de las acciones realizadas por el personal.") +
        `<div class="card">${table(["Fecha y hora", "Usuario", "Acción"], rows.map(r => `<tr><td class="mono">${esc(r.created_at)}</td><td>${who(r.username)}</td><td>${esc(r.action)}</td></tr>`))}</div>`;
    },
  };

  async function profile(id) {
    const c = await api(`/api/admin/customers/${id}`);
    if (current !== "customers" && current !== "requests" && current !== "pipeline") current = "customers";
    view.classList.remove("enter");
    view.innerHTML = `<p><button class="btn btn-ghost btn-sm" id="back">${icon("back")}Volver</button></p>
      <div class="card"><div class="profile-head"><span class="avatar lg">${esc(initials(c.alias))}</span><div>
        <h1>${esc(c.alias)} ${badge(c.stage)}</h1>
        <div class="meta"><span>${icon("phone")}${esc(c.phone || "Sin teléfono")}</span><span>${icon("mail")}${esc(c.email || "Sin correo")}</span>
        <span>${icon("pin")}Origen: ${esc(chan(c.source))}</span><span>${icon("calendar")}Alta: ${esc(fmtDate(c.created_at))}</span></div></div></div></div>
      <div class="two-col">
        <div>
          <div class="card"><div class="card-head"><h3>Historial de seguimiento</h3></div><div class="card-body">
            <ul class="timeline">${c.interactions.map(i => `<li><b>${esc(i.kind)}</b><small>${esc(ago(i.created_at))}</small><p>${esc(i.note)}</p></li>`).join("") || "<li><p>Sin interacciones registradas.</p></li>"}</ul></div></div>
          <div class="card"><div class="card-head"><h3>Citas</h3></div>${table(["Folio", "Servicio", "Fecha", "Estado"], c.appointments.map(a => `<tr><td class="mono">${esc(a.code)}</td><td>${esc(a.specialty)}</td><td>${esc(fmtDate(a.date))} · ${esc(a.time)}</td><td>${badge(a.status)}</td></tr>`), "Este paciente aún no tiene citas.")}</div>
        </div>
        <div>
          <div class="card"><div class="card-head"><h3>Etapa del paciente</h3></div><div class="card-body">
            <div class="field"><label for="ns">Etapa</label><select id="ns">${STAGES.map(s => `<option value="${s}" ${s === c.stage ? "selected" : ""}>${s[0].toUpperCase() + s.slice(1)}</option>`).join("")}</select></div>
            <button class="btn btn-primary" id="sv">Actualizar etapa</button></div></div>
          <div class="card"><div class="card-head"><h3>Registrar seguimiento</h3></div><div class="card-body">
            <div class="field"><label for="ik">Tipo</label><select id="ik"><option value="llamada">Llamada</option><option value="mensaje">Mensaje</option><option value="visita">Visita</option><option value="nota">Nota</option></select></div>
            <div class="field"><label for="in">Nota</label><textarea id="in" maxlength="500" placeholder="Ej. Se confirmó asistencia por teléfono"></textarea></div>
            <button class="btn btn-primary" id="ai">Agregar al historial</button></div></div>
        </div>
      </div>`;
    void view.offsetWidth; view.classList.add("enter"); afterRender();
    $("back").onclick = () => go(current);
    $("sv").onclick = guard(async () => { await api(`/api/admin/customers/${id}`, {method: "PATCH", body: {stage: $("ns").value}}); toast("Etapa actualizada"); profile(id); });
    $("ai").onclick = guard(async () => {
      if (!$("in").value.trim()) return toast("Escribe una nota", false);
      await api(`/api/admin/customers/${id}/interactions`, {method: "POST", body: {kind: $("ik").value, note: $("in").value.trim()}});
      toast("Seguimiento registrado"); profile(id);
    });
  }

  // ------------------------------------------------------------ paleta de comandos
  const pal = $("palette"), palQ = $("pal-q"), palList = $("pal-list");
  let palItems = [], palSel = 0, palTimer;
  function openPalette() {
    if (!me) return;
    palQ.value = "";
    renderPalette([]);
    pal.showModal();
    palQ.focus();
  }
  function renderPalette(groups) {
    const q = palQ.value.trim().toLowerCase();
    const mods = MODULES.filter(m => allowed(m.v) && (!q || m.t.toLowerCase().includes(q)))
      .map(m => ({icon: m.i, label: m.t, hint: `G ${m.k.toUpperCase()}`, run: () => go(m.v)}));
    const actions = [
      {icon: "plus", label: "Registrar nueva cita", hint: "N", run: () => guard(walkIn)()},
      {icon: "external", label: "Abrir portal público", hint: "", run: () => window.open("/sitio", "_blank", "noopener")},
      {icon: "logout", label: "Cerrar sesión", hint: "", run: () => $("logout").click()},
    ].filter(a => !q || a.label.toLowerCase().includes(q));
    const sections = [...groups, ["Ir a", mods], ["Acciones", actions]].filter(([, items]) => items.length);
    palItems = sections.flatMap(([, items]) => items);
    palSel = Math.min(palSel, Math.max(0, palItems.length - 1));
    let idx = 0;
    palList.innerHTML = sections.length ? sections.map(([title, items]) => `<h5>${esc(title)}</h5>${items.map(it => {
      const i = idx++;
      return `<button class="pal-item" role="option" id="pal-${i}" data-i="${i}" aria-selected="${i === palSel}">${icon(it.icon)}<span>${esc(it.label)}${it.sub ? ` <small>· ${esc(it.sub)}</small>` : ""}</span>${it.hint ? `<kbd>${esc(it.hint)}</kbd>` : ""}</button>`;
    }).join("")}`).join("") : `<div class="pal-empty">Sin resultados para «${esc(palQ.value)}».</div>`;
    palQ.setAttribute("aria-activedescendant", palItems.length ? `pal-${palSel}` : "");
    palList.querySelectorAll(".pal-item").forEach(b => {
      b.onclick = () => runPal(Number(b.dataset.i));
      b.onmousemove = () => { if (palSel !== Number(b.dataset.i)) { palSel = Number(b.dataset.i); highlight(); } };
    });
  }
  function highlight() {
    palList.querySelectorAll(".pal-item").forEach(b => b.setAttribute("aria-selected", String(Number(b.dataset.i) === palSel)));
    const el = $(`pal-${palSel}`); if (el) el.scrollIntoView({block: "nearest"});
    palQ.setAttribute("aria-activedescendant", `pal-${palSel}`);
  }
  function runPal(i) { const it = palItems[i]; if (!it) return; pal.close(); setTimeout(it.run, 120); }
  palQ.addEventListener("input", () => {
    palSel = 0;
    renderPalette([]);
    clearTimeout(palTimer);
    const q = palQ.value.trim();
    if (q.length < 2) return;
    palTimer = setTimeout(async () => {
      try {
        const r = await api(`/api/admin/search?q=${encodeURIComponent(q)}`);
        if (palQ.value.trim() !== q) return;
        renderPalette([
          ["Pacientes", r.customers.map(c => ({icon: "user", label: c.alias, sub: `${c.phone || "sin teléfono"} · ${c.stage}`, run: () => guard(profile)(c.id)}))],
          ["Citas", r.appointments.map(a => ({icon: "calendar", label: `${a.code} · ${a.alias}`, sub: `${a.specialty} · ${fmtDate(a.date)} ${a.time}`, run: () => apptDetail(a)}))],
          ["Facturas", r.invoices.map(v => ({icon: "ticket", label: v.invoice, sub: `${money(v.amount)} · ${v.code}`, run: () => go("payments")}))],
        ].filter(([, items]) => items.length));
      } catch (e) { if (e.status === 401) { pal.close(); showLogin(); } }
    }, 220);
  });
  palQ.addEventListener("keydown", e => {
    if (e.key === "ArrowDown") { e.preventDefault(); palSel = Math.min(palItems.length - 1, palSel + 1); highlight(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); palSel = Math.max(0, palSel - 1); highlight(); }
    else if (e.key === "Enter") { e.preventDefault(); runPal(palSel); }
  });

  // ------------------------------------------------------------ atajos de teclado
  let gPending = 0;
  document.addEventListener("keydown", e => {
    if ($("app").hidden || !me) return;
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) || document.activeElement.isContentEditable;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); return; }
    if (typing || dlg.open || pal.open || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "/") { e.preventDefault(); openPalette(); return; }
    if (e.key === "Escape") { setNav(false); return; }
    if (e.key.toLowerCase() === "n") { e.preventDefault(); guard(walkIn)(); return; }
    if (e.key.toLowerCase() === "g") { gPending = Date.now(); return; }
    if (gPending && Date.now() - gPending < 1200) {
      const m = MODULES.find(x => x.k === e.key.toLowerCase() && allowed(x.v));
      gPending = 0;
      if (m) { e.preventDefault(); go(m.v); }
    }
  });

  // ------------------------------------------------------------ arranque
  document.querySelectorAll(".sidebar nav button").forEach(b => b.addEventListener("click", () => go(b.dataset.v)));
  $("menu-btn").addEventListener("click", () => setNav(!$("app").classList.contains("nav-open")));
  $("scrim").addEventListener("click", () => setNav(false));
  $("cmd-open").addEventListener("click", openPalette);
  $("bell").addEventListener("click", () => { filters.req = "pendiente"; go("requests"); });
  $("pw-toggle").addEventListener("click", () => {
    const p = $("p"), show = p.type === "password";
    p.type = show ? "text" : "password";
    $("pw-toggle").innerHTML = icon(show ? "eyeOff" : "eye");
    $("pw-toggle").setAttribute("aria-label", show ? "Ocultar contraseña" : "Mostrar contraseña");
  });
  $("login").addEventListener("submit", async e => {
    e.preventDefault();
    const m = $("login-msg"), btn = $("login-btn"), form = $("login");
    if (!$("u").value.trim() || !$("p").value) {
      m.className = "msg err"; m.innerHTML = icon("alert") + "<span>Escribe tu usuario y contraseña.</span>"; return;
    }
    btn.classList.add("is-loading"); btn.textContent = "Verificando";
    try {
      me = await api("/api/admin/login", {method: "POST", body: {username: $("u").value.trim(), password: $("p").value}});
      $("p").value = ""; m.className = "msg"; m.replaceChildren();
      showApp();
    } catch (err) {
      m.className = "msg err"; m.innerHTML = icon("alert") + `<span>${esc(err.message)}</span>`;
      form.classList.remove("shake"); void form.offsetWidth; form.classList.add("shake");
      $("p").select();
    } finally { btn.classList.remove("is-loading"); btn.textContent = "Entrar"; }
  });
  $("logout").addEventListener("click", async () => {
    try { await api("/api/admin/logout", {method: "POST"}); } catch (_) { /* sin red: se cierra localmente */ }
    toast("Sesión cerrada");
    showLogin();
  });
  api("/api/admin/me").then(u => { me = u; showApp(); }).catch(showLogin);
})();

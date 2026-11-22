"use strict";
// Recepción virtual MediBot 3.0 (widget). Se inserta en cualquier página pública.
// Privacidad: solo se guarda en sessionStorage el estado del flujo (sin alias, teléfono ni PIN) y un historial
// de texto con los datos personales enmascarados. El identificador de sesión es aleatorio y anónimo.
(function () {
  const KEY = "medibot.chat.v3";
  const SID_KEY = "medibot.sid";
  const PAGE = location.pathname.startsWith("/reservar") ? "reservar" : "sitio";
  const SENSITIVE = ["alias", "phone", "pin"];
  const plus = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>';
  const sid = (() => {
    let s = sessionStorage.getItem(SID_KEY);
    if (!s) { s = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2)).replace(/[^A-Za-z0-9-]/g, "").slice(0, 36); sessionStorage.setItem(SID_KEY, s); }
    return s;
  })();

  document.body.insertAdjacentHTML("beforeend", `
    <button id="chat-toggle" type="button" aria-controls="chat" aria-expanded="false" aria-label="Abrir recepción virtual">
      ${icon("chat")}<span class="pulse" aria-hidden="true"></span>
    </button>
    <section id="chat" role="dialog" aria-modal="false" aria-labelledby="chat-title">
      <div class="chat-head" id="chat-head">
        <span class="avatar" aria-hidden="true">${plus}</span>
        <div><b id="chat-title">MediBot · Recepción virtual</b><small id="chat-status">En línea · responde al instante</small></div>
        <div class="tools">
          <button id="chat-reset" type="button" aria-label="Reiniciar conversación" title="Reiniciar conversación">${icon("refresh")}</button>
          <button id="chat-close" type="button" aria-label="Cerrar asistente" title="Cerrar">${icon("x")}</button>
        </div>
      </div>
      <div class="chat-progress" id="chat-progress" hidden></div>
      <div class="chat-net" id="chat-net" hidden role="alert">${icon("wifiOff")}<span>Sin conexión con el servidor.</span><button type="button" id="chat-retry">Reintentar</button></div>
      <div id="chat-log" role="log" aria-live="polite" aria-relevant="additions" tabindex="0"></div>
      <div id="chat-opts" role="group" aria-label="Respuestas rápidas"></div>
      <form id="chat-form" autocomplete="off">
        <label for="chat-input" class="sr-only">Escribe tu mensaje</label>
        <input id="chat-input" maxlength="500" placeholder="Ej. cardiología el viernes después de las 11" enterkeyhint="send">
        <button class="btn btn-primary" aria-label="Enviar mensaje">${icon("send")}</button>
      </form>
      <div class="chat-legal">Asistente automático · no brinda diagnósticos · emergencias: 911</div>
    </section>`);

  const toggle = document.getElementById("chat-toggle");
  const box = document.getElementById("chat");
  const log = document.getElementById("chat-log");
  const opts = document.getElementById("chat-opts");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const progressEl = document.getElementById("chat-progress");
  let mem = load(), busy = false, expects = null, lastSend = null;
  const typedSecrets = [];  // solo en memoria: sirve para enmascarar ecos del bot antes de guardar
  const redact = text => typedSecrets.reduce((t, s) => s ? t.split(s).join("•••") : t, String(text));

  function blank() { return {state: {}, items: [], buttons: [], progress: null, expects: null, open: false}; }
  function load() { try { return Object.assign(blank(), JSON.parse(sessionStorage.getItem(KEY)) || {}); } catch (_) { return blank(); } }
  function save() {
    const st = {...mem.state};
    SENSITIVE.forEach(k => delete st[k]);  // el servidor volverá a pedirlos si se pierden
    try { sessionStorage.setItem(KEY, JSON.stringify({...mem, state: st, items: mem.items.slice(-40)})); } catch (_) { /* almacenamiento lleno */ }
  }
  const now = () => new Date().toLocaleTimeString("es-MX", {hour: "2-digit", minute: "2-digit"});
  const scroll = () => { log.scrollTop = log.scrollHeight; };

  // ---------------------------------------------------------- render de mensajes
  function userBubble(text, masked) {
    const d = document.createElement("div");
    d.className = "bubble me" + (masked ? " masked" : "");
    d.textContent = text;
    d.insertAdjacentHTML("beforeend", `<time>${now()}</time>`);
    log.appendChild(d); scroll();
  }
  function botRow(text, ui) {
    const row = document.createElement("div");
    row.className = "row-bot";
    row.innerHTML = `<span class="mini" aria-hidden="true">${plus}</span><div class="stack"></div>`;
    const stack = row.querySelector(".stack");
    if (text) {
      const b = document.createElement("div");
      b.className = "bubble bot";
      b.textContent = text;
      stack.appendChild(b);
    }
    if (ui) stack.insertAdjacentHTML("beforeend", component(ui));
    bindComponent(stack, ui);
    log.appendChild(row); scroll();
    return row;
  }
  function component(ui) {
    if (!ui) return "";
    if (ui.type === "cards") return `<div class="c-cards">${ui.items.map(it => `
      <button type="button" class="c-card" data-v="${esc(it.value)}" data-l="${esc(it.title)}">
        <span class="svc-ico">${icon(it.icon === "user" || it.icon === "clock" ? it.icon : specIcon(it.icon || it.title))}</span>
        <div><b>${esc(it.title)}</b>${it.subtitle ? `<small>${esc(it.subtitle)}</small>` : ""}</div>
        <span class="meta-r">${it.price ? `<b>${esc(it.price)}</b>` : ""}${it.meta ? `<small>${esc(it.meta)}</small>` : ""}</span>
      </button>`).join("")}</div>`;
    if (ui.type === "dates") return `<div class="c-dates" role="group" aria-label="Fechas disponibles">${ui.items.map(d => `
      <button type="button" class="c-date ${d.today ? "today" : ""}" data-v="${esc(d.value)}" data-l="${esc(d.label + " " + d.day + " " + d.month)}" aria-label="${esc(d.label + " " + d.day + " de " + d.month + ", " + d.sub)}">
        <small>${esc(d.label)}</small><b>${esc(d.day)}</b><span>${esc(d.sub)}</span></button>`).join("")}</div>`;
    if (ui.type === "slots") return `<div class="c-slots">${ui.groups.map(g => `
      <h6>${icon("user")}${esc(g.professional)}</h6>
      <div class="grid">${g.items.map(s => `<button type="button" data-v="${esc(s.value)}" data-l="${esc(s.label)}" aria-label="${esc(s.label + " con " + g.professional)}">${esc(s.label)}</button>`).join("")}</div>`).join("")}</div>`;
    if (ui.type === "summary") return `<div class="c-summary">${ui.rows.map(([k, v]) => `<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join("")}
      ${ui.edits ? `<div class="edits">${ui.edits.map(e => `<button type="button" data-v="${esc(e.value)}" data-l="${esc(e.label)}">${esc(e.label)}</button>`).join("")}</div>` : ""}</div>`;
    if (ui.type === "confirmation") return `<div class="c-confirm">
      <div class="top"><span class="ok-ico">${icon("check")}</span><b>Cita confirmada</b></div>
      <div class="codes">
        <div class="code"><small>Folio</small><div><b>${esc(ui.code)}</b><button type="button" data-copy="${esc(ui.code)}" aria-label="Copiar folio">${icon("copy")}</button></div></div>
        <div class="code"><small>PIN privado</small><div><b>${esc(ui.pin)}</b><button type="button" data-copy="${esc(ui.pin)}" aria-label="Copiar PIN">${icon("copy")}</button></div></div>
      </div>
      <div class="rows">${ui.rows.map(([k, v]) => `<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join("")}</div>
      <div class="foot"><a class="btn btn-outline btn-sm" href="${esc(ui.ics)}">${icon("download")}Calendario</a>
        <button type="button" class="btn btn-outline btn-sm" data-copy="Folio: ${esc(ui.code)} · PIN: ${esc(ui.pin)}">${icon("copy")}Copiar ambos</button></div>
    </div>`;
    if (ui.type === "appointment") return `<div class="c-appt"><header><b>${esc(ui.code)}</b><span class="badge ${esc(ui.status)}">${esc(ui.status)}</span></header>
      ${ui.rows.map(([k, v]) => `<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join("")}</div>`;
    if (ui.type === "emergency") return `<div class="c-emergency">${icon("alert")}<b>Emergencias</b><a class="btn btn-danger btn-sm" href="tel:${esc(ui.number)}">${icon("phone")}Llamar al ${esc(ui.number)}</a></div>`;
    return "";
  }
  function bindComponent(root, ui) {
    root.querySelectorAll("[data-v]").forEach(b => b.addEventListener("click", () => send(b.dataset.v, b.dataset.l)));
    root.querySelectorAll("[data-copy]").forEach(b => b.addEventListener("click", async () => {
      const ok = await copyText(b.dataset.copy);
      const prev = b.innerHTML;
      b.innerHTML = icon(ok ? "check" : "alert") + (b.textContent.trim() ? (ok ? "Copiado" : "Error") : "");
      setTimeout(() => { b.innerHTML = prev; }, 1600);
    }));
  }
  function setButtons(buttons) {
    mem.buttons = buttons || [];
    opts.replaceChildren();
    mem.buttons.forEach((b, i) => {
      const el = document.createElement("button");
      el.type = "button";
      el.textContent = b.label;
      if (b.primary) el.className = "primary";
      if (b.danger) el.className = "danger";
      el.style.animationDelay = `${i * 30}ms`;
      el.addEventListener("click", () => send(b.value, b.label));
      opts.appendChild(el);
    });
  }
  function setProgress(p) {
    mem.progress = p || null;
    progressEl.hidden = !p;
    if (!p) return;
    progressEl.innerHTML = `<ol aria-hidden="true">${p.labels.map((_, i) => `<li class="${i < p.current ? "on" : ""}"></li>`).join("")}</ol>
      <span>Paso ${p.current} de ${p.total} · ${esc(p.labels[p.current - 1])}</span>`;
  }
  function setExpects(kind) {
    expects = mem.expects = kind || null;
    input.type = kind === "pin" ? "password" : "text";
    input.inputMode = kind === "phone" || kind === "pin" ? "numeric" : "text";
    input.placeholder = {alias: "Escribe un alias o nombre corto", phone: "10 dígitos", pin: "PIN de 6 dígitos", folio: "MB-XXXXXXXX"}[kind] || "Escribe tu mensaje…";
    input.autocomplete = "off";
  }
  function setOnline(ok) {
    document.getElementById("chat-net").hidden = ok;
    document.getElementById("chat-head").classList.toggle("offline", !ok);
    document.getElementById("chat-status").textContent = ok ? "En línea · responde al instante" : "Sin conexión";
  }

  // ---------------------------------------------------------- envío
  async function send(message, shown, silent) {
    if (busy) return;
    busy = true;
    lastSend = [message, shown, silent];
    const masked = SENSITIVE.includes(expects) && !String(message).startsWith("#");
    if (!silent) {
      const visible = shown || message;
      userBubble(visible, false);
      if (masked) typedSecrets.push(String(message).trim());
      mem.items.push({who: "me", text: masked ? "••••••" : visible});
    }
    opts.replaceChildren();
    const typing = document.createElement("div");
    typing.className = "row-bot";
    typing.innerHTML = `<span class="mini" aria-hidden="true">${plus}</span><div class="bubble bot typing" aria-label="MediBot está escribiendo"><i></i><i></i><i></i></div>`;
    log.appendChild(typing); scroll();
    try {
      const [out] = await Promise.all([
        api("/api/chat", {method: "POST", body: {message, state: mem.state, page: PAGE, session: sid}}),
        new Promise(r => setTimeout(r, REDUCED ? 0 : 320))]);
      typing.remove();
      setOnline(true);
      mem.state = out.state || {};
      botRow(out.reply, out.ui);
      // Historial: los componentes no se guardan (el de confirmación contiene el PIN).
      mem.items.push({who: "bot", text: redact(out.reply) + (out.ui && out.ui.type === "confirmation" ? `\nFolio ${out.ui.code} (PIN no guardado)` : "")});
      setButtons(out.buttons);
      setProgress(out.progress);
      setExpects(out.expects);
      save();
    } catch (e) {
      typing.remove();
      setOnline(e.status !== 0);
      if (e.status !== 0) { botRow(e.message || "Ocurrió un error. Inténtalo de nuevo."); setButtons(mem.buttons); }
    } finally {
      busy = false;
      if (box.classList.contains("open") && !matchMedia("(pointer:coarse)").matches) input.focus();
    }
  }
  function open(v) {
    box.classList.toggle("open", v);
    document.body.classList.toggle("chat-open", v);
    toggle.setAttribute("aria-expanded", String(v));
    toggle.setAttribute("aria-label", v ? "Cerrar recepción virtual" : "Abrir recepción virtual");
    toggle.innerHTML = v ? icon("x") : icon("chat") + '<span class="pulse" aria-hidden="true"></span>';
    mem.open = v; save();
    if (v && !log.children.length) send("Hola", null, true);
    if (v) setTimeout(() => input.focus(), 60);
  }
  function reset() {
    mem = blank(); mem.open = true;
    log.replaceChildren(); setProgress(null); setExpects(null); save();
    send("Hola", null, true);
  }

  // Restaura el historial de texto de la sesión.
  mem.items.forEach(it => it.who === "me" ? userBubble(it.text, it.text === "••••••") : botRow(it.text));
  setButtons(mem.buttons);
  setProgress(mem.progress);
  setExpects(mem.expects);
  if (mem.open && innerWidth > 720) open(true);

  toggle.addEventListener("click", () => open(!box.classList.contains("open")));
  document.getElementById("chat-close").addEventListener("click", () => { open(false); toggle.focus(); });
  document.getElementById("chat-reset").addEventListener("click", reset);
  document.getElementById("chat-retry").addEventListener("click", () => { if (lastSend) { log.lastElementChild?.classList.contains("bubble") && log.lastElementChild.remove(); send(...lastSend); } });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && box.classList.contains("open")) { open(false); toggle.focus(); } });
  document.querySelectorAll("[data-open-chat]").forEach(b => b.addEventListener("click", () => open(true)));
  window.addEventListener("online", () => setOnline(true));
  form.addEventListener("submit", e => {
    e.preventDefault();
    const v = input.value.trim();
    if (v && !busy) { input.value = ""; send(v); }
  });
})();

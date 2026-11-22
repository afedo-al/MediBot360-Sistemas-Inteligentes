"use strict";
// Reservación por pasos: especialidad → especialista (opcional) → fecha → horario → datos → confirmación con folio y PIN.
(async function () {
  const $ = id => document.getElementById(id);
  const DOW = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];
  const MON = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  const iso = d => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  const longDate = s => new Date(s + "T12:00:00").toLocaleDateString("es-MX", {weekday: "long", day: "numeric", month: "long"});
  const sel = {spec: null, pro: null, date: "", time: "", proName: ""};
  let specs = [], pros = [];

  function show(id, text, ok) {
    const el = $(id);
    el.className = "msg " + (ok ? "ok" : "err");
    el.innerHTML = icon(ok ? "checkCircle" : "alert") + `<span>${esc(text)}</span>`;
  }
  const clearMsg = id => { $(id).className = "msg"; $(id).replaceChildren(); };

  // ---- Pestañas
  function tab(which) {
    const look = which === "look";
    $("tab-book").setAttribute("aria-selected", String(!look));
    $("tab-look").setAttribute("aria-selected", String(look));
    $("pane-book").hidden = look;
    $("pane-look").hidden = !look;
  }
  $("tab-book").addEventListener("click", () => { tab("book"); history.replaceState(null, "", "/reservar"); });
  $("tab-look").addEventListener("click", () => { tab("look"); history.replaceState(null, "", "#mis-citas"); });
  if (location.hash === "#mis-citas") tab("look");
  window.addEventListener("hashchange", () => tab(location.hash === "#mis-citas" ? "look" : "book"));

  // ---- Resumen persistente y progreso
  function setVal(id, text) {
    const el = $(id);
    if (el.textContent === text) return;
    el.textContent = text;
    el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
  }
  function summary() {
    const s = specs.find(x => x.id === sel.spec);
    setVal("s-spec", s ? s.name : "—");
    setVal("s-pro", sel.proName || (sel.pro ? (pros.find(p => p.id === sel.pro) || {}).name : (s ? "Primer especialista disponible" : "—")) || "—");
    setVal("s-date", sel.date ? longDate(sel.date) : "—");
    setVal("s-time", sel.time ? sel.time + " h" : "—");
    setVal("s-price", s ? money(s.price) : "$0");
    const done = [!!sel.spec, !!(sel.date && sel.time), $("alias").value.trim().length >= 2];
    const cur = done.indexOf(false) === -1 ? 3 : done.indexOf(false);
    $("stepper").querySelectorAll("li").forEach((li, i) => {
      li.classList.toggle("done", i < cur);
      li.classList.toggle("cur", i === cur);
    });
  }
  $("alias").addEventListener("input", summary);

  // ---- Paso 1: especialidades
  try {
    specs = await api("/api/specialties");
  } catch (e) {
    $("spec").innerHTML = `<p class="empty">${esc(e.message)}</p>`;
    return;
  }
  $("spec").innerHTML = specs.map(s => `
    <button type="button" class="spec-opt" role="radio" aria-checked="false" data-id="${s.id}">
      <span class="svc-ico">${icon(specIcon(s.name))}</span>
      <b>${esc(s.name)}</b><small>${money(s.price)}</small>
    </button>`).join("");
  $("spec").querySelectorAll(".spec-opt").forEach(b => b.addEventListener("click", () => pickSpec(Number(b.dataset.id))));
  $("spec").addEventListener("keydown", e => {  // navegación con flechas en el grupo de radio
    if (!["ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp"].includes(e.key)) return;
    const opts = [...$("spec").querySelectorAll(".spec-opt")];
    const i = opts.indexOf(document.activeElement);
    const next = opts[(i + (e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : -1) + opts.length) % opts.length];
    e.preventDefault(); next.focus(); next.click();
  });

  async function pickSpec(id) {
    sel.spec = id; sel.pro = null; sel.time = ""; sel.proName = "";
    $("spec").querySelectorAll(".spec-opt").forEach(b => b.setAttribute("aria-checked", String(Number(b.dataset.id) === id)));
    pros = await api(`/api/professionals?specialty_id=${id}`).catch(() => []);
    $("pro-wrap").hidden = pros.length < 2;
    $("pros").innerHTML = [`<button type="button" aria-pressed="true" data-pro="">${icon("clock")}Sin preferencia</button>`]
      .concat(pros.map(p => `<button type="button" aria-pressed="false" data-pro="${p.id}">${icon("user")}${esc(p.name)}</button>`)).join("");
    $("pros").querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
      sel.pro = b.dataset.pro ? Number(b.dataset.pro) : null; sel.time = ""; sel.proName = "";
      $("pros").querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
      summary(); loadSlots();
    }));
    summary();
    if (sel.date) loadSlots();
  }

  // ---- Paso 2: días (próximas 3 semanas, sin domingos) y horarios por especialista
  const today = new Date();
  const days = [];
  for (let i = 0; days.length < 18 && i < 45; i++) {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() + i);
    if (d.getDay() !== 0) days.push(d);
  }
  $("days").innerHTML = days.map(d => `
    <button type="button" class="day" aria-pressed="false" data-d="${iso(d)}" aria-label="${longDate(iso(d))}">
      <small>${DOW[d.getDay()]}</small><b>${d.getDate()}</b><span>${MON[d.getMonth()]}</span>
    </button>`).join("");
  $("days").querySelectorAll(".day").forEach(b => b.addEventListener("click", () => {
    sel.date = b.dataset.d; sel.time = ""; sel.proName = "";
    $("days").querySelectorAll(".day").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    summary(); loadSlots();
  }));

  async function loadSlots() {
    const box = $("slots");
    if (!sel.spec || !sel.date) {
      box.innerHTML = `<p class="empty">${!sel.spec ? "Selecciona primero una especialidad." : "Selecciona una fecha."}</p>`;
      return;
    }
    box.innerHTML = Array.from({length: 6}, () => `<div class="sk" style="height:44px"></div>`).join("");
    try {
      const q = `/api/slots?specialty_id=${sel.spec}&date=${sel.date}&detailed=true` + (sel.pro ? `&professional_id=${sel.pro}` : "");
      const rows = await api(q);
      if (!rows.length) { box.innerHTML = `<p class="empty">No hay horarios libres este día. Prueba con otra fecha.</p>`; return; }
      // Sin preferencia: una opción por hora (primer especialista libre); con varios, se muestra el nombre.
      const seen = new Map();
      rows.forEach(r => { if (sel.pro || !seen.has(r.time)) seen.set(sel.pro ? r.time + r.professional_id : r.time, r); });
      box.replaceChildren();
      [...seen.values()].forEach((r, i) => {
        const b = document.createElement("button");
        b.type = "button"; b.className = "slot"; b.setAttribute("aria-pressed", "false");
        b.innerHTML = `${esc(r.time)}${pros.length > 1 ? `<small>${esc(r.professional.split(" ").slice(0, 2).join(" "))}</small>` : ""}`;
        b.setAttribute("aria-label", `${r.time} con ${r.professional}`);
        b.style.animation = `fadeUp .24s ${i * 20}ms var(--ease) both`;
        b.addEventListener("click", () => {
          sel.time = r.time; sel.proName = r.professional; sel.slotPro = r.professional_id;
          box.querySelectorAll(".slot").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
          summary();
        });
        box.appendChild(b);
      });
    } catch (e) { box.innerHTML = `<p class="empty">${esc(e.message)}</p>`; }
  }

  const pre = Number(new URLSearchParams(location.search).get("especialidad"));
  if (specs.some(s => s.id === pre)) pickSpec(pre);
  summary();

  // ---- Confirmar
  $("book").addEventListener("submit", async e => {
    e.preventDefault();
    clearMsg("book-msg"); $("ticket").replaceChildren();
    const alias = $("alias").value.trim(), phone = $("phone").value.trim();
    $("alias").removeAttribute("aria-invalid"); $("phone").removeAttribute("aria-invalid");
    if (!sel.spec) return show("book-msg", "Selecciona una especialidad.", false);
    if (!sel.date || !sel.time) return show("book-msg", "Selecciona fecha y horario.", false);
    if (alias.length < 2) { $("alias").setAttribute("aria-invalid", "true"); $("alias").focus(); return show("book-msg", "Escribe un alias de al menos 2 caracteres.", false); }
    if (phone && !/^\d{10}$/.test(phone)) { $("phone").setAttribute("aria-invalid", "true"); $("phone").focus(); return show("book-msg", "El teléfono debe tener 10 dígitos.", false); }
    $("submit").classList.add("is-loading");
    try {
      const r = await api("/api/appointments", {method: "POST", body: {
        specialty_id: sel.spec, date: sel.date, time: sel.time, alias, phone, email: $("email").value.trim(),
        professional_id: sel.slotPro || null}});
      show("book-msg", "¡Tu cita quedó confirmada!", true);
      $("ticket").innerHTML = `<div class="ticket">
          <div class="pin-box"><div><small>Folio</small><b>${esc(r.code)}</b></div><div><small>PIN privado</small><b>${esc(r.pin)}</b></div></div>
          <span>${esc(r.specialty)} con ${esc(r.professional)}<br>${esc(longDate(r.date))} · ${esc(r.time)} h</span></div>
        <div class="ticket-actions no-print">
          <button type="button" class="btn btn-outline btn-sm" id="copy">${icon("copy")}Copiar folio y PIN</button>
          <a class="btn btn-outline btn-sm" href="/api/appointments/${encodeURIComponent(r.code)}/ics?pin=${encodeURIComponent(r.pin)}">${icon("download")}Agregar al calendario</a>
          <button type="button" class="btn btn-outline btn-sm" id="print">${icon("printer")}Imprimir</button>
        </div>
        <p class="hint" style="text-align:center">Guarda tu folio y tu PIN: los necesitarás para consultar o cancelar. El PIN no se vuelve a mostrar.</p>`;
      $("print").addEventListener("click", () => window.print());
      $("copy").addEventListener("click", async () => {
        const ok = await copyText(`Folio: ${r.code} · PIN: ${r.pin}`);
        $("copy").innerHTML = icon(ok ? "check" : "alert") + (ok ? "Copiado" : "No se pudo copiar");
      });
      $("stepper").querySelectorAll("li").forEach(li => { li.classList.add("done"); li.classList.remove("cur"); });
      $("code").value = r.code;
      sel.time = ""; loadSlots();
      $("ticket").scrollIntoView({behavior: REDUCED ? "auto" : "smooth", block: "nearest"});
    } catch (err) {
      show("book-msg", err.message, false);
      sel.time = ""; summary(); loadSlots();
    } finally { $("submit").classList.remove("is-loading"); }
  });

  // ---- Mis citas (folio + PIN)
  function renderResult(a, pin) {
    const r = $("look-result");
    r.hidden = false;
    r.innerHTML = `<div class="status-card"><span class="avatar lg">${icon(specIcon(a.specialty))}</span>
      <div><b style="font-size:17px">${esc(a.specialty)}</b> <span class="badge ${esc(a.status)}">${esc(a.status)}</span>
      <div class="meta" style="margin-top:8px"><span>${icon("user")}${esc(a.professional)}</span>
      <span>${icon("calendar")}${esc(longDate(a.date))}</span><span>${icon("clock")}${esc(a.time)} h</span></div></div></div>
      ${a.status === "confirmada" ? `<div class="ticket-actions" style="justify-content:flex-start"><a class="btn btn-outline btn-sm" href="/api/appointments/${encodeURIComponent(a.code)}/ics?pin=${encodeURIComponent(pin)}">${icon("download")}Agregar al calendario</a></div>` : ""}`;
  }
  const lookArgs = () => [$("code").value.trim().toUpperCase(), $("lpin").value.trim()];
  function validLook(code, pin) {
    if (!/^MB-[A-Z0-9]{8}$/.test(code)) { show("look-msg", "El folio tiene el formato MB-XXXXXXXX.", false); return false; }
    if (!/^\d{6}$/.test(pin)) { show("look-msg", "El PIN tiene 6 dígitos.", false); return false; }
    return true;
  }
  $("lookup").addEventListener("submit", async e => {
    e.preventDefault(); clearMsg("look-msg");
    const [code, pin] = lookArgs();
    if (!validLook(code, pin)) return;
    $("btn-find").classList.add("is-loading");
    try { renderResult(await api(`/api/appointments/${encodeURIComponent(code)}?pin=${encodeURIComponent(pin)}`), pin); }
    catch (err) { $("look-result").hidden = true; show("look-msg", err.message, false); }
    finally { $("btn-find").classList.remove("is-loading"); }
  });
  $("btn-cancel").addEventListener("click", async () => {
    clearMsg("look-msg");
    const [code, pin] = lookArgs();
    if (!validLook(code, pin)) return;
    if (!confirm("¿Seguro que quieres cancelar esta cita? El horario quedará libre para otra persona.")) return;
    try {
      const r = await api(`/api/appointments/${encodeURIComponent(code)}/cancel`, {method: "POST", body: {pin}});
      show("look-msg", `La cita ${r.code} fue cancelada.`, true);
      renderResult(await api(`/api/appointments/${encodeURIComponent(code)}?pin=${encodeURIComponent(pin)}`), pin);
    } catch (err) { show("look-msg", err.message, false); }
  });
})();

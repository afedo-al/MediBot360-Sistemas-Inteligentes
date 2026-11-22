"use strict";
(async function () {
  const $ = id => document.getElementById(id);
  const relDay = iso => {
    const d = new Date(iso + "T12:00:00"), t = new Date(); t.setHours(12, 0, 0, 0);
    const diff = Math.round((d - t) / 864e5);
    if (diff === 0) return "Hoy";
    if (diff === 1) return "Mañana";
    return d.toLocaleDateString("es-MX", {weekday: "short", day: "numeric", month: "short"}).replace(/\.$/, "");
  };

  try {
    const [sp, next, stats] = await Promise.all([api("/api/specialties"), api("/api/next-available"), api("/api/stats")]);
    const nextBy = Object.fromEntries(next.map(n => [n.specialty_id, n]));

    // Buscador rápido del hero
    $("qb-spec").insertAdjacentHTML("beforeend", sp.map(s => `<option value="${s.id}">${esc(s.name)} · ${money(s.price)}</option>`).join(""));

    // Panel de disponibilidad en vivo
    $("av-list").innerHTML = next.map(n => `
      <li><a href="/reservar?especialidad=${n.specialty_id}">
        <span class="svc-ico">${icon(specIcon(n.specialty))}</span>
        <span class="av-main"><b>${esc(n.specialty)}</b><small>${esc(n.professional || "Sin horarios próximos")}</small></span>
        <span class="av-when">${n.date ? `<b>${esc(relDay(n.date))}</b><small>${esc(n.time)} h</small>` : "<small>—</small>"}</span>
      </a></li>`).join("");

    // Tarjetas de especialidades
    $("specialties").innerHTML = sp.map(s => {
      const n = nextBy[s.id];
      return `<article class="svc reveal">
        <div class="svc-top"><span class="svc-ico">${icon(specIcon(s.name))}</span>
          ${n && n.date ? `<span class="tag-next">${icon("clock")}${esc(relDay(n.date))} ${esc(n.time)}</span>` : ""}</div>
        <h3>${esc(s.name)}</h3>
        <p>${esc(s.description)}</p>
        ${s.professionals ? `<span class="doc">${icon("user")}${esc(s.professionals)}</span>` : ""}
        <div class="svc-foot">
          <span class="price">${money(s.price).replace(" MXN", "")}<small>MXN</small></span>
          <a href="/reservar?especialidad=${s.id}">Agendar ${icon("arrow")}</a>
        </div>
      </article>`;
    }).join("");

    // Equipo y cifras
    const pros = sp.flatMap(s => (s.professionals || "").split(", ").filter(Boolean).map(p => ({name: p, spec: s.name})));
    $("team").innerHTML = pros.map(p =>
      `<div class="member reveal"><span class="avatar lg">${esc(initials(p.name))}</span><b>${esc(p.name)}</b><span>${esc(p.spec)}</span></div>`).join("");
    $("c-specs").dataset.count = sp.length;
    $("c-pros").dataset.count = pros.length;
    $("c-appts").dataset.count = stats.total;
  } catch (e) {
    $("specialties").innerHTML = `<p class="empty">No se pudo cargar el catálogo. Intenta de nuevo más tarde.</p>`;
    $("av-list").innerHTML = `<li class="empty">Disponibilidad no disponible por el momento.</li>`;
  }
  observeReveal();
})();

"use strict";
// Utilidades compartidas: fetch JSON con manejo de errores, escape de HTML e iconos SVG.
async function api(url, opts = {}) {
  const init = {method: opts.method || "GET", headers: {}, credentials: "same-origin"};
  if (opts.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.body);
  }
  let res;
  try {
    res = await fetch(url, init);
  } catch (_) {
    const err = new Error("No hay conexión con el servidor. Revisa tu red e inténtalo de nuevo.");
    err.status = 0;
    throw err;
  }
  let data = null;
  try { data = await res.json(); } catch (_) { /* sin cuerpo */ }
  if (!res.ok) {
    let detail = data && data.detail;
    if (Array.isArray(detail)) detail = detail.map(d => d.msg).join("; ");
    const err = new Error(detail || "Error " + res.status);
    err.status = res.status;
    throw err;
  }
  return data;
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}
const money = n => "$" + Number(n || 0).toLocaleString("es-MX", {maximumFractionDigits: 0}) + " MXN";
const initials = name => String(name || "?").replace(/^(Dra?\.|Psic\.|L\. ?N\.)\s*/i, "").split(/\s+/).slice(0, 2).map(w => w[0]).join("").toUpperCase();

const ICONS = {
  stethoscope: '<path d="M6 3v6a4 4 0 0 0 8 0V3"/><path d="M10 13v2a5 5 0 0 0 10 0v-2"/><circle cx="20" cy="11" r="2"/>',
  heart: '<path d="M20.8 5.6a5.5 5.5 0 0 0-7.8 0L12 6.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l8.8 8.8 8.8-8.8a5.5 5.5 0 0 0 0-7.8z"/><path d="M3.5 12h4l2-3 3 6 2-3h6"/>',
  skin: '<path d="M12 2.7S6 9 6 14a6 6 0 0 0 12 0c0-5-6-11.3-6-11.3z"/><path d="M10 15a2 2 0 0 0 2 2"/>',
  baby: '<circle cx="12" cy="8" r="5"/><path d="M9.5 8h.01M14.5 8h.01M10 10.5a3 3 0 0 0 4 0"/><path d="M5 21a7 7 0 0 1 14 0"/>',
  apple: '<path d="M12 7c-2-2-6-1.5-7 2s.5 9 3.5 11c1.3.9 2.3.5 3.5 0 1.2.5 2.2.9 3.5 0 3-2 4.5-8 3.5-11s-5-4-7-2z"/><path d="M12 7c0-2 1-4 3-4"/>',
  brain: '<path d="M9.5 3A2.5 2.5 0 0 0 7 5.5v.1A3 3 0 0 0 4.6 10 3 3 0 0 0 5 15.5 3 3 0 0 0 9.5 20h.5V3z"/><path d="M14.5 3A2.5 2.5 0 0 1 17 5.5v.1a3 3 0 0 1 2.4 4.4 3 3 0 0 1-.4 5.5 3 3 0 0 1-4.5 4.5H14V3z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  calendar: '<rect x="3" y="4.5" width="18" height="17" rx="2.5"/><path d="M16 2.5v4M8 2.5v4M3 10h18"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.9A8 8 0 1 1 21 12z"/><path d="M8.5 12h.01M12 12h.01M15.5 12h.01"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
  ticket: '<path d="M3 9a3 3 0 0 0 0 6v3a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3a3 3 0 0 1 0-6V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v3z"/><path d="M13 5v2M13 11v2M13 17v2"/>',
  pin: '<path d="M12 22s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="10" r="2.5"/>',
  phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/>',
  mail: '<rect x="2.5" y="4.5" width="19" height="15" rx="2"/><path d="m3 6 9 7 9-7"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  checkCircle: '<circle cx="12" cy="12" r="9"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  send: '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7z"/>',
  menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  funnel: '<path d="M3 4h18l-7 8.5V19l-4 2v-8.5L3 4z"/>',
  card: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20M6 15h4"/>',
  layers: '<path d="m12 2 10 5-10 5L2 7l10-5z"/><path d="m2 17 10 5 10-5M2 12l10 5 10-5"/>',
  box: '<path d="M21 8 12 3 3 8v8l9 5 9-5V8z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
  chart: '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 6-6"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  money: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 12h.01M18 12h.01"/>',
  external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  printer: '<path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
  chevL: '<path d="m15 18-6-6 6-6"/>', chevR: '<path d="m9 18 6-6-6-6"/>',
  walk: '<circle cx="12" cy="5" r="2"/><path d="m10 22 2-7 3 3v6M8 12l2-4h4l2 3 3 1"/>',
  eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  eyeOff: '<path d="M9.9 4.2A10 10 0 0 1 12 4c6.4 0 10 8 10 8a17 17 0 0 1-2.2 3.2M6.6 6.6A17 17 0 0 0 2 12s3.6 8 10 8a9.7 9.7 0 0 0 5.4-1.6M3 3l18 18M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
  inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
  bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
  copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  back: '<path d="M19 12H5M11 18l-6-6 6-6"/>',
  wifiOff: '<path d="M2 8.8a15 15 0 0 1 4.2-2.6M10.7 5.1A15 15 0 0 1 22 8.8M5 12.9a10 10 0 0 1 5.2-2.7M16.8 11a10 10 0 0 1 2.2 1.9M8.5 16.4a5 5 0 0 1 7 0M12 20h.01M2 2l20 20"/>',
};
function icon(name, cls = "ico") {
  return `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.plus}</svg>`;
}
function specIcon(name) {
  const n = String(name).toLowerCase();
  if (n.includes("cardio")) return "heart";
  if (n.includes("dermat")) return "skin";
  if (n.includes("pediat")) return "baby";
  if (n.includes("nutri")) return "apple";
  if (n.includes("psico")) return "brain";
  if (n.includes("general")) return "stethoscope";
  return "plus";
}
// Animación de aparición al hacer scroll y contadores numéricos (respeta «reducir movimiento»).
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
document.documentElement.classList.add("js");
function countUp(el) {
  const target = Number(el.dataset.count || 0);
  const fmt = el.dataset.fmt === "money" ? money : el.dataset.fmt === "pct" ? v => v + "%" : v => v.toLocaleString("es-MX");
  if (REDUCED || !target) { el.textContent = fmt(target); return; }
  const t0 = performance.now(), dur = 900;
  const step = now => {
    const p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    el.textContent = fmt(Math.round(target * e));
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
function observeReveal(root = document) {
  const items = root.querySelectorAll(".reveal:not(.in), [data-count]:not(.counted)");
  if (!("IntersectionObserver" in window) || REDUCED) {
    items.forEach(el => { el.classList.add("in"); if (el.hasAttribute("data-count")) { el.classList.add("counted"); countUp(el); } });
    return;
  }
  const io = new IntersectionObserver(entries => entries.forEach(en => {
    if (!en.isIntersecting) return;
    const el = en.target;
    el.classList.add("in");
    if (el.hasAttribute("data-count")) { el.classList.add("counted"); countUp(el); }
    io.unobserve(el);
  }), {rootMargin: "0px 0px -40px 0px", threshold: 0.01});
  items.forEach((el, i) => { if (el.classList.contains("reveal")) el.style.transitionDelay = `${(i % 4) * 60}ms`; io.observe(el); });
}

// Rellena los <i data-icon="..."> estáticos del HTML.
function hydrateIcons(root = document) {
  root.querySelectorAll("i[data-icon]").forEach(el => { el.outerHTML = icon(el.dataset.icon, el.className || "ico"); });
}
document.addEventListener("DOMContentLoaded", () => {
  hydrateIcons();
  const t = document.querySelector(".nav-toggle"), nav = document.querySelector(".main-nav");
  if (t && nav) t.addEventListener("click", () => { const o = nav.classList.toggle("open"); t.setAttribute("aria-expanded", o); });
  const y = document.getElementById("year"); if (y) y.textContent = new Date().getFullYear();
  const header = document.querySelector(".site-header");
  if (header) {
    const onScroll = () => header.classList.toggle("scrolled", window.scrollY > 8);
    window.addEventListener("scroll", onScroll, {passive: true});
    onScroll();
  }
});
// Copia texto al portapapeles con alternativa para navegadores sin API moderna.
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (_) {
    const ta = Object.assign(document.createElement("textarea"), {value: text});
    document.body.appendChild(ta); ta.select();
    const ok = document.execCommand("copy"); ta.remove(); return ok;
  }
}

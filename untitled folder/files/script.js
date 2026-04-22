/* ════════════════════════════════════════════════════════════
   FarFinder v2 — script.js — Enhanced with Accessibility & UX
   Features: Form validation, Toast notifications, Debouncing,
             Local storage, Error handling, Accessibility
   ════════════════════════════════════════════════════════════ */

const API = "http://127.0.0.1:8001";
const $ = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);

// ── State ──────────────────────────────────────────────────
let allRoutes   = [];
let adults      = 1;
let activeSort  = "price";
let activeType  = "all";
let flxDays     = 3;
let requestInProgress = false;

// ── Defaults ─────────────────────────────────────────────
const defaultDate = () => {
  const d = new Date();
  d.setDate(d.getDate() + 7);
  return d.toISOString().split("T")[0];
};

const todayStr = () => new Date().toISOString().split("T")[0];

// ── Initialize ───────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  setInitialDefaults();
  loadFromStorage();
  setupAccessibility();
});

function setInitialDefaults() {
  $("fDate").value    = defaultDate();
  $("fDate").min      = todayStr();
  $("flxDate").value  = defaultDate();
  $("flxDate").min    = todayStr();
  $("cMonth").value   = new Date().toISOString().slice(0, 7);
}

function setupAccessibility() {
  // Add aria-live announcements for status updates
  const liveRegion = document.createElement("div");
  liveRegion.id = "ariaLive";
  liveRegion.setAttribute("aria-live", "polite");
  liveRegion.setAttribute("aria-atomic", "true");
  liveRegion.setAttribute("class", "sr-only");
  document.body.appendChild(liveRegion);
}

function announceToScreen(message) {
  const liveRegion = $("ariaLive");
  if (liveRegion) {
    liveRegion.textContent = message;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
//  TOAST NOTIFICATIONS
// ─────────────────────────────────────────────────────────────────────────────

function showToast(message, type = "info") {
  const container = $("toastContainer");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  toast.setAttribute("role", "status");
  
  container.appendChild(toast);
  
  setTimeout(() => {
    toast.style.animation = "slideOut 0.3s ease-in forwards";
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// ─────────────────────────────────────────────────────────────────────────────
//  LOCAL STORAGE HELPERS
// ─────────────────────────────────────────────────────────────────────────────

function saveToStorage() {
  try {
    const data = {
      fOrigin: $("fOrigin").value,
      fDest: $("fDest").value,
      fRadius: $("fRadius").value,
      adults: adults,
      timestamp: Date.now(),
    };
    localStorage.setItem("farfinderSearch", JSON.stringify(data));
  } catch (e) {
    console.warn("Storage failed:", e);
  }
}

function loadFromStorage() {
  try {
    const data = JSON.parse(localStorage.getItem("farfinderSearch"));
    if (data && Date.now() - data.timestamp < 24 * 60 * 60 * 1000) {
      if (data.fOrigin) $("fOrigin").value = data.fOrigin;
      if (data.fDest) $("fDest").value = data.fDest;
      if (data.fRadius) {
        $("fRadius").value = data.fRadius;
        $("radiusVal").textContent = `${data.fRadius} km`;
      }
      if (data.adults) {
        adults = data.adults;
        $("adultsVal").textContent = adults;
      }
    }
  } catch (e) {
    console.warn("Storage load failed:", e);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
//  FORM VALIDATION
// ─────────────────────────────────────────────────────────────────────────────

function validateSearchForm() {
  const origin = $("fOrigin").value.trim();
  const dest = $("fDest").value.trim();
  const date = $("fDate").value;

  if (!origin) {
    showToast("Please enter a departure city", "error");
    $("fOrigin").focus();
    announceToScreen("Validation error: Departure city is required");
    return false;
  }
  if (!dest) {
    showToast("Please enter a destination city", "error");
    $("fDest").focus();
    announceToScreen("Validation error: Destination city is required");
    return false;
  }
  if (!date) {
    showToast("Please select a travel date", "error");
    $("fDate").focus();
    announceToScreen("Validation error: Travel date is required");
    return false;
  }

  const travelDate = new Date(date);
  if (travelDate < new Date()) {
    showToast("Travel date must be in the future", "error");
    announceToScreen("Validation error: Travel date is in the past");
    return false;
  }

  return true;
}

// ─────────────────────────────────────────────────────────────────────────────
//  TAB SWITCHING
// ─────────────────────────────────────────────────────────────────────────────

$$(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    const tabName = tab.dataset.tab;
    $$(".tab").forEach(t => t.classList.remove("active"));
    $$(".tab-panel").forEach(p => p.classList.remove("active"));
    tab.classList.add("active");
    tab.setAttribute("aria-selected", "true");
    $(`tab-${tabName}`).classList.add("active");
    announceToScreen(`Switched to ${tab.textContent.trim()} tab`);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
//  RADIUS SLIDER
// ─────────────────────────────────────────────────────────────────────────────

$("fRadius").addEventListener("input", () => {
  const v = parseInt($("fRadius").value);
  $("radiusVal").textContent = `${v} km`;
  announceToScreen(`Search radius set to ${v} km`);
  $$(".preset").forEach(b =>
    b.classList.toggle("active", parseInt(b.dataset.v) === v)
  );
});

$$(".preset").forEach(btn => {
  btn.addEventListener("click", () => {
    const v = parseInt(btn.dataset.v);
    $("fRadius").value = v;
    $("radiusVal").textContent = `${v} km`;
    $$(".preset").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    announceToScreen(`Search radius set to ${v} km`);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
//  PASSENGERS STEPPER
// ─────────────────────────────────────────────────────────────────────────────

$("stepUp").addEventListener("click", () => {
  adults = Math.min(9, adults + 1);
  $("adultsVal").textContent = adults;
  announceToScreen(`${adults} passenger${adults > 1 ? 's' : ''}`);
});

$("stepDown").addEventListener("click", () => {
  adults = Math.max(1, adults - 1);
  $("adultsVal").textContent = adults;
  announceToScreen(`${adults} passenger${adults > 1 ? 's' : ''}`);
});

// ─────────────────────────────────────────────────────────────────────────────
//  SWAP CITIES
// ─────────────────────────────────────────────────────────────────────────────

$("swapBtn").addEventListener("click", () => {
  [$("fOrigin").value, $("fDest").value] = [$("fDest").value, $("fOrigin").value];
  $("swapBtn").classList.add("spin");
  announceToScreen("Cities swapped");
  setTimeout(() => $("swapBtn").classList.remove("spin"), 350);
});

// ─────────────────────────────────────────────────────────────────────────────
//  FLEXIBLE DAYS STEPPER
// ─────────────────────────────────────────────────────────────────────────────

$("flxUp").addEventListener("click", () => {
  flxDays = Math.min(14, flxDays + 1);
  $("flxDays").textContent = flxDays;
  announceToScreen(`Flexibility window: ±${flxDays} days`);
});

$("flxDown").addEventListener("click", () => {
  flxDays = Math.max(1, flxDays - 1);
  $("flxDays").textContent = flxDays;
  announceToScreen(`Flexibility window: ±${flxDays} days`);
});

// ─────────────────────────────────────────────────────────────────────────────
//  API HELPER
// ─────────────────────────────────────────────────────────────────────────────

async function apiFetch(endpoint, body) {
  try {
    const r = await fetch(`${API}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(60000), // 60s timeout
    });

    if (!r.ok) {
      const errData = await r.json().catch(() => ({}));
      const errorMsg = errData.detail || errData.message || `Error ${r.status}`;
      throw new Error(errorMsg);
    }

    return r.json();
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("Request timed out. Please try again.");
    }
    throw err;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
//  LOADING HELPERS
// ─────────────────────────────────────────────────────────────────────────────

const LOAD_MSGS = [
  "Geocoding your location…",
  "Scanning nearby airports…",
  "Fetching flight prices…",
  "Calculating ground transport…",
  "Ranking multi-modal routes…",
  "Polishing results…",
];

function startLoader(fillId, msgId) {
  let step = 0;
  if (msgId) $(msgId).textContent = LOAD_MSGS[0];
  const iv = setInterval(() => {
    step++;
    if (fillId) $(fillId).style.width = `${Math.min(92, step * 15)}%`;
    if (msgId) $(msgId).textContent = LOAD_MSGS[Math.min(step, LOAD_MSGS.length - 1)];
    if (step >= LOAD_MSGS.length) clearInterval(iv);
  }, 800);
  return iv;
}

function stopLoader(iv, fillId, loadingId) {
  clearInterval(iv);
  if (fillId) $(fillId).style.width = "100%";
  if (loadingId) {
    setTimeout(() => {
      $(loadingId).style.display = "none";
    }, 250);
  }
}

function showEl(id) { $(id).hidden = false; }
function hideEl(id) { $(id).hidden = true; }

// ─────────────────────────────────────────────────────────────────────────────
//  MARKDOWN RENDERER
// ─────────────────────────────────────────────────────────────────────────────

function md(text) {
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
}

// ─────────────────────────────────────────────────────────────────────────────
//  FORMAT HELPERS
// ─────────────────────────────────────────────────────────────────────────────

const inr = n => `₹${Number(n).toLocaleString("en-IN")}`;

function timeStr(mins) {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h ? `${h}h ${m}m` : `${m}m`;
}

function stopsClass(s) {
  return `stops-tag s${Math.min(s, 2)}`;
}

function stopsLabel(s) {
  return s === 0 ? "Non-stop" : s === 1 ? "1 Stop" : `${s} Stops`;
}

// ─────────────────────────────────────────────────────────────────────────────
//  RENDER INSIGHTS
// ─────────────────────────────────────────────────────────────────────────────

function renderInsights(insights) {
  if (!insights?.length) return;
  $("insights").innerHTML = insights
    .map(t => `<div class="insight">${md(t)}</div>`)
    .join("");
  showEl("insights");
}

// ─────────────────────────────────────────────────────────────────────────────
//  RENDER COMPARE TABLE
// ─────────────────────────────────────────────────────────────────────────────

function renderCompare(table) {
  if (!table?.length) return;
  $("compareBody").innerHTML = table
    .map(row => `
      <tr class="rank-${row.rank}">
        <td>${row.rank}</td>
        <td><strong>${row.city}</strong> <span style="color:var(--text-muted);font-family:var(--mono);font-size:10px">${row.iata}</span></td>
        <td>${row.distance_km} km</td>
        <td>${row.ground_mode} ~${row.ground_time}m</td>
        <td class="cost-cell">${inr(row.flight_price)}</td>
        <td class="cost-cell"><strong>${inr(row.total_cost)}</strong></td>
        <td class="save-cell">${row.savings > 0 ? `Save ${inr(row.savings)}` : "—"}</td>
        <td>${row.carrier}</td>
      </tr>`)
    .join("");
  showEl("compareSection");
}

// ─────────────────────────────────────────────────────────────────────────────
//  RENDER ROUTE CARDS
// ─────────────────────────────────────────────────────────────────────────────

function renderRoutes() {
  let routes = [...allRoutes];

  if (activeType === "direct")
    routes = routes.filter(r => r.route_type === "direct");
  if (activeType === "multimodal")
    routes = routes.filter(r => r.route_type === "multimodal");

  if (activeSort === "price") routes.sort((a, b) => a.total_cost_inr - b.total_cost_inr);
  if (activeSort === "time") routes.sort((a, b) => a.total_time_min - b.total_time_min);
  if (activeSort === "stops") routes.sort((a, b) => a.flight.stops - b.flight.stops);

  $("routesGrid").innerHTML = "";

  if (!routes.length) {
    showEl("emptyState");
    announceToScreen("No routes found matching your criteria");
    return;
  }

  hideEl("emptyState");
  showEl("routesTitle");

  routes.forEach((r, i) => {
    const card = buildCard(r, i === 0);
    card.style.animationDelay = `${i * 40}ms`;
    $("routesGrid").appendChild(card);
  });

  announceToScreen(`Showing ${routes.length} route${routes.length !== 1 ? 's' : ''}`);
}

function buildCard(r, isBest) {
  const f = r.flight;
  const g = r.ground;
  const ap = r.origin_airport;
  const ds = r.destination;
  const links = r.booking_links || {};

  const groundHTML = g.mode !== "walk" && g.cost_inr > 0
    ? `<div class="ground-pill">${g.emoji} ${g.note} · ${inr(g.cost_inr)} · ~${g.time_min}min</div>`
    : "";

  const breakdown = g.cost_inr > 0
    ? `Flight: ${inr(f.price_inr)}<br>${g.mode}: ${inr(g.cost_inr)}`
    : `Flight only`;

  const saveBadge = r.savings_inr > 0
    ? `<div class="save-badge">💚 Save ${inr(r.savings_inr)}</div>`
    : "";

  const bookLinks = Object.entries(links)
    .map(([site, url]) => `<a class="book-btn" href="${url}" target="_blank" rel="noopener">${site}</a>`)
    .join("");

  const depDate = f.dep_date
    ? `<span style="font-size:11px;color:var(--text-muted);font-family:var(--mono)">${f.dep_date}</span>`
    : "";

  const card = document.createElement("div");
  card.className = `route-card${isBest ? " best" : ""}`;
  card.setAttribute("role", "listitem");
  card.innerHTML = `
    ${isBest ? '<div class="best-tag">★ BEST DEAL</div>' : ""}
    <div class="card-left">
      <div class="card-route">
        <span class="city">${r.origin_city || ap.city}</span>
        <span class="iata">${ap.iata}</span>
        <span class="arrow">→</span>
        <span class="city">${ds.city}</span>
        <span class="iata">${ds.iata}</span>
      </div>
      ${groundHTML}
      <div class="flight-row">
        <span class="carrier">✈ ${f.carrier}</span>
        ${f.duration_fmt !== "—" ? `<span class="dur">⏱ ${f.duration_fmt}</span>` : ""}
        <span class="${stopsClass(f.stops)}">${stopsLabel(f.stops)}</span>
        ${depDate}
      </div>
      ${bookLinks ? `<div class="book-row">${bookLinks}</div>` : ""}
    </div>
    <div class="card-right">
      <div class="price-big">${inr(r.total_cost_inr)}</div>
      <div class="price-breakdown">${breakdown}</div>
      ${saveBadge}
      <div class="total-time">🕐 ${timeStr(r.total_time_min)} total</div>
    </div>`;

  return card;
}

// ─────────────────────────────────────────────────────────────────────────────
//  SEARCH — STRUCTURED
// ─────────────────────────────────────────────────────────────────────────────

async function runSearch() {
  if (!validateSearchForm()) return;

  const origin = $("fOrigin").value.trim();
  const dest = $("fDest").value.trim();
  const date = $("fDate").value;
  const radius = parseFloat($("fRadius").value);
  const direct = $("fDirect").checked;

  saveToStorage();
  _resetSearchUI();

  const iv = startLoader("progFill", "loadMsg");
  $("searchBtn").disabled = true;
  $("nlBtn").disabled = true;
  requestInProgress = true;

  try {
    const data = await apiFetch("/search", {
      origin,
      destination: dest,
      date,
      radius_km: radius,
      adults,
      direct_only: direct,
    });

    stopLoader(iv, "progFill", "searchLoading");
    _renderSearchData(data);
    announceToScreen(`Found ${data.routes?.length || 0} routes`);
    showToast(`✅ Found ${data.routes?.length || 0} routes!`, "info");
  } catch (err) {
    stopLoader(iv, "progFill", "searchLoading");
    $("routesGrid").innerHTML = `<div class="empty-state"><span>⚠️</span><h3>Search failed</h3><p>${err.message}</p></div>`;
    showToast(err.message, "error");
    announceToScreen(`Search failed: ${err.message}`);
  } finally {
    $("searchBtn").disabled = false;
    $("nlBtn").disabled = false;
    requestInProgress = false;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
//  SEARCH — NATURAL LANGUAGE
// ─────────────────────────────────────────────────────────────────────────────

async function runNLSearch() {
  const query = $("nlInput").value.trim();
  if (!query) {
    showToast("Please enter a search query", "error");
    $("nlInput").focus();
    return;
  }

  _resetSearchUI();
  const iv = startLoader("progFill", "loadMsg");
  $("searchBtn").disabled = true;
  $("nlBtn").disabled = true;
  requestInProgress = true;

  try {
    const data = await apiFetch("/search-nl", { query });

    if (data.parsed_query?.confidence === "low") {
      showToast("ℹ️ Parsed with low confidence. Check the form values.", "info");
    }

    stopLoader(iv, "progFill", "searchLoading");

    // Back-fill form
    if (data.parsed_query) {
      const p = data.parsed_query;
      if (p.origin && p.origin !== "unknown") $("fOrigin").value = p.origin;
      if (p.destination && p.destination !== "unknown") $("fDest").value = p.destination;
      if (p.date) $("fDate").value = p.date;
      if (p.radius_km) {
        $("fRadius").value = p.radius_km;
        $("radiusVal").textContent = `${p.radius_km} km`;
      }
    }

    _renderSearchData(data);
    announceToScreen(`Found ${data.routes?.length || 0} routes`);
    showToast(`✅ Natural language search complete!`, "info");
  } catch (err) {
    stopLoader(iv, "progFill", "searchLoading");
    $("routesGrid").innerHTML = `<div class="empty-state"><span>⚠️</span><h3>Search failed</h3><p>${err.message}</p></div>`;
    showToast(err.message, "error");
  } finally {
    $("searchBtn").disabled = false;
    $("nlBtn").disabled = false;
    requestInProgress = false;
  }
}

function _resetSearchUI() {
  showEl("searchResults");
  $("searchLoading").style.display = "block";
  $("progFill").style.width = "0%";
  $("routesGrid").innerHTML = "";
  hideEl("insights");
  hideEl("controlsRow");
  hideEl("compareSection");
  hideEl("routesTitle");
  hideEl("emptyState");
  allRoutes = [];
}

function _renderSearchData(data) {
  renderInsights(data.insights);
  renderCompare(data.comparison_table);
  allRoutes = data.routes || [];
  showEl("controlsRow");
  renderRoutes();
  $("searchResults").scrollIntoView({ behavior: "smooth" });
}

// ─────────────────────────────────────────────────────────────────────────────
//  CALENDAR
// ─────────────────────────────────────────────────────────────────────────────

async function runCalendar() {
  const origin = $("cOrigin").value.trim();
  const dest = $("cDest").value.trim();
  const month = $("cMonth").value;

  if (!origin || !dest || !month) {
    showToast("Fill in Origin, Destination, and Month.", "error");
    return;
  }

  showEl("calResults");
  $("calLoading").style.display = "block";
  $("calGrid").innerHTML = "";
  hideEl("calBanner");
  requestInProgress = true;

  try {
    const data = await apiFetch("/calendar", { origin, destination: dest, month });
    $("calLoading").style.display = "none";

    if (!data.days_with_data) {
      $("calGrid").innerHTML = `<div class="empty-state"><span>📭</span><h3>No price data</h3><p>Try a different month or route.</p></div>`;
      announceToScreen("No price data available");
      return;
    }

    const cd = data.cheapest_day;
    if (cd) {
      $("calBanner").innerHTML = `🏆 Cheapest day: <strong>${cd.date}</strong> — <strong>${inr(cd.price)}</strong> with ${cd.airline}`;
      showEl("calBanner");
    }

    renderCalendar(data.calendar, month);
    announceToScreen(`Loaded calendar with ${data.days_with_data} days of data`);
    showToast(`✅ Calendar loaded!`, "info");
  } catch (err) {
    $("calLoading").style.display = "none";
    $("calGrid").innerHTML = `<div class="empty-state"><span>⚠️</span><h3>${err.message}</h3></div>`;
    showToast(err.message, "error");
  } finally {
    requestInProgress = false;
  }
}

function renderCalendar(calendar, month) {
  const [yr, mo] = month.split("-").map(Number);
  const firstDay = new Date(yr, mo - 1, 1).getDay();
  const daysInMonth = new Date(yr, mo, 0).getDate();

  const prices = Object.values(calendar).map(c => c.price);
  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);

  const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  let html = dayNames.map(d => `<div class="cal-day-name">${d}</div>`).join("");

  for (let i = 0; i < firstDay; i++) html += `<div class="cal-cell empty"></div>`;

  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = `${month}-${String(day).padStart(2, "0")}`;
    const info = calendar[dateStr];
    if (info) {
      const ratio = maxP > minP ? (info.price - minP) / (maxP - minP) : 0;
      const hue = Math.round(120 - ratio * 120);
      const isCheapest = info.price === minP;
      html += `
        <div class="cal-cell${isCheapest ? " cheapest" : ""}"
             style="border-color: hsl(${hue},60%,40%,0.5)"
             onclick="calDayClick('${dateStr}','${$("cOrigin").value.trim()}','${$("cDest").value.trim()}')">
          <span class="cal-date">${day}</span>
          <span class="cal-price">${inr(info.price)}</span>
          <span class="cal-air">${info.airline}</span>
        </div>`;
    } else {
      html += `<div class="cal-cell empty"><span class="cal-date">${day}</span><span class="cal-air" style="opacity:.3">—</span></div>`;
    }
  }
  $("calGrid").innerHTML = html;
}

function calDayClick(dateStr, origin, dest) {
  document.querySelector('[data-tab="search"]').click();
  $("fOrigin").value = origin;
  $("fDest").value = dest;
  $("fDate").value = dateStr;
  runSearch();
}

// ─────────────────────────────────────────────────────────────────────────────
//  FLEXIBLE DATES
// ─────────────────────────────────────────────────────────────────────────────

async function runFlexible() {
  const origin = $("flxOrigin").value.trim();
  const dest = $("flxDest").value.trim();
  const date = $("flxDate").value;

  if (!origin || !dest || !date) {
    showToast("Fill in Origin, Destination, and Target Date.", "error");
    return;
  }

  showEl("flxResults");
  $("flxLoading").style.display = "block";
  hideEl("flxBanner");
  $("flxGrid").innerHTML = "";
  requestInProgress = true;

  try {
    const data = await apiFetch("/flexible", {
      origin,
      destination: dest,
      date,
      flex_days: flxDays,
    });

    $("flxLoading").style.display = "none";

    if (!data.options?.length) {
      $("flxGrid").innerHTML = `<div class="empty-state"><span>📭</span><h3>No data</h3></div>`;
      announceToScreen("No flexible date options found");
      return;
    }

    if (data.savings_if_flexible > 200) {
      $("flxBanner").innerHTML = `✅ Fly on <strong>${data.cheapest_day.date}</strong> instead of ${data.target_date} → Save <strong>${inr(data.savings_if_flexible)}</strong>!`;
      showEl("flxBanner");
      showToast(`💰 Save ${inr(data.savings_if_flexible)} with flexible dates!`, "info");
    }

    _renderFlexibleData(data.options, data.target_date);
    announceToScreen(`Cheapest date is ${data.cheapest_day.date}`);
  } catch (err) {
    $("flxLoading").style.display = "none";
    $("flxGrid").innerHTML = `<div class="empty-state"><span>⚠️</span><h3>${err.message}</h3></div>`;
    showToast(err.message, "error");
  } finally {
    requestInProgress = false;
  }
}

function _renderFlexibleData(options, targetDate) {
  const minPrice = Math.min(...options.map(o => o.price));
  $("flxGrid").innerHTML = options
    .map(opt => {
      const isCheapest = opt.price === minPrice;
      const isTarget = opt.date === targetDate;
      const diffVsTarget = options.find(o => o.is_target || o.date === targetDate);
      const priceDiff = diffVsTarget ? opt.price - diffVsTarget.price : 0;

      let diffHTML = "";
      if (priceDiff < 0) diffHTML = `<div class="flex-diff cheaper">↓ Save ${inr(-priceDiff)}</div>`;
      else if (priceDiff > 0) diffHTML = `<div class="flex-diff pricier">↑ ${inr(priceDiff)} more</div>`;

      return `<div class="flex-card${isCheapest ? " cheapest-flex" : ""}${isTarget ? " target" : ""}">
        <div class="flex-label">${isTarget ? "YOUR DATE" : isCheapest ? "CHEAPEST" : opt.label}</div>
        <div class="flex-date">${opt.date}</div>
        <div class="flex-price">${inr(opt.price)}</div>
        <div class="flex-airline">${opt.airline}</div>
        ${diffHTML}
      </div>`;
    })
    .join("");
  showEl("flxResults");
}

// ─────────────────────────────────────────────────────────────────────────────
//  BUDGET FINDER
// ─────────────────────────────────────────────────────────────────────────────

async function runBudget() {
  const origin = $("bOrigin").value.trim();
  const bmin = parseInt($("bMin").value) || 0;
  const bmax = parseInt($("bMax").value) || 5000;
  const direct = $("bDirect").checked;

  if (!origin) {
    showToast("Please enter your departure city.", "error");
    return;
  }

  if (bmax < bmin) {
    showToast("Max budget must be greater than min budget.", "error");
    return;
  }

  showEl("budgetResults");
  $("budgetLoading").style.display = "block";
  $("destGrid").innerHTML = "";
  hideEl("budgetEmpty");
  requestInProgress = true;

  try {
    const data = await apiFetch("/budget", {
      origin,
      budget_min: bmin,
      budget_max: bmax,
      direct_only: direct,
    });

    $("budgetLoading").style.display = "none";

    if (!data.destinations?.length) {
      showEl("budgetEmpty");
      announceToScreen("No destinations found within budget");
      return;
    }

    $("destGrid").innerHTML = data.destinations
      .map((d, i) => `
        <div class="dest-card" style="animation-delay:${i * 30}ms">
          <div class="dest-name">${d.destination}</div>
          <div class="dest-iata">${d.destination_iata}</div>
          <div class="dest-price">${inr(d.price)}</div>
          <div class="dest-airline">${d.airline}</div>
          <div class="dest-stops ${stopsClass(d.stops)}">${stopsLabel(d.stops)}</div>
          ${d.depart_date ? `<div style="font-size:10px;color:var(--text-muted);margin-top:4px">${d.depart_date}</div>` : ""}
        </div>`)
      .join("");

    announceToScreen(`Found ${data.destinations.length} destinations`);
    showToast(`✅ Found ${data.destinations.length} destinations!`, "info");
  } catch (err) {
    $("budgetLoading").style.display = "none";
    $("destGrid").innerHTML = `<div class="empty-state"><span>⚠️</span><h3>${err.message}</h3></div>`;
    showToast(err.message, "error");
  } finally {
    requestInProgress = false;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
//  SORT / FILTER CONTROLS
// ─────────────────────────────────────────────────────────────────────────────

$$("[data-sort]").forEach(btn => {
  btn.addEventListener("click", () => {
    $$("[data-sort]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    activeSort = btn.dataset.sort;
    renderRoutes();
    announceToScreen(`Sorted by ${btn.textContent.trim()}`);
  });
});

$$("[data-type]").forEach(btn => {
  btn.addEventListener("click", () => {
    $$("[data-type]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    activeType = btn.dataset.type;
    renderRoutes();
    announceToScreen(`Filtered to ${btn.textContent.trim()}`);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
//  MODAL / INFO
// ─────────────────────────────────────────────────────────────────────────────

const infoModal = $("infoModal");
const infoBtn = $("infoBtn");
const modalClose = document.querySelector(".modal-close");

infoBtn.addEventListener("click", () => {
  infoModal.showModal();
  announceToScreen("Information dialog opened");
});

modalClose.addEventListener("click", () => {
  infoModal.close();
  announceToScreen("Information dialog closed");
});

infoModal.addEventListener("click", e => {
  if (e.target === infoModal) {
    infoModal.close();
  }
});

// ─────────────────────────────────────────────────────────────────────────────
//  THEME TOGGLE
// ─────────────────────────────────────────────────────────────────────────────

const themeToggle = $("themeToggle");
themeToggle.addEventListener("click", () => {
  document.documentElement.classList.toggle("dark-mode");
  const isDark = document.documentElement.classList.contains("dark-mode");
  localStorage.setItem("theme", isDark ? "dark" : "light");
  announceToScreen(`Switched to ${isDark ? "dark" : "light"} mode`);
});

// Load saved theme
const savedTheme = localStorage.getItem("theme");
if (savedTheme === "dark") {
  document.documentElement.classList.add("dark-mode");
}

// ─────────────────────────────────────────────────────────────────────────────
//  EVENT BINDINGS
// ─────────────────────────────────────────────────────────────────────────────

$("searchBtn").addEventListener("click", runSearch);
$("nlBtn").addEventListener("click", runNLSearch);
$("calBtn").addEventListener("click", runCalendar);
$("flxBtn").addEventListener("click", runFlexible);
$("budgetBtn").addEventListener("click", runBudget);

// Enter key bindings
$("nlInput").addEventListener("keydown", e => {
  if (e.key === "Enter" && !requestInProgress) runNLSearch();
});

$("fOrigin").addEventListener("keydown", e => {
  if (e.key === "Enter") $("fDest").focus();
});

$("fDest").addEventListener("keydown", e => {
  if (e.key === "Enter" && !requestInProgress) runSearch();
});

$("flxOrigin").addEventListener("keydown", e => {
  if (e.key === "Enter") $("flxDest").focus();
});

$("flxDest").addEventListener("keydown", e => {
  if (e.key === "Enter" && !requestInProgress) runFlexible();
});

$("bOrigin").addEventListener("keydown", e => {
  if (e.key === "Enter" && !requestInProgress) runBudget();
});

// Prevent multiple submissions
document.addEventListener("submit", e => {
  if (requestInProgress) {
    e.preventDefault();
    showToast("Request in progress. Please wait.", "error");
  }
});

/* ════════════════════════════════════════════════════════════
   FarFinder v2 — script.js
   Features: search, NL, calendar heatmap, flexible dates,
             budget finder, route cards, booking deep links,
             compare table, price trend badges
   ════════════════════════════════════════════════════════════ */

const API = "http://127.0.0.1:8001";
const $ = id => document.getElementById(id);

// ── State ──────────────────────────────────────────────────
let allRoutes   = [];
let adults      = 1;
let activeSort  = "price";
let activeType  = "all";
let flxDays     = 3;

// ── Init defaults ──────────────────────────────────────────
const defaultDate = () => {
  const d = new Date();
  d.setDate(d.getDate() + 7);
  return d.toISOString().split("T")[0];
};
const todayStr = () => new Date().toISOString().split("T")[0];

$("fDate").value  = defaultDate();
$("fDate").min    = todayStr();
$("flxDate").value= defaultDate();
$("flxDate").min  = todayStr();
$("cMonth").value = new Date().toISOString().slice(0, 7);


/* ════════════════════════════════════════════════════════════
   TAB SWITCHING
   ════════════════════════════════════════════════════════════ */
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    tab.classList.add("active");
    $(`tab-${tab.dataset.tab}`).classList.add("active");
  });
});


/* ════════════════════════════════════════════════════════════
   RADIUS SLIDER
   ════════════════════════════════════════════════════════════ */
$("fRadius").addEventListener("input", () => {
  const v = parseInt($("fRadius").value);
  $("radiusVal").textContent = `${v} km`;
  document.querySelectorAll(".preset").forEach(b =>
    b.classList.toggle("active", parseInt(b.dataset.v) === v)
  );
});

document.querySelectorAll(".preset").forEach(btn => {
  btn.addEventListener("click", () => {
    const v = parseInt(btn.dataset.v);
    $("fRadius").value = v;
    $("radiusVal").textContent = `${v} km`;
    document.querySelectorAll(".preset").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
  });
});


/* ════════════════════════════════════════════════════════════
   PASSENGERS STEPPER
   ════════════════════════════════════════════════════════════ */
$("stepUp").addEventListener  ("click", () => { adults = Math.min(9, adults + 1); $("adultsVal").textContent = adults; });
$("stepDown").addEventListener("click", () => { adults = Math.max(1, adults - 1); $("adultsVal").textContent = adults; });


/* ════════════════════════════════════════════════════════════
   SWAP CITIES
   ════════════════════════════════════════════════════════════ */
$("swapBtn").addEventListener("click", () => {
  [$("fOrigin").value, $("fDest").value] = [$("fDest").value, $("fOrigin").value];
  $("swapBtn").classList.add("spin");
  setTimeout(() => $("swapBtn").classList.remove("spin"), 280);
});


/* ════════════════════════════════════════════════════════════
   FLEXIBLE DAYS STEPPER
   ════════════════════════════════════════════════════════════ */
$("flxUp").addEventListener  ("click", () => { flxDays = Math.min(14, flxDays + 1); $("flxDays").textContent = flxDays; });
$("flxDown").addEventListener("click", () => { flxDays = Math.max(1,  flxDays - 1); $("flxDays").textContent = flxDays; });


/* ════════════════════════════════════════════════════════════
   SHARED API HELPER
   ════════════════════════════════════════════════════════════ */
async function apiFetch(endpoint, body) {
  const r = await fetch(`${API}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw new Error(e.detail || `HTTP ${r.status}`);
  }
  return r.json();
}


/* ════════════════════════════════════════════════════════════
   LOADING HELPERS
   ════════════════════════════════════════════════════════════ */
const LOAD_MSGS = [
  "Geocoding your city…",
  "Scanning airports in radius…",
  "Fetching Travelpayouts prices…",
  "Calculating ground transport…",
  "Ranking multi-modal routes…",
  "Finding the best deals…",
];

function startLoader(fillId, msgId) {
  let step = 0;
  if (msgId) $(msgId).textContent = LOAD_MSGS[0];
  const iv = setInterval(() => {
    step++;
    if (fillId) $(fillId).style.width = `${Math.min(92, step * 16)}%`;
    if (msgId)  $(msgId).textContent = LOAD_MSGS[Math.min(step, LOAD_MSGS.length - 1)];
    if (step >= LOAD_MSGS.length) clearInterval(iv);
  }, 1100);
  return iv;
}

function stopLoader(iv, fillId, loadingId) {
  clearInterval(iv);
  if (fillId)     $(fillId).style.width = "100%";
  if (loadingId)  setTimeout(() => { $(loadingId).style.display = "none"; }, 350);
}

function showEl(id)  { $(id).hidden = false; }
function hideEl(id)  { $(id).hidden = true; }


/* ════════════════════════════════════════════════════════════
   MARKDOWN BOLD RENDERER
   ════════════════════════════════════════════════════════════ */
function md(text) {
  return text
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
}


/* ════════════════════════════════════════════════════════════
   FORMAT HELPERS
   ════════════════════════════════════════════════════════════ */
const inr = n => `₹${Number(n).toLocaleString("en-IN")}`;
function timeStr(mins) {
  const h = Math.floor(mins / 60), m = mins % 60;
  return h ? `${h}h ${m}m` : `${m}m`;
}
function stopsClass(s) { return `stops-tag s${Math.min(s, 2)}`; }
function stopsLabel(s) { return s === 0 ? "Non-stop" : s === 1 ? "1 Stop" : `${s} Stops`; }


/* ════════════════════════════════════════════════════════════
   RENDER INSIGHTS
   ════════════════════════════════════════════════════════════ */
function renderInsights(insights) {
  if (!insights?.length) return;
  $("insights").innerHTML = insights.map(t => `<div class="insight">${md(t)}</div>`).join("");
  showEl("insights");
}


/* ════════════════════════════════════════════════════════════
   RENDER COMPARE TABLE
   ════════════════════════════════════════════════════════════ */
function renderCompare(table) {
  if (!table?.length) return;
  $("compareBody").innerHTML = table.map(row => `
    <tr class="rank-${row.rank}">
      <td>${row.rank}</td>
      <td><strong>${row.city}</strong> <span style="color:var(--tmuted);font-family:var(--mono);font-size:10px">${row.iata}</span></td>
      <td>${row.distance_km} km</td>
      <td>${row.ground_mode} ~${row.ground_time}min</td>
      <td class="cost-cell">${inr(row.flight_price)}</td>
      <td class="cost-cell"><strong>${inr(row.total_cost)}</strong></td>
      <td class="save-cell">${row.savings > 0 ? `Save ${inr(row.savings)}` : "—"}</td>
      <td>${row.carrier}</td>
    </tr>`).join("");
  showEl("compareSection");
}


/* ════════════════════════════════════════════════════════════
   RENDER ROUTE CARDS
   ════════════════════════════════════════════════════════════ */
function renderRoutes() {
  let routes = [...allRoutes];
  if (activeType === "direct")    routes = routes.filter(r => r.route_type === "direct");
  if (activeType === "multimodal") routes = routes.filter(r => r.route_type === "multimodal");
  if (activeSort === "price")  routes.sort((a,b) => a.total_cost_inr - b.total_cost_inr);
  if (activeSort === "time")   routes.sort((a,b) => a.total_time_min - b.total_time_min);
  if (activeSort === "stops")  routes.sort((a,b) => a.flight.stops - b.flight.stops);

  $("routesGrid").innerHTML = "";
  if (!routes.length) { showEl("emptyState"); return; }
  hideEl("emptyState");
  showEl("routesTitle");

  routes.forEach((r, i) => {
    const card = buildCard(r, i === 0);
    card.style.animationDelay = `${i * 50}ms`;
    $("routesGrid").appendChild(card);
  });
}

function buildCard(r, isBest) {
  const f  = r.flight;
  const g  = r.ground;
  const ap = r.origin_airport;
  const ds = r.destination;
  const links = r.booking_links || {};

  const groundHTML = (g.mode !== "walk" && g.cost_inr > 0)
    ? `<div class="ground-pill">${g.emoji} ${g.note} · ${inr(g.cost_inr)} · ~${g.time_min}min</div>`
    : "";

  const breakdown = g.cost_inr > 0
    ? `Flight: ${inr(f.price_inr)}<br>${g.mode}: ${inr(g.cost_inr)}`
    : `Flight only`;

  const saveBadge = r.savings_inr > 0
    ? `<div class="save-badge">💚 Save ${inr(r.savings_inr)}</div>` : "";

  const bookLinks = Object.entries(links).map(([site, url]) =>
    `<a class="book-btn" href="${url}" target="_blank" rel="noopener">${site}</a>`
  ).join("");

  const depDate = f.dep_date ? `<span style="font-size:11px;color:var(--tmuted);font-family:var(--mono)">${f.dep_date}</span>` : "";

  const card = document.createElement("div");
  card.className = `route-card${isBest ? " best" : ""}`;
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


/* ════════════════════════════════════════════════════════════
   SEARCH — STRUCTURED
   ════════════════════════════════════════════════════════════ */
async function runSearch() {
  const origin = $("fOrigin").value.trim();
  const dest   = $("fDest").value.trim();
  const date   = $("fDate").value;
  const radius = parseFloat($("fRadius").value);
  const direct = $("fDirect").checked;

  if (!origin || !dest || !date) return alert("Please fill Origin, Destination, and Date.");

  _resetSearchUI();
  const iv = startLoader("progFill", "loadMsg");

  try {
    const data = await apiFetch("/search", {
      origin, destination: dest, date, radius_km: radius, adults, direct_only: direct,
    });
    stopLoader(iv, "progFill", "searchLoading");
    _renderSearchData(data);
  } catch (err) {
    stopLoader(iv, "progFill", "searchLoading");
    $("routesGrid").innerHTML = `<div class="empty-state"><span>⚠️</span><h3>Search failed</h3><p>${err.message}</p></div>`;
  } finally {
    $("searchBtn").disabled = false;
    $("nlBtn").disabled     = false;
  }
}


/* ════════════════════════════════════════════════════════════
   SEARCH — NATURAL LANGUAGE
   ════════════════════════════════════════════════════════════ */
async function runNLSearch() {
  const query = $("nlInput").value.trim();
  if (!query) return $("nlInput").focus();

  _resetSearchUI();
  const iv = startLoader("progFill", "loadMsg");

  try {
    const data = await apiFetch("/search-nl", { query });
    stopLoader(iv, "progFill", "searchLoading");

    // Back-fill form
    if (data.parsed_query) {
      const p = data.parsed_query;
      if (p.origin      && p.origin !== "unknown")      $("fOrigin").value = p.origin;
      if (p.destination && p.destination !== "unknown")  $("fDest").value   = p.destination;
      if (p.date)   $("fDate").value   = p.date;
      if (p.radius_km) {
        $("fRadius").value = p.radius_km;
        $("radiusVal").textContent = `${p.radius_km} km`;
      }
    }

    _renderSearchData(data);

    // Flexible results if parsed
    if (data.flexible_dates?.length) {
      _renderFlexibleData(data.flexible_dates, data.search?.date || "");
    }
  } catch (err) {
    stopLoader(iv, "progFill", "searchLoading");
    $("routesGrid").innerHTML = `<div class="empty-state"><span>⚠️</span><h3>Parse/search failed</h3><p>${err.message}</p></div>`;
  } finally {
    $("searchBtn").disabled = false;
    $("nlBtn").disabled     = false;
  }
}

function _resetSearchUI() {
  $("searchBtn").disabled = true;
  $("nlBtn").disabled     = true;
  showEl("searchResults");
  $("searchLoading").style.display = "block";
  $("progFill").style.width = "0%";
  $("routesGrid").innerHTML = "";
  hideEl("insights"); hideEl("controlsRow"); hideEl("compareSection");
  hideEl("routesTitle"); hideEl("emptyState");
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


/* ════════════════════════════════════════════════════════════
   CALENDAR
   ════════════════════════════════════════════════════════════ */
async function runCalendar() {
  const origin = $("cOrigin").value.trim();
  const dest   = $("cDest").value.trim();
  const month  = $("cMonth").value;
  if (!origin || !dest || !month) return alert("Fill Origin, Destination, and Month.");

  showEl("calResults");
  $("calLoading").style.display = "block";
  $("calGrid").innerHTML = "";
  hideEl("calBanner");

  try {
    const data = await apiFetch("/calendar", { origin, destination: dest, month });
    $("calLoading").style.display = "none";

    if (!data.days_with_data) {
      $("calGrid").innerHTML = `<div class="empty-state"><span>📭</span><h3>No price data</h3><p>Try a different month or route. Data comes from user searches cached by Travelpayouts.</p></div>`;
      return;
    }

    // Cheapest day banner
    const cd = data.cheapest_day;
    if (cd) {
      $("calBanner").innerHTML = `🏆 Cheapest day: <strong>${cd.date}</strong> — <strong>${inr(cd.price)}</strong> with ${cd.airline}`;
      showEl("calBanner");
    }

    renderCalendar(data.calendar, month);
  } catch (err) {
    $("calLoading").style.display = "none";
    $("calGrid").innerHTML = `<div class="empty-state"><span>⚠️</span><h3>${err.message}</h3></div>`;
  }
}

function renderCalendar(calendar, month) {
  const [yr, mo] = month.split("-").map(Number);
  const firstDay = new Date(yr, mo - 1, 1).getDay();  // 0=Sun
  const daysInMonth = new Date(yr, mo, 0).getDate();

  const prices = Object.values(calendar).map(c => c.price);
  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);

  const dayNames = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
  let html = dayNames.map(d => `<div class="cal-day-name">${d}</div>`).join("");

  // Empty cells before first day
  for (let i = 0; i < firstDay; i++) html += `<div class="cal-cell empty"></div>`;

  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = `${month}-${String(day).padStart(2, "0")}`;
    const info    = calendar[dateStr];
    if (info) {
      const ratio = maxP > minP ? (info.price - minP) / (maxP - minP) : 0;
      // Hue from 120 (green, cheap) to 0 (red, expensive)
      const hue   = Math.round(120 - ratio * 120);
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
  // Switch to search tab and pre-fill
  document.querySelector('[data-tab="search"]').click();
  $("fOrigin").value = origin;
  $("fDest").value   = dest;
  $("fDate").value   = dateStr;
  $("nlInput").value = `${origin} to ${dest} on ${dateStr}`;
  runSearch();
}


/* ════════════════════════════════════════════════════════════
   FLEXIBLE DATES
   ════════════════════════════════════════════════════════════ */
async function runFlexible() {
  const origin = $("flxOrigin").value.trim();
  const dest   = $("flxDest").value.trim();
  const date   = $("flxDate").value;
  if (!origin || !dest || !date) return alert("Fill all flexible search fields.");

  showEl("flxResults");
  $("flxLoading").style.display = "block";
  hideEl("flxBanner");
  $("flxGrid").innerHTML = "";

  try {
    const data = await apiFetch("/flexible", { origin, destination: dest, date, flex_days: flxDays });
    $("flxLoading").style.display = "none";

    if (!data.options?.length) {
      $("flxGrid").innerHTML = `<div class="empty-state"><span>📭</span><h3>No data for this window</h3><p>Try a more popular route or wider flex range.</p></div>`;
      return;
    }

    if (data.savings_if_flexible > 200) {
      $("flxBanner").innerHTML = `✅ Fly on <strong>${data.cheapest_day.date}</strong> instead of ${data.target_date} → Save <strong>${inr(data.savings_if_flexible)}</strong>!`;
      showEl("flxBanner");
    }

    _renderFlexibleData(data.options, data.target_date);
  } catch (err) {
    $("flxLoading").style.display = "none";
    $("flxGrid").innerHTML = `<div class="empty-state"><span>⚠️</span><h3>${err.message}</h3></div>`;
  }
}

function _renderFlexibleData(options, targetDate) {
  const minPrice = Math.min(...options.map(o => o.price));
  $("flxGrid").innerHTML = options.map(opt => {
    const isCheapest = opt.price === minPrice;
    const isTarget   = opt.date  === targetDate;
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
  }).join("");
  showEl("flxResults");
}


/* ════════════════════════════════════════════════════════════
   BUDGET FINDER
   ════════════════════════════════════════════════════════════ */
async function runBudget() {
  const origin = $("bOrigin").value.trim();
  const bmin   = parseInt($("bMin").value) || 0;
  const bmax   = parseInt($("bMax").value) || 5000;
  const direct = $("bDirect").checked;
  if (!origin) return alert("Please enter your departure city/IATA.");

  showEl("budgetResults");
  $("budgetLoading").style.display = "block";
  $("destGrid").innerHTML = "";
  hideEl("budgetEmpty");

  try {
    const data = await apiFetch("/budget", { origin, budget_min: bmin, budget_max: bmax, direct_only: direct });
    $("budgetLoading").style.display = "none";

    if (!data.destinations?.length) { showEl("budgetEmpty"); return; }

    $("destGrid").innerHTML = data.destinations.map((d, i) => `
      <div class="dest-card" style="animation-delay:${i*40}ms">
        <div class="dest-name">${d.destination}</div>
        <div class="dest-iata">${d.destination_iata}</div>
        <div class="dest-price">${inr(d.price)}</div>
        <div class="dest-airline">${d.airline}</div>
        <div class="dest-stops ${stopsClass(d.stops)}">${stopsLabel(d.stops)}</div>
        ${d.depart_date ? `<div style="font-size:10px;color:var(--tmuted);margin-top:4px">${d.depart_date}</div>` : ""}
      </div>`).join("");
  } catch (err) {
    $("budgetLoading").style.display = "none";
    $("destGrid").innerHTML = `<div class="empty-state"><span>⚠️</span><h3>${err.message}</h3></div>`;
  }
}


/* ════════════════════════════════════════════════════════════
   SORT / FILTER CONTROLS
   ════════════════════════════════════════════════════════════ */
document.querySelectorAll("[data-sort]").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("[data-sort]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    activeSort = btn.dataset.sort;
    renderRoutes();
  });
});

document.querySelectorAll("[data-type]").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("[data-type]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    activeType = btn.dataset.type;
    renderRoutes();
  });
});


/* ════════════════════════════════════════════════════════════
   EVENT BINDINGS
   ════════════════════════════════════════════════════════════ */
$("searchBtn").addEventListener("click", runSearch);
$("nlBtn").addEventListener    ("click", runNLSearch);
$("calBtn").addEventListener   ("click", runCalendar);
$("flxBtn").addEventListener   ("click", runFlexible);
$("budgetBtn").addEventListener("click", runBudget);

$("nlInput").addEventListener("keydown",  e => { if (e.key === "Enter") runNLSearch(); });
$("fOrigin").addEventListener("keydown",  e => { if (e.key === "Enter") $("fDest").focus(); });
$("fDest").addEventListener  ("keydown",  e => { if (e.key === "Enter") runSearch(); });
$("flxOrigin").addEventListener("keydown",e => { if (e.key === "Enter") $("flxDest").focus(); });
$("flxDest").addEventListener("keydown",  e => { if (e.key === "Enter") runFlexible(); });
$("bOrigin").addEventListener("keydown",  e => { if (e.key === "Enter") runBudget(); });

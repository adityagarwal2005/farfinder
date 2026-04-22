'use strict';

const API = 'http://127.0.0.1:8001';
const $   = id => document.getElementById(id);

// ══════════════════════════════════════════════════════
// STATE — routes stored in array, referenced by index
// This is the core fix: NO JSON.stringify in onclick attrs
// ══════════════════════════════════════════════════════
const S = {
  adults: 1, flexDays: 3, sort: 'price', filter: 'all',
  routes: [],   // main search results stored here
};

const RECENTS_KEY   = 'ff3_recents';
const WATCHLIST_KEY = 'ff3_watchlist';

// ── Formatters ────────────────────────────────────────
const inr  = n => `₹${Number(n||0).toLocaleString('en-IN')}`;
const esc  = s => String(s??'').replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const bold = s => esc(s).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

function fmtTime(m) {
  const v=Number(m||0); if(!v) return '—';
  const h=Math.floor(v/60),r=v%60;
  return h?`${h}h ${r}m`:`${r}m`;
}
function stopsClass(s) { return s===0?'s-nonstop':s===1?'s-one':'s-multi'; }
function stopsLabel(s) { return s===0?'Non-stop':s===1?'1 Stop':`${s} Stops`; }
function confClass(c)  { const l=(c||'').toLowerCase(); return `conf-${l||'low'}`; }
function confLabel(c)  { const l=(c||'').toLowerCase(); return l==='high'?'✓ Confirmed':l==='medium'?'Est.':'~Approx'; }

// ── DOM helpers ───────────────────────────────────────
function show(el) { const e=typeof el==='string'?$(el):el; if(e){e.style.display='';e.hidden=false;} }
function hide(el) { const e=typeof el==='string'?$(el):el; if(e){e.style.display='none';e.hidden=true;} }
function setText(id, txt) { const e=$(id); if(e) e.innerHTML=txt; }

// ── API ───────────────────────────────────────────────
async function apiFetch(ep, body) {
  const r = await fetch(`${API}${ep}`, {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body),
  });
  if (!r.ok) {
    const e = await r.json().catch(()=>({}));
    throw new Error(e.detail || `Server error ${r.status}`);
  }
  return r.json();
}

// ── Toast ─────────────────────────────────────────────
let _toastTimer = null;
function showToast(msg) {
  const t=$('toastEl');
  t.textContent=msg;
  show(t);
  clearTimeout(_toastTimer);
  _toastTimer=setTimeout(()=>hide(t),2500);
}

// ══════════════════════════════════════════════════════
// DARK MODE
// ══════════════════════════════════════════════════════
(function initTheme() {
  const saved = localStorage.getItem('ff3_theme');
  const sys   = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark':'light';
  const theme = saved || sys;
  document.documentElement.setAttribute('data-theme', theme);
  $('themeLabel').textContent = theme==='dark'?'Light Mode':'Dark Mode';
})();

$('themeToggle').addEventListener('click', () => {
  const cur  = document.documentElement.getAttribute('data-theme');
  const next = cur==='dark'?'light':'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('ff3_theme', next);
  $('themeLabel').textContent = next==='dark'?'Light Mode':'Dark Mode';
});

// ══════════════════════════════════════════════════════
// TAB SWITCHING
// ══════════════════════════════════════════════════════
function activateTab(name) {
  document.querySelectorAll('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.tab===name));
  document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id===`panel-${name}`));
}
document.querySelectorAll('.nav-item').forEach(b =>
  b.addEventListener('click', () => activateTab(b.dataset.tab))
);

// ══════════════════════════════════════════════════════
// DATE DEFAULTS
// ══════════════════════════════════════════════════════
(function initDates() {
  const today = new Date().toISOString().split('T')[0];
  const d7    = new Date(); d7.setDate(d7.getDate()+7);
  const iso7  = d7.toISOString().split('T')[0];
  $('fDate').min  = today;  $('fDate').value  = iso7;
  $('flDate').min = today;  $('flDate').value = iso7;
  $('cMonth').value = new Date().toISOString().slice(0,7);
})();

// ══════════════════════════════════════════════════════
// RADIUS SLIDER
// ══════════════════════════════════════════════════════
$('fRadius').addEventListener('input', () => {
  const v = $('fRadius').value;
  $('radiusPill').textContent = `${v} km`;
  document.querySelectorAll('.chip').forEach(b => b.classList.toggle('active', b.dataset.v===v));
});
document.querySelectorAll('.chip').forEach(btn => {
  btn.addEventListener('click', () => {
    $('fRadius').value = btn.dataset.v;
    $('radiusPill').textContent = `${btn.dataset.v} km`;
    document.querySelectorAll('.chip').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  });
});

// ══════════════════════════════════════════════════════
// STEPPERS
// ══════════════════════════════════════════════════════
$('sUp').addEventListener ('click', ()=>{S.adults=Math.min(9,S.adults+1);  $('adultsVal').textContent=S.adults;});
$('sDn').addEventListener ('click', ()=>{S.adults=Math.max(1,S.adults-1);  $('adultsVal').textContent=S.adults;});
$('flUp').addEventListener('click', ()=>{S.flexDays=Math.min(14,S.flexDays+1);$('flDaysVal').textContent=S.flexDays;});
$('flDn').addEventListener('click', ()=>{S.flexDays=Math.max(1, S.flexDays-1);$('flDaysVal').textContent=S.flexDays;});

// ══════════════════════════════════════════════════════
// SWAP CITIES
// ══════════════════════════════════════════════════════
$('swapBtn').addEventListener('click', () => {
  [$('fOrigin').value, $('fDest').value] = [$('fDest').value, $('fOrigin').value];
  $('swapBtn').classList.add('spin');
  setTimeout(() => $('swapBtn').classList.remove('spin'), 260);
});

// ══════════════════════════════════════════════════════
// LOADER
// ══════════════════════════════════════════════════════
const LOAD_MSGS = [
  'Geocoding your city…',
  'Scanning airports in radius…',
  'Fetching Travelpayouts prices…',
  'Searching via connecting hubs…',
  'Calculating door-to-door costs…',
  'Ranking all route options…',
];
let _loaderIv = null;

function startLoader() {
  let i = 0;
  $('loaderFill').style.width = '0%';
  $('loaderMsg').textContent   = LOAD_MSGS[0];
  clearInterval(_loaderIv);
  _loaderIv = setInterval(() => {
    i = Math.min(i+1, LOAD_MSGS.length-1);
    $('loaderFill').style.width = `${Math.round((i+1)*100/LOAD_MSGS.length)}%`;
    $('loaderMsg').textContent   = LOAD_MSGS[i];
  }, 1000);
}

function stopLoader() {
  clearInterval(_loaderIv);
  $('loaderFill').style.width = '100%';
  setTimeout(() => hide('searchLoader'), 300);
}

// ══════════════════════════════════════════════════════
// RECENT SEARCHES
// ══════════════════════════════════════════════════════
function loadRecents() {
  try { return JSON.parse(localStorage.getItem(RECENTS_KEY)||'[]'); } catch { return []; }
}
function saveRecent(o, d, dt, r) {
  let rows = loadRecents().filter(x => !(x.o===o && x.d===d && x.dt===dt));
  rows.unshift({o, d, dt, r, ts: Date.now()});
  localStorage.setItem(RECENTS_KEY, JSON.stringify(rows.slice(0,6)));
  renderRecents();
}
function renderRecents() {
  const list = $('recentList'); if (!list) return;
  const rows = loadRecents();
  if (!rows.length) {
    list.innerHTML='<div style="font-size:11px;color:var(--sb-sec);padding:5px 4px">No recent searches</div>';
    return;
  }
  list.innerHTML = rows.map(r =>
    `<button class="recent-item" data-o="${esc(r.o)}" data-d="${esc(r.d)}" data-dt="${esc(r.dt)}" data-r="${esc(r.r)}">
      <span>✈ ${esc(r.o)} → ${esc(r.d)}</span>
    </button>`
  ).join('');
  list.querySelectorAll('.recent-item').forEach(btn => {
    btn.addEventListener('click', () => {
      $('fOrigin').value = btn.dataset.o;
      $('fDest').value   = btn.dataset.d;
      $('fDate').value   = btn.dataset.dt;
      $('fRadius').value = btn.dataset.r;
      $('radiusPill').textContent = `${btn.dataset.r} km`;
      activateTab('search');
      runSearch();
    });
  });
}
renderRecents();

// ══════════════════════════════════════════════════════
// WATCHLIST — stored as serialised route data
// ══════════════════════════════════════════════════════
function loadWatchlist() {
  try { return JSON.parse(localStorage.getItem(WATCHLIST_KEY)||'[]'); } catch { return []; }
}
function saveWatchlist(items) {
  localStorage.setItem(WATCHLIST_KEY, JSON.stringify(items));
  updateWatchBadge();
  renderWatchlist();
}
function routeId(r) {
  return [
    r.origin_airport?.iata||'',
    r.destination?.iata||'',
    r.flight?.carrier_code||'',
    r.flight?.dep_date||'',
    String(r.total_cost_inr||''),
  ].join('|');
}
function isWatched(r) {
  const id = routeId(r);
  return loadWatchlist().some(x => x.id===id);
}
function toggleWatch(routeIndex) {
  const r = S.routes[routeIndex];
  if (!r) return;
  const id = routeId(r);
  let items = loadWatchlist();
  if (items.some(x => x.id===id)) {
    items = items.filter(x => x.id!==id);
    showToast('Removed from Watchlist');
  } else {
    // Store a serialisable summary (not the full route object to avoid size issues)
    items.unshift({
      id,
      ts:          Date.now(),
      origin:      r.origin_city || r.origin_airport?.city || '',
      dest:        r.destination?.city || '',
      carrier:     r.flight?.carrier || '—',
      stops:       r.flight?.stops ?? 0,
      dep:         r.flight?.dep_date || '',
      price:       r.total_cost_inr || 0,
      time_min:    r.total_time_min || 0,
      origin_iata: r.origin_airport?.iata || '',
      dest_iata:   r.destination?.iata || '',
    });
    showToast('Saved to Watchlist ✓');
  }
  saveWatchlist(items);
  // Refresh the Save button for this card
  const btn = document.querySelector(`.action-btn.save-btn[data-idx="${routeIndex}"]`);
  if (btn) {
    const now = isWatched(r);
    btn.textContent = now ? '★ Saved' : '☆ Save';
    btn.classList.toggle('starred', now);
  }
}
function updateWatchBadge() {
  const n = loadWatchlist().length;
  const b = $('watchBadge');
  if (n > 0) { b.textContent=n; show(b); } else { hide(b); }
}
function renderWatchlist() {
  const items = loadWatchlist();
  const empty = $('watchlistEmpty'), grid = $('watchGrid');
  if (!items.length) { show(empty); grid.innerHTML=''; return; }
  hide(empty);
  grid.innerHTML = items.map((item, idx) => `
    <div class="watch-card">
      <div>
        <div class="watch-route">${esc(item.origin)} → ${esc(item.dest)}</div>
        <div class="watch-meta">${esc(item.carrier)} · ${stopsLabel(item.stops)} · ${esc(item.dep)}</div>
        <div class="watch-actions">
          <button class="action-btn watch-search-btn" data-wid="${esc(item.id)}"
            data-o="${esc(item.origin)}" data-d="${esc(item.dest)}" data-dt="${esc(item.dep)}">
            ↗ Search again
          </button>
          <button class="action-btn watch-remove-btn" data-wid="${esc(item.id)}">Remove</button>
        </div>
      </div>
      <div class="watch-price">${inr(item.price)}</div>
    </div>`).join('');

  // Bind buttons
  grid.querySelectorAll('.watch-search-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      $('fOrigin').value = btn.dataset.o;
      $('fDest').value   = btn.dataset.d;
      if (btn.dataset.dt) $('fDate').value = btn.dataset.dt;
      activateTab('search');
      runSearch();
    });
  });
  grid.querySelectorAll('.watch-remove-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      saveWatchlist(loadWatchlist().filter(x => x.id !== btn.dataset.wid));
      showToast('Removed from Watchlist');
    });
  });
}
updateWatchBadge();
renderWatchlist();

// ══════════════════════════════════════════════════════
// WEATHER
// ══════════════════════════════════════════════════════
async function fetchWeather(city) {
  if (!city) return;
  try {
    const data = await apiFetch('/weather', {city});
    const el   = $('weatherWidget');
    if (!data.available) { hide(el); return; }
    const emoji = condEmoji(data.condition||'');
    const forecast = (data.forecast||[]).map(d => `
      <div class="weather-day">
        <div class="wd-date">${esc(d.date?.slice(5)||'')}</div>
        <div class="wd-desc">${esc(d.desc||'')}</div>
        <div class="wd-temp">${esc(d.max_c||'')}°/${esc(d.min_c||'')}°</div>
      </div>`).join('');
    el.innerHTML = `
      <div class="weather-main">${emoji}</div>
      <div class="weather-info">
        <div class="weather-city">${esc(data.city)} Weather</div>
        <div class="weather-cond">${esc(data.condition||'')}</div>
      </div>
      <div class="weather-temp">${esc(data.temp_c||'—')}°C</div>
      ${forecast ? `<div class="weather-forecast">${forecast}</div>` : ''}`;
    show(el);
  } catch { hide($('weatherWidget')); }
}
function condEmoji(c) {
  c = c.toLowerCase();
  if (c.includes('sun')||c.includes('clear'))   return '☀️';
  if (c.includes('cloud'))                       return '⛅';
  if (c.includes('rain')||c.includes('drizzle')) return '🌧️';
  if (c.includes('storm')||c.includes('thunder'))return '⛈️';
  if (c.includes('snow'))                        return '❄️';
  if (c.includes('fog')||c.includes('mist'))     return '🌫️';
  return '🌤️';
}

// ══════════════════════════════════════════════════════
// SPARKLINE
// ══════════════════════════════════════════════════════
function renderSparkline(monthly) {
  if (!monthly?.length || monthly.length < 2) return '';
  const prices = monthly.map(m => m.price);
  const min = Math.min(...prices), max = Math.max(...prices);
  const range = max - min || 1;
  const W=120, H=28, pad=2;
  const pts = prices.map((p,i) => {
    const x = pad + i * ((W-pad*2)/(prices.length-1));
    const y = H - pad - (p-min)/range*(H-pad*2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return `<div class="sparkline-wrap">
    <div class="sparkline-label">Price trend (${monthly[0].month} – ${monthly[monthly.length-1].month})</div>
    <svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" fill="none">
      <polyline points="${pts}" stroke="var(--blue)" stroke-width="1.5" fill="none" stroke-linejoin="round" stroke-linecap="round"/>
    </svg>
  </div>`;
}

// ══════════════════════════════════════════════════════
// INSIGHTS
// ══════════════════════════════════════════════════════
function renderInsights(insights, monthly=[]) {
  const card = $('insightsCard');
  if (!insights?.length) { hide(card); return; }
  card.innerHTML = insights.map(t => `<div class="insight-row">${bold(t)}</div>`).join('');
  if (monthly?.length >= 2) card.innerHTML += renderSparkline(monthly);
  show(card);
}

// ══════════════════════════════════════════════════════
// COMPARE TABLE
// ══════════════════════════════════════════════════════
function renderCompare(table) {
  const card = $('compareCard');
  if (!table?.length) { hide(card); return; }
  $('compareBody').innerHTML = table.map(row => `
    <tr class="${row.rank===1?'rank-1':''}">
      <td>${row.rank}</td>
      <td><strong>${esc(row.city)}</strong>
        <span style="font-family:var(--mono);font-size:9px;color:var(--text-ter);margin-left:4px">${esc(row.iata)}</span>
      </td>
      <td class="td-mono">${esc(row.distance_km)} km</td>
      <td>${esc(row.ground_emoji||'')} ${esc(row.ground_mode)} ~${esc(row.ground_time)}m · ${inr(row.ground_cost)}</td>
      <td class="td-mono">${inr(row.flight_price)}</td>
      <td class="td-mono">${inr(row.last_mile||0)}</td>
      <td class="td-total">${inr(row.total_cost)}</td>
      <td class="td-save">${row.savings>0?`↓ ${inr(row.savings)}`:'—'}</td>
      <td>${esc(row.carrier||'—')}</td>
    </tr>`).join('');
  show(card);
}

// ══════════════════════════════════════════════════════
// TRIP MODAL — opened via event delegation, not inline onclick
// ══════════════════════════════════════════════════════
const tripModal = $('tripModal');
$('modalClose').addEventListener('click', () => tripModal.close());
tripModal.addEventListener('click', e => { if (e.target===tripModal) tripModal.close(); });

function openTripModal(routeIndex) {
  const r = S.routes[routeIndex];
  if (!r) return;

  const f     = r.flight || {};
  const steps = r.journey_breakdown || [];
  const lmModes = r.last_mile_modes || [];

  $('modalTitle').textContent = `${r.origin_city||r.origin_airport?.city||'?'} → ${r.destination?.city||'?'}`;

  let stepsHtml = steps.map(step => `
    <div class="modal-step">
      <div class="modal-step-icon">${esc(step.emoji||'')}</div>
      <div class="modal-step-body">
        <div class="modal-step-title">${esc(step.step||'')}</div>
        <div class="modal-step-desc">${esc(step.desc||step.note||'')}</div>
        ${step.time ? `<div class="modal-step-desc" style="margin-top:2px">~${fmtTime(step.time)}</div>` : ''}
      </div>
      <div class="modal-step-cost">${inr(step.cost||0)}</div>
    </div>`).join('');

  let lmHtml = '';
  if (lmModes.length > 1) {
    lmHtml = `<div class="modal-lm-section">
      <h3>All last-mile options at ${esc(r.destination?.iata||'')} Airport</h3>
      ${lmModes.map(m => `<div class="lm-option">
        <span class="lm-name">${esc(m.emoji||'')} ${esc(m.label||m.mode||'')}</span>
        <span class="lm-time">~${m.mins}min</span>
        <span class="lm-cost">${inr(m.cost)}</span>
      </div>`).join('')}
    </div>`;
  }

  $('modalBody').innerHTML = `
    ${stepsHtml}
    <div class="modal-total">
      <span class="modal-total-label">Total door-to-door</span>
      <span class="modal-total-price">${inr(r.total_cost_inr)}</span>
    </div>
    ${lmHtml}`;
  tripModal.showModal();
}

// ══════════════════════════════════════════════════════
// SHARE
// ══════════════════════════════════════════════════════
function shareRoute(routeIndex) {
  const r = S.routes[routeIndex];
  if (!r) return;
  const f = r.flight || {};
  const text = [
    `✈ FarFinder: ${r.origin_city||r.origin_airport?.city} → ${r.destination?.city}`,
    `Total (door-to-door): ${inr(r.total_cost_inr)}`,
    `Airline: ${f.carrier||'—'} · ${stopsLabel(f.stops||0)}`,
    `Date: ${f.dep_date||'—'} · Time: ${fmtTime(r.total_time_min)}`,
    `Breakdown: Flight ${inr(f.price_inr||0)} + Transfer ${inr(r.ground?.cost_inr||0)} + Last Mile ${inr(r.last_mile?.cost||0)}`,
  ].join('\n');
  navigator.clipboard.writeText(text)
    .then(() => showToast('Copied to clipboard ✓'))
    .catch(() => alert(text));
}

// ══════════════════════════════════════════════════════
// BUILD ROUTE CARD HTML
// Uses data-idx attribute — NO JSON in onclick
// ══════════════════════════════════════════════════════
function buildRouteCard(r, isBest, idx) {
  const f  = r.flight || {};
  const g  = r.ground || {};
  const ap = r.origin_airport || {};
  const ds = r.destination || {};
  const lm = r.last_mile || {};
  const links = r.booking_links || {};
  const isGround = r.route_type === 'ground_only';
  const watched  = isWatched(r);

  // Journey pills
  const pills = (r.journey_breakdown||[]).map(step => {
    const cls = step.mode==='flight' ? 'flight'
              : (step.mode==='cab'||step.mode==='metro'||step.mode==='auto')&&step.step?.includes('Airport →') ? 'lastmile'
              : 'ground';
    return `<div class="j-pill ${cls}">${esc(step.emoji||'')} ${esc(step.step||'')} · ${inr(step.cost)} · ~${fmtTime(step.time)}</div>`;
  }).join('');

  // Price breakdown lines
  let breakdown = '';
  if (isGround) {
    breakdown = `${esc(g.mode)} (door-to-door)`;
  } else {
    const parts = [];
    if (f.price_inr > 0)  parts.push(`Flight: ${inr(f.price_inr)}`);
    if (g.cost_inr > 0)   parts.push(`Transfer: ${inr(g.cost_inr)}`);
    if (lm.cost > 0)      parts.push(`Last mile: ${inr(lm.cost)}`);
    breakdown = parts.join('<br>') || 'Inclusive';
  }

  // Booking links HTML
  const bookLinks = Object.entries(links)
    .map(([name, url]) => `<a class="book-link" href="${esc(url)}" target="_blank" rel="noopener">${esc(name)} ↗</a>`)
    .join('');

  // Flight meta
  let metaHtml = '';
  if (isGround) {
    metaHtml = `<div class="meta-row">
      <span class="carrier-name">${esc(g.emoji||'')} Intercity ${esc(g.mode)}</span>
      <span class="duration">${fmtTime(r.total_time_min)}</span>
    </div>`;
  } else {
    const via = f.connecting_via ? `<span class="duration">via ${esc(f.connecting_via)}</span>` : '';
    metaHtml = `<div class="meta-row">
      <span class="carrier-name">✈ ${esc(f.carrier||'Unknown')}</span>
      ${f.duration_fmt&&f.duration_fmt!=='—'?`<span class="duration">${esc(f.duration_fmt)}</span>`:''}
      <span class="stops-tag ${stopsClass(Number(f.stops||0))}">${stopsLabel(Number(f.stops||0))}</span>
      ${via}
      ${f.dep_date?`<span class="dep-date">${esc(f.dep_date)}</span>`:''}
      <span class="${confClass(r.confidence)} conf-tag">${confLabel(r.confidence)}</span>
    </div>`;
  }

  const saveBadge = r.savings_inr > 0
    ? `<div class="savings-tag">Save ${inr(r.savings_inr)}</div>` : '';

  // Action buttons — data-idx instead of JSON
  const actionBtns = `
    <button class="action-btn details-btn" data-idx="${idx}">⬡ Details</button>
    <button class="action-btn save-btn${watched?' starred':''}" data-idx="${idx}">${watched?'★ Saved':'☆ Save'}</button>
    <button class="action-btn share-btn" data-idx="${idx}">⎋ Share</button>`;

  return `
    <div class="route-card${isBest?' is-best':''}${isGround?' is-ground':''}">
      <div>
        ${isBest ? '<div class="best-label">★ Best Deal</div>' : ''}
        <div class="route-path">
          <span class="city">${esc(r.origin_city||ap.city||'Origin')}</span>
          <span class="airport-code">${esc(ap.iata||'—')}</span>
          <span class="path-arrow">→</span>
          <span class="city">${esc(ds.city||'Dest')}</span>
          <span class="airport-code">${esc(ds.iata||'—')}</span>
        </div>
        ${pills ? `<div class="journey-row">${pills}</div>` : ''}
        ${metaHtml}
        <div class="card-actions">
          ${bookLinks}
          ${actionBtns}
        </div>
      </div>
      <div class="card-right">
        <div class="price-total">${inr(r.total_cost_inr)}</div>
        <div class="price-breakdown">${breakdown}</div>
        ${saveBadge}
        <div class="time-total">🕐 ${fmtTime(r.total_time_min)}</div>
      </div>
    </div>`;
}

// ══════════════════════════════════════════════════════
// EVENT DELEGATION for route cards (Details / Save / Share)
// This is the key fix — single listener on the container
// ══════════════════════════════════════════════════════
$('routesContainer').addEventListener('click', e => {
  const detailsBtn = e.target.closest('.details-btn');
  const saveBtn    = e.target.closest('.save-btn');
  const shareBtn   = e.target.closest('.share-btn');

  if (detailsBtn) {
    const idx = parseInt(detailsBtn.dataset.idx, 10);
    openTripModal(idx);
  }
  if (saveBtn) {
    const idx = parseInt(saveBtn.dataset.idx, 10);
    toggleWatch(idx);
  }
  if (shareBtn) {
    const idx = parseInt(shareBtn.dataset.idx, 10);
    shareRoute(idx);
  }
});

// ══════════════════════════════════════════════════════
// RENDER ROUTES
// ══════════════════════════════════════════════════════
function renderRoutes() {
  let routes = [...S.routes];

  if (S.filter === 'direct')     routes = routes.filter(r => r.route_type==='direct');
  if (S.filter === 'multimodal') routes = routes.filter(r => r.route_type==='multimodal');
  if (S.filter === 'ground_only')routes = routes.filter(r => r.route_type==='ground_only');

  if (S.sort === 'price') routes.sort((a,b) => a.total_cost_inr - b.total_cost_inr);
  if (S.sort === 'time')  routes.sort((a,b) => a.total_time_min - b.total_time_min);
  if (S.sort === 'stops') routes.sort((a,b) => (a.flight?.stops||0) - (b.flight?.stops||0));

  const wrap = $('routesContainer');
  wrap.innerHTML = '';

  if (!routes.length) { show('emptyCard'); hide('routesHeading'); return; }
  hide('emptyCard'); show('routesHeading');

  const bestCost = Math.min(...routes.map(r => r.total_cost_inr));

  // IMPORTANT: we render using the ORIGINAL index in S.routes so data-idx is always correct
  wrap.innerHTML = S.routes
    .map((r, idx) => {
      // Check if this route passes the current filter
      if (S.filter === 'direct'     && r.route_type !== 'direct')     return '';
      if (S.filter === 'multimodal' && r.route_type !== 'multimodal') return '';
      if (S.filter === 'ground_only'&& r.route_type !== 'ground_only')return '';
      return buildRouteCard(r, r.total_cost_inr===bestCost, idx);
    })
    .filter(Boolean)
    .join('');

  // Apply sort visually
  const cards = Array.from(wrap.children);
  if (S.sort === 'price') cards.sort((a,b)=>{
    const ai=parseInt(a.querySelector('.price-total').textContent.replace(/[₹,]/g,''));
    const bi=parseInt(b.querySelector('.price-total').textContent.replace(/[₹,]/g,''));
    return ai-bi;
  });
  if (cards.length) { wrap.innerHTML=''; cards.forEach(c=>wrap.appendChild(c)); }
}

// ══════════════════════════════════════════════════════
// SEARCH
// ══════════════════════════════════════════════════════
async function runSearch() {
  const origin = $('fOrigin').value.trim();
  const dest   = $('fDest').value.trim();
  const date   = $('fDate').value;
  const radius = parseFloat($('fRadius').value);
  const direct = $('fDirect').checked;

  if (!origin||!dest||!date) { alert('Please fill in: From, To, and Date.'); return; }

  $('searchBtn').disabled = $('nlBtn').disabled = true;
  show('searchResults'); show('searchLoader');
  $('loaderFill').style.width = '0%';
  hide('statusBar'); hide('insightsCard'); hide('controlsRow');
  hide('compareCard'); hide('routesHeading'); hide('emptyCard'); hide('weatherWidget');
  $('routesContainer').innerHTML = '';
  S.routes = [];
  startLoader();

  try {
    const data = await apiFetch('/search', {
      origin, destination:dest, date, radius_km:radius, adults:S.adults, direct_only:direct,
    });
    stopLoader();
    _renderSearchData(data);
    saveRecent(origin, dest, date, radius);
    fetchWeather(dest);
  } catch(err) {
    stopLoader();
    $('routesContainer').innerHTML = `<div class="empty-card"><span>⚠️</span><h3>Search failed</h3><p>${esc(err.message)}</p></div>`;
    show('routesContainer');
  } finally {
    $('searchBtn').disabled = $('nlBtn').disabled = false;
  }
}

async function runNLSearch() {
  const query = $('nlInput').value.trim();
  if (!query) { $('nlInput').focus(); return; }

  $('searchBtn').disabled = $('nlBtn').disabled = true;
  show('searchResults'); show('searchLoader');
  $('loaderFill').style.width = '0%';
  hide('statusBar'); hide('insightsCard'); hide('controlsRow');
  hide('compareCard'); hide('routesHeading'); hide('emptyCard'); hide('weatherWidget');
  $('routesContainer').innerHTML = '';
  S.routes = [];
  startLoader();

  try {
    const data = await apiFetch('/search-nl', {query});
    stopLoader();
    const p = data.parsed_query || {};
    if (p.origin && p.origin!=='unknown')      $('fOrigin').value = p.origin;
    if (p.destination&&p.destination!=='unknown') $('fDest').value = p.destination;
    if (p.date)      $('fDate').value   = p.date;
    if (p.radius_km) { $('fRadius').value=p.radius_km; $('radiusPill').textContent=`${p.radius_km} km`; }
    _renderSearchData(data);
    if (p.origin&&p.destination) saveRecent(p.origin, p.destination, p.date||$('fDate').value, p.radius_km||100);
    fetchWeather(p.destination || $('fDest').value);
  } catch(err) {
    stopLoader();
    $('routesContainer').innerHTML = `<div class="empty-card"><span>⚠️</span><h3>Search failed</h3><p>${esc(err.message)}</p></div>`;
    show('routesContainer');
  } finally {
    $('searchBtn').disabled = $('nlBtn').disabled = false;
  }
}

function _renderSearchData(data) {
  if (data.system_message?.length) {
    $('statusBar').innerHTML = data.system_message.map(s=>esc(s)).join(' · ');
    show('statusBar');
  }
  renderInsights(data.insights, data.monthly_cheapest);
  renderCompare(data.comparison_table);
  S.routes = data.routes || [];
  show('controlsRow');
  renderRoutes();
  $('searchResults').scrollIntoView({behavior:'smooth', block:'start'});
}

// ══════════════════════════════════════════════════════
// SORT / FILTER CONTROLS
// ══════════════════════════════════════════════════════
document.querySelectorAll('[data-sort]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('[data-sort]').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    S.sort = btn.dataset.sort;
    renderRoutes();
  });
});
document.querySelectorAll('[data-type]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('[data-type]').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    S.filter = btn.dataset.type;
    renderRoutes();
  });
});

// ══════════════════════════════════════════════════════
// CALENDAR
// ══════════════════════════════════════════════════════
async function runCalendar() {
  const o = $('cOrigin').value.trim();
  const d = $('cDest').value.trim();
  const m = $('cMonth').value;
  if (!o||!d||!m) { alert('Please fill in: From, To, and Month.'); return; }

  show('calResults'); show('calLoader');
  $('calGrid').innerHTML=''; hide('calBanner'); hide('calWarn');

  try {
    const data = await apiFetch('/calendar', {origin:o, destination:d, month:m});
    hide('calLoader');

    if (!data.days_with_data) {
      $('calWarn').innerHTML = data.message || 'No price data for this route/month. Try DEL↔BOM or BLR↔HYD.';
      show('calWarn');
      $('calGrid').innerHTML = '';
      return;
    }

    if (data.cheapest_day) {
      $('calBanner').innerHTML =
        `🏆 Cheapest day: <strong>${esc(data.cheapest_day.date)}</strong> · <strong>${inr(data.cheapest_day.price)}</strong> · ${esc(data.cheapest_day.airline)}`;
      show('calBanner');
    }

    renderCalGrid(data.calendar, m, o, d);
  } catch(err) {
    hide('calLoader');
    $('calGrid').innerHTML = `<div class="empty-card"><span>⚠️</span><h3>Error</h3><p>${esc(err.message)}</p></div>`;
  }
}

function renderCalGrid(cal, month, origin, dest) {
  const [yr, mo] = month.split('-').map(Number);
  const firstDow = new Date(yr, mo-1, 1).getDay();
  const daysTotal = new Date(yr, mo, 0).getDate();
  const prices = Object.values(cal).map(c=>c.price).filter(Boolean);
  const minP = prices.length ? Math.min(...prices) : 0;
  const maxP = prices.length ? Math.max(...prices) : 1;

  let html = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
    .map(d => `<div class="day-name">${d}</div>`).join('');
  for (let i=0;i<firstDow;i++) html += '<div class="cal-cell empty"></div>';

  for (let day=1; day<=daysTotal; day++) {
    const ds   = `${month}-${String(day).padStart(2,'0')}`;
    const info = cal[ds];
    if (info) {
      const ratio  = maxP>minP ? (info.price-minP)/(maxP-minP) : 0;
      const hue    = Math.round(120 - ratio*120);
      const cheap  = info.price === minP;
      html += `<div class="cal-cell${cheap?' is-cheapest':''}"
                    style="border-color:hsl(${hue},50%,42%)"
                    data-origin="${esc(origin)}" data-dest="${esc(dest)}" data-date="${esc(ds)}">
                 <span class="cal-day">${day}</span>
                 <span class="cal-price">${inr(info.price)}</span>
                 <span class="cal-air">${esc(info.airline||'')}</span>
               </div>`;
    } else {
      html += `<div class="cal-cell empty"><span class="cal-day" style="opacity:.3">${day}</span></div>`;
    }
  }

  $('calGrid').innerHTML = html;

  // Calendar cell clicks — event delegation
  $('calGrid').addEventListener('click', e => {
    const cell = e.target.closest('.cal-cell[data-date]');
    if (!cell) return;
    $('fOrigin').value = cell.dataset.origin;
    $('fDest').value   = cell.dataset.dest;
    $('fDate').value   = cell.dataset.date;
    activateTab('search');
    runSearch();
  }, {once: true});  // Re-registered each time renderCalGrid runs
}

// ══════════════════════════════════════════════════════
// FLEXIBLE DATES
// ══════════════════════════════════════════════════════
async function runFlexible() {
  const o  = $('flOrigin').value.trim();
  const d  = $('flDest').value.trim();
  const dt = $('flDate').value;
  if (!o||!d||!dt) { alert('Please fill in: From, To, and Target Date.'); return; }

  show('flResults'); show('flLoader');
  $('flGrid').innerHTML=''; hide('flBanner'); hide('flWarn');

  try {
    const data = await apiFetch('/flexible', {origin:o, destination:d, date:dt, flex_days:S.flexDays});
    hide('flLoader');

    if (!data.options?.length) {
      $('flWarn').innerHTML = data.message || 'No flexible date data. Try a popular route like DEL↔BOM.';
      show('flWarn');
      return;
    }

    if (data.savings_if_flexible > 200 && data.cheapest_day?.date) {
      $('flBanner').innerHTML =
        `✅ Fly on <strong>${esc(data.cheapest_day.date)}</strong> instead and save <strong>${inr(data.savings_if_flexible)}</strong>!`;
      show('flBanner');
    }

    const minP   = Math.min(...data.options.map(o => o.price));
    const target = data.options.find(o => o.is_target || o.date===dt);

    $('flGrid').innerHTML = data.options.map(opt => {
      const cheap = opt.price === minP;
      const isT   = opt.is_target || opt.date === dt;
      const diff  = target ? opt.price - target.price : 0;
      let diffHtml = '';
      if (!isT && target) {
        if (diff < 0) diffHtml = `<div class="fc-diff cheaper">↓ Save ${inr(-diff)}</div>`;
        if (diff > 0) diffHtml = `<div class="fc-diff pricier">↑ ${inr(diff)} more</div>`;
      }
      return `<div class="flex-card${cheap?' is-cheapest':''}${isT?' is-target':''}">
        <div class="fc-lbl">${isT?'YOUR DATE':cheap?'✦ CHEAPEST':esc(opt.label||'')}</div>
        <div class="fc-date">${esc(opt.date)}</div>
        <div class="fc-price">${inr(opt.price)}</div>
        <div class="fc-air">${esc(opt.airline||'')}</div>
        ${diffHtml}
      </div>`;
    }).join('');

  } catch(err) {
    hide('flLoader');
    $('flGrid').innerHTML = `<div class="empty-card"><span>⚠️</span><h3>Error</h3><p>${esc(err.message)}</p></div>`;
  }
}

// ══════════════════════════════════════════════════════
// BUDGET FINDER
// ══════════════════════════════════════════════════════
async function runBudget() {
  const o     = $('bOrigin').value.trim();
  const bmin  = parseInt($('bMin').value)||0;
  const bmax  = parseInt($('bMax').value)||5000;
  const direct= $('bDirect').checked;

  if (!o) { alert('Please enter your departure city or IATA code.'); return; }
  if (bmax <= bmin) { alert('Max budget must be greater than min budget.'); return; }

  show('budgetResults'); show('budgetLoader');
  $('destGrid').innerHTML = ''; hide('budgetEmpty'); hide('budgetWarn');

  try {
    const data = await apiFetch('/budget', {origin:o, budget_min:bmin, budget_max:bmax, direct_only:direct});
    hide('budgetLoader');

    if (!data.destinations?.length) {
      if (data.message) { $('budgetWarn').innerHTML = data.message; show('budgetWarn'); }
      show('budgetEmpty');
      return;
    }

    $('destGrid').innerHTML = data.destinations.map((d, i) => `
      <div class="dest-card" style="animation-delay:${i*28}ms">
        <div class="dc-name">${esc(d.destination||'—')}</div>
        <div class="dc-iata">${esc(d.destination_iata)}</div>
        <div class="dc-price">${inr(d.price)}</div>
        <div class="dc-air">${esc(d.airline)}</div>
        <div><span class="stops-tag ${stopsClass(Number(d.stops||0))}">${stopsLabel(Number(d.stops||0))}</span></div>
        ${d.dep_date ? `<div class="dc-date">${esc(d.dep_date)}</div>` : ''}
      </div>`).join('');

  } catch(err) {
    hide('budgetLoader');
    $('destGrid').innerHTML = `<div class="empty-card"><span>⚠️</span><h3>Error</h3><p>${esc(err.message)}</p></div>`;
  }
}

// ══════════════════════════════════════════════════════
// EVENT BINDINGS
// ══════════════════════════════════════════════════════
$('searchBtn').addEventListener('click', runSearch);
$('nlBtn').addEventListener    ('click', runNLSearch);
$('calBtn').addEventListener   ('click', runCalendar);
$('flBtn').addEventListener    ('click', runFlexible);
$('budgetBtn').addEventListener('click', runBudget);

// Enter key shortcuts
$('nlInput').addEventListener ('keydown', e => { if(e.key==='Enter') runNLSearch(); });
$('fOrigin').addEventListener ('keydown', e => { if(e.key==='Enter') $('fDest').focus(); });
$('fDest').addEventListener   ('keydown', e => { if(e.key==='Enter') runSearch(); });
$('cOrigin').addEventListener ('keydown', e => { if(e.key==='Enter') $('cDest').focus(); });
$('cDest').addEventListener   ('keydown', e => { if(e.key==='Enter') runCalendar(); });
$('flOrigin').addEventListener('keydown', e => { if(e.key==='Enter') $('flDest').focus(); });
$('flDest').addEventListener  ('keydown', e => { if(e.key==='Enter') runFlexible(); });
$('bOrigin').addEventListener ('keydown', e => { if(e.key==='Enter') runBudget(); });
$('bMin').addEventListener    ('keydown', e => { if(e.key==='Enter') $('bMax').focus(); });
$('bMax').addEventListener    ('keydown', e => { if(e.key==='Enter') runBudget(); });
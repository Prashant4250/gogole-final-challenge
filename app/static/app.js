const state = {
  tenantId: 'league-x',
  stadiumId: 'stadium-1',
  defaultTenantId: 'league-x',
  defaultStadiumId: 'stadium-1',
  status: null,
  hotZones: {},
  flowHistory: [],
  riskHistoryByZone: {},
  chatOpen: false,
  authMode: 'login',
  authOpen: false,
  token: localStorage.getItem('crowdflow.token') || '',
  user: null,
  guestMode: true,
  picklistOpen: null,
  autoSeedAttempted: false,
  weatherSnapshot: null,
  userLocation: null,
  locationAttempted: false,
};

const elements = {
  tenantInput: document.querySelector('#tenant-id'),
  stadiumInput: document.querySelector('#stadium-id'),
  tenantPicklist: document.querySelector('#tenant-picklist'),
  stadiumPicklist: document.querySelector('#stadium-picklist'),
  backendPill: document.querySelector('#backend-pill'),
  publisherPill: document.querySelector('#publisher-pill'),
  authPill: document.querySelector('#auth-pill'),
  highestRisk: document.querySelector('#highest-risk'),
  highestZone: document.querySelector('#highest-zone'),
  totalOccupancy: document.querySelector('#total-occupancy'),
  zoneCount: document.querySelector('#zone-count'),
  netFlow: document.querySelector('#net-flow'),
  riskSummary: document.querySelector('#risk-summary'),
  occupancySummary: document.querySelector('#occupancy-summary'),
  flowSummary: document.querySelector('#flow-summary'),
  zoneRiskSummary: document.querySelector('#zone-risk-summary'),
  zoneRiskTrends: document.querySelector('#zone-risk-trends'),
  stadiumMap: document.querySelector('#stadium-map'),
  stadiumSummary: document.querySelector('#stadium-summary'),
  stadiumWeather: document.querySelector('#stadium-weather'),
  stadiumZoneStrip: document.querySelector('#stadium-zone-strip'),
  riskDonut: document.querySelector('#risk-donut'),
  riskLegend: document.querySelector('#risk-legend'),
  occupancyChart: document.querySelector('#occupancy-chart'),
  flowChart: document.querySelector('#flow-chart'),
  zoneList: document.querySelector('#zone-list'),
  hotZones: document.querySelector('#hot-zones'),
  actionFeed: document.querySelector('#action-feed'),
  lastUpdated: document.querySelector('#last-updated'),
  loadDemo: document.querySelector('#load-demo'),
  refresh: document.querySelector('#refresh'),
  chatForm: document.querySelector('#chat-form'),
  chatInput: document.querySelector('#chat-input'),
  chatLog: document.querySelector('#chat-log'),
  chatSuggestions: document.querySelector('#chat-suggestions'),
  chatToggle: document.querySelector('#chat-toggle'),
  chatClose: document.querySelector('#chat-close'),
  chatWidget: document.querySelector('#chat-widget'),
  chatSend: document.querySelector('#chat-send'),
  toastStack: document.querySelector('#toast-stack'),
  chatBackdrop: document.querySelector('#chat-backdrop'),
  authBackdrop: document.querySelector('#auth-backdrop'),
  authModal: document.querySelector('#auth-modal'),
  authTitle: document.querySelector('#auth-title'),
  authCopy: document.querySelector('#auth-copy'),
  authForm: document.querySelector('#auth-form'),
  authSubmit: document.querySelector('#auth-submit'),
  authSwitch: document.querySelector('#auth-switch'),
  authClose: document.querySelector('#auth-close'),
  authEmail: document.querySelector('#auth-email'),
  authPassword: document.querySelector('#auth-password'),
  authFullName: document.querySelector('#auth-full-name'),
  fullNameField: document.querySelector('#full-name-field'),
  authGuest: document.querySelector('#auth-guest'),
  authLogout: document.querySelector('#auth-logout'),
  authModeLogin: document.querySelector('#auth-mode-login'),
  authModeSignup: document.querySelector('#auth-mode-signup'),
  authError: document.querySelector('#auth-error'),
  accountTrigger: document.querySelector('#account-trigger'),
  accountLabel: document.querySelector('#account-label'),
};

const suggestionDebounce = {
  tenant: null,
  stadium: null,
};

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function setPicklistOpen(kind) {
  state.picklistOpen = kind;
  elements.tenantPicklist.classList.toggle('hidden', kind !== 'tenant');
  elements.stadiumPicklist.classList.toggle('hidden', kind !== 'stadium');
}

function closePicklists() {
  setPicklistOpen(null);
}

function renderPicklist(kind, items) {
  const target = kind === 'tenant' ? elements.tenantPicklist : elements.stadiumPicklist;
  if (!items.length) {
    target.innerHTML = '<div class="picklist-empty">No matches found.</div>';
    setPicklistOpen(kind);
    return;
  }

  target.innerHTML = items.map((item) => `
    <button class="picklist-option" type="button" data-kind="${kind}" data-value="${escapeHtml(item.value)}">
      <span class="value">${escapeHtml(item.value)}</span>
      <span class="meta">${escapeHtml(item.source)}</span>
    </button>
  `).join('');
  setPicklistOpen(kind);
}

async function loadSuggestions(kind, query) {
  const trimmed = query.trim();
  if (!trimmed) {
    closePicklists();
    return;
  }

  const endpoint = kind === 'tenant'
    ? `/v1/discovery/tenants?q=${encodeURIComponent(trimmed)}&limit=8`
    : `/v1/discovery/stadiums?q=${encodeURIComponent(trimmed)}&tenant_id=${encodeURIComponent(elements.tenantInput.value.trim())}&limit=8`;

  try {
    const payload = await fetchJson(endpoint);
    renderPicklist(kind, payload.items || []);
  } catch (error) {
    renderPicklist(kind, []);
  }
}

function queueSuggestions(kind, query) {
  if (suggestionDebounce[kind]) {
    clearTimeout(suggestionDebounce[kind]);
  }
  suggestionDebounce[kind] = setTimeout(() => {
    loadSuggestions(kind, query);
  }, 220);
}

async function applyPicklistSelection(kind, value) {
  const input = kind === 'tenant' ? elements.tenantInput : elements.stadiumInput;
  input.value = value;
  closePicklists();
  await savePreferencesIfNeeded();
  await refreshData();
}

function setAuthError(message) {
  if (!message) {
    elements.authError.textContent = '';
    elements.authError.classList.add('hidden');
    return;
  }
  elements.authError.textContent = message;
  elements.authError.classList.remove('hidden');
}

function formatApiErrorMessage(status, payload) {
  const detail = payload?.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] || {};
    if (typeof first.msg === 'string' && first.msg.trim()) {
      return first.msg;
    }
  }

  if (status === 401) {
    return 'Invalid email or password.';
  }
  if (status === 409) {
    return 'This email is already registered.';
  }
  if (status === 422) {
    return 'Please check your input fields and try again.';
  }

  return 'Something went wrong. Please try again.';
}

function authHeaders() {
  return state.token ? { Authorization: `Bearer ${state.token}` } : {};
}

function getCurrentPosition(timeoutMs = 3500) {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('Geolocation unavailable'));
      return;
    }
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: false,
      timeout: timeoutMs,
      maximumAge: 300000,
    });
  });
}

async function initializeUserLocation() {
  if (state.locationAttempted) {
    return;
  }
  state.locationAttempted = true;
  try {
    const position = await getCurrentPosition();
    state.userLocation = {
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
    };
  } catch (error) {
    state.userLocation = null;
  }
}

function resetChatLog() {
  elements.chatLog.innerHTML = `
    <article class="chat-bubble bot">
      <strong>Assistant</strong>
      <p>Ask about risk, occupancy, or recommended actions for the current stadium.</p>
    </article>
  `;
}

function setChatOpen(nextOpen) {
  state.chatOpen = nextOpen;
  elements.chatWidget.classList.toggle('open', nextOpen);
  elements.chatBackdrop.classList.toggle('visible', nextOpen);
  elements.chatWidget.setAttribute('aria-hidden', String(!nextOpen));
  elements.chatBackdrop.setAttribute('aria-hidden', String(!nextOpen));
  elements.chatToggle.setAttribute('aria-expanded', String(nextOpen));
  if (nextOpen) {
    elements.chatInput.focus();
  }
}

function setAuthOpen(nextOpen) {
  state.authOpen = nextOpen;
  elements.authModal.hidden = !nextOpen;
  elements.authBackdrop.hidden = !nextOpen;
  elements.authModal.classList.toggle('open', nextOpen);
  elements.authBackdrop.classList.toggle('visible', nextOpen);
  elements.authModal.setAttribute('aria-hidden', String(!nextOpen));
  elements.authBackdrop.setAttribute('aria-hidden', String(!nextOpen));
  if (!nextOpen) {
    setAuthError('');
  }
  if (nextOpen) {
    setAuthError('');
    elements.authEmail.focus();
  }
}

function setAuthMode(mode) {
  state.authMode = mode;
  setAuthError('');
  const signup = mode === 'signup';
  elements.authTitle.textContent = signup ? 'Create your account' : 'Welcome back';
  elements.authCopy.textContent = signup
    ? 'Create an account to save your stadium preferences and assistant history across sessions.'
    : 'Log in to persist your stadium preferences and assistant history. Guest sessions stay local and are not stored.';
  elements.authSubmit.textContent = signup ? 'Sign up' : 'Log in';
  elements.authSwitch.textContent = signup ? 'Already have an account? Log in' : 'Need an account? Sign up';
  elements.fullNameField.classList.toggle('hidden', !signup);
  elements.authModeLogin.classList.toggle('primary', !signup);
  elements.authModeLogin.classList.toggle('secondary', signup);
  elements.authModeSignup.classList.toggle('primary', signup);
  elements.authModeSignup.classList.toggle('ghost', !signup);
  elements.authModeSignup.classList.toggle('secondary', false);
}

function showToast(title, message, kind = 'loading', duration = 2200) {
  const toast = document.createElement('article');
  toast.className = `toast ${kind}`;
  toast.innerHTML = `
    <span class="spinner" aria-hidden="true"></span>
    <div>
      <strong>${title}</strong>
      <p>${message}</p>
    </div>
  `;
  elements.toastStack.appendChild(toast);
  if (duration > 0) {
    setTimeout(() => toast.remove(), duration);
  }
  return {
    update(nextTitle, nextMessage, nextKind = kind, nextDuration = duration) {
      toast.className = `toast ${nextKind}`;
      toast.querySelector('strong').textContent = nextTitle;
      toast.querySelector('p').textContent = nextMessage;
      if (nextDuration > 0) {
        setTimeout(() => toast.remove(), nextDuration);
      }
    },
    remove() {
      toast.remove();
    },
  };
}

function appendChatMessage(role, message, thoughts = []) {
  const card = document.createElement('article');
  card.className = `chat-bubble ${role}`;
  let html = `<strong>${role === 'user' ? 'You' : 'Assistant'}</strong><p>${message}</p>`;
  if (thoughts && thoughts.length > 0) {
    html += `
      <div class="thoughts-section">
        <div class="thought-title">
          <svg style="width:12px;height:12px;fill:currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>
          Agent execution logs
        </div>
        ${thoughts.map(t => `<div class="thought-log-item">> ${t}</div>`).join('')}
      </div>
    `;
  }
  card.innerHTML = html;
  elements.chatLog.appendChild(card);
  elements.chatLog.scrollTop = elements.chatLog.scrollHeight;
  return card;
}

function renderSuggestions(items) {
  elements.chatSuggestions.innerHTML = items.map((item) => `
    <button class="suggestion" type="button" data-question="${item.replace(/"/g, '&quot;')}">${item}</button>
  `).join('');
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(value);
}

function severityClass(value) {
  return String(value || 'low').toLowerCase();
}

function renderEmpty(target, message) {
  target.innerHTML = `<div class="empty">${message}</div>`;
}

function colorForSeverity(severity) {
  const normalized = String(severity || 'low').toLowerCase();
  if (normalized === 'critical') return '#ff6b57';
  if (normalized === 'high') return '#ffad42';
  if (normalized === 'medium') return '#7cd3b9';
  return '#8bc1ff';
}

function renderWeatherCards({ temperatureC, rainChance, windChance, condition, source, cityName }) {
  const sourceLabel = source === 'open-meteo' ? 'Live weather feed' : 'Fallback estimate';
  const placeLabel = cityName ? `City: ${cityName}` : 'City unavailable';
  elements.stadiumWeather.innerHTML = `
    <article class="stadium-weather-card">
      <span class="stadium-weather-label">Temperature</span>
      <strong class="stadium-weather-value">${temperatureC.toFixed(1)} C</strong>
      <span class="stadium-weather-meta">${condition} · ${placeLabel}</span>
    </article>
    <article class="stadium-weather-card">
      <span class="stadium-weather-label">Weather possibility</span>
      <strong class="stadium-weather-value">Rain ${rainChance}%</strong>
      <span class="stadium-weather-meta">Wind disruption chance ${windChance}% · ${sourceLabel}</span>
    </article>
  `;
}

function renderStadiumView(zones) {
  if (!zones.length) {
    elements.stadiumSummary.innerHTML = '';
    const weather = state.weatherSnapshot;
    if (weather) {
      renderWeatherCards({
        temperatureC: weather.temperature_c,
        rainChance: weather.precipitation_probability,
        windChance: Math.round(Math.min(100, weather.wind_kph * 2.2)),
        condition: weather.condition,
        source: weather.source,
        cityName: weather.city_name,
      });
    } else {
      elements.stadiumWeather.innerHTML = `
        <article class="stadium-weather-card">
          <span class="stadium-weather-label">Temperature</span>
          <strong class="stadium-weather-value">--</strong>
          <span class="stadium-weather-meta">Waiting for weather feed</span>
        </article>
        <article class="stadium-weather-card">
          <span class="stadium-weather-label">Weather possibility</span>
          <strong class="stadium-weather-value">--</strong>
          <span class="stadium-weather-meta">Chance updates with selected stadium</span>
        </article>
      `;
    }
    renderEmpty(elements.stadiumZoneStrip, 'Zone cards will appear when live stadium data is available.');
    elements.stadiumMap.innerHTML = `
      <svg viewBox="0 0 520 300" role="img" aria-label="Stadium map placeholder">
        <ellipse cx="260" cy="150" rx="218" ry="122" fill="rgba(255,255,255,0.04)" stroke="rgba(255,255,255,0.16)" stroke-width="2"></ellipse>
        <ellipse cx="260" cy="150" rx="144" ry="72" fill="rgba(95,224,208,0.12)" stroke="rgba(95,224,208,0.35)" stroke-width="2"></ellipse>
        <text x="260" y="155" fill="rgba(255,255,255,0.56)" font-size="12" text-anchor="middle" font-family="IBM Plex Mono, monospace">NO LIVE ZONES</text>
      </svg>
    `;
    return;
  }

  const sortedZones = zones.slice().sort((a, b) => b.risk_score - a.risk_score);
  const maxNodes = Math.min(8, sortedZones.length);
  const plottedZones = sortedZones.slice(0, maxNodes);
  const centerX = 260;
  const centerY = 150;
  const radiusX = 176;
  const radiusY = 98;

  const nodes = plottedZones.map((zone, index) => {
    const angle = ((Math.PI * 2) / maxNodes) * index - (Math.PI / 2);
    const x = centerX + Math.cos(angle) * radiusX;
    const y = centerY + Math.sin(angle) * radiusY;
    const color = colorForSeverity(zone.severity);
    return {
      zone,
      x,
      y,
      color,
      shortName: zone.zone_id.length > 12 ? `${zone.zone_id.slice(0, 10)}…` : zone.zone_id,
    };
  });

  const avgRisk = zones.reduce((sum, zone) => sum + zone.risk_score, 0) / zones.length;
  const avgUtilization = zones.reduce((sum, zone) => sum + zone.occupancy_ratio, 0) / zones.length;
  const avgWeatherRisk = zones.reduce((sum, zone) => sum + (zone.weather_risk || 0), 0) / zones.length;
  elements.stadiumSummary.innerHTML = `
    <span class="summary-pill">Mapped zones: <strong>${plottedZones.length}</strong></span>
    <span class="summary-pill">Avg risk: <strong>${avgRisk.toFixed(2)}</strong></span>
    <span class="summary-pill">Avg utilization: <strong>${(avgUtilization * 100).toFixed(1)}%</strong></span>
  `;

  const weather = state.weatherSnapshot;
  if (weather) {
    renderWeatherCards({
      temperatureC: weather.temperature_c,
      rainChance: weather.precipitation_probability,
      windChance: Math.round(Math.min(100, weather.wind_kph * 2.2)),
      condition: weather.condition,
      source: weather.source,
      cityName: weather.city_name,
    });
  } else {
    const rainChance = Math.round(avgWeatherRisk * 100);
    const windChance = Math.round(Math.min(100, (avgWeatherRisk * 0.8 + avgUtilization * 0.35) * 100));
    const temperatureC = Math.max(
      12,
      Math.min(42, 28 + (avgUtilization * 4.5) - (avgWeatherRisk * 7.5)),
    );
    renderWeatherCards({
      temperatureC,
      rainChance,
      windChance,
      condition: 'Estimated from live zone risk',
      source: 'fallback',
      cityName: state.stadiumId.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
    });
  }

  elements.stadiumMap.innerHTML = `
    <svg viewBox="0 0 520 300" role="img" aria-label="Live stadium zone map">
      <defs>
        <linearGradient id="pitchGlow" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="rgba(95,224,208,0.24)"></stop>
          <stop offset="100%" stop-color="rgba(95,224,208,0.08)"></stop>
        </linearGradient>
      </defs>
      <ellipse cx="260" cy="150" rx="218" ry="122" fill="rgba(255,255,255,0.04)" stroke="rgba(255,255,255,0.18)" stroke-width="2"></ellipse>
      <ellipse cx="260" cy="150" rx="182" ry="102" fill="rgba(255,255,255,0.02)" stroke="rgba(255,255,255,0.12)" stroke-width="1.5" stroke-dasharray="4 6"></ellipse>
      <ellipse cx="260" cy="150" rx="132" ry="62" fill="url(#pitchGlow)" stroke="rgba(95,224,208,0.42)" stroke-width="2"></ellipse>
      ${nodes.map((node) => `
        <line x1="260" y1="150" x2="${node.x.toFixed(1)}" y2="${node.y.toFixed(1)}" stroke="${node.color}" stroke-opacity="0.45" stroke-width="1.4"></line>
        <circle cx="${node.x.toFixed(1)}" cy="${node.y.toFixed(1)}" r="10.5" fill="${node.color}" fill-opacity="0.25" stroke="${node.color}" stroke-width="2"></circle>
        <text x="${node.x.toFixed(1)}" y="${(node.y + 24).toFixed(1)}" fill="rgba(255,255,255,0.86)" font-size="10" text-anchor="middle" font-family="IBM Plex Mono, monospace">${node.shortName}</text>
      `).join('')}
    </svg>
  `;

  elements.stadiumZoneStrip.innerHTML = sortedZones.slice(0, 5).map((zone) => {
    const color = colorForSeverity(zone.severity);
    const zoneWeatherRisk = Number.isFinite(zone.weather_risk) ? zone.weather_risk : 0;
    return `
      <article class="stadium-zone-chip">
        <div class="stadium-zone-chip-head">
          <span class="stadium-zone-name"><span class="stadium-zone-dot" style="background:${color}"></span>${zone.zone_id}</span>
          <span class="severity ${severityClass(zone.severity)}">${zone.severity}</span>
        </div>
        <div class="stadium-zone-meta">Risk ${zone.risk_score.toFixed(2)} • Weather ${(zoneWeatherRisk * 100).toFixed(0)}% • ${(zone.occupancy_ratio * 100).toFixed(1)}% utilization • ${zone.net_flow_per_min > 0 ? '+' : ''}${zone.net_flow_per_min.toFixed(0)} flow/min</div>
      </article>
    `;
  }).join('');
}

function renderCharts(zones) {
  if (!zones.length) {
    elements.riskSummary.innerHTML = '';
    elements.occupancySummary.innerHTML = '';
    elements.flowSummary.innerHTML = '';
    elements.zoneRiskSummary.innerHTML = '';
    state.riskHistoryByZone = {};
    elements.riskDonut.style.background = 'conic-gradient(rgba(124, 211, 185, 0.35) 0turn, rgba(124, 211, 185, 0.35) 1turn)';
    renderEmpty(elements.riskLegend, 'No risk data yet.');
    renderEmpty(elements.occupancyChart, 'Occupancy chart will appear once zones are active.');
    state.flowHistory = [];
    renderEmpty(elements.flowChart, 'Flow trend starts after live updates.');
    renderEmpty(elements.zoneRiskTrends, 'Zone risk trends will appear after live refreshes.');
    return;
  }

  const maxHistoryPoints = 24;
  for (const zone of zones) {
    if (!state.riskHistoryByZone[zone.zone_id]) {
      state.riskHistoryByZone[zone.zone_id] = [];
    }
    state.riskHistoryByZone[zone.zone_id].push(zone.risk_score);
    if (state.riskHistoryByZone[zone.zone_id].length > maxHistoryPoints) {
      state.riskHistoryByZone[zone.zone_id] = state.riskHistoryByZone[zone.zone_id].slice(-maxHistoryPoints);
    }
  }

  for (const zoneId of Object.keys(state.riskHistoryByZone)) {
    if (!zones.some((zone) => zone.zone_id === zoneId)) {
      delete state.riskHistoryByZone[zoneId];
    }
  }

  const severityOrder = ['critical', 'high', 'medium', 'low'];
  const severityColors = {
    critical: '#ff6b57',
    high: '#ffad42',
    medium: '#7cd3b9',
    low: '#8bc1ff',
  };
  const counts = {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
  };

  for (const zone of zones) {
    const key = String(zone.severity || 'low').toLowerCase();
    if (counts[key] !== undefined) {
      counts[key] += 1;
    }
  }

  const total = zones.length;
  const highOrCritical = counts.high + counts.critical;
  elements.riskSummary.innerHTML = `
    <span class="summary-pill">Active zones: <strong>${total}</strong></span>
    <span class="summary-pill">High/Critical: <strong>${highOrCritical}</strong></span>
  `;

  let turnsSoFar = 0;
  const segments = [];
  for (const level of severityOrder) {
    const portion = counts[level] / total;
    const start = turnsSoFar;
    const end = turnsSoFar + portion;
    segments.push(`${severityColors[level]} ${start}turn ${end}turn`);
    turnsSoFar = end;
  }
  elements.riskDonut.style.background = `conic-gradient(${segments.join(', ')})`;

  elements.riskLegend.innerHTML = severityOrder.map((level) => `
    <div class="risk-legend-item">
      <span class="risk-legend-key">
        <span class="risk-dot" style="background:${severityColors[level]}"></span>
        ${level.toUpperCase()}
      </span>
      <strong>${counts[level]}</strong>
    </div>
  `).join('');

  elements.occupancyChart.innerHTML = zones
    .slice()
    .sort((a, b) => b.occupancy_ratio - a.occupancy_ratio)
    .map((zone) => {
      const width = Math.max(3, Math.min(100, zone.occupancy_ratio * 100));
      return `
        <div class="bar-row">
          <span class="bar-label">${zone.zone_id}</span>
          <span class="bar-track"><span class="bar-fill" style="width:${width}%"></span></span>
          <span class="bar-value">${(zone.occupancy_ratio * 100).toFixed(1)}%</span>
        </div>
      `;
    }).join('');

  const avgUtil = zones.reduce((sum, zone) => sum + zone.occupancy_ratio, 0) / zones.length;
  const overNinety = zones.filter((zone) => zone.occupancy_ratio >= 0.9).length;
  elements.occupancySummary.innerHTML = `
    <span class="summary-pill">Avg utilization: <strong>${(avgUtil * 100).toFixed(1)}%</strong></span>
    <span class="summary-pill">Zones above 90%: <strong>${overNinety}</strong></span>
  `;

  const totalNetFlow = zones.reduce((sum, zone) => sum + zone.net_flow_per_min, 0);
  state.flowHistory.push(totalNetFlow);
  if (state.flowHistory.length > 24) {
    state.flowHistory = state.flowHistory.slice(-24);
  }

  const values = state.flowHistory;
  const svgWidth = 540;
  const svgHeight = 150;
  const pad = 12;
  const minValue = Math.min(...values, 0);
  const maxValue = Math.max(...values, 0);
  const valueRange = Math.max(1, maxValue - minValue);

  const points = values.map((value, index) => {
    const x = values.length === 1
      ? svgWidth / 2
      : pad + (index * (svgWidth - (pad * 2))) / (values.length - 1);
    const y = svgHeight - pad - ((value - minValue) / valueRange) * (svgHeight - (pad * 2));
    return { x, y };
  });

  const zeroY = svgHeight - pad - ((0 - minValue) / valueRange) * (svgHeight - (pad * 2));
  const polyline = points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ');
  const areaPath = points.length
    ? `M ${points[0].x.toFixed(1)} ${svgHeight - pad} L ${points.map((point) => `${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' L ')} L ${points[points.length - 1].x.toFixed(1)} ${svgHeight - pad} Z`
    : '';
  const last = points[points.length - 1];
  const avgFlow = values.reduce((sum, value) => sum + value, 0) / values.length;
  const peakFlow = Math.max(...values);

  elements.flowSummary.innerHTML = `
    <span class="summary-pill">Current flow: <strong>${totalNetFlow > 0 ? '+' : ''}${totalNetFlow.toFixed(0)}/min</strong></span>
    <span class="summary-pill">Avg flow: <strong>${avgFlow > 0 ? '+' : ''}${avgFlow.toFixed(0)}/min</strong></span>
    <span class="summary-pill">Peak flow: <strong>${peakFlow > 0 ? '+' : ''}${peakFlow.toFixed(0)}/min</strong></span>
  `;

  elements.flowChart.innerHTML = `
    <svg viewBox="0 0 ${svgWidth} ${svgHeight}" role="img" aria-label="Net flow trend chart">
      <line x1="${pad}" y1="${pad}" x2="${svgWidth - pad}" y2="${pad}" stroke="rgba(255,255,255,0.08)" stroke-width="1"></line>
      <line x1="${pad}" y1="${zeroY.toFixed(1)}" x2="${svgWidth - pad}" y2="${zeroY.toFixed(1)}" stroke="rgba(255,255,255,0.2)" stroke-width="1" stroke-dasharray="4 4"></line>
      <line x1="${pad}" y1="${svgHeight - pad}" x2="${svgWidth - pad}" y2="${svgHeight - pad}" stroke="rgba(255,255,255,0.08)" stroke-width="1"></line>
      <path d="${areaPath}" fill="rgba(95,224,208,0.18)"></path>
      <polyline points="${polyline}" fill="none" stroke="#5fe0d0" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>
      <circle cx="${last.x.toFixed(1)}" cy="${last.y.toFixed(1)}" r="4.5" fill="#ffd166"></circle>
    </svg>
  `;

  const topRiskZones = zones
    .slice()
    .sort((a, b) => b.risk_score - a.risk_score)
    .slice(0, 4);
  const averageRisk = zones.reduce((sum, zone) => sum + zone.risk_score, 0) / zones.length;
  const alertingZones = zones.filter((zone) => zone.risk_score >= 0.6).length;

  elements.zoneRiskSummary.innerHTML = `
    <span class="summary-pill">Average risk: <strong>${averageRisk.toFixed(2)}</strong></span>
    <span class="summary-pill">Alerting zones (>=0.60): <strong>${alertingZones}</strong></span>
  `;

  const severityStroke = {
    critical: '#ff6b57',
    high: '#ffad42',
    medium: '#7cd3b9',
    low: '#8bc1ff',
  };

  elements.zoneRiskTrends.innerHTML = topRiskZones.map((zone) => {
    const pointsData = state.riskHistoryByZone[zone.zone_id] || [zone.risk_score];
    const width = 320;
    const height = 66;
    const padX = 8;
    const padY = 8;
    const min = Math.min(...pointsData);
    const max = Math.max(...pointsData);
    const span = Math.max(0.01, max - min);

    const points = pointsData.map((value, index) => {
      const x = pointsData.length === 1
        ? width / 2
        : padX + (index * (width - (padX * 2))) / (pointsData.length - 1);
      const y = height - padY - ((value - min) / span) * (height - (padY * 2));
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');

    const first = pointsData[0];
    const last = pointsData[pointsData.length - 1];
    const delta = last - first;
    const trend = delta > 0.01 ? 'rising' : delta < -0.01 ? 'falling' : 'steady';
    const stroke = severityStroke[String(zone.severity || 'low').toLowerCase()] || '#8bc1ff';

    return `
      <article class="zone-trend-card">
        <div class="zone-trend-head">
          <strong>${zone.zone_id}</strong>
          <span class="zone-trend-meta">Risk ${zone.risk_score.toFixed(2)} · ${trend}</span>
        </div>
        <div class="zone-trend-sparkline">
          <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${zone.zone_id} risk trend">
            <polyline points="${points}" fill="none" stroke="${stroke}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>
          </svg>
        </div>
      </article>
    `;
  }).join('');
}

function renderStatus() {
  const zones = state.status?.zones || [];
  if (!zones.length) {
    elements.highestRisk.textContent = '--';
    elements.highestZone.textContent = 'Awaiting feed';
    elements.totalOccupancy.textContent = '--';
    elements.zoneCount.textContent = '0 zones online';
    elements.netFlow.textContent = '--';
    elements.lastUpdated.textContent = 'No updates yet';
    renderEmpty(elements.zoneList, 'No stadium data yet. Load the demo surge or ingest live signals.');
    renderEmpty(elements.actionFeed, 'Recommendations will appear once a zone becomes active.');
    renderCharts(zones);
    renderStadiumView(zones);
    return;
  }

  const highest = zones[0];
  const totalOccupancy = zones.reduce((sum, zone) => sum + zone.occupancy, 0);
  const totalNetFlow = zones.reduce((sum, zone) => sum + zone.net_flow_per_min, 0);
  const actions = zones.flatMap((zone) => zone.recommendations.map((item) => ({ ...item, zone: zone.zone_id })));

  elements.highestRisk.textContent = highest.risk_score.toFixed(2);
  elements.highestZone.textContent = `${highest.zone_id} • ${highest.severity.toUpperCase()}`;
  elements.totalOccupancy.textContent = formatNumber(totalOccupancy);
  elements.zoneCount.textContent = `${zones.length} zones online`;
  elements.netFlow.textContent = `${totalNetFlow > 0 ? '+' : ''}${totalNetFlow.toFixed(0)}/min`;
  elements.lastUpdated.textContent = new Date(state.status.generated_at).toLocaleTimeString();

  elements.zoneList.innerHTML = zones.map((zone) => {
    const interventionsHtml = zone.applied_interventions && zone.applied_interventions.length > 0
      ? `<div class="interventions-list">
          ${zone.applied_interventions.map(i => `
            <span class="intervention-badge" title="Applied at: ${new Date(i.applied_at).toLocaleTimeString()}\nReason: ${i.reason}">
              ✓ ${i.action.replace(/_/g, ' ')}
            </span>
          `).join('')}
         </div>`
      : '';

    return `
      <article class="zone-card">
        <div>
          <h3>${zone.zone_id}</h3>
          <p class="zone-meta">Occupancy ${formatNumber(zone.occupancy)} / ${formatNumber(zone.safe_capacity)} • Updated ${new Date(zone.last_update).toLocaleTimeString()}</p>
          ${interventionsHtml}
        </div>
        <div class="metric-stack">
          <strong>${(zone.occupancy_ratio * 100).toFixed(1)}% full</strong>
          <span>${zone.net_flow_per_min > 0 ? '+' : ''}${zone.net_flow_per_min.toFixed(0)} net flow/min</span>
        </div>
        <div class="severity ${severityClass(zone.severity)}">${zone.severity}</div>
      </article>
    `;
  }).join('');

  if (!actions.length) {
    renderEmpty(elements.actionFeed, 'No active interventions required.');
  } else {
    elements.actionFeed.innerHTML = actions.map((action) => `
      <article class="action-card">
        <span class="action-tag">${action.action}</span>
        <strong>${action.zone}</strong>
        <div class="severity ${severityClass(action.severity)}">${action.severity}</div>
        <p>${action.reason}</p>
      </article>
    `).join('');
  }

  renderCharts(zones);
  renderStadiumView(zones);
}

function renderHotZones() {
  const groups = Object.entries(state.hotZones || {});
  if (!groups.length) {
    renderEmpty(elements.hotZones, 'No zones above the current alert threshold.');
    return;
  }

  elements.hotZones.innerHTML = groups.flatMap(([key, zones]) => zones.map((zone) => `
    <article class="hot-card">
      <span class="action-tag">${key}</span>
      <strong>${zone.zone_id}</strong>
      <div class="severity ${severityClass(zone.severity)}">${zone.severity}</div>
      <p>Risk score ${zone.risk_score.toFixed(2)} with occupancy ratio ${(zone.occupancy_ratio * 100).toFixed(1)}%</p>
    </article>
  `)).join('');
}

function renderAuthState() {
  const signedIn = Boolean(state.user && state.token);
  state.guestMode = !signedIn;
  elements.authPill.textContent = signedIn
    ? `Signed in: ${state.user.full_name}`
    : 'Mode: guest';
  elements.accountLabel.textContent = signedIn ? state.user.full_name : 'Account';
  elements.authGuest.classList.toggle('hidden', signedIn);
  elements.authLogout.classList.toggle('hidden', !signedIn);
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let errorMessage = 'Something went wrong. Please try again.';
    try {
      const payload = await response.json();
      errorMessage = formatApiErrorMessage(response.status, payload);
    } catch (error) {
      errorMessage = formatApiErrorMessage(response.status, null);
    }
    throw new Error(errorMessage);
  }
  return response.json();
}

async function loadConfig() {
  const config = await fetchJson('/v1/config');
  state.defaultTenantId = config.dashboard_default_tenant;
  state.defaultStadiumId = config.dashboard_default_stadium;
  state.tenantId = config.dashboard_default_tenant;
  state.stadiumId = config.dashboard_default_stadium;
  elements.tenantInput.value = state.tenantId;
  elements.stadiumInput.value = state.stadiumId;
  elements.backendPill.textContent = `Backend: ${config.store_backend}`;
  elements.publisherPill.textContent = `Publisher: ${config.publisher_backend}`;
  renderAuthState();
  queueSuggestions('tenant', state.tenantId);
  queueSuggestions('stadium', state.stadiumId);
}

async function loadUserState() {
  if (!state.token) {
    state.user = null;
    renderAuthState();
    return;
  }

  try {
    const payload = await fetchJson('/v1/auth/me', { headers: authHeaders() });
    state.user = payload.user;
    state.tenantId = payload.preferences.tenant_id;
    state.stadiumId = payload.preferences.stadium_id;
    elements.tenantInput.value = state.tenantId;
    elements.stadiumInput.value = state.stadiumId;
    resetChatLog();
    for (const item of payload.chat_history || []) {
      appendChatMessage(item.role, item.message);
    }
    renderAuthState();
  } catch (error) {
    state.token = '';
    state.user = null;
    localStorage.removeItem('crowdflow.token');
    resetChatLog();
    renderAuthState();
  }
}

async function savePreferencesIfNeeded() {
  if (!state.token) {
    return;
  }

  await fetchJson('/v1/user/preferences', {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
    },
    body: JSON.stringify({
      tenant_id: elements.tenantInput.value.trim(),
      stadium_id: elements.stadiumInput.value.trim(),
    }),
  });
}

async function refreshData() {
  state.tenantId = elements.tenantInput.value.trim();
  state.stadiumId = elements.stadiumInput.value.trim();

  if (!state.tenantId) {
    state.tenantId = state.defaultTenantId;
    elements.tenantInput.value = state.tenantId;
  }
  if (!state.stadiumId) {
    state.stadiumId = state.defaultStadiumId;
    elements.stadiumInput.value = state.stadiumId;
  }

  let usedFallback = false;
  try {
    state.status = await fetchJson(`/v1/stadiums/${encodeURIComponent(state.stadiumId)}/status?tenant_id=${encodeURIComponent(state.tenantId)}`);
  } catch (error) {
    state.status = null;
    const shouldFallback =
      state.tenantId !== state.defaultTenantId || state.stadiumId !== state.defaultStadiumId;
    if (shouldFallback) {
      state.tenantId = state.defaultTenantId;
      state.stadiumId = state.defaultStadiumId;
      elements.tenantInput.value = state.tenantId;
      elements.stadiumInput.value = state.stadiumId;
      try {
        state.status = await fetchJson(`/v1/stadiums/${encodeURIComponent(state.stadiumId)}/status?tenant_id=${encodeURIComponent(state.tenantId)}`);
        usedFallback = true;
      } catch (fallbackError) {
        state.status = null;
      }
    }
  }

  if (usedFallback) {
    await savePreferencesIfNeeded();
    showToast('Selection updated', 'Saved values had no live feed. Showing default stadium data.', 'success', 2200);
  }

  const weatherParams = new URLSearchParams({
    stadium_id: state.stadiumId,
    tenant_id: state.tenantId,
  });
  if (state.userLocation) {
    weatherParams.set('latitude', String(state.userLocation.latitude));
    weatherParams.set('longitude', String(state.userLocation.longitude));
  }

  try {
    state.weatherSnapshot = await fetchJson(`/v1/weather/current?${weatherParams.toString()}`);
  } catch (weatherError) {
    state.weatherSnapshot = null;
  }

  // If the feed is empty on first load, seed demo signals once for this session.
  if (!state.status && !state.autoSeedAttempted) {
    state.autoSeedAttempted = true;
    try {
      const demoPayload = await fetchJson('/v1/demo/signals');
      await fetchJson('/v1/signals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(demoPayload),
      });
      state.tenantId = state.defaultTenantId;
      state.stadiumId = state.defaultStadiumId;
      elements.tenantInput.value = state.tenantId;
      elements.stadiumInput.value = state.stadiumId;
      state.status = await fetchJson(`/v1/stadiums/${encodeURIComponent(state.stadiumId)}/status?tenant_id=${encodeURIComponent(state.tenantId)}`);
      await savePreferencesIfNeeded();
      showToast('Live feed initialized', 'Loaded baseline stadium signals for your session.', 'success', 2200);
    } catch (seedError) {
      // Keep empty state if seeding fails; user can still manually load demo surge.
    }
  }

  state.hotZones = await fetchJson('/v1/hot-zones?min_score=0.7');
  renderStatus();
  renderHotZones();
}

async function loadDemo() {
  const toast = showToast('Loading demo surge', 'Injecting sample stadium signals...', 'loading', 0);
  const payload = await fetchJson('/v1/demo/signals');
  await fetchJson('/v1/signals', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  await refreshData();
  toast.update('Demo data ready', 'The dashboard is showing live sample signals.', 'success', 1800);
}

async function sendChat(message) {
  setChatOpen(true);
  elements.chatSend.disabled = true;
  appendChatMessage('user', message);
  const loadingCard = appendChatMessage('bot loading', '<span class="spinner" aria-hidden="true"></span>Thinking with live stadium state...');
  const toast = showToast('Assistant is replying', 'Fetching the latest stadium context...', 'loading', 0);
  await refreshData();

  const payload = {
    tenant_id: elements.tenantInput.value.trim(),
    stadium_id: elements.stadiumInput.value.trim(),
    message,
  };

  try {
    const response = await fetchJson('/v1/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify(payload),
    });
    loadingCard.remove();
    appendChatMessage('bot', response.answer, response.thoughts);
    renderSuggestions(response.suggested_questions || []);
    toast.update('Assistant replied', 'Live answer delivered from current stadium data.', 'success', 1600);
  } catch (error) {
    loadingCard.remove();
    appendChatMessage('bot', 'The assistant could not answer right now. Refresh data and try again.');
    toast.update('Assistant unavailable', 'Could not generate a live answer.', 'error', 2200);
  } finally {
    elements.chatSend.disabled = false;
  }
}

async function submitAuth(event) {
  event.preventDefault();
  setAuthError('');
  const endpoint = state.authMode === 'signup' ? '/v1/auth/signup' : '/v1/auth/login';
  const body = {
    email: elements.authEmail.value.trim(),
    password: elements.authPassword.value,
  };
  if (state.authMode === 'signup') {
    body.full_name = elements.authFullName.value.trim();
  }

  const toast = showToast(
    state.authMode === 'signup' ? 'Creating account' : 'Logging in',
    'Securing your session...',
    'loading',
    0,
  );

  try {
    const response = await fetchJson(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    state.token = response.token;
    state.user = response.user;
    localStorage.setItem('crowdflow.token', response.token);
    setAuthOpen(false);
    await loadUserState();
    await refreshData();
    toast.update('Signed in', 'Your preferences and chat history are now synced.', 'success', 1800);
  } catch (error) {
    const friendlyMessage = error?.message || 'Authentication failed. Please try again.';
    setAuthError(friendlyMessage);
    toast.update('Authentication failed', friendlyMessage, 'error', 2800);
  }
}

function useGuestMode() {
  state.token = '';
  state.user = null;
  localStorage.removeItem('crowdflow.token');
  state.tenantId = 'league-x';
  state.stadiumId = 'stadium-1';
  elements.tenantInput.value = state.tenantId;
  elements.stadiumInput.value = state.stadiumId;
  resetChatLog();
  renderAuthState();
  closePicklists();
  setAuthOpen(false);
}

function logout() {
  useGuestMode();
  showToast('Logged out', 'You are now using the dashboard as a guest.', 'success', 1600);
}

elements.refresh.addEventListener('click', async () => {
  const toast = showToast('Refreshing data', 'Pulling the latest zone status...', 'loading', 0);
  await refreshData();
  toast.update('Dashboard updated', 'The latest signals are now visible.', 'success', 1500);
});
elements.loadDemo.addEventListener('click', loadDemo);
elements.tenantInput.addEventListener('change', async () => {
  await savePreferencesIfNeeded();
  await refreshData();
});
elements.stadiumInput.addEventListener('change', async () => {
  await savePreferencesIfNeeded();
  await refreshData();
});
elements.tenantInput.addEventListener('focus', () => {
  queueSuggestions('tenant', elements.tenantInput.value);
});
elements.stadiumInput.addEventListener('focus', () => {
  queueSuggestions('stadium', elements.stadiumInput.value);
});
elements.tenantInput.addEventListener('input', () => {
  queueSuggestions('tenant', elements.tenantInput.value);
});
elements.stadiumInput.addEventListener('input', () => {
  queueSuggestions('stadium', elements.stadiumInput.value);
});
elements.tenantPicklist.addEventListener('mousedown', async (event) => {
  const button = event.target.closest('.picklist-option');
  if (!button) {
    return;
  }
  event.preventDefault();
  await applyPicklistSelection('tenant', button.dataset.value || '');
  queueSuggestions('stadium', elements.stadiumInput.value);
});
elements.stadiumPicklist.addEventListener('mousedown', async (event) => {
  const button = event.target.closest('.picklist-option');
  if (!button) {
    return;
  }
  event.preventDefault();
  await applyPicklistSelection('stadium', button.dataset.value || '');
});
document.addEventListener('click', (event) => {
  const target = event.target;
  if (!(target instanceof Element)) {
    closePicklists();
    return;
  }
  if (target.closest('.picklist-field')) {
    return;
  }
  closePicklists();
});
elements.chatToggle.addEventListener('click', () => setChatOpen(!state.chatOpen));
elements.chatClose.addEventListener('click', () => setChatOpen(false));
elements.chatBackdrop.addEventListener('click', () => setChatOpen(false));
elements.authBackdrop.addEventListener('click', () => setAuthOpen(false));
elements.authClose.addEventListener('click', () => setAuthOpen(false));
elements.authForm.addEventListener('submit', submitAuth);
elements.authSwitch.addEventListener('click', () => {
  setAuthMode(state.authMode === 'signup' ? 'login' : 'signup');
});
elements.authModeLogin.addEventListener('click', () => setAuthMode('login'));
elements.authModeSignup.addEventListener('click', () => setAuthMode('signup'));
elements.authGuest.addEventListener('click', useGuestMode);
elements.authLogout.addEventListener('click', () => {
  logout();
  setAuthOpen(false);
});
elements.accountTrigger.addEventListener('click', () => {
  setAuthMode('login');
  setAuthOpen(true);
});
elements.chatForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = elements.chatInput.value.trim();
  if (!message) {
    return;
  }
  elements.chatInput.value = '';
  await sendChat(message);
});
elements.chatSuggestions.addEventListener('click', async (event) => {
  const button = event.target.closest('.suggestion');
  if (!button) {
    return;
  }
  await sendChat(button.dataset.question);
});

async function initializeApp() {
  await loadConfig();
  await loadUserState();
  await initializeUserLocation();
  await refreshData();
}

initializeApp();
renderSuggestions([
  'What is the highest risk zone?',
  'What actions should operators take now?',
  'Give me a stadium summary.',
]);
resetChatLog();
setAuthMode('login');
renderAuthState();
setAuthOpen(false);
setChatOpen(false);
setInterval(refreshData, 8000);

/*
 * KEVIN® card for Home Assistant (design v6).
 *
 * Normative reference: docs/card/prototypes/kevin-ha-card-v6.html
 *
 * The card is a small window with KEVIN on a shelf:
 *  - the day-night strip is the wake / standby switch (drag, tap or arrow keys),
 *  - the subscription is a ring that counts the days left,
 *  - "Now playing" shows what KEVIN chose to play, read-only,
 *  - the schedule shows the Presence windows of the week,
 *  - preferences (environment, lifestyle, occupancy, energy) open behind a gear,
 *  - reboot goes through a confirmation dialog.
 *
 * Every value comes from mitipi_kevin entities resolved through the device and
 * entity registries from one configured entity. Mutations are never optimistic:
 * the card shows a pending state until the entity reports the requested value.
 */

const CARD_TYPE = "kevin-presence-card";
const EDITOR_TYPE = "kevin-presence-card-editor";
const DOMAIN = "mitipi_kevin";
const LAYOUTS = ["compact", "standard", "full"];
const LEGACY_SIZE_TO_LAYOUT = { compact: "compact", standard: "standard", expanded: "full" };
const MODE_PENDING_MS = 60000;
const REBOOT_WINDOW_MS = 150000;
const SAVE_CONFIRM_MS = 20000;
const LEVEL_MIN = 0;
const LEVEL_MAX = 10;

/* ---------------- formatting helpers ---------------- */
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DOW = ["M", "T", "W", "T", "F", "S", "S"];
const DOWL = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmtDate = (d) => `${d.getDate()} ${MON[d.getMonth()]} ${d.getFullYear()}`;
const hm = (h) => {
  const H = Math.floor(h);
  const M = Math.round((h - H) * 60);
  return `${String(H % 24).padStart(2, "0")}:${String(M).padStart(2, "0")}`;
};
const startOfToday = () => {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
};
const daysLeft = (end) => Math.round((end - startOfToday()) / 864e5);
const nowHour = () => {
  const d = new Date();
  return d.getHours() + d.getMinutes() / 60;
};
const todayIndex = () => (new Date().getDay() + 6) % 7;
const parseDate = (v) => {
  if (v === null || v === undefined || v === "") return null;
  if (typeof v === "number") return new Date(v < 1e12 ? v * 1000 : v);
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
};
function relativeAgo(date) {
  if (!date) return "unknown";
  const sec = Math.max(0, (Date.now() - date.getTime()) / 1000);
  if (sec < 90) return "just now";
  const min = Math.round(sec / 60);
  if (min < 60) return `${min} min ago`;
  const h = Math.round(min / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} d ago`;
}
const capitalize = (s) => (s ? String(s).charAt(0).toUpperCase() + String(s).slice(1).toLowerCase() : "");
const isUnavailable = (st) => !st || st.state === "unavailable" || st.state === "unknown";
const CSS_ESCAPE = (s) =>
  globalThis.CSS && globalThis.CSS.escape ? globalThis.CSS.escape(s) : String(s).replace(/"/g, '\\"');

/* ---------------- icons and artwork ---------------- */
const KEVIN_PATH =
  "M5.3 5.5h.2L7.1 17.5H3.8c-1.1 0-1.9-1.1-1.6-2.2l1.6-8.6c.1-.7.7-1.2 1.5-1.2ZM6.6 5.5h12.3c.7 0 1.3.5 1.5 1.2l2.2 8.6c.3 1.1-.5 2.2-1.6 2.2H8.2ZM9.9 15.8h2.8l-1.4-2.9Z";
const kevinGlyph = (a = "") =>
  `<svg ${a} viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" fill-rule="evenodd" d="${KEVIN_PATH}"/></svg>`;
const IC = {
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  power: '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.8 0"/>',
  plug: '<path d="M9 2v6M15 2v6M6 8h12v3a6 6 0 0 1-12 0zM12 17v5"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
};
const ic = (n) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IC[n]}</svg>`;
const pulse = () =>
  '<svg class="pulse" viewBox="0 0 48 16" aria-hidden="true"><path d="M0 8H12L15 3 19 13 22 8H48"/></svg>';

const STARS = [[40, 24, 1.4], [88, 52, 1], [130, 18, 1.2], [176, 40, 1], [220, 16, 1.4], [262, 44, 1], [310, 22, 1.2], [352, 50, 1.4], [372, 14, 1], [24, 74, 1], [150, 78, 1.2], [330, 86, 1]];
const PAL = {
  day: { s1: "#FFE3A0", s2: "#FEF6E1", h1: "#F6DFAE", h2: "#EFCB86", sh: "#D9B26A", w: "#E7C27A" },
  night: { s1: "#0F1E30", s2: "#2B4E69", h1: "#25405A", h2: "#1D3248", sh: "#0B1724", w: "#13263A" },
  off: { s1: "#A3A6A9", s2: "#BABABA", h1: "#B0B3B5", h2: "#A6A9AB", sh: "#8A8D90", w: "#9C9FA2" },
};
function layer(id, m) {
  const P = PAL[m];
  return `<svg class="lay lay-${m}" viewBox="0 0 400 200" preserveAspectRatio="xMidYMax slice" aria-hidden="true"><defs>
    <linearGradient id="${id}${m}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${P.s1}"/><stop offset="1" stop-color="${P.s2}"/></linearGradient>
    ${m === "day" ? `<radialGradient id="${id}g" cx=".14" cy=".08" r=".75"><stop offset="0" stop-color="#FFAD00" stop-opacity=".6"/><stop offset="1" stop-color="#FFAD00" stop-opacity="0"/></radialGradient>` : ""}</defs>
    <rect width="400" height="200" fill="url(#${id}${m})"/>
    ${m === "day" ? `<rect width="400" height="200" fill="url(#${id}g)"/>` : ""}
    ${m === "night" ? STARS.map(([x, y, r]) => `<circle cx="${x}" cy="${y}" r="${r}" fill="#fff" opacity=".85"/>`).join("") : ""}
    <path d="M0 128C60 108 110 118 170 112S300 98 400 120V150H0Z" fill="${P.h1}"/>
    <path d="M0 140C80 126 150 136 230 130S350 124 400 136V150H0Z" fill="${P.h2}"/>
    <rect y="148" width="400" height="52" fill="${P.w}"/><rect y="140" width="400" height="8" fill="${P.sh}"/></svg>`;
}
/* KEVIN device in a 200 x 120 box: grey fabric wedge, white side, triangle logo. */
function deviceArt(id) {
  return `<defs>
    <linearGradient id="${id}f" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#A9AFB2"/><stop offset="1" stop-color="#868C90"/></linearGradient>
    <linearGradient id="${id}w" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#D9DDE0"/></linearGradient>
    <linearGradient id="${id}l" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#E0348A"/><stop offset="1" stop-color="#5C8BC1"/></linearGradient>
    <filter id="${id}t"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" seed="3"/><feColorMatrix values="0 0 0 0 .3 0 0 0 0 .33 0 0 0 0 .35 0 0 0 .35 0"/><feComposite in2="SourceGraphic" operator="in"/></filter></defs>
    <g stroke-linejoin="round" stroke-width="5">
      <path d="M40 18 24 84l34 9-11-75Z" fill="url(#${id}w)" stroke="url(#${id}w)"/>
      <path d="M47 18h110l16 60q2 5-3 8L58 93Z" fill="url(#${id}f)" stroke="url(#${id}f)"/></g>
    <path d="M47 18h110l16 60q2 5-3 8L58 93Z" fill="#000" filter="url(#${id}t)" opacity=".5"/>
    <path d="M67 81l6-12 6 12Z" fill="url(#${id}l)" stroke="url(#${id}l)" stroke-width="3" stroke-linejoin="round"/>`;
}
function foreground(id) {
  return `<svg class="fg" viewBox="0 0 400 200" preserveAspectRatio="xMaxYMax meet" role="img" aria-label="KEVIN on a shelf">
    <ellipse cx="288" cy="142" rx="72" ry="5" fill="#000" opacity=".18"/>
    ${[0, 1, 2].map((i) => `<ellipse class="arc" style="animation-delay:${i * 0.8}s" cx="288" cy="104" rx="62" ry="40"/>`).join("")}
    <g transform="translate(206 66) scale(.82)">${deviceArt(id)}</g></svg>`;
}
function wave(name, playing) {
  let h = 0;
  for (const ch of String(name)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const bars = [];
  for (let i = 0; i < 11; i++) {
    h = (h * 1103515245 + 12345) >>> 0;
    const v = 25 + ((h >> 8) % 75);
    bars.push(`<i style="--h:${v}%;--d:${(i * 0.09).toFixed(2)}s"></i>`);
  }
  return `<span class="wave ${playing ? "playing" : ""}" aria-hidden="true">${bars.join("")}</span>`;
}

/* ---------------- onboarding preferences (Mitipi app) ---------------- */
const ENVS = [
  { id: "HOME", name: "Private home", hint: "House or apartment", tags: [["kids", "Kids"], ["teens", "Teens"], ["dogs", "Dogs"], ["cats", "Cats"]], occ: ["Solo", "Full house"], energy: ["Zen", "Party"] },
  { id: "BUSINESS", name: "Business", hint: "Office or shop", tags: [["customersPresent", "Customers present"], ["callsAndMeetings", "Calls and meetings"], ["deliveryAndLogistics", "Delivery and logistics"], ["petsAllowed", "Pets allowed"]], occ: ["Low occupancy", "High occupancy"], energy: ["Quiet", "Busy"] },
  { id: "INDUSTRIAL", name: "Industrial", hint: "Production facility", tags: [["heavyMachinery", "Heavy machinery"], ["manualWorkstations", "Manual workstations"], ["forkliftTraffic", "Forklift traffic"], ["safetyAlerts", "Safety alerts"]], occ: ["Skeleton crew", "Full shift"], energy: ["Idle", "Peak load"] },
];
const ENV_BY = Object.fromEntries(ENVS.map((e) => [e.id, e]));
const clampLevel = (v) => {
  const n = Math.round(Number(v));
  if (!Number.isFinite(n)) return Math.round((LEVEL_MIN + LEVEL_MAX) / 2);
  return Math.min(LEVEL_MAX, Math.max(LEVEL_MIN, n));
};

/* ---------------- schedule helpers ---------------- */
function nextSlot(sched) {
  const ti = todayIndex();
  const nh = nowHour();
  for (let k = 0; k < 7; k++) {
    const i = (ti + k) % 7;
    for (const [f, t] of sched[i] || []) {
      if (k === 0 && t <= nh) continue;
      if (k === 0 && f <= nh && nh < t) return { k, i, f, t, live: true };
      return { k, i, f, t, live: false };
    }
  }
  return null;
}
const dayName = (k, i) => (k === 0 ? "Today" : k === 1 ? "Tomorrow" : DOWL[i]);
function normalizeWindows(raw) {
  const out = [[], [], [], [], [], [], []];
  if (!Array.isArray(raw)) return out;
  for (let i = 0; i < 7; i++) {
    const day = Array.isArray(raw[i]) ? raw[i] : [];
    out[i] = day
      .filter((w) => Array.isArray(w) && w.length === 2 && Number.isFinite(+w[0]) && Number.isFinite(+w[1]) && +w[1] > +w[0])
      .map(([f, t]) => [Math.max(0, +f), Math.min(24, +t)])
      .sort((a, b) => a[0] - b[0]);
  }
  return out;
}

/* ---------------- subscription ---------------- */
function readSubscription(stateObj) {
  if (!stateObj) return { status: "unknown" };
  const a = stateObj.attributes || {};
  const st = String(stateObj.state || "").toLowerCase();
  if (st === "unavailable" || st === "unknown" || st === "forbidden" || st === "") {
    return { status: "unknown", source: a.source };
  }
  if (st === "none") return null;
  const end = parseDate(a.current_period_end || a.expires_at || a.trial_ends_at);
  let start = parseDate(a.current_period_start);
  if (!start && end) {
    const days = String(a.interval || "").toLowerCase().startsWith("year") ? 365 : 30;
    start = new Date(end.getTime() - days * 864e5);
  }
  const trial = a.is_trial === true || st === "trialing" || st === "trial";
  const expired = st === "expired" || st === "canceled" || st === "cancelled" || st === "ended";
  return {
    plan: capitalize(a.tier || a.plan_code || "Plan"),
    status: trial ? "trial" : expired ? "expired" : "active",
    start,
    end,
  };
}
function subInfo(sub) {
  if (!sub) return { key: "none", pill: ["mute", "No subscription"], endTxt: "", tone: "" };
  if (sub.status === "unknown") {
    return { key: "unknown", pill: ["mute", "Not available"], endTxt: "", tone: "" };
  }
  if (!sub.end) {
    return { key: "active", pill: ["ok", sub.status === "trial" ? "Trial" : "Active"], endLabel: "Ends", endTxt: "—", tone: "", frac: 1, d: null, text: "∞", sm: "no end date" };
  }
  const d = daysLeft(sub.end);
  const total = Math.max(1, Math.round((sub.end - (sub.start || sub.end)) / 864e5));
  if (sub.status === "expired" || d < 0) {
    return { key: "expired", pill: ["err", "Expired"], endLabel: "Ended", endTxt: fmtDate(sub.end), tone: "err", frac: 1, d, text: "Expired", sm: `${Math.abs(d)} d ago` };
  }
  const frac = Math.min(1, Math.max(0, d / total));
  const pill = sub.status === "trial" ? ["warn", "Trial"] : d <= 14 ? ["warn", "Expires soon"] : ["ok", "Active"];
  return {
    key: sub.status === "trial" ? "trial" : d <= 14 ? "soon" : "active",
    pill,
    endLabel: "Ends",
    endTxt: fmtDate(sub.end),
    tone: d <= 14 ? "warn" : "",
    frac,
    d,
    text: String(d),
    sm: d === 1 ? "day left" : "days left",
  };
}

/* ---------------- entity resolution ---------------- */
const DEVICE_ROLES = { switch: "power", binary_sensor: "connectivity", button: "reboot", select: "scene" };
const SENSOR_ROLES = ["mode", "firmware", "activity", "schedule"];
const ACCOUNT_ROLES = { account_subscription: "subscription", preferences: "preferences" };

function resolveEntities(hass, configEntity, registryCache) {
  const out = {};
  const entities = (hass && hass.entities) || {};
  const base = entities[configEntity];
  const deviceId = base && base.device_id;
  const deviceEntities = Object.values(entities).filter(
    (e) => e.platform === DOMAIN && deviceId && e.device_id === deviceId,
  );
  for (const e of deviceEntities) {
    const domain = e.entity_id.split(".")[0];
    if (domain === "sensor") {
      const key = e.translation_key;
      if (SENSOR_ROLES.includes(key)) out[key] = e.entity_id;
      continue;
    }
    const role = DEVICE_ROLES[domain];
    if (role && !out[role]) out[role] = e.entity_id;
  }
  if (!out.power && configEntity && configEntity.startsWith("switch.")) out.power = configEntity;
  /* Account entities have no device. Match them to the same config entry when the
     registry is readable; otherwise use the only candidate. */
  const accountCandidates = Object.values(entities).filter(
    (e) => e.platform === DOMAIN && !e.device_id && ACCOUNT_ROLES[e.translation_key],
  );
  const byEntity = registryCache && registryCache.byEntity;
  const entryId = byEntity ? byEntity[configEntity] : undefined;
  for (const [tk, role] of Object.entries(ACCOUNT_ROLES)) {
    const options = accountCandidates.filter((e) => e.translation_key === tk);
    let pick = null;
    if (entryId) pick = options.find((e) => byEntity[e.entity_id] === entryId) || null;
    if (!pick && options.length) pick = options[0];
    if (pick) out[role] = pick.entity_id;
  }
  out.deviceId = deviceId || null;
  return out;
}

/* ---------------- CSS (ported from the v6 prototype) ---------------- */
const CSS = `
:host{display:block;
  --kv-ok:#0A7A52;--kv-okS:#DDF4EA;--kv-warn:#8A5A00;--kv-warnS:#FFF1D1;--kv-bad:#B3342B;--kv-badS:#FBE4E1;
  --kv-surface:color-mix(in srgb,var(--primary-text-color,#212121) 5%,var(--ha-card-background,var(--card-background-color,#fff)));
  --kv-plus-bg:#E4EDF4;--kv-plus-fg:#2B4E69}
:host([dark]){--kv-ok:#4FD1A1;--kv-okS:#12332A;--kv-warn:#FFC24D;--kv-warnS:#3A2C0B;--kv-bad:#F2877E;--kv-badS:#3A1B19;--kv-plus-bg:#1E3345;--kv-plus-fg:#9CCBF0}
.kv-host{container-type:inline-size;width:100%;position:relative}
.kv{
  --pad:16px;
  background:var(--ha-card-background,var(--card-background-color,#fff));color:var(--primary-text-color);
  font-family:var(--ha-font-family-body,Roboto,system-ui,sans-serif);
  border-radius:var(--ha-card-border-radius,12px);border:var(--ha-card-border-width,1px) solid var(--ha-card-border-color,var(--divider-color));
  box-shadow:var(--ha-card-box-shadow,none);overflow:hidden;position:relative;font-size:14px;line-height:1.4;box-sizing:border-box
}
.kv *{box-sizing:border-box}
:where(.kv) button,:where(.kv) select{font:inherit;color:inherit}
.kv button,.kv .trig,.kv .track{cursor:pointer}
.kv button:disabled{cursor:not-allowed}
.kv :focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}
.kv svg{display:block}

.kv-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:12px var(--pad) 0;cursor:pointer;border-radius:8px}
.kv-head:hover .kv-word{opacity:.85}
.kv-word{display:flex;align-items:center;gap:7px;font-weight:800;font-size:15px;letter-spacing:.01em}
.kv-word svg{width:20px;height:20px;color:var(--secondary-text-color)}
.kv-word .grad{background:linear-gradient(90deg,#E0348A,#5C8BC1);-webkit-background-clip:text;background-clip:text;color:transparent}
.kv-word sup{font-size:.7em;font-weight:700;margin-left:1px;line-height:1;position:relative;top:-.15em;color:#5C8BC1}
.live{display:flex;align-items:center;gap:6px;font-size:13px;font-weight:500;white-space:nowrap}
.live.ok{color:var(--kv-ok)}.live.off{color:var(--secondary-text-color)}.live.warn{color:var(--kv-warn)}
.pulse{width:40px;height:14px;overflow:visible}
.pulse path{fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.live.ok .pulse path{stroke-dasharray:70 40;animation:beat 2.4s linear infinite}
.live.warn .pulse path{stroke-dasharray:70 40;animation:beat .9s linear infinite}
.live.off .pulse path{stroke-dasharray:2 4}
@keyframes beat{from{stroke-dashoffset:110}to{stroke-dashoffset:0}}

.kv-stage{margin:12px var(--pad) 0;position:relative}
.scene{border-radius:var(--feature-border-radius,12px);overflow:hidden;position:relative;height:150px;color:var(--ink);transition:color .6s}
.scene[data-v="on"]{--ink:#2B4E69}
.scene[data-v="standby"]{--ink:#F3F7FB}
.scene[data-v="off"]{--ink:#2E3133}
.lay{position:absolute;inset:0;width:100%;height:100%;opacity:0;transition:opacity .9s ease}
.scene[data-v="on"] .lay-day,.scene[data-v="standby"] .lay-night,.scene[data-v="off"] .lay-off{opacity:1}
.fg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.scene[data-v="off"] .fg{filter:grayscale(1);opacity:.7}
.arc{fill:none;stroke:var(--ink);stroke-width:1.6;opacity:0;transform-box:fill-box;transform-origin:center}
.playing .arc{animation:ripple 2.4s ease-out infinite}
@keyframes ripple{0%{transform:scale(.55);opacity:.55}100%{transform:scale(1.55);opacity:0}}
.scene-txt{position:absolute;left:14px;bottom:12px;max-width:52%;min-width:0}
.kv-name{font-size:19px;font-weight:500;letter-spacing:-.015em;line-height:1.15;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.kv-serial{font-size:12px;font-weight:500;opacity:.85;margin-top:3px;font-variant-numeric:tabular-nums;letter-spacing:.02em}

.strip{position:relative;height:var(--feature-height,42px);border-radius:var(--feature-border-radius,12px);margin:8px 0 0;transition:background .6s,color .6s;display:flex;align-items:center;justify-content:center}
.strip[data-v="on"]{background:linear-gradient(90deg,#FFE3A0,#FEF6E1);color:#2B4E69}
.strip[data-v="standby"]{background:linear-gradient(90deg,#1B2F42,#2B4E69);color:#F3F7FB}
.strip[data-v="off"]{background:#BABABA;color:#2E3133}
.track{position:absolute;inset:0;touch-action:pan-y;user-select:none;-webkit-user-select:none;border-radius:inherit}
.track:focus-visible{outline-offset:-3px}
.track[aria-disabled="true"]{cursor:not-allowed}
.track .ghost{position:absolute;top:50%;transform:translateY(-50%);width:20px;height:20px;opacity:.5}
.track .ghost.l{left:11px}.track .ghost.r{right:11px}
.track .ghost svg{width:20px;height:20px}
.strip .state{position:relative;font-size:13px;font-weight:500;pointer-events:none;display:flex;align-items:center;gap:6px;max-width:calc(100% - 110px);text-align:center}
.state .dots::after{content:'';animation:dots 1.2s steps(4) infinite}
@keyframes dots{0%{content:''}25%{content:'.'}50%{content:'..'}75%{content:'...'}}
.thumb{position:absolute;top:3px;left:3px;width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  box-shadow:0 2px 6px rgba(0,0,0,.28);transition:left .7s cubic-bezier(.3,.9,.3,1),background .6s,color .6s;touch-action:none}
.thumb[data-v="on"]{left:3px;background:#FFAD00;color:#2A2B39}
.thumb[data-v="standby"]{left:calc(100% - 39px);background:#FCFCFF;color:#2B4E69;box-shadow:0 2px 6px rgba(0,0,0,.4),0 0 0 3px rgba(255,255,255,.18)}
.thumb[data-v="off"]{left:3px;background:#8A8D90;color:#fff;box-shadow:none}
.thumb.drag{transition:none}
.thumb svg{width:20px;height:20px}

.kv-body{padding:12px var(--pad) var(--pad);display:grid;grid-template-columns:1fr;gap:12px}
.blk{min-width:0}
.sec-l{font-size:13px;font-weight:500;color:var(--secondary-text-color);margin:0 0 6px}

.sub{display:flex;align-items:center;gap:16px}
.ring{position:relative;flex:0 0 auto;width:80px;height:80px}
.ring svg{width:100%;height:100%;transform:rotate(-90deg)}
.ring .bg{fill:none;stroke:var(--divider-color);stroke-width:8}
.ring .fgc{fill:none;stroke-width:8;stroke-linecap:round;transition:stroke-dashoffset 1s cubic-bezier(.3,.9,.3,1)}
.ring .rmid{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
.ring .big{font-size:22px;font-weight:500;letter-spacing:-.03em;line-height:1;font-variant-numeric:tabular-nums}
.ring .sm{font-size:11px;font-weight:600;color:var(--secondary-text-color);margin-top:3px}
.ring .rmid.err .big,.ring .rmid.err .sm{color:var(--kv-bad)}
.ring .rmid.warn .big{color:var(--kv-warn)}
.subtxt{min-width:0;display:flex;flex-direction:column;gap:6px}
.chips{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.plan{display:inline-flex;align-items:center;border-radius:6px;padding:2px 9px;font-size:12px;font-weight:800;letter-spacing:.03em}
.plan.max{background:linear-gradient(90deg,#B0287A,#5F56C7);color:#fff}
.plan.plus{background:var(--kv-plus-bg);color:var(--kv-plus-fg)}
.plan.none{background:var(--kv-surface);color:var(--secondary-text-color);border:1px solid var(--divider-color)}
.pill{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:2px 9px 2px 7px;font-size:12px;font-weight:700;white-space:nowrap}
.pill i{width:6px;height:6px;border-radius:50%;background:currentColor}
.pill.ok{background:var(--kv-okS);color:var(--kv-ok)}
.pill.warn{background:var(--kv-warnS);color:var(--kv-warn)}
.pill.err{background:var(--kv-badS);color:var(--kv-bad)}
.pill.mute{background:var(--kv-surface);color:var(--secondary-text-color);border:1px solid var(--divider-color)}
.ends{font-size:15px;font-weight:500;letter-spacing:-.01em}
.ends span{font-weight:500;color:var(--secondary-text-color);font-size:13px;margin-right:4px;white-space:nowrap}
.note{font-size:12px;color:var(--secondary-text-color);line-height:1.4}

.wave{flex:0 0 auto;display:flex;align-items:center;gap:2px;height:24px;width:44px}
.wave i{flex:1;min-width:2px;border-radius:2px;background:var(--primary-color);height:var(--h);opacity:.9;transform-origin:center}
.wave.playing i{animation:eq 1s ease-in-out infinite;animation-delay:var(--d)}
@keyframes eq{0%,100%{transform:scaleY(.35)}50%{transform:scaleY(1.15)}}
.spin{width:14px;height:14px;border-radius:50%;border:2px solid currentColor;border-right-color:transparent;animation:rot .7s linear infinite;display:inline-block}
@keyframes rot{to{transform:rotate(360deg)}}

.fbtn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:var(--feature-height,42px);padding:0 16px;border-radius:var(--feature-border-radius,12px);border:1px solid var(--divider-color);background:var(--kv-surface);font-weight:500;font-size:14px;color:var(--primary-text-color);white-space:nowrap}
.fbtn svg{width:18px;height:18px}
.fbtn:hover:not(:disabled){filter:brightness(1.06)}
.fbtn:disabled{opacity:.5}
.dlg-scrim{position:absolute;inset:0;background:rgba(0,0,0,.32);display:flex;align-items:center;justify-content:center;padding:16px;z-index:5}
.dlg-scrim.fixed{position:fixed;z-index:9}
.dlg{background:var(--ha-card-background,var(--card-background-color,#fff));color:var(--primary-text-color);border-radius:28px;padding:24px;max-width:360px;width:100%;box-shadow:0 8px 32px rgba(0,0,0,.4)}
.dlg h3{margin:0 0 8px;font-size:20px;font-weight:500;line-height:1.3}
.dlg p{margin:0 0 18px;font-size:14px;color:var(--secondary-text-color)}
.dlg .acts{display:flex;justify-content:flex-end;gap:4px}
.dlg .acts button{border:0;background:transparent;border-radius:999px;padding:0 16px;height:40px;font-weight:500;font-size:14px;color:var(--primary-color)}
.dlg .acts button.danger{color:var(--kv-bad)}
.dlg .acts button:hover{background:var(--kv-surface)}
.mi{max-width:420px}
.mi dl{display:grid;grid-template-columns:auto 1fr;gap:6px 16px;margin:0 0 18px;font-size:14px}
.mi dt{color:var(--secondary-text-color)}.mi dd{margin:0;font-weight:500;overflow-wrap:anywhere}
.mi .hdr{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.mi .hdr .circ{flex:0 0 auto;width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#FFE3A0;color:#2B4E69}
.mi .hdr .circ svg{width:22px;height:22px}
.mi .hdr h3{margin:0}
.mi .hdr small{display:block;font-weight:400;font-size:12px;color:var(--secondary-text-color)}
.foot{display:flex;align-items:center;justify-content:space-between;gap:10px;border-top:1px solid var(--divider-color);padding-top:10px}
.fw{font-size:13px;color:var(--secondary-text-color);display:flex;flex-direction:column;line-height:1.25}
.fw b{font-size:14px;color:var(--primary-text-color);font-weight:500;font-variant-numeric:tabular-nums}

.np{display:flex;align-items:center;gap:12px;background:var(--kv-surface);border:1px solid var(--divider-color);border-radius:12px;padding:8px 12px}
.np .wave{width:44px;height:28px}
.np .t{flex:1;min-width:0}
.np .nm{font-weight:500;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.np .sub2{font-size:12px;color:var(--secondary-text-color);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.np .since{flex:0 0 auto;font-size:12px;font-weight:600;color:var(--secondary-text-color);font-variant-numeric:tabular-nums}
.np.quiet .wave i{background:var(--secondary-text-color);opacity:.5}
.np.quiet .nm{color:var(--secondary-text-color);font-weight:600}

.sched{display:grid;grid-template-columns:auto 1fr;gap:3px 10px;align-items:center}
.sched .d{font-size:12px;font-weight:600;color:var(--secondary-text-color);width:16px;text-align:center}
.sched .d.today{color:var(--primary-text-color);font-weight:800}
.sched .r{position:relative;height:12px;border-radius:4px;background:var(--kv-surface);border:1px solid var(--divider-color);cursor:pointer;padding:0;display:block;width:100%}
.sched .r:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}
.sched .r.today{border-color:var(--primary-color)}
.sched .r b{position:absolute;top:2px;bottom:2px;border-radius:3px;background:var(--primary-color);opacity:.85}
.sched .r.today b{opacity:1}
.sched .r .now{position:absolute;top:-3px;bottom:-3px;width:2px;background:#FFAD00;border-radius:1px}
.sched .r .ni{position:absolute;top:0;bottom:0;background:repeating-linear-gradient(90deg,transparent 0 3px,var(--divider-color) 3px 4px);opacity:.6;pointer-events:none}
.sched-foot{display:flex;justify-content:space-between;gap:8px;font-size:12px;color:var(--secondary-text-color);margin-top:8px}
.sched-foot b{color:var(--primary-text-color);font-weight:700}
.sched-foot .hrs{font-variant-numeric:tabular-nums}
.sched-detail{font-size:12px;color:var(--primary-text-color);margin-top:6px}
.sched-detail:empty{display:none}

.chipset{display:grid;grid-template-columns:1fr 1fr;gap:8px var(--feature-button-spacing,12px)}
.chipset .pchip:last-child:nth-child(odd){grid-column:1/-1}
.pchip{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:var(--feature-height,42px);padding:0 12px;border-radius:var(--feature-border-radius,12px);white-space:nowrap;overflow:hidden;border:1px solid var(--divider-color);background:var(--kv-surface);font-size:13px;font-weight:500;color:var(--primary-text-color);min-width:0}
.pchip span.l{overflow:hidden;text-overflow:ellipsis}
.pchip i{width:8px;height:8px;border-radius:50%;background:var(--divider-color);flex:0 0 auto}
.pchip[aria-pressed="true"]{background:var(--primary-color);border-color:var(--primary-color);color:var(--text-primary-color)}
.pchip[aria-pressed="true"] i{background:currentColor;opacity:.9}
.pchip:disabled{opacity:.5}
.pref-row{display:flex;align-items:center;gap:10px;min-height:var(--feature-height,42px)}
.pref-t{flex:1;min-width:0}
.pref-sum{font-size:13px;color:var(--primary-text-color);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gear{flex:0 0 auto;width:36px;height:36px;border-radius:50%;border:0;background:var(--kv-surface);color:var(--secondary-text-color);display:flex;align-items:center;justify-content:center;padding:0}
.gear svg{width:20px;height:20px}
.gear:hover:not(:disabled){color:var(--primary-text-color);filter:brightness(1.12)}
.gear[aria-expanded="true"]{background:var(--primary-color);color:var(--text-primary-color)}
.gear:disabled{opacity:.5}
.prefs{display:flex;flex-direction:column;gap:10px;margin-top:10px;padding-top:10px;border-top:1px solid var(--divider-color)}
.trig{position:relative;display:flex;align-items:center;gap:10px;min-height:48px;height:var(--feature-height,42px);padding:0 12px;border:1px solid var(--divider-color);background:var(--kv-surface);border-radius:var(--feature-border-radius,12px);cursor:pointer}
.trig:focus-within{outline:2px solid var(--primary-color);outline-offset:2px}
.trig.dis{opacity:.5;cursor:not-allowed}
.trig select{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer;font-size:16px}
.trig select:disabled{cursor:not-allowed}
.trig .nm{font-weight:500;font-size:14px;white-space:nowrap;flex:0 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis}
.trig .hint2{flex:1;min-width:0;font-size:12px;color:var(--secondary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.trig svg{flex:0 0 auto;width:16px;height:16px;color:var(--secondary-text-color)}
.sl{display:flex;flex-direction:column;gap:2px}
.sl-h{display:flex;justify-content:space-between;font-size:13px;color:var(--primary-text-color)}
.sl-v{color:var(--secondary-text-color);font-variant-numeric:tabular-nums}
.sl-l{display:flex;justify-content:space-between;font-size:11px;color:var(--secondary-text-color)}
.sl input[type=range]{width:100%;height:var(--feature-height,42px);margin:0;appearance:none;-webkit-appearance:none;background:transparent;cursor:pointer}
.sl input[type=range]::-webkit-slider-runnable-track{height:var(--feature-height,42px);border-radius:var(--feature-border-radius,12px);background:linear-gradient(90deg,var(--primary-color) 0 var(--p),var(--kv-surface) var(--p) 100%);border:1px solid var(--divider-color)}
.sl input[type=range]::-webkit-slider-thumb{appearance:none;-webkit-appearance:none;width:4px;height:26px;margin-top:7px;border-radius:2px;background:#fff;box-shadow:0 0 0 1px rgba(0,0,0,.25)}
.sl input[type=range]::-moz-range-track{height:var(--feature-height,42px);border-radius:var(--feature-border-radius,12px);background:var(--kv-surface);border:1px solid var(--divider-color)}
.sl input[type=range]::-moz-range-progress{height:var(--feature-height,42px);border-radius:var(--feature-border-radius,12px);background:var(--primary-color)}
.sl input[type=range]::-moz-range-thumb{width:4px;height:26px;border:0;border-radius:2px;background:#fff}
.sl input[type=range]:disabled{opacity:.5;cursor:not-allowed}
.sl input[type=range]:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}
.saving{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--secondary-text-color);margin-left:8px}
.saving .spin{width:10px;height:10px;border-width:1.5px}

.kv.compact{display:flex;align-items:center;gap:12px;padding:0 12px;height:56px}
.tile-ic{flex:0 0 auto;width:36px;height:36px;border-radius:50%;border:0;display:flex;align-items:center;justify-content:center;padding:0;transition:background .3s,color .3s}
.tile-ic svg{width:22px;height:22px}
.tile-ic.on{background:rgba(255,173,0,.2);color:var(--state-active-color,#FFAD00)}
.tile-ic.standby{background:rgba(75,141,197,.2);color:#4B8DC5}
.tile-ic.off{background:rgba(189,189,189,.2);color:var(--state-unavailable-color,#BDBDBD)}
.tile-ic:hover:not(:disabled){filter:brightness(1.15)}
.tile-ic:disabled{opacity:.6}
.kv.compact .tmid{flex:1;min-width:0;cursor:pointer;border-radius:8px}
.kv.compact .nm{font-weight:500;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kv.compact .st{font-size:12px;color:var(--secondary-text-color);margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kv.compact .st.warn{color:var(--kv-warn);font-weight:500}

.kv.full{--pad:20px}
.kv.full .scene{height:180px}
.kv.full .ring{width:96px;height:96px}
.kv.full .ring .big{font-size:26px}
.kv.full .kv-body{gap:20px}
.kv.full .np{padding:12px 14px}
.kv.full .kv-name{font-size:22px}
.kv.full .foot{align-items:flex-start}

@container (max-width:319px){
  .scene{height:150px}
  .kv-name{font-size:16px}
  .ring{width:76px;height:76px}.ring .big{font-size:21px}
  .sub{gap:12px}
  .foot{flex-direction:column;align-items:stretch}
}
@container (min-width:560px){
  .kv:not(.compact){display:grid;grid-template-columns:minmax(240px,40%) 1fr;grid-template-rows:auto 1fr}
  .kv:not(.compact) .kv-body{grid-template-columns:1fr 1fr;align-content:start;column-gap:20px}
  .kv:not(.compact) .blk.foot{grid-column:1/-1}
  .kv:not(.compact) .blk.now{grid-column:1/-1}
  .kv:not(.compact) .kv-head{grid-column:1/-1}
  .kv:not(.compact) .kv-stage{margin:12px 0 var(--pad) var(--pad);display:flex;flex-direction:column;align-self:start}
  .kv:not(.compact) .scene{height:auto;aspect-ratio:400/230}
  .kv.full:not(.compact) .kv-stage{margin-left:20px;margin-bottom:20px}
  .kv:not(.compact) .kv-body{padding-top:12px}
}
@container (min-width:860px){
  .kv:not(.compact){grid-template-columns:minmax(260px,30%) 1fr}
  .kv:not(.compact) .kv-body{grid-template-columns:minmax(0,1fr) minmax(0,1.1fr) minmax(0,1.2fr)}
  .kv:not(.compact) .chipset{grid-template-columns:1fr}
  .kv:not(.compact) .chipset .pchip{justify-content:flex-start}
  .kv:not(.compact) .chipset .pchip:last-child:nth-child(odd){grid-column:auto}
  .kv:not(.compact) .trig .hint2{display:none}
  .kv:not(.compact) .pref-sum{white-space:normal;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;line-height:1.35}
  .kv:not(.compact) .pref-row{align-items:flex-start}
  .kv:not(.compact) .trig .nm{flex:1}
  .kv:not(.compact) .subtxt{gap:4px}
  .kv:not(.compact) .ends{font-size:14px}
  .kv:not(.compact) .sub{gap:12px}
  .kv:not(.compact) .ring{width:76px;height:76px}
  .kv:not(.compact) .ring .big{font-size:21px}
  .kv:not(.compact) .np{max-width:560px}
}
@media (prefers-reduced-motion:reduce){
  .kv *{animation:none!important;transition:none!important}
}
`;

let uidN = 0;

/* ======================================================================= */
class KevinPresenceCard extends HTMLElement {
  constructor() {
    super();
    this._uid = `k${++uidN}`;
    this._ui = { dialog: null, openDay: null, prefsOpen: false };
    this._busy = null;
    this._draft = null;
    this._saving = false;
    this._prev = {};
    this._sig = "";
    this._registry = null;
    this._drag = null;
    this.attachShadow({ mode: "open" });
    this._bindEvents();
  }

  static getConfigElement() {
    return document.createElement(EDITOR_TYPE);
  }

  static getStubConfig(hass) {
    const entities = (hass && hass.entities) || {};
    const power = Object.values(entities).find(
      (e) => e.platform === DOMAIN && e.entity_id.startsWith("switch."),
    );
    return { entity: power ? power.entity_id : "", layout: "standard" };
  }

  setConfig(config) {
    if (!config || typeof config !== "object") throw new Error("Invalid configuration");
    const layout = config.layout || LEGACY_SIZE_TO_LAYOUT[config.size] || "standard";
    if (!LAYOUTS.includes(layout)) throw new Error(`layout must be one of ${LAYOUTS.join(", ")}`);
    this._config = { ...config, layout };
    this._sig = "";
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this.toggleAttribute("dark", Boolean(hass && hass.themes && hass.themes.darkMode));
    if (!this._registry && hass && hass.callWS && !this._registryLoading) this._loadRegistry();
    this._reconcileBusy();
    this._render();
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    const layout = this._config ? this._config.layout : "standard";
    return layout === "compact" ? 1 : layout === "full" ? 9 : 16;
  }

  getGridOptions() {
    const layout = this._config ? this._config.layout : "standard";
    if (layout === "compact") return { columns: 6, rows: 1, min_columns: 3, max_rows: 1 };
    if (layout === "full") return { columns: "full", min_columns: 12 };
    return { columns: 12, min_columns: 9 };
  }

  connectedCallback() {
    clearInterval(this._tick);
    this._tick = setInterval(() => {
      this._sig = "";
      this._render();
    }, 60000);
    this._sig = "";
    this._render();
  }

  disconnectedCallback() {
    clearInterval(this._tick);
    clearTimeout(this._busyTimer);
    clearTimeout(this._saveTimer);
  }

  async _loadRegistry() {
    this._registryLoading = true;
    try {
      const list = await this._hass.callWS({ type: "config/entity_registry/list" });
      const byEntity = {};
      for (const e of list) if (e.platform === DOMAIN) byEntity[e.entity_id] = e.config_entry_id;
      this._registry = { byEntity };
    } catch (_err) {
      this._registry = { byEntity: null };
    }
    this._sig = "";
    this._render();
  }

  /* ---------------- model ---------------- */
  _model() {
    const hass = this._hass;
    const cfg = this._config;
    if (!hass || !cfg) return null;
    const roles = resolveEntities(hass, cfg.entity, this._registry);
    const st = (role) => (roles[role] ? hass.states[roles[role]] : undefined);
    const power = st("power");
    const conn = st("connectivity");
    const fwS = st("firmware");
    const actS = st("activity");
    const schS = st("schedule");
    const prefS = st("preferences");
    const device = roles.deviceId && hass.devices ? hass.devices[roles.deviceId] : null;

    const serial = (device && device.serial_number) || "";
    const name =
      cfg.name ||
      (device && (device.name_by_user || device.name)) ||
      (power && power.attributes.friendly_name) ||
      "KEVIN";
    const connected = conn ? conn.state === "on" : power ? !isUnavailable(power) : false;
    const lastSeenDate = parseDate(conn && conn.attributes.last_seen);
    const mode = power && power.state === "on" ? "ON" : "STAND_BY";

    let current = null;
    if (actS && !isUnavailable(actS) && actS.state) {
      const since = parseDate(actS.attributes.since);
      current = {
        activity: actS.state,
        group: actS.attributes.group || "",
        sinceMin: since ? Math.max(0, Math.round((Date.now() - since.getTime()) / 60000)) : null,
      };
    }
    const schedules = normalizeWindows(schS && schS.attributes.windows);

    let prefs = null;
    if (prefS && !isUnavailable(prefS) && ENV_BY[prefS.state]) {
      const chars = prefS.attributes.characteristics || {};
      prefs = {
        environment: prefS.state,
        tags: ENV_BY[prefS.state].tags.map((t) => t[0]).filter((k) => chars[k] === true),
        occupancy: clampLevel(prefS.attributes.occupancy_level),
        energy: clampLevel(prefS.attributes.energy_level),
      };
    }
    if (this._draft) prefs = { ...this._draft, tags: [...this._draft.tags] };

    return {
      roles,
      name,
      serial,
      connected,
      lastSeen: relativeAgo(lastSeenDate),
      mode,
      fw: fwS && !isUnavailable(fwS) ? fwS.state : "—",
      sub: readSubscription(st("subscription")),
      current,
      schedules,
      prefs,
      prefsAvailable: Boolean(prefS && !isUnavailable(prefS)),
      missing: !power,
    };
  }

  /* ---------------- busy reconciliation (non-optimistic) ---------------- */
  _reconcileBusy() {
    const b = this._busy;
    if (!b || !this._hass || !this._config) return;
    const roles = resolveEntities(this._hass, this._config.entity, this._registry);
    const power = roles.power ? this._hass.states[roles.power] : null;
    const conn = roles.connectivity ? this._hass.states[roles.connectivity] : null;
    if (b.kind === "waking" || b.kind === "sleeping") {
      const want = b.kind === "waking" ? "on" : "off";
      if (b.sent && power && power.state === want) this._clearBusy();
    } else if (b.kind === "rebooting") {
      const online = conn ? conn.state === "on" : true;
      if (!online) b.sawOffline = true;
      if (b.sawOffline && online) {
        this._clearBusy();
        const m = this._model();
        this._toast(`${m ? m.name : "KEVIN"} is back online`);
      }
    }
  }

  _setBusy(kind, ms) {
    clearTimeout(this._busyTimer);
    this._busy = { kind, since: Date.now(), sawOffline: false, sent: false };
    this._busyTimer = setTimeout(() => {
      const was = this._busy;
      this._busy = null;
      this._sig = "";
      this._render();
      if (was && (was.kind === "waking" || was.kind === "sleeping")) {
        this._toast("KEVIN® has not confirmed the change yet");
      }
    }, ms);
    this._sig = "";
    this._render();
  }

  _clearBusy() {
    clearTimeout(this._busyTimer);
    this._busy = null;
    this._sig = "";
  }

  /* ---------------- render ---------------- */
  _render() {
    if (!this.shadowRoot || !this._config || this._drag) return;
    const m = this._model();
    if (!m) return;
    const sig = JSON.stringify([m, this._ui, this._busy && this._busy.kind, this._saving, this._config]);
    if (sig === this._sig) return;
    this._sig = sig;

    const active = this.shadowRoot.activeElement;
    const focusKey = active && active.dataset ? active.dataset.fk : null;

    this.shadowRoot.innerHTML = `<style>${CSS}</style><div class="kv-host">${this._tpl(m)}</div>`;

    this.shadowRoot.querySelectorAll('input[data-act="slider"]').forEach((r) => {
      r.style.setProperty("--p", `${((r.value - LEVEL_MIN) / (LEVEL_MAX - LEVEL_MIN)) * 100}%`);
    });
    this.shadowRoot.querySelectorAll("[data-anim]").forEach((el) => {
      const k = el.dataset.anim;
      const nv = el.dataset.v;
      const pv = this._prev[k];
      if (pv && pv !== nv) {
        el.dataset.v = pv;
        void el.offsetWidth;
        el.dataset.v = nv;
      }
      this._prev[k] = nv;
    });
    if (focusKey) {
      const el = this.shadowRoot.querySelector(`[data-fk="${CSS_ESCAPE(focusKey)}"]`);
      if (el) el.focus();
    }
  }

  _tpl(m) {
    const id = this._uid;
    const layout = this._config.layout;
    if (m.missing) {
      return `<div class="kv ${layout}" style="padding:16px"><div class="note">Select a KEVIN® power entity in the card settings.</div></div>`;
    }
    const busy = this._busy ? this._busy.kind : null;
    const off = !m.connected;
    const target = busy === "waking" ? "on" : busy === "sleeping" ? "standby" : m.mode === "ON" ? "on" : "standby";
    const vis = off ? "off" : target;
    const sub = subInfo(m.sub);
    const planCls = sub.key === "none" || sub.key === "unknown" ? "none" : (m.sub.plan || "").toLowerCase() === "max" ? "max" : "plus";
    const playing = !off && m.mode === "ON" && !busy && !!m.current;
    const ui = this._ui;

    /* ---- compact: tile anatomy ---- */
    if (layout === "compact") {
      const state =
        busy === "rebooting" ? "Rebooting…" : busy === "waking" ? "Waking up…" : busy === "sleeping" ? "Going to sleep…"
          : off ? `Unavailable · ${esc(m.lastSeen)}`
            : m.mode === "ON" ? (m.current ? `On · ${esc(m.current.activity)}` : "On") : "Standby";
      const warn = !off && (sub.key === "soon" || sub.key === "expired");
      const dlg = ui.dialog === "info" ? this._moreInfo(m, true) : "";
      return `<div class="kv compact">${dlg}
        <button class="tile-ic ${vis}" data-act="toggle" data-fk="toggle" aria-label="${vis === "on" ? "Put on standby" : "Wake up"}" ${off || busy ? "disabled" : ""}>${kevinGlyph()}</button>
        <div class="tmid" data-act="info" data-fk="info" role="button" tabindex="0" aria-label="More info for ${esc(m.name)}"><div class="nm">${esc(m.name)}</div><div class="st ${warn ? "warn" : ""}">${warn ? (sub.key === "expired" ? "Subscription expired" : `Subscription ends in ${sub.d} d`) : state}</div></div>
        ${busy ? '<span class="spin" style="color:var(--secondary-text-color)"></span>' : ""}
      </div>`;
    }

    /* ---- header ---- */
    const live = busy === "rebooting"
      ? `<span class="live warn">${pulse()}Rebooting</span>`
      : off ? `<span class="live off">${pulse()}Unavailable</span>` : `<span class="live ok">${pulse()}Online</span>`;

    /* ---- strip ---- */
    const stateTxt = busy === "waking" ? 'Waking up<span class="dots"></span>' : busy === "sleeping" ? 'Going to sleep<span class="dots"></span>'
      : busy === "rebooting" ? 'Rebooting<span class="dots"></span>' : off ? `Unavailable, last seen ${esc(m.lastSeen)}`
        : vis === "on" ? "On" : "Standby";
    const dis = off || busy;
    const thumbIcon = vis === "on" ? ic("sun") : vis === "standby" ? ic("moon") : ic("plug");

    /* ---- subscription ring ---- */
    const R = 36;
    const C = 2 * Math.PI * R;
    let ring;
    if (sub.key === "none" || sub.key === "unknown") {
      const label = sub.key === "none" ? "Basic" : "—";
      ring = `<div class="ring"><svg viewBox="0 0 88 88" aria-hidden="true"><circle class="bg" cx="44" cy="44" r="${R}" stroke-dasharray="3 7"/></svg><div class="rmid"><span class="big" style="font-size:18px">${label}</span></div></div>`;
    } else {
      const stroke = sub.tone === "err" ? "var(--kv-bad)" : sub.tone === "warn" ? "#FFAD00" : `url(#${id}r)`;
      const off2 = C * (1 - sub.frac);
      ring = `<div class="ring" role="img" aria-label="${sub.key === "expired" ? "Subscription expired" : sub.d === null ? "Subscription active" : `${sub.d} days left`}"><svg viewBox="0 0 88 88" aria-hidden="true"><defs><linearGradient id="${id}r" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#E0348A"/><stop offset="1" stop-color="#5C8BC1"/></linearGradient></defs>
        <circle class="bg" cx="44" cy="44" r="${R}"/>
        <circle class="fgc" cx="44" cy="44" r="${R}" stroke="${stroke}" stroke-dasharray="${C.toFixed(1)}" stroke-dashoffset="${off2.toFixed(1)}"/></svg>
        <div class="rmid ${sub.tone}"><span class="big" ${sub.key === "expired" ? 'style="font-size:15px"' : ""}>${sub.text}</span><span class="sm">${sub.sm}</span></div></div>`;
    }
    let subTxt;
    if (sub.key === "none") {
      subTxt = '<div class="chips"><span class="plan none">Basic</span><span class="pill mute"><i></i>No subscription</span></div><div class="note">Adaptive Presence and the Protection report need Plus or Max.</div>';
    } else if (sub.key === "unknown") {
      subTxt = '<div class="chips"><span class="plan none">Plan</span><span class="pill mute"><i></i>Not available</span></div><div class="note">Subscription details can\'t be read right now. KEVIN® keeps working.</div>';
    } else {
      subTxt = `<div class="chips"><span class="plan ${planCls}">${esc(m.sub.plan)}</span><span class="pill ${sub.pill[0]}"><i></i>${sub.pill[1]}</span></div><div class="ends"><span>${sub.endLabel}</span>${sub.endTxt}</div>`;
    }

    /* ---- now playing ---- */
    const cur = !off && m.mode === "ON" && !busy ? m.current : null;
    let np;
    if (cur) {
      const src = sub.key === "none" || sub.key === "expired" ? "Basic Presence" : "Adaptive Presence";
      const sub2 = [cur.group, src].filter(Boolean).map(esc).join(" · ");
      np = `<div class="np">${wave(cur.activity, true)}<div class="t"><div class="nm">${esc(cur.activity)}</div><div class="sub2">${sub2}</div></div>${cur.sinceMin !== null ? `<div class="since">${cur.sinceMin} min</div>` : ""}</div>`;
    } else {
      const nx = nextSlot(m.schedules);
      const why = off ? "Offline" : busy ? "Changing mode" : "Quiet";
      const when = off ? `Last seen ${esc(m.lastSeen)}`
        : nx ? `Presence ${nx.live ? `runs until ${hm(nx.t)}` : `starts ${dayName(nx.k, nx.i).toLowerCase()} at ${hm(nx.f)}`}` : "No Presence scheduled";
      np = `<div class="np quiet">${wave("quiet", false)}<div class="t"><div class="nm">${why}</div><div class="sub2">${when}</div></div></div>`;
    }
    const nowBlock = `<div class="blk now"><p class="sec-l">Now playing</p>${np}</div>`;

    /* ---- schedule ---- */
    const TI = todayIndex();
    const NH = nowHour();
    const rows = DOW.map((d, i) => {
      const slots = m.schedules[i] || [];
      const today = i === TI;
      const bars = slots.map(([f, t]) => `<b style="left:${((f / 24) * 100).toFixed(1)}%;width:${(((t - f) / 24) * 100).toFixed(1)}%" title="${hm(f)}–${hm(t)}"></b>`).join("");
      const night = `<span class="ni" style="left:0;width:${((7.5 / 24) * 100).toFixed(1)}%"></span><span class="ni" style="left:${((21.5 / 24) * 100).toFixed(1)}%;width:${((2.5 / 24) * 100).toFixed(1)}%"></span>`;
      const nowLine = today ? `<span class="now" style="left:${((NH / 24) * 100).toFixed(1)}%"></span>` : "";
      return `<span class="d ${today ? "today" : ""}" aria-hidden="true">${d}</span><button class="r ${today ? "today" : ""}" data-act="day" data-i="${i}" data-fk="day${i}" aria-label="${DOWL[i]}: ${slots.length ? slots.map(([f, t]) => `${hm(f)} to ${hm(t)}`).join(", ") : "no Presence"}" aria-expanded="${ui.openDay === i}">${night}${bars}${nowLine}</button>`;
    }).join("");
    const total = m.schedules.reduce((a, day) => a + day.reduce((b, [f, t]) => b + (t - f), 0), 0);
    const od = ui.openDay;
    const detail = od === null || od === undefined ? ""
      : `<b>${DOWL[od]}</b>: ${(m.schedules[od] || []).length ? m.schedules[od].map(([f, t]) => `${hm(f)}–${hm(t)}`).join(", ") : "no Presence"}`;
    const schedBlock = `<div class="blk"><p class="sec-l">Schedule</p><div class="sched">${rows}</div>
      <div class="sched-detail" aria-live="polite">${detail}</div>
      <div class="sched-foot"><span class="hrs"><b>${total.toFixed(total % 1 ? 1 : 0)} h</b> of Presence a week</span></div></div>`;

    /* ---- preferences ---- */
    let prefBlock;
    if (m.prefs) {
      const env = ENV_BY[m.prefs.environment];
      const pdis = off || busy;
      const envSel = `<label class="trig ${pdis ? "dis" : ""}"><span class="nm">${esc(env.name)}</span><span class="hint2">${esc(env.hint)}</span>${ic("down")}
        <select data-act="env" data-fk="env" aria-label="Where KEVIN lives" ${pdis ? "disabled" : ""}>${ENVS.map((e) => `<option value="${e.id}" ${e.id === env.id ? "selected" : ""}>${esc(e.name)}</option>`).join("")}</select></label>`;
      const tagBtns = env.tags.map(([k, label]) => {
        const on = m.prefs.tags.includes(k);
        return `<button class="pchip" data-act="tag" data-k="${k}" data-fk="tag-${k}" aria-pressed="${on}" ${pdis ? "disabled" : ""}><i></i><span class="l">${esc(label)}</span></button>`;
      }).join("");
      const slider = (key, label, [lo, hi]) => `<div class="sl"><div class="sl-h"><span>${label}</span><span class="sl-v">${m.prefs[key]} of ${LEVEL_MAX}</span></div>
        <input type="range" min="${LEVEL_MIN}" max="${LEVEL_MAX}" step="1" value="${m.prefs[key]}" data-act="slider" data-k="${key}" data-fk="sl-${key}" aria-label="${label}" ${pdis ? "disabled" : ""}>
        <div class="sl-l"><span>${esc(lo)}</span><span>${esc(hi)}</span></div></div>`;
      const saving = this._saving ? '<span class="saving"><span class="spin"></span>Saving</span>' : "";
      const tagNames = m.prefs.tags.map((k) => (env.tags.find((t) => t[0] === k) || [k, k])[1]);
      const summary = `${esc(env.name)}${tagNames.length ? ` · ${esc(tagNames.join(", "))}` : ""} · Occupancy ${m.prefs.occupancy} · Energy ${m.prefs.energy}`;
      const editor = ui.prefsOpen ? `<div class="prefs" id="${id}pe">${envSel}<div class="chipset">${tagBtns}</div>${slider("occupancy", "Occupancy", env.occ)}${slider("energy", "Energy", env.energy)}</div>` : "";
      prefBlock = `<div class="blk">
        <div class="pref-row ${ui.prefsOpen ? "open" : ""}">
          <div class="pref-t"><p class="sec-l" style="margin:0">Preferences ${saving}</p><div class="pref-sum" ${ui.prefsOpen ? "hidden" : ""}>${summary}</div></div>
          <button class="gear" data-act="prefs" data-fk="prefs" aria-expanded="${!!ui.prefsOpen}" aria-controls="${id}pe" aria-label="${ui.prefsOpen ? "Close preferences" : "Edit preferences"}" ${(off || busy) && !ui.prefsOpen ? "disabled" : ""}>${ui.prefsOpen ? ic("x") : ic("gear")}</button>
        </div>${editor}</div>`;
    } else {
      prefBlock = `<div class="blk"><div class="pref-row"><div class="pref-t"><p class="sec-l" style="margin:0">Preferences</p><div class="pref-sum">${m.prefsAvailable ? "Not set up yet. Finish onboarding in the Mitipi app." : "Not available right now"}</div></div>
        <button class="gear" aria-label="Edit preferences" disabled>${ic("gear")}</button></div></div>`;
    }

    /* ---- footer ---- */
    const foot = `<div class="blk foot"><div class="fw"><span>Firmware</span><b>${m.fw === "—" ? "—" : `v${esc(m.fw)}`}</b></div><button class="fbtn" data-act="reboot" data-fk="reboot" ${dis || !m.roles.reboot ? "disabled" : ""}>${ic("power")}Reboot</button></div>`;

    const dlg = ui.dialog === "reboot"
      ? `<div class="dlg-scrim" data-act="cancel"><div class="dlg" role="alertdialog" aria-modal="true" aria-labelledby="${id}dt" data-stop><h3 id="${id}dt">Reboot ${esc(m.name)}?</h3><p>KEVIN® goes offline for about a minute, then returns to its current mode.</p><div class="acts"><button data-act="cancel" data-fk="dlg-cancel">Cancel</button><button class="danger" data-act="reboot-yes" data-fk="dlg-reboot">Reboot</button></div></div></div>`
      : ui.dialog === "info" ? this._moreInfo(m, false) : "";

    return `<div class="kv ${layout} ${playing ? "playing" : ""}">
      ${dlg}
      <div class="kv-head" data-act="info" data-fk="info" role="button" tabindex="0" aria-label="More info for ${esc(m.name)}"><div class="kv-word">${kevinGlyph()}<span class="grad">KEVIN</span><sup>®</sup></div>${live}</div>
      <div class="kv-stage ${playing ? "playing" : ""}">
        <div class="scene" data-anim="scene" data-v="${vis}">${layer(id, "day")}${layer(id, "night")}${layer(id, "off")}${foreground(id)}
          <div class="scene-txt"><div class="kv-name">${esc(m.name)}</div><div class="kv-serial">${esc(m.serial)}</div></div></div>
        <div class="strip" data-anim="strip" data-v="${vis}">
          <div class="track" role="switch" tabindex="${dis ? -1 : 0}" aria-checked="${vis === "on"}" aria-disabled="${dis ? "true" : "false"}" aria-label="Awake. Drag, tap or use the arrow keys" data-track data-fk="track">
            <span class="ghost l">${ic("sun")}</span><span class="ghost r">${ic("moon")}</span>
            <span class="thumb" data-anim="thumb" data-v="${vis}">${thumbIcon}</span></div>
          <span class="state" aria-live="polite">${stateTxt}</span>
        </div>
      </div>
      <div class="kv-body">
        ${nowBlock}
        <div class="blk"><p class="sec-l">Subscription</p><div class="sub">${ring}<div class="subtxt">${subTxt}</div></div></div>
        ${schedBlock}
        ${prefBlock}
        ${foot}
      </div></div>`;
  }

  _moreInfo(m, fixed) {
    const id = this._uid;
    const sub = subInfo(m.sub);
    const hrs = m.schedules.reduce((a, d) => a + d.reduce((b, [f, t]) => b + (t - f), 0), 0);
    let subTxt;
    if (sub.key === "none") subTxt = "Basic";
    else if (sub.key === "unknown") subTxt = "Not available";
    else subTxt = `${esc(m.sub.plan)} · ${sub.pill[1]}${sub.endTxt ? ` · ${sub.endLabel || "Ends"} ${sub.endTxt}` : ""}`;
    let lives = "Not available";
    if (m.prefs) {
      const env = ENV_BY[m.prefs.environment];
      lives = `${esc(env.name)}${m.prefs.tags.length ? ` · ${m.prefs.tags.map((k) => esc((env.tags.find((t) => t[0] === k) || [k, k])[1])).join(", ")}` : ""}`;
    }
    return `<div class="dlg-scrim ${fixed ? "fixed" : ""}" data-act="cancel"><div class="dlg mi" role="dialog" aria-modal="true" aria-labelledby="${id}mt" data-stop>
      <div class="hdr"><span class="circ">${kevinGlyph()}</span><h3 id="${id}mt">${esc(m.name)}<small>${esc(m.serial)}</small></h3></div>
      <dl>
        <dt>State</dt><dd>${!m.connected ? "Unavailable" : m.mode === "ON" ? "On" : "Standby"}</dd>
        <dt>Firmware</dt><dd>${m.fw === "—" ? "—" : `v${esc(m.fw)}`}</dd>
        <dt>Subscription</dt><dd>${subTxt}</dd>
        <dt>Now playing</dt><dd>${m.current && m.connected && m.mode === "ON" ? esc(m.current.activity) : "Nothing"}</dd>
        <dt>Schedule</dt><dd>${hrs ? `${hrs.toFixed(hrs % 1 ? 1 : 0)} h a week` : "None"}</dd>
        <dt>Lives in</dt><dd>${lives}</dd>
        <dt>Occupancy</dt><dd>${m.prefs ? `${m.prefs.occupancy} of ${LEVEL_MAX}` : "—"}</dd>
        <dt>Energy</dt><dd>${m.prefs ? `${m.prefs.energy} of ${LEVEL_MAX}` : "—"}</dd>
      </dl>
      <div class="acts"><button data-act="cancel" data-fk="dlg-close">Close</button></div></div></div>`;
  }

  /* ---------------- actions ---------------- */
  _toast(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
  }

  async _setMode(target) {
    const m = this._model();
    if (!m || this._busy || !m.connected || m.mode === target || !m.roles.power) return;
    this._setBusy(target === "ON" ? "waking" : "sleeping", MODE_PENDING_MS);
    try {
      await this._hass.callService("switch", target === "ON" ? "turn_on" : "turn_off", { entity_id: m.roles.power });
      if (this._busy) this._busy.sent = true;
      this._reconcileBusy();
      this._sig = "";
      this._render();
    } catch (err) {
      this._clearBusy();
      this._render();
      this._toast(`Could not change mode: ${err && err.message ? err.message : "request failed"}`);
    }
  }

  async _reboot() {
    const m = this._model();
    if (!m || this._busy || !m.connected || !m.roles.reboot) return;
    this._setBusy("rebooting", REBOOT_WINDOW_MS);
    try {
      await this._hass.callService("button", "press", { entity_id: m.roles.reboot });
    } catch (err) {
      this._clearBusy();
      this._render();
      this._toast(`Could not reboot: ${err && err.message ? err.message : "request failed"}`);
    }
  }

  _savePrefs(next) {
    const m = this._model();
    if (!m || !m.roles.preferences) return;
    this._draft = { ...next, tags: [...next.tags] };
    this._saving = true;
    this._sig = "";
    this._render();
    clearTimeout(this._saveTimer);
    this._saveTimer = setTimeout(() => this._sendPrefs(m.roles.preferences), 450);
  }

  async _sendPrefs(entityId) {
    const d = this._draft;
    if (!d) return;
    const env = ENV_BY[d.environment];
    const characteristics = Object.fromEntries(env.tags.map(([k]) => [k, d.tags.includes(k)]));
    let failed = false;
    try {
      await this._hass.callService(DOMAIN, "set_preferences", {
        entity_id: entityId,
        environment: d.environment,
        characteristics,
        occupancy_level: d.occupancy,
        energy_level: d.energy,
      });
    } catch (err) {
      failed = true;
      this._toast(`Could not save preferences: ${err && err.message ? err.message : "request failed"}`);
    }
    const started = Date.now();
    const settle = () => {
      if (this._draft !== d) return;
      const st = this._hass && this._hass.states[entityId];
      const a = (st && st.attributes) || {};
      const chars = a.characteristics || {};
      const reported = Boolean(st) && st.state === d.environment
        && clampLevel(a.occupancy_level) === d.occupancy && clampLevel(a.energy_level) === d.energy
        && env.tags.every(([k]) => Boolean(chars[k]) === d.tags.includes(k));
      if (failed || reported || Date.now() - started > SAVE_CONFIRM_MS) {
        this._draft = null;
        this._saving = false;
        this._sig = "";
        this._render();
        if (reported) this._toast("Preferences saved");
        return;
      }
      this._saveTimer = setTimeout(settle, 1000);
    };
    settle();
  }

  /* ---------------- events ---------------- */
  _bindEvents() {
    const root = this.shadowRoot;
    root.addEventListener("click", (e) => {
      const b = e.target.closest("[data-act]");
      if (!b) return;
      const a = b.dataset.act;
      const m = this._model();
      if (!m) return;
      if (a === "toggle") this._setMode(m.mode === "ON" ? "STAND_BY" : "ON");
      else if (a === "info") this._openDialog("info", '[data-fk="dlg-close"]');
      else if (a === "reboot") this._openDialog("reboot", '[data-fk="dlg-reboot"]');
      else if (a === "cancel") {
        if (e.target.closest("[data-stop]") && !e.target.closest('[data-act="cancel"]')) return;
        this._ui = { ...this._ui, dialog: null };
        this._render();
      } else if (a === "reboot-yes") {
        this._ui = { ...this._ui, dialog: null };
        this._reboot();
      } else if (a === "day") {
        const i = +b.dataset.i;
        this._ui = { ...this._ui, openDay: this._ui.openDay === i ? null : i };
        this._render();
      } else if (a === "prefs") {
        this._ui = { ...this._ui, prefsOpen: !this._ui.prefsOpen };
        this._render();
      } else if (a === "tag" && m.prefs) {
        const k = b.dataset.k;
        const on = m.prefs.tags.includes(k);
        this._savePrefs({ ...m.prefs, tags: on ? m.prefs.tags.filter((x) => x !== k) : [...m.prefs.tags, k] });
      }
    });
    root.addEventListener("change", (e) => {
      const m = this._model();
      if (!m || !m.prefs) return;
      const sel = e.target.closest('select[data-act="env"]');
      if (sel) {
        if (sel.value !== m.prefs.environment) this._savePrefs({ ...m.prefs, environment: sel.value, tags: [] });
        return;
      }
      const r = e.target.closest('input[data-act="slider"]');
      if (r) this._savePrefs({ ...m.prefs, [r.dataset.k]: clampLevel(r.value) });
    });
    root.addEventListener("input", (e) => {
      const r = e.target.closest('input[data-act="slider"]');
      if (!r) return;
      r.style.setProperty("--p", `${((r.value - LEVEL_MIN) / (LEVEL_MAX - LEVEL_MIN)) * 100}%`);
      const v = r.closest(".sl").querySelector(".sl-v");
      if (v) v.textContent = `${r.value} of ${LEVEL_MAX}`;
    });
    root.addEventListener("pointerdown", (e) => {
      const tr = e.target.closest("[data-track]");
      if (!tr || tr.getAttribute("aria-disabled") === "true") return;
      const th = tr.querySelector(".thumb");
      try {
        tr.setPointerCapture(e.pointerId);
      } catch (_err) {
        /* pointer capture is optional */
      }
      this._drag = { tr, th, x0: e.clientX, moved: false, rect: tr.getBoundingClientRect(), pos: 3 };
    });
    root.addEventListener("pointermove", (e) => {
      const d = this._drag;
      if (!d) return;
      if (Math.abs(e.clientX - d.x0) > 5) d.moved = true;
      if (d.moved) {
        d.th.classList.add("drag");
        const x = Math.min(d.rect.width - 39, Math.max(3, e.clientX - d.rect.left - 18));
        d.th.style.left = `${x}px`;
        d.pos = x;
      }
    });
    const endDrag = (cancel) => {
      const d = this._drag;
      if (!d) return;
      this._drag = null;
      d.th.classList.remove("drag");
      d.th.style.left = "";
      if (cancel) return;
      const m = this._model();
      if (!m) return;
      const target = d.moved ? (d.pos + 18 > d.rect.width / 2 ? "STAND_BY" : "ON") : m.mode === "ON" ? "STAND_BY" : "ON";
      this._sig = "";
      if (target === m.mode) this._render();
      else this._setMode(target);
    };
    root.addEventListener("pointerup", () => endDrag(false));
    root.addEventListener("pointercancel", () => endDrag(true));
    root.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this._ui.dialog) {
        this._ui = { ...this._ui, dialog: null };
        this._render();
        return;
      }
      const hd = e.target.closest && e.target.closest('[data-act="info"]');
      if (hd && (e.key === "Enter" || e.key === " ")) {
        e.preventDefault();
        hd.click();
        return;
      }
      const tr = e.target.closest && e.target.closest("[data-track]");
      if (!tr || tr.getAttribute("aria-disabled") === "true") return;
      const m = this._model();
      if (!m) return;
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        this._setMode("ON");
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        this._setMode("STAND_BY");
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        this._setMode(m.mode === "ON" ? "STAND_BY" : "ON");
      }
    });
  }

  _openDialog(kind, focusSel) {
    this._ui = { ...this._ui, dialog: kind };
    this._render();
    const f = this.shadowRoot.querySelector(focusSel);
    if (f) f.focus();
  }
}

/* ======================================================================= */
class KevinPresenceCardEditor extends HTMLElement {
  setConfig(config) {
    const layout = config.layout || LEGACY_SIZE_TO_LAYOUT[config.size] || "standard";
    this._config = { ...config, layout };
    this._renderEditor();
  }

  set hass(hass) {
    this._hass = hass;
    this._renderEditor();
  }

  _schema() {
    return [
      { name: "entity", required: true, selector: { entity: { integration: DOMAIN, domain: "switch" } } },
      {
        name: "layout",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "compact", label: "Compact tile (6 × 1)" },
              { value: "standard", label: "Standard (12 columns)" },
              { value: "full", label: "Full width" },
            ],
          },
        },
      },
      { name: "name", selector: { text: {} } },
    ];
  }

  _renderEditor() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) =>
        ({ entity: "KEVIN® device (power entity)", layout: "Layout", name: "Name (optional)" })[s.name] || s.name;
      this._form.addEventListener("value-changed", (ev) => {
        const value = { ...ev.detail.value };
        delete value.size;
        delete value.theme;
        if (!value.name) delete value.name;
        this._config = { ...this._config, ...value };
        if (!value.name) delete this._config.name;
        delete this._config.size;
        delete this._config.theme;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = this._schema();
    this._form.data = this._config;
  }
}

/* ---------------- registration ---------------- */
if (globalThis.customElements && !globalThis.customElements.get(CARD_TYPE)) {
  globalThis.customElements.define(CARD_TYPE, KevinPresenceCard);
}
if (globalThis.customElements && !globalThis.customElements.get(EDITOR_TYPE)) {
  globalThis.customElements.define(EDITOR_TYPE, KevinPresenceCardEditor);
}
const lovelaceGlobal = globalThis;
lovelaceGlobal.customCards = lovelaceGlobal.customCards || [];
if (!lovelaceGlobal.customCards.some((entry) => entry.type === CARD_TYPE)) {
  lovelaceGlobal.customCards.push({
    type: CARD_TYPE,
    name: "KEVIN® Presence",
    description: "KEVIN® presence simulator: day-night switch, now playing, subscription, schedule and preferences.",
    preview: true,
    documentationURL: "https://github.com/vasyl127/mitipi-kevin-ha",
  });
}

export { KevinPresenceCard, KevinPresenceCardEditor, resolveEntities, readSubscription, subInfo, normalizeWindows };

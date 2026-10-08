/* Kevin Presence Lovelace card (bundled with mitipi_kevin integration). */

const CARD_TYPE = "kevin-presence-card";
const ROLES = ["power", "mode", "connectivity", "firmware", "subscription", "scene", "reboot"];
const THEMES = ["ambient", "minimal", "contrast"];
const SIZES = ["compact", "standard", "expanded"];
const ENV_ORDER = ["HOME", "BUSINESS", "INDUSTRIAL", "Other"];
const POWER_PENDING_MS = 60000;
const REBOOT_COOLDOWN_MS = 60000;

const resolverCache = new WeakMap();

function normalizeSearch(text) {
  return String(text || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

class KevinEntityResolver {
  constructor(hass) {
    this.hass = hass;
    this._cache = null;
    this._cacheKey = "";
  }

  async _loadRegistry() {
    const [entities, devices] = await Promise.all([
      this.hass.callWS({ type: "config/entity_registry/list" }),
      this.hass.callWS({ type: "config/device_registry/list" }),
    ]);
    return { entities, devices };
  }

  async resolve(switchEntityId) {
    const key = `${switchEntityId}:${this.hass.connection?.subscribed ? "live" : "static"}`;
    if (this._cache && this._cacheKey === key) return this._cache;
    const reg = await this._loadRegistry();
    const switchEntry = reg.entities.find((e) => e.entity_id === switchEntityId);
    if (!switchEntry?.device_id) {
      this._cache = { error: "Power switch is not linked to a device." };
      this._cacheKey = key;
      return this._cache;
    }
    const deviceId = switchEntry.device_id;
    const siblings = reg.entities.filter(
      (e) => e.device_id === deviceId && e.platform === "mitipi_kevin"
    );
    const byRole = {};
    const ambiguous = new Set();
    for (const role of ROLES) {
      const matches = siblings.filter((e) => e.unique_id?.endsWith(`_${role}`));
      if (matches.length === 1) byRole[role] = matches[0].entity_id;
      else if (matches.length > 1) ambiguous.add(role);
    }
    const device = reg.devices.find((d) => d.id === deviceId);
    this._cache = { deviceId, device, byRole, ambiguous, switchEntityId };
    this._cacheKey = key;
    return this._cache;
  }

  invalidate() {
    this._cache = null;
    this._cacheKey = "";
  }
}

function getResolver(hass) {
  let map = resolverCache.get(hass);
  if (!map) {
    map = new KevinEntityResolver(hass);
    resolverCache.set(hass, map);
  }
  return map;
}

class KevinPresenceCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("kevin-presence-card-editor");
  }

  static getStubConfig(hass) {
    const sw = Object.keys(hass.states).find(
      (id) => id.startsWith("switch.") && id.includes("mitipi_kevin") && id.endsWith("_power")
    );
    return {
      type: `custom:${CARD_TYPE}`,
      entity: sw || "",
      theme: "ambient",
      size: "standard",
    };
  }

  static get version() {
    return "0.2.0";
  }

  setConfig(config) {
    if (!config || typeof config !== "object") throw new Error("Invalid configuration object");
    if (!config.entity || typeof config.entity !== "string") {
      throw new Error("Missing required config key: entity (Kevin power switch entity_id)");
    }
    if (!config.entity.startsWith("switch.")) {
      throw new Error("entity must be a switch.* entity_id for the Kevin power switch");
    }
    const theme = config.theme || "ambient";
    if (!THEMES.includes(theme)) {
      throw new Error(`theme must be one of: ${THEMES.join(", ")}`);
    }
    const size = config.size || "standard";
    if (!SIZES.includes(size)) {
      throw new Error(`size must be one of: ${SIZES.join(", ")}`);
    }
    this._config = { entity: config.entity, theme, size };
    if (!this._built) this._buildDom();
    this._applyThemeSize();
  }

  getCardSize() {
    const size = this._config?.size || "standard";
    if (size === "compact") return 2;
    if (size === "expanded") return 8;
    return 5;
  }

  set hass(hass) {
    const prev = this._hass;
    this._hass = hass;
    if (!this._built) this._buildDom();
    if (prev !== hass) getResolver(hass).invalidate();
    this._scheduleRender();
  }

  connectedCallback() {
    if (!this._built) this._buildDom();
  }

  disconnectedCallback() {
    if (this._raf) cancelAnimationFrame(this._raf);
    if (this._powerTimer) clearTimeout(this._powerTimer);
  }

  _buildDom() {
    this._built = true;
    this.attachShadow({ mode: "open" });
    this._styleEl = document.createElement("style");
    this._styleEl.textContent = this._css();
    this.shadowRoot.append(this._styleEl);
    this._root = document.createElement("article");
    this._root.className = "card";
    this._root.setAttribute("role", "region");
    this.shadowRoot.append(this._root);
    this._powerFsm = { phase: "idle", target: null, since: 0 };
    this._rebootBlockedUntil = 0;
    this._lastViewKey = "";
    this._sceneDraft = null;
    this._sceneDialogOpen = false;
    this._nodes = {};
    const ids = [
      "title",
      "status",
      "connectivity",
      "beacon",
      "powerBtn",
      "powerLabel",
      "pendingArc",
      "sceneField",
      "sceneBtn",
      "firmware",
      "serial",
      "subscription",
      "subInfo",
      "rebootBtn",
      "note",
    ];
    for (const id of ids) {
      const el =
        id === "powerBtn" || id === "sceneBtn" || id === "rebootBtn"
          ? document.createElement("button")
          : id === "status"
            ? document.createElement("div")
            : document.createElement("span");
      if (id === "status") {
        el.setAttribute("aria-live", "polite");
        el.className = "status-line";
      }
      if (id.endsWith("Btn")) {
        el.type = "button";
        el.className = "btn";
      }
      this._nodes[id] = el;
    }
    this._nodes.beacon.append(this._nodes.pendingArc);
    [
      "title",
      "connectivity",
      "beacon",
      "status",
      "powerLabel",
      "powerBtn",
      "sceneField",
      "sceneBtn",
      "firmware",
      "serial",
      "subscription",
      "subInfo",
      "rebootBtn",
      "note",
    ].forEach((id) => this._root.append(this._nodes[id]));
    this._nodes.powerBtn.addEventListener("click", () => this._onPowerClick());
    this._nodes.sceneBtn.addEventListener("click", () => this._openSceneDialog());
    this._nodes.rebootBtn.addEventListener("click", () => this._onRebootClick());
    this._dialog = null;
  }

  _css() {
    return `
      :host { display: block; }
      .card {
        box-sizing: border-box;
        padding: 12px 14px;
        border-radius: var(--ha-card-border-radius, 12px);
        background: var(--card-background-color, var(--ha-card-background, #fff));
        color: var(--primary-text-color, #212121);
        position: relative;
        overflow: hidden;
        min-height: 112px;
      }
      .card.size-standard { min-height: 256px; }
      .card.size-expanded { min-height: 440px; }
      .card.theme-ambient::before {
        content: "";
        position: absolute;
        inset: -20% 10% auto;
        height: 70%;
        background: radial-gradient(circle, color-mix(in srgb, var(--primary-color, #03a9f4) 18%, transparent) 0%, transparent 70%);
        pointer-events: none;
        opacity: 0.9;
      }
      @supports not (background: color-mix(in srgb, red, blue)) {
        .card.theme-ambient::before { background: radial-gradient(circle, rgba(3,169,244,0.12) 0%, transparent 70%); }
      }
      .card.theme-minimal::before { display: none; }
      .card.theme-contrast { border: 1px solid var(--primary-text-color, #212121); }
      .title { font-weight: 600; font-size: 1.05rem; display: block; margin-bottom: 6px; }
      .connectivity { font-size: 0.85rem; color: var(--secondary-text-color, #757575); display: block; }
      .beacon {
        width: 88px; height: 88px; border-radius: 50%; margin: 12px auto;
        border: 3px solid var(--divider-color, #e0e0e0);
        position: relative;
      }
      .theme-minimal .beacon { border-width: 2px; }
      .theme-minimal .beacon::after {
        content: ""; width: 10px; height: 10px; border-radius: 50%;
        background: var(--primary-color, #03a9f4);
        position: absolute; top: 8px; right: 18px;
      }
      .beacon.on { box-shadow: 0 0 0 6px color-mix(in srgb, var(--primary-color, #03a9f4) 25%, transparent); }
      @supports not (background: color-mix(in srgb, red, blue)) {
        .beacon.on { box-shadow: 0 0 0 6px rgba(3,169,244,0.25); }
      }
      .pending-arc {
        position: absolute; inset: 0; border-radius: 50%;
        border: 3px solid transparent;
        border-top-color: var(--primary-color, #03a9f4);
        animation: spin 900ms linear infinite;
        opacity: 0;
      }
      @keyframes spin { to { transform: rotate(360deg); } }
      @media (prefers-reduced-motion: reduce) {
        .pending-arc { animation: none; opacity: 0.6; }
        .card { transition: none !important; }
      }
      .btn {
        min-height: 44px; min-width: 44px;
        border-radius: var(--ha-card-border-radius, 10px);
        border: none;
        cursor: pointer;
        font: inherit;
        padding: 10px 14px;
        width: 100%;
        margin-top: 10px;
        background: var(--primary-color, #03a9f4);
        color: var(--text-primary-color, #fff);
      }
      .theme-contrast .btn {
        background: transparent;
        color: var(--primary-text-color, #212121);
        border: 1px solid var(--primary-text-color, #212121);
      }
      .btn:disabled { opacity: 0.5; cursor: not-allowed; }
      .btn:focus-visible { outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 2px; }
      .meta { display: block; margin-top: 8px; font-size: 0.85rem; color: var(--secondary-text-color, #757575); }
      .hidden { display: none !important; }
      .status-line { font-size: 0.82rem; margin-top: 6px; color: var(--secondary-text-color, #757575); min-height: 1.2em; }
      .dialog-backdrop {
        position: fixed; inset: 0; background: rgba(0,0,0,0.45);
        display: flex; align-items: center; justify-content: center; z-index: 1000;
      }
      .dialog {
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color, #212121);
        border-radius: var(--ha-card-border-radius, 12px);
        max-height: 80dvh; width: min(520px, 96vw);
        display: flex; flex-direction: column;
        padding: 12px;
      }
      @media (max-width: 600px) {
        .dialog-backdrop { align-items: flex-end; }
        .dialog { width: 100%; border-bottom-left-radius: 0; border-bottom-right-radius: 0; }
      }
      .scene-list { overflow: auto; flex: 1; margin: 8px 0; }
      .scene-group { font-weight: 600; margin: 8px 0 4px; }
      .scene-row {
        min-height: 44px; display: flex; flex-direction: column;
        padding: 8px; border-radius: 8px; cursor: pointer;
      }
      .scene-row[aria-selected="true"] { background: color-mix(in srgb, var(--primary-color, #03a9f4) 12%, transparent); }
      @supports not (background: color-mix(in srgb, red, blue)) {
        .scene-row[aria-selected="true"] { background: rgba(3,169,244,0.12); }
      }
      .scene-row.hidden { display: none; }
      .card-enter { animation: fadeIn 180ms ease; }
      @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
    `;
  }

  _applyThemeSize() {
    if (!this._root || !this._config) return;
    this._root.className = `card card-enter theme-${this._config.theme} size-${this._config.size}`;
  }

  _scheduleRender() {
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = requestAnimationFrame(() => {
      this._raf = null;
      this._render().catch(() => {});
    });
  }

  async _render() {
    if (!this._hass || !this._config) return;
    const resolved = await getResolver(this._hass).resolve(this._config.entity);
    const view = this._buildViewModel(resolved);
    const key = JSON.stringify(view);
    if (key === this._lastViewKey) return;
    this._lastViewKey = key;
    this._patchDom(view);
  }

  _buildViewModel(resolved) {
    const h = this._hass;
    const powerState = h.states[this._config.entity];
    const confirmedOn = powerState?.state === "on";
    const name =
      resolved.device?.name_by_user ||
      resolved.device?.name ||
      powerState?.attributes?.friendly_name ||
      this._config.entity;
    const get = (role) => (resolved.byRole[role] ? h.states[resolved.byRole[role]] : null);
    const connectivity = get("connectivity");
    const firmware = get("firmware");
    const subscription = get("subscription");
    const scene = get("scene");
    return {
      name,
      error: resolved.error,
      ambiguous: [...(resolved.ambiguous || [])],
      confirmedOn,
      connectivityText: connectivity?.state === "on" ? "Online" : connectivity?.state === "off" ? "Offline" : "Unknown",
      firmware: firmware?.state !== "unavailable" ? firmware?.state : null,
      serial: resolved.device?.serial_number || null,
      subscriptionStatus: subscription?.state,
      subscriptionAttrs: subscription?.attributes || {},
      sceneState: scene?.state,
      sceneOptions: scene?.attributes?.options || [],
      size: this._config.size,
    };
  }

  _patchDom(view) {
    const n = this._nodes;
    n.title.textContent = view.name;
    n.title.className = "title";
    n.connectivity.textContent = view.connectivityText;
    n.connectivity.className = "connectivity";
    const pending = this._powerFsm.phase === "sending" || this._powerFsm.phase === "awaiting_report";
    n.pendingArc.className = pending ? "pending-arc" : "pending-arc hidden";
    n.pendingArc.style.opacity = pending ? "1" : "0";
    n.beacon.className = `beacon ${view.confirmedOn ? "on" : ""}`;
    n.beacon.classList.toggle("hidden", view.size === "compact");
    const targetLabel = this._powerFsm.target === "on" ? "Turn on" : "Turn off";
    n.powerBtn.textContent = view.confirmedOn ? "Turn off Kevin" : "Turn on Kevin";
    n.powerBtn.disabled = !!view.error || pending;
    n.powerLabel.textContent = pending ? `Sending ${targetLabel}…` : "";
    n.status.textContent = this._powerStatusLine(view);
    n.sceneField.className = view.size === "compact" ? "hidden" : "meta";
    n.sceneField.textContent = view.sceneState && view.sceneState !== "unknown"
      ? `Scene: ${view.sceneState}`
      : "No active scene";
    n.sceneBtn.classList.toggle("hidden", view.size === "compact" || view.ambiguous.includes("scene"));
    n.sceneBtn.textContent = "Choose scene";
    n.firmware.className = view.size === "expanded" ? "meta" : "hidden";
    n.firmware.textContent = view.firmware ? `Firmware ${view.firmware}` : "";
    n.serial.className = view.size === "expanded" ? "meta" : "hidden";
    n.serial.textContent = view.serial ? `Serial ${view.serial}` : "";
    n.subscription.className = view.size === "expanded" ? "meta" : "hidden";
    n.subscription.textContent = view.subscriptionStatus
      ? `Subscription: ${view.subscriptionStatus}`
      : "";
    const src = view.subscriptionAttrs.source;
    n.subInfo.className = view.size === "expanded" ? "meta" : "hidden";
    n.subInfo.textContent =
      src === "not_configured"
        ? "Subscription data is not connected to a billing source yet."
        : "";
    n.rebootBtn.classList.toggle("hidden", view.size !== "expanded" || view.ambiguous.includes("reboot"));
    n.rebootBtn.disabled = Date.now() < this._rebootBlockedUntil;
    n.note.textContent = view.error || "";
    n.note.className = view.error ? "status-line" : "hidden";
  }

  _powerStatusLine(view) {
    if (this._powerFsm.phase === "failed") return "Command failed. Try again.";
    if (this._powerFsm.phase === "unconfirmed") {
      return "Confirmation did not arrive; the command may still apply.";
    }
    if (this._powerFsm.phase === "awaiting_report" || this._powerFsm.phase === "sending") {
      return "Waiting for confirmed power state…";
    }
    return "";
  }

  async _onPowerClick() {
    if (!this._hass || !this._config) return;
    const st = this._hass.states[this._config.entity];
    const target = st?.state === "on" ? "off" : "on";
    this._powerFsm = { phase: "sending", target, since: Date.now() };
    this._scheduleRender();
    const service = target === "on" ? "turn_on" : "turn_off";
    try {
      await this._hass.callService("switch", service, { entity_id: this._config.entity });
      this._powerFsm.phase = "awaiting_report";
      this._watchPowerConfirmation(target);
    } catch (_e) {
      this._powerFsm.phase = "failed";
      this._scheduleRender();
    }
  }

  _watchPowerConfirmation(target) {
    if (this._powerTimer) clearTimeout(this._powerTimer);
    const desired = target === "on" ? "on" : "off";
    const tick = () => {
      const st = this._hass?.states[this._config.entity];
      if (st?.state === desired) {
        this._powerFsm = { phase: "confirmed", target: null, since: 0 };
        this._scheduleRender();
        return;
      }
      if (Date.now() - this._powerFsm.since > POWER_PENDING_MS) {
        this._powerFsm.phase = "unconfirmed";
        this._scheduleRender();
        return;
      }
      this._powerTimer = setTimeout(tick, 500);
    };
    this._powerTimer = setTimeout(tick, 500);
  }

  async _onRebootClick() {
    const resolved = await getResolver(this._hass).resolve(this._config.entity);
    const rebootId = resolved.byRole.reboot;
    if (!rebootId) return;
    if (!window.confirm("Send reboot request to Kevin? The device may restart if the command is accepted.")) {
      return;
    }
    await this._hass.callService("button", "press", { entity_id: rebootId });
    this._rebootBlockedUntil = Date.now() + REBOOT_COOLDOWN_MS;
    this._nodes.status.textContent = "Reboot request sent.";
    this._scheduleRender();
  }

  async _openSceneDialog() {
    if (this._sceneDialogOpen || !this._hass || !this._config) return;
    const resolved = await getResolver(this._hass).resolve(this._config.entity);
    const sceneEntityId = resolved.byRole.scene;
    if (!sceneEntityId) return;
    this._sceneDialogOpen = true;
    const backdrop = document.createElement("div");
    backdrop.className = "dialog-backdrop";
    const dialog = document.createElement("div");
    dialog.className = "dialog";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    const search = document.createElement("input");
    search.type = "search";
    search.placeholder = "Search scenes";
    search.setAttribute("aria-label", "Search scenes");
    const list = document.createElement("div");
    list.className = "scene-list";
    const applyBtn = document.createElement("button");
    applyBtn.type = "button";
    applyBtn.className = "btn";
    applyBtn.textContent = "Apply scene";
    applyBtn.disabled = true;
    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "btn";
    cancelBtn.textContent = "Cancel";
    cancelBtn.style.marginTop = "6px";
    dialog.append(search, list, applyBtn, cancelBtn);
    backdrop.append(dialog);
    document.body.append(backdrop);
    this._dialog = backdrop;
    const sceneState = this._hass.states[sceneEntityId];
    const options = sceneState?.attributes?.options || [];
    const rows = [];
    for (const opt of options) {
      const row = document.createElement("div");
      row.className = "scene-row";
      row.setAttribute("role", "option");
      row.setAttribute("aria-selected", "false");
      row.tabIndex = 0;
      const title = document.createElement("span");
      title.textContent = opt;
      row.append(title);
      row.dataset.option = opt;
      row.dataset.group = "Other";
      row.addEventListener("click", () => {
        rows.forEach((r) => r.setAttribute("aria-selected", "false"));
        row.setAttribute("aria-selected", "true");
        this._sceneDraft = opt;
        applyBtn.disabled = false;
      });
      rows.push(row);
      list.append(row);
    }
    const close = () => {
      backdrop.remove();
      this._sceneDialogOpen = false;
      this._dialog = null;
    };
    cancelBtn.addEventListener("click", close);
    backdrop.addEventListener("click", (ev) => {
      if (ev.target === backdrop) close();
    });
    applyBtn.addEventListener("click", async () => {
      const resolved = await getResolver(this._hass).resolve(this._config.entity);
      const sceneId = resolved.byRole.scene;
      if (!sceneId || !this._sceneDraft) return;
      await this._hass.callService("select", "select_option", {
        entity_id: sceneId,
        option: this._sceneDraft,
      });
      close();
      this._scheduleRender();
    });
    search.addEventListener("input", () => {
      const q = normalizeSearch(search.value);
      rows.forEach((row) => {
        const hay = normalizeSearch(row.dataset.option);
        row.classList.toggle("hidden", q && !hay.includes(q));
      });
    });
  }
}

class KevinPresenceCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) {
      this._built = true;
      this.innerHTML = "";
      const wrap = document.createElement("div");
      wrap.textContent = "Use the visual editor fields below.";
      this.append(wrap);
    }
  }

  configChanged(key, value) {
    const next = { ...this._config, [key]: value };
    this._config = next;
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: next }, bubbles: true, composed: true }));
  }
}

customElements.define(CARD_TYPE, KevinPresenceCard);
customElements.define("kevin-presence-card-editor", KevinPresenceCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: CARD_TYPE,
  name: "Kevin Presence",
  preview: true,
  description: "Mitipi Kevin device card with confirmed power control and scenes.",
});

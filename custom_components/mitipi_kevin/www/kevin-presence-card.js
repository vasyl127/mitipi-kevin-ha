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

function createHaIcon(icon, label) {
  const el = document.createElement("ha-icon");
  el.setAttribute("icon", icon);
  if (label) el.setAttribute("aria-label", label);
  return el;
}

function groupForEnvironment(env) {
  const value = String(env || "").toUpperCase();
  if (ENV_ORDER.slice(0, 3).includes(value)) return value;
  return "Other";
}

function focusableElements(root) {
  return [...root.querySelectorAll("button, input, [href], select, textarea, [tabindex]:not([tabindex='-1'])")].filter(
    (el) => !el.disabled && el.offsetParent !== null
  );
}

function installDialogFocusTrap(backdrop, panel, initialFocusEl, onRequestClose) {
  const restoreFocus = document.activeElement;
  const onKeyDown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onRequestClose();
      return;
    }
    if (event.key !== "Tab") return;
    const items = focusableElements(panel);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };
  backdrop.addEventListener("keydown", onKeyDown);
  const teardown = () => {
    backdrop.removeEventListener("keydown", onKeyDown);
    if (restoreFocus && typeof restoreFocus.focus === "function") restoreFocus.focus();
  };
  (initialFocusEl || panel).focus();
  return teardown;
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
    return "0.2.1";
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
    this._closeSceneDialog();
    this._closeRebootDialog();
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
    this._scenePickerCacheKey = "";
    this._scenePickerDom = null;
    this._nodes = {};

    this._nodes.title = document.createElement("span");
    this._nodes.title.className = "title";

    this._nodes.connectivityWrap = document.createElement("div");
    this._nodes.connectivityWrap.className = "connectivity-wrap";
    this._nodes.connectivityIcon = createHaIcon("mdi:help-circle", "Connectivity");
    this._nodes.connectivity = document.createElement("span");
    this._nodes.connectivity.className = "connectivity";
    this._nodes.connectivityWrap.append(this._nodes.connectivityIcon, this._nodes.connectivity);

    this._nodes.beacon = document.createElement("div");
    this._nodes.beacon.className = "beacon";
    this._nodes.beaconIcon = createHaIcon("mdi:power", "Power state");
    this._nodes.beacon.append(this._nodes.beaconIcon);
    this._nodes.pendingArc = document.createElement("div");
    this._nodes.pendingArc.className = "pending-arc hidden";
    this._nodes.beacon.append(this._nodes.pendingArc);

    this._nodes.status = document.createElement("div");
    this._nodes.status.className = "status-line";
    this._nodes.status.setAttribute("aria-live", "polite");

    this._nodes.powerLabel = document.createElement("span");
    this._nodes.powerLabel.className = "power-label";

    this._nodes.powerBtn = document.createElement("button");
    this._nodes.powerBtn.type = "button";
    this._nodes.powerBtn.className = "btn btn-primary";

    this._nodes.powerRetryBtn = document.createElement("button");
    this._nodes.powerRetryBtn.type = "button";
    this._nodes.powerRetryBtn.className = "btn btn-secondary hidden";
    this._nodes.powerRetryBtn.textContent = "Retry command";

    this._nodes.sceneField = document.createElement("span");
    this._nodes.sceneField.className = "meta";

    this._nodes.sceneBtn = document.createElement("button");
    this._nodes.sceneBtn.type = "button";
    this._nodes.sceneBtn.className = "btn btn-secondary";
    const sceneBtnIcon = createHaIcon("mdi:playlist-music", "Open scene picker");
    this._nodes.sceneBtn.append(sceneBtnIcon, document.createTextNode(" Choose scene"));

    this._nodes.firmware = document.createElement("span");
    this._nodes.serial = document.createElement("span");
    this._nodes.subscription = document.createElement("span");
    this._nodes.subInfo = document.createElement("span");

    this._nodes.rebootBtn = document.createElement("button");
    this._nodes.rebootBtn.type = "button";
    this._nodes.rebootBtn.className = "btn btn-secondary btn-low";
    const rebootIcon = createHaIcon("mdi:restart", "Reboot device");
    this._nodes.rebootBtn.append(rebootIcon, document.createTextNode(" Reboot"));

    this._nodes.note = document.createElement("span");
    this._nodes.note.className = "status-line hidden";

    [
      "title",
      "connectivityWrap",
      "beacon",
      "status",
      "powerLabel",
      "powerBtn",
      "powerRetryBtn",
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
    this._nodes.powerRetryBtn.addEventListener("click", () => this._onPowerRetry());
    this._nodes.sceneBtn.addEventListener("click", () => {
      this._sceneOpener = this._nodes.sceneBtn;
      this._openSceneDialog();
    });
    this._nodes.rebootBtn.addEventListener("click", () => {
      this._rebootOpener = this._nodes.rebootBtn;
      this._openRebootDialog();
    });
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
        animation: cardEnter 180ms ease;
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
      .connectivity-wrap { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
      .connectivity { font-size: 0.85rem; color: var(--secondary-text-color, #757575); }
      .beacon {
        width: 88px; height: 88px; border-radius: 50%; margin: 12px auto;
        border: 3px solid var(--divider-color, #e0e0e0);
        position: relative; display: flex; align-items: center; justify-content: center;
        transition: opacity 220ms ease, transform 220ms ease;
      }
      .beacon ha-icon { --mdc-icon-size: 36px; opacity: 0.85; }
      .theme-minimal .beacon { border-width: 2px; }
      .theme-minimal .beacon::after {
        content: ""; width: 10px; height: 10px; border-radius: 50%;
        background: var(--primary-color, #03a9f4);
        position: absolute; top: 8px; right: 18px;
      }
      .beacon.on { transform: scale(1.02); opacity: 1; box-shadow: 0 0 0 6px color-mix(in srgb, var(--primary-color, #03a9f4) 25%, transparent); }
      @supports not (background: color-mix(in srgb, red, blue)) {
        .beacon.on { box-shadow: 0 0 0 6px rgba(3,169,244,0.25); }
      }
      .pending-arc {
        position: absolute; inset: 0; border-radius: 50%;
        border: 3px solid transparent;
        border-top-color: var(--primary-color, #03a9f4);
        animation: spin 900ms linear infinite;
        opacity: 0;
        pointer-events: none;
      }
      @keyframes spin { to { transform: rotate(360deg); } }
      @keyframes cardEnter { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
      @keyframes statusFade { from { opacity: 0; } to { opacity: 1; } }
      @media (prefers-reduced-motion: reduce) {
        .pending-arc { animation: none; opacity: 0.6; }
        .card, .beacon, .btn, .status-line { animation: none !important; transition: none !important; }
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
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        transition: transform 100ms ease, opacity 140ms ease;
      }
      .btn:active { transform: scale(0.98); }
      .btn-primary { background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff); }
      .theme-contrast .btn-primary {
        background: transparent;
        color: var(--primary-text-color, #212121);
        border: 1px solid var(--primary-text-color, #212121);
      }
      .btn-secondary { background: transparent; color: var(--primary-text-color, #212121); border: 1px solid var(--divider-color, #ccc); }
      .theme-contrast .btn-secondary { border-color: var(--primary-text-color, #212121); }
      .btn-low { font-size: 0.9rem; opacity: 0.9; }
      .btn:disabled { opacity: 0.5; cursor: not-allowed; }
      .btn:focus-visible { outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 2px; }
      .meta { display: block; margin-top: 8px; font-size: 0.85rem; color: var(--secondary-text-color, #757575); }
      .hidden { display: none !important; }
      .status-line { font-size: 0.82rem; margin-top: 6px; color: var(--secondary-text-color, #757575); min-height: 1.2em; animation: statusFade 140ms ease; }
      .power-label { display: block; font-size: 0.85rem; color: var(--secondary-text-color, #757575); min-height: 1.1em; }
      .dialog-backdrop {
        position: fixed; inset: 0; background: rgba(0,0,0,0.45);
        display: flex; align-items: center; justify-content: center; z-index: 1000;
        animation: dialogOpen 180ms ease;
      }
      @keyframes dialogOpen { from { opacity: 0; } to { opacity: 1; } }
      .dialog {
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color, #212121);
        border-radius: var(--ha-card-border-radius, 12px);
        max-height: 80dvh; width: min(520px, 96vw);
        display: flex; flex-direction: column;
        padding: 12px;
        transform: translateY(0);
        animation: dialogOpen 180ms ease;
      }
      @media (max-width: 600px) {
        .dialog-backdrop { align-items: flex-end; }
        .dialog { width: 100%; border-bottom-left-radius: 0; border-bottom-right-radius: 0; }
      }
      .scene-toolbar { display: flex; gap: 8px; align-items: center; }
      .scene-toolbar input { flex: 1; min-height: 44px; }
      .scene-list { overflow: auto; flex: 1; margin: 8px 0; min-height: 120px; }
      .scene-group-title { font-weight: 600; margin: 10px 0 4px; font-size: 0.9rem; }
      .scene-group-title.hidden { display: none; }
      .scene-row {
        min-height: 44px; display: flex; flex-direction: column;
        padding: 8px; border-radius: 8px; cursor: pointer;
        border: 1px solid transparent;
      }
      .scene-row[aria-selected="true"] { background: color-mix(in srgb, var(--primary-color, #03a9f4) 12%, transparent); }
      .scene-row.scene-confirmed { border-color: var(--primary-color, #03a9f4); }
      @supports not (background: color-mix(in srgb, red, blue)) {
        .scene-row[aria-selected="true"] { background: rgba(3,169,244,0.12); }
      }
      .scene-row.hidden { display: none; }
      .scene-title { font-weight: 500; }
      .scene-desc { font-size: 0.82rem; color: var(--secondary-text-color, #757575); }
      .scene-empty { padding: 16px; text-align: center; color: var(--secondary-text-color, #757575); }
      .dialog-actions { display: flex; flex-direction: column; gap: 6px; }
      .reboot-text { margin: 8px 0 12px; line-height: 1.4; }
    `;
  }

  _applyThemeSize() {
    if (!this._root || !this._config) return;
    this._root.className = `card theme-${this._config.theme} size-${this._config.size}`;
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
    if (key === this._lastViewKey && this._powerFsm.phase !== "unconfirmed") return;
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
    let connectivityIcon = "mdi:help-circle";
    if (connectivity?.state === "on") connectivityIcon = "mdi:lan-connect";
    else if (connectivity?.state === "off") connectivityIcon = "mdi:lan-disconnect";
    return {
      name,
      error: resolved.error,
      ambiguous: [...(resolved.ambiguous || [])],
      confirmedOn,
      connectivityIcon,
      connectivityText: connectivity?.state === "on" ? "Online" : connectivity?.state === "off" ? "Offline" : "Unknown",
      firmware: firmware?.state !== "unavailable" ? firmware?.state : null,
      serial: resolved.device?.serial_number || null,
      subscriptionStatus: subscription?.state,
      subscriptionAttrs: subscription?.attributes || {},
      sceneState: scene?.state,
      sceneCatalog: scene?.attributes?.scene_catalog || [],
      size: this._config.size,
    };
  }

  _patchDom(view) {
    const n = this._nodes;
    n.title.textContent = view.name;
    n.connectivity.textContent = view.connectivityText;
    n.connectivityIcon.setAttribute("icon", view.connectivityIcon);
    const pending = this._powerFsm.phase === "sending" || this._powerFsm.phase === "awaiting_report";
    n.pendingArc.classList.toggle("hidden", !pending);
    n.beacon.classList.toggle("on", view.confirmedOn);
    n.beacon.classList.toggle("hidden", view.size === "compact");
    n.beaconIcon.setAttribute("icon", view.confirmedOn ? "mdi:power" : "mdi:power-standby");
    const targetLabel = this._powerFsm.target === "on" ? "Turn on" : "Turn off";
    n.powerBtn.textContent = view.confirmedOn ? "Turn off Kevin" : "Turn on Kevin";
    n.powerBtn.disabled = !!view.error || pending;
    n.powerLabel.textContent = pending ? `Sending ${targetLabel}…` : "";
    n.status.textContent = this._powerStatusLine(view);
    n.powerRetryBtn.classList.toggle("hidden", this._powerFsm.phase !== "unconfirmed");
    n.sceneField.className = view.size === "compact" ? "hidden" : "meta";
    n.sceneField.textContent =
      view.sceneState && view.sceneState !== "unknown" && view.sceneState !== "unavailable"
        ? `Scene: ${view.sceneState}`
        : "No active scene";
    n.sceneBtn.classList.toggle("hidden", view.size === "compact" || view.ambiguous.includes("scene"));
    n.firmware.className = view.size === "expanded" ? "meta" : "hidden";
    n.firmware.textContent = view.firmware ? `Firmware ${view.firmware}` : "";
    n.serial.className = view.size === "expanded" ? "meta" : "hidden";
    n.serial.textContent = view.serial ? `Serial ${view.serial}` : "";
    n.subscription.className = view.size === "expanded" ? "meta" : "hidden";
    n.subscription.textContent = view.subscriptionStatus ? `Subscription: ${view.subscriptionStatus}` : "";
    const src = view.subscriptionAttrs.source;
    n.subInfo.className = view.size === "expanded" ? "meta" : "hidden";
    n.subInfo.textContent =
      src === "not_configured" ? "Subscription data is not connected to a billing source yet." : "";
    n.rebootBtn.classList.toggle("hidden", view.size !== "expanded" || view.ambiguous.includes("reboot"));
    n.rebootBtn.disabled = Date.now() < this._rebootBlockedUntil;
    n.note.textContent = view.error || "";
    n.note.classList.toggle("hidden", !view.error);
  }

  _powerStatusLine(_view) {
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
    if (!this._hass || !this._config || this._powerFsm.phase === "unconfirmed") return;
    const st = this._hass.states[this._config.entity];
    const target = st?.state === "on" ? "off" : "on";
    await this._sendPowerCommand(target);
  }

  async _onPowerRetry() {
    if (!this._powerFsm.target) return;
    await this._sendPowerCommand(this._powerFsm.target);
  }

  async _sendPowerCommand(target) {
    if (!this._hass || !this._config) return;
    this._powerFsm = { phase: "sending", target, since: Date.now() };
    this._lastViewKey = "";
    this._scheduleRender();
    const service = target === "on" ? "turn_on" : "turn_off";
    try {
      await this._hass.callService("switch", service, { entity_id: this._config.entity });
      this._powerFsm.phase = "awaiting_report";
      this._watchPowerConfirmation(target);
    } catch (_err) {
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
        this._lastViewKey = "";
        this._scheduleRender();
        return;
      }
      if (Date.now() - this._powerFsm.since > POWER_PENDING_MS) {
        this._powerFsm.phase = "unconfirmed";
        this._lastViewKey = "";
        this._scheduleRender();
        return;
      }
      this._powerTimer = setTimeout(tick, 500);
    };
    this._powerTimer = setTimeout(tick, 500);
  }

  _closeRebootDialog() {
    if (this._rebootBackdrop) {
      this._rebootBackdrop.remove();
      this._rebootBackdrop = null;
      this._rebootFocusTeardown?.();
      this._rebootFocusTeardown = null;
    }
  }

  async _openRebootDialog() {
    if (this._rebootBackdrop || !this._hass) return;
    const resolved = await getResolver(this._hass).resolve(this._config.entity);
    const rebootId = resolved.byRole.reboot;
    if (!rebootId) return;

    const backdrop = document.createElement("div");
    backdrop.className = "dialog-backdrop";
    const dialog = document.createElement("div");
    dialog.className = "dialog";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-label", "Confirm reboot request");

    const title = document.createElement("strong");
    title.textContent = "Send reboot request?";
    const text = document.createElement("p");
    text.className = "reboot-text";
    text.textContent =
      "This sends a reboot request to Kevin. It does not guarantee the device has rebooted.";

    const actions = document.createElement("div");
    actions.className = "dialog-actions";
    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "btn btn-secondary";
    cancelBtn.textContent = "Cancel";
    const confirmBtn = document.createElement("button");
    confirmBtn.type = "button";
    confirmBtn.className = "btn btn-primary";
    confirmBtn.textContent = "Send reboot request";

    actions.append(cancelBtn, confirmBtn);
    dialog.append(title, text, actions);
    backdrop.append(dialog);
    document.body.append(backdrop);
    this._rebootBackdrop = backdrop;

    const close = () => this._closeRebootDialog();
    cancelBtn.addEventListener("click", close);
    confirmBtn.addEventListener("click", async () => {
      await this._hass.callService("button", "press", { entity_id: rebootId });
      this._rebootBlockedUntil = Date.now() + REBOOT_COOLDOWN_MS;
      this._nodes.status.textContent = "Reboot request sent.";
      close();
      this._scheduleRender();
    });
    backdrop.addEventListener("click", (ev) => {
      if (ev.target === backdrop) close();
    });

    this._rebootFocusTeardown = installDialogFocusTrap(backdrop, dialog, cancelBtn, close);
  }

  _closeSceneDialog() {
    if (this._sceneBackdrop) {
      if (this._scenePickerDom?.list?.parentElement) {
        this._scenePickerDom.list.remove();
      }
      this._sceneBackdrop.remove();
      this._sceneBackdrop = null;
      this._sceneFocusTeardown?.();
      this._sceneFocusTeardown = null;
      this._sceneDialogOpen = false;
    }
  }

  _ensureScenePickerDom(catalog, confirmedOption) {
    const cacheKey = JSON.stringify(catalog);
    if (this._scenePickerDom && this._scenePickerCacheKey === cacheKey) {
      return this._scenePickerDom;
    }
    this._scenePickerCacheKey = cacheKey;
    const grouped = {};
    for (const env of ENV_ORDER) grouped[env] = [];
    for (const scene of catalog) {
      const optionLabel = scene.option || scene.title;
      grouped[groupForEnvironment(scene.environment)].push({ ...scene, optionLabel });
    }

    const list = document.createElement("div");
    list.className = "scene-list";
    const groupTitles = {};
    const rows = [];

    for (const env of ENV_ORDER) {
      const heading = document.createElement("div");
      heading.className = "scene-group-title";
      heading.textContent = env;
      heading.dataset.group = env;
      list.append(heading);
      groupTitles[env] = heading;

      for (const scene of grouped[env]) {
        const row = document.createElement("div");
        row.className = "scene-row";
        row.setAttribute("role", "option");
        row.setAttribute("aria-selected", "false");
        row.tabIndex = 0;
        row.dataset.option = scene.optionLabel;
        row.dataset.group = env;
        row.dataset.search = normalizeSearch(
          `${scene.optionLabel} ${scene.description || ""} ${env}`
        );
        if (confirmedOption && scene.optionLabel === confirmedOption) {
          row.classList.add("scene-confirmed");
        }
        const titleEl = document.createElement("span");
        titleEl.className = "scene-title";
        titleEl.textContent = scene.optionLabel;
        row.append(titleEl);
        if (scene.description) {
          const desc = document.createElement("span");
          desc.className = "scene-desc";
          desc.textContent = String(scene.description);
          row.append(desc);
        }
        rows.push(row);
        list.append(row);
      }
    }

    const empty = document.createElement("div");
    empty.className = "scene-empty hidden";
    empty.textContent = "No scenes match your search.";
    list.append(empty);

    this._scenePickerDom = { list, rows, groupTitles, empty };
    return this._scenePickerDom;
  }

  _applySceneSearch(query, pickerDom) {
    const q = normalizeSearch(query);
    let visibleCount = 0;
    for (const row of pickerDom.rows) {
      const match = !q || row.dataset.search.includes(q);
      row.classList.toggle("hidden", !match);
      if (match) visibleCount += 1;
    }
    for (const env of ENV_ORDER) {
      const heading = pickerDom.groupTitles[env];
      const anyVisible = pickerDom.rows.some(
        (row) => row.dataset.group === env && !row.classList.contains("hidden")
      );
      heading.classList.toggle("hidden", !anyVisible);
    }
    pickerDom.empty.classList.toggle("hidden", visibleCount > 0);
  }

  async _openSceneDialog() {
    if (this._sceneDialogOpen || !this._hass || !this._config) return;
    const resolved = await getResolver(this._hass).resolve(this._config.entity);
    const sceneEntityId = resolved.byRole.scene;
    if (!sceneEntityId) return;

    const sceneState = this._hass.states[sceneEntityId];
    const catalogRaw = sceneState?.attributes?.scene_catalog || [];
    const optionMap = {};
    for (const opt of sceneState?.attributes?.options || []) optionMap[opt] = opt;
    const catalog = catalogRaw.map((item) => ({
      ...item,
      option: Object.keys(optionMap).find((k) => k === item.title) || item.title,
    }));

    const confirmedOption =
      sceneState?.state && sceneState.state !== "unknown" && sceneState.state !== "unavailable"
        ? sceneState.state
        : null;

    const pickerDom = this._ensureScenePickerDom(catalog, confirmedOption);
    this._sceneDialogOpen = true;
    this._sceneDraft = null;

    const backdrop = document.createElement("div");
    backdrop.className = "dialog-backdrop";
    const dialog = document.createElement("div");
    dialog.className = "dialog";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-label", "Choose Kevin scene");

    const toolbar = document.createElement("div");
    toolbar.className = "scene-toolbar";
    const search = document.createElement("input");
    search.type = "search";
    search.placeholder = "Search scenes";
    search.setAttribute("aria-label", "Search scenes");
    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "btn btn-secondary";
    clearBtn.style.marginTop = "0";
    clearBtn.style.width = "auto";
    clearBtn.append(createHaIcon("mdi:close-circle", "Clear search"), document.createTextNode(" Clear"));
    toolbar.append(search, clearBtn);

    if (pickerDom.list.parentElement) pickerDom.list.parentElement.removeChild(pickerDom.list);
    pickerDom.rows.forEach((row) => {
      row.setAttribute("aria-selected", "false");
    });

    const applyBtn = document.createElement("button");
    applyBtn.type = "button";
    applyBtn.className = "btn btn-primary";
    applyBtn.textContent = "Apply scene";
    applyBtn.disabled = true;
    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "btn btn-secondary";
    cancelBtn.textContent = "Cancel";

    const actions = document.createElement("div");
    actions.className = "dialog-actions";
    actions.append(applyBtn, cancelBtn);
    dialog.append(toolbar, pickerDom.list, actions);
    backdrop.append(dialog);
    document.body.append(backdrop);
    this._sceneBackdrop = backdrop;

    const selectRow = (row) => {
      pickerDom.rows.forEach((r) => r.setAttribute("aria-selected", "false"));
      row.setAttribute("aria-selected", "true");
      this._sceneDraft = row.dataset.option;
      applyBtn.disabled = false;
    };
    pickerDom.rows.forEach((row) => {
      row.onclick = () => selectRow(row);
      row.onkeydown = (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          selectRow(row);
        }
      };
    });

    const close = () => this._closeSceneDialog();
    cancelBtn.addEventListener("click", close);
    backdrop.addEventListener("click", (ev) => {
      if (ev.target === backdrop) close();
    });
    clearBtn.addEventListener("click", () => {
      search.value = "";
      this._applySceneSearch("", pickerDom);
      search.focus();
    });
    search.addEventListener("input", () => this._applySceneSearch(search.value, pickerDom));

    applyBtn.addEventListener("click", async () => {
      if (!this._sceneDraft) return;
      await this._hass.callService("select", "select_option", {
        entity_id: sceneEntityId,
        option: this._sceneDraft,
      });
      close();
      this._scheduleRender();
    });

    this._sceneFocusTeardown = installDialogFocusTrap(backdrop, dialog, search, close);
  }
}

class KevinPresenceCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = {
      type: `custom:${CARD_TYPE}`,
      entity: config?.entity || "",
      theme: config?.theme || "ambient",
      size: config?.size || "standard",
    };
    this._renderEditor();
  }

  set hass(hass) {
    this._hass = hass;
    this._renderEditor();
  }

  _emitConfig(config) {
    this._config = config;
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true })
    );
  }

  _renderEditor() {
    if (!this._hass || !this._config) return;
    while (this.firstChild) this.removeChild(this.firstChild);

    const entityPicker = document.createElement("ha-entity-picker");
    entityPicker.hass = this._hass;
    entityPicker.includeDomains = ["switch"];
    entityPicker.allowCustomEntity = false;
    entityPicker.label = "Kevin power switch";
    entityPicker.value = this._config.entity;
    entityPicker.addEventListener("value-changed", (ev) => {
      this._emitConfig({ ...this._config, entity: ev.detail.value });
    });

    const themeSelect = document.createElement("ha-selector");
    themeSelect.hass = this._hass;
    themeSelect.label = "Theme";
    themeSelect.selector = {
      select: { mode: "dropdown", options: THEMES.map((v) => ({ value: v, label: v })) },
    };
    themeSelect.value = this._config.theme;
    themeSelect.addEventListener("value-changed", (ev) => {
      this._emitConfig({ ...this._config, theme: ev.detail.value });
    });

    const sizeSelect = document.createElement("ha-selector");
    sizeSelect.hass = this._hass;
    sizeSelect.label = "Size";
    sizeSelect.selector = {
      select: { mode: "dropdown", options: SIZES.map((v) => ({ value: v, label: v })) },
    };
    sizeSelect.value = this._config.size;
    sizeSelect.addEventListener("value-changed", (ev) => {
      this._emitConfig({ ...this._config, size: ev.detail.value });
    });

    this.append(entityPicker, themeSelect, sizeSelect);
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

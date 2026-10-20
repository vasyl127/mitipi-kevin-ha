/**
 * Smoke test: Kevin Presence card registers with Lovelace when loaded as an ES module.
 */
import { pathToFileURL } from "node:url";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const __dirname = dirname(fileURLToPath(import.meta.url));
const cardPath = join(
  __dirname,
  "../../custom_components/mitipi_kevin/www/kevin-presence-card.js"
);

const definedTags = [];

class HTMLElementStub {}
class CustomEventStub {
  constructor(type, init) {
    this.type = type;
    this.detail = init?.detail;
  }
}

const elementRegistry = new Map();

globalThis.HTMLElement = HTMLElementStub;
globalThis.CustomEvent = CustomEventStub;
globalThis.cancelAnimationFrame = () => {};
globalThis.requestAnimationFrame = (fn) => {
  fn();
  return 0;
};

globalThis.document = {
  createElement(tag) {
    const el = {
      tagName: tag.toUpperCase(),
      className: "",
      textContent: "",
      disabled: false,
      offsetParent: {},
      children: [],
      setAttribute() {},
      append(...nodes) {
        this.children.push(...nodes);
      },
      appendChild(node) {
        this.children.push(node);
      },
      removeChild(node) {
        this.children = this.children.filter((child) => child !== node);
      },
      addEventListener() {},
      removeEventListener() {},
      querySelectorAll() {
        return [];
      },
      focus() {},
    };
    return el;
  },
  activeElement: null,
};

globalThis.customElements = {
  define(name, ctor) {
    definedTags.push(name);
    elementRegistry.set(name, ctor);
  },
  get(name) {
    return elementRegistry.get(name);
  },
};

globalThis.customCards = undefined;

const card = await import(pathToFileURL(cardPath).href);

assert.ok(
  Array.isArray(globalThis.customCards),
  "globalThis.customCards must be initialized when absent"
);

const cardEntry = globalThis.customCards.find((entry) => entry.type === "kevin-presence-card");
assert.ok(cardEntry, "customCards must include kevin-presence-card");
assert.equal(cardEntry.name, "KEVIN® Presence");
assert.equal(cardEntry.preview, true);

assert.ok(
  definedTags.includes("kevin-presence-card"),
  "customElements.define must register kevin-presence-card"
);
assert.ok(
  definedTags.includes("kevin-presence-card-editor"),
  "customElements.define must register kevin-presence-card-editor"
);

assert.equal(
  `custom:${cardEntry.type}`,
  "custom:kevin-presence-card",
  "YAML type must match registered custom element tag"
);

/* Variants: new key wins, legacy layout/size keys keep old dashboards working. */
const { variantOf, KevinPresenceCard } = card;
assert.equal(variantOf({}), "standard");
assert.equal(variantOf({ variant: "full" }), "full");
assert.equal(variantOf({ layout: "compact" }), "minimal");
assert.equal(variantOf({ size: "compact" }), "minimal");
assert.equal(variantOf({ size: "expanded" }), "full");
assert.equal(variantOf({ variant: "minimal", layout: "full" }), "minimal");

const sizing = (config) => {
  const c = Object.create(KevinPresenceCard.prototype);
  c._config = { ...config, variant: variantOf(config) };
  return [c.getGridOptions(), c.getCardSize()];
};
assert.deepEqual(sizing({ variant: "minimal" }), [{ columns: 6, rows: 1, min_columns: 3, max_rows: 1 }, 1]);
assert.deepEqual(sizing({ variant: "standard" }), [{ columns: 12, min_columns: 9 }, 16]);
assert.deepEqual(sizing({ variant: "full" }), [{ columns: 12, min_columns: 9 }, 27]);

console.log("card_registration_smoke: ok");

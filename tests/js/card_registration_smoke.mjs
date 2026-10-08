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

await import(pathToFileURL(cardPath).href);

assert.ok(
  Array.isArray(globalThis.customCards),
  "globalThis.customCards must be initialized when absent"
);

const cardEntry = globalThis.customCards.find((entry) => entry.type === "kevin-presence-card");
assert.ok(cardEntry, "customCards must include kevin-presence-card");
assert.equal(cardEntry.name, "Kevin Presence");
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

console.log("card_registration_smoke: ok");

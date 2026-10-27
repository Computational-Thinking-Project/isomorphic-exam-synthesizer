/**
 * Môi trường DOM giả lập cho ReactDOM trong Node runner.
 * Phục vụ mount và kiểm thử component React thật mà không cần thư viện ngoài.
 */

export class DOMNode {
  constructor(nodeType, nodeName) {
    this.nodeType = nodeType;
    this.nodeName = nodeName;
    this.childNodes = [];
    this.parentNode = null;
    this.ownerDocument = null;
  }
  appendChild(child) {
    this.childNodes.push(child);
    child.parentNode = this;
    return child;
  }
  removeChild(child) {
    const idx = this.childNodes.indexOf(child);
    if (idx >= 0) this.childNodes.splice(idx, 1);
    child.parentNode = null;
    return child;
  }
  insertBefore(child, before) {
    const idx = this.childNodes.indexOf(before);
    if (idx >= 0) this.childNodes.splice(idx, 0, child);
    else this.childNodes.push(child);
    child.parentNode = this;
    return child;
  }
  get textContent() {
    if (this.nodeType === 3) return this._text || '';
    return this.childNodes.map((c) => c.textContent).join('');
  }
  set textContent(v) {
    if (this.nodeType === 3) {
      this._text = String(v);
    } else {
      this.childNodes = [];
      if (v) {
        const textNode = this.ownerDocument?.createTextNode(v) || new DOMNode(3, '#text');
        textNode._text = String(v);
        this.appendChild(textNode);
      }
    }
  }
}

export class DOMElement extends DOMNode {
  constructor(tagName) {
    super(1, tagName.toUpperCase());
    this.tagName = tagName.toUpperCase();
    this.style = {};
    this.attributes = {};
    this.listeners = {};
    this._value = '';
    this._checked = false;
  }
  get value() {
    return this._value;
  }
  set value(v) {
    this._value = String(v);
  }
  get checked() {
    return this._checked;
  }
  set checked(v) {
    this._checked = Boolean(v);
  }
  setAttribute(name, val) {
    this.attributes[name] = String(val);
    this[name] = val;
  }
  getAttribute(name) {
    return this.attributes[name] ?? null;
  }
  removeAttribute(name) {
    delete this.attributes[name];
    delete this[name];
  }
  addEventListener(event, fn) {
    (this.listeners[event] = this.listeners[event] || []).push(fn);
  }
  removeEventListener(event, fn) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter((f) => f !== fn);
    }
  }
  dispatchEvent(event) {
    event.target = event.target || this;
    event.currentTarget = this;
    if (this.listeners[event.type]) {
      for (const fn of [...this.listeners[event.type]]) {
        fn(event);
      }
    }
    if (this.parentNode && event.bubbles !== false && !event.cancelBubble) {
      this.parentNode.dispatchEvent(event);
    }
  }
  contains(node) {
    let curr = node;
    while (curr) {
      if (curr === this) return true;
      curr = curr.parentNode;
    }
    return false;
  }
  querySelectorAll(selector) {
    const results = [];
    function matches(child, sel) {
      if (child.nodeType !== 1) return false;
      const tag = child.tagName.toLowerCase();

      if (sel.includes('button') && sel.includes('input')) {
        return ['button', 'input', 'select', 'textarea'].includes(tag);
      }

      if (sel.includes('[') && sel.endsWith(']')) {
        const bracketIndex = sel.indexOf('[');
        const prefixTag = sel.slice(0, bracketIndex);
        if (prefixTag && prefixTag.toLowerCase() !== tag) return false;

        const attrExpr = sel.slice(bracketIndex + 1, -1);
        const eqIndex = attrExpr.indexOf('=');
        if (eqIndex >= 0) {
          const attrName = attrExpr.slice(0, eqIndex).trim();
          const attrVal = attrExpr.slice(eqIndex + 1).trim().replace(/['"]/g, '');
          return child.getAttribute(attrName) === attrVal;
        }
        return child.getAttribute(attrExpr.trim()) !== null;
      }

      if (sel.startsWith('#')) {
        return child.getAttribute('id') === sel.slice(1);
      }

      if (sel.startsWith('.')) {
        return (child.attributes.class || '').split(/\s+/).includes(sel.slice(1));
      }

      return tag === sel.toLowerCase();
    }

    function walk(el) {
      for (const child of el.childNodes) {
        if (matches(child, selector)) {
          results.push(child);
        }
        walk(child);
      }
    }
    walk(this);
    return results;
  }
  querySelector(selector) {
    const all = this.querySelectorAll(selector);
    return all[0] || null;
  }
  focus() {
    if (this.ownerDocument) {
      this.ownerDocument.activeElement = this;
    }
  }
  select() {}
  click() {
    if (this.getAttribute('disabled') !== null) return;
    this.dispatchEvent({
      type: 'click',
      bubbles: true,
      cancelable: true,
      preventDefault: () => {},
    });
  }
}

export class DOMDocument extends DOMNode {
  constructor() {
    super(9, '#document');
    this.activeElement = null;
    this.listeners = {};
    this.defaultView = null;
  }
  createElement(tag) {
    const el = new DOMElement(tag);
    el.ownerDocument = this;
    return el;
  }
  createElementNS(namespaceURI, tag) {
    const el = new DOMElement(tag);
    el.ownerDocument = this;
    el.namespaceURI = namespaceURI;
    return el;
  }
  createTextNode(text) {
    const t = new DOMNode(3, '#text');
    t._text = text;
    t.ownerDocument = this;
    return t;
  }
  createComment(text) {
    const c = new DOMNode(8, '#comment');
    c._text = text;
    c.ownerDocument = this;
    return c;
  }
  addEventListener(event, fn) {
    (this.listeners[event] = this.listeners[event] || []).push(fn);
  }
  removeEventListener(event, fn) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter((f) => f !== fn);
    }
  }
  dispatchEvent(event) {
    event.currentTarget = this;
    if (this.listeners[event.type]) {
      for (const fn of [...this.listeners[event.type]]) {
        fn(event);
      }
    }
  }
}

export function ensureDomEnvironment() {
  if (globalThis.document && globalThis.window) {
    return { document: globalThis.document, window: globalThis.window };
  }

  const doc = new DOMDocument();
  const win = {
    document: doc,
    location: {
      href: 'http://localhost/',
      origin: 'http://localhost',
      protocol: 'http:',
      host: 'localhost',
      hostname: 'localhost',
      pathname: '/',
      search: '',
      hash: '',
    },
    addEventListener(event, fn) {
      (this.listeners = this.listeners || {})[event] = (this.listeners[event] || []).concat(fn);
    },
    removeEventListener(event, fn) {
      if (this.listeners?.[event]) {
        this.listeners[event] = this.listeners[event].filter((f) => f !== fn);
      }
    },
    dispatchEvent(event) {
      if (this.listeners?.[event.type]) {
        for (const fn of [...this.listeners[event.type]]) {
          fn(event);
        }
      }
    },
    HTMLElement: DOMElement,
    HTMLInputElement: DOMElement,
    HTMLButtonElement: DOMElement,
    HTMLIFrameElement: DOMElement,
    Node: DOMNode,
    Element: DOMElement,
  };
  doc.defaultView = win;

  globalThis.document = doc;
  globalThis.window = win;
  globalThis.Node = DOMNode;
  globalThis.Element = DOMElement;
  globalThis.HTMLElement = DOMElement;
  globalThis.HTMLInputElement = DOMElement;
  globalThis.HTMLButtonElement = DOMElement;
  globalThis.HTMLIFrameElement = DOMElement;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;

  return { document: doc, window: win };
}

import { translations } from './zh-en.js';

const STORAGE_KEY = 'privgrid.language';
let language = 'zh-CN';
try { if (localStorage.getItem(STORAGE_KEY) === 'en') language = 'en'; } catch { /* Storage can be disabled. */ }

export const getLanguage = () => language;
const escapePattern = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const keys = Object.keys(translations).sort((a, b) => b.length - a.length);
const pattern = new RegExp(keys.map(escapePattern).join('|'), 'gu');

export function translate(value, target = language) {
  const text = String(value ?? '');
  if (target !== 'en') return text;
  if (translations[text.trim()]) return text.replace(text.trim(), translations[text.trim()]);
  // One pass: an English replacement is never interpreted as another source key.
  return text.replace(pattern, (key, offset, original) => {
    if (key.length === 1 && /[\u4e00-\u9fff]/u.test((original[offset - 1] || '') + (original[offset + 1] || ''))) return key;
    return ` ${translations[key]} `;
  }).replace(/ {2,}/g, ' ').trim();
}

export function setLanguage(value) {
  language = value === 'en' ? 'en' : 'zh-CN';
  try { localStorage.setItem(STORAGE_KEY, language); } catch { /* Keep the in-memory preference. */ }
  document.documentElement.lang = language;
}

export function languageControl() {
  return `<div class="language-switch" role="group" aria-label="Language / 语言">
    <button type="button" data-ui-language="zh-CN" lang="zh-CN" aria-pressed="${language === 'zh-CN'}">中文</button>
    <button type="button" data-ui-language="en" lang="en" aria-pressed="${language === 'en'}">English</button>
  </div>`;
}

// Change presentation in place. No form values, IDs, event handlers, API fields,
// or task state are changed, and no translation requests leave the browser.
export function installLocalization(root = document.body) {
  const sources = new WeakMap();
  const attributes = new WeakMap();
  const protectedSelector = '[data-i18n-ignore], [translate="no"], script, style, textarea, .agent-message-user .agent-message-content, #q-explanation .advice-box p, .agent-typewriter, .agent-response-reply, .agent-response-explanation';
  let observer;
  const originalTitle = document.title;
  function protectedNode(node) {
    return node.parentElement?.closest(protectedSelector);
  }
  function refresh() {
    observer?.disconnect();
    document.documentElement.lang = language;
    document.title = translate(originalTitle);
    const walker = document.createTreeWalker(root, 4);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (protectedNode(node) || node.parentElement?.closest('.language-switch')) continue;
      const prior = sources.get(node);
      const original = prior && node.data === prior.shown ? prior.original : node.data;
      const shown = translate(original);
      sources.set(node, { original, shown });
      if (node.data !== shown) node.data = shown;
    }
    for (const element of root.querySelectorAll('[placeholder], [title], [aria-label]')) {
      if (element.closest('[data-i18n-ignore], [translate="no"], .language-switch')) continue;
      const saved = attributes.get(element) || {};
      for (const name of ['placeholder', 'title', 'aria-label']) {
        if (!element.hasAttribute(name)) continue;
        const current = element.getAttribute(name);
        const old = saved[name];
        const original = old && current === old.shown ? old.original : current;
        const shown = translate(original);
        saved[name] = { original, shown };
        if (shown !== current) element.setAttribute(name, shown);
      }
      attributes.set(element, saved);
    }
    for (const button of root.querySelectorAll('[data-ui-language]')) {
      button.setAttribute('aria-pressed', String(button.dataset.uiLanguage === language));
    }
    observer?.observe(root, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['placeholder', 'title', 'aria-label'] });
  }
  const handleClick = event => {
    const button = event.target.closest?.('[data-ui-language]');
    if (!button || !root.contains(button)) return;
    setLanguage(button.dataset.uiLanguage);
    refresh();
  };
  root.addEventListener('click', handleClick);
  const Observer = root.ownerDocument.defaultView.MutationObserver;
  observer = new Observer(refresh);
  refresh();
  return { refresh, dispose() { observer.disconnect(); root.removeEventListener('click', handleClick); } };
}

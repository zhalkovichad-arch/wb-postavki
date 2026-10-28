#!/usr/bin/env python3
"""Собирает автономную HTML-страницу календаря поставок (без Claude, без интернета).

python3 make_html.py index.html supplies.json items.json out.html
index.html — страница дашборда; данные встраиваются прямо в файл.
"""
import json, sys

page, sup, it, out = sys.argv[1:5]
html = open(page, encoding="utf-8").read().replace('<meta name="dash-one-writer">', "")
S = json.load(open(sup, encoding="utf-8"))
I = json.load(open(it, encoding="utf-8"))
data = {"supplies": S.get("rows", S), "items": I.get("rows", I)}
blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
updated = S.get("updated", "") if isinstance(S, dict) else ""

SHIM = r"""
<script>
(function () {
  const DATA = JSON.parse(document.getElementById('wb-data').textContent);
  const calcs = {}, draws = [], hooks = [];
  let params = { cab: 'all', month: null, sid: null, day: null, q: null };
  try { const h = new URLSearchParams(location.hash.slice(1)); for (const [k, v] of h) params[k] = v || null; } catch (e) {}
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const ok = (data) => ({ status: 'ok', data, rows: data, meta: [] });
  let scheduled = false;
  const redraw = () => {
    if (scheduled) return; scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      for (const f of hooks) try { f(); } catch (e) { console.error(e); }
      for (const [name, fn] of draws) for (const el of document.querySelectorAll('[data-draw="' + name + '"]')) try { fn(el); } catch (e) { console.error(e); }
    });
  };
  window.d3 = { group: (arr, key) => { const m = new Map(); for (const x of arr) { const k = key(x); if (!m.has(k)) m.set(k, []); m.get(k).push(x); } return m; } };
  window.dash = {
    colors: ['#2f7fd6', '#d0682e', '#8a63c9', '#3a9b6a', '#8a63c9', '#c2932a', '#3aa1a8', '#b5527a'],
    data: (id) => (id in DATA ? ok(DATA[id]) : id in calcs ? ok(calcs[id]) : { status: 'missing', data: [] }),
    calc: (id, o) => { calcs[id] = o.fn(...o.inputs.map((x) => DATA[x] || calcs[x] || [])); },
    loader: () => {},
    onData: (fn) => { hooks.push(fn); redraw(); },
    draw: (name, fn) => { if (typeof fn === 'function') { draws.push([name, fn]); redraw(); } else redraw(); },
    params: () => ({ ...params }),
    setParams: (o) => {
      params = { ...params, ...o };
      try { const h = new URLSearchParams(); for (const [k, v] of Object.entries(params)) if (v && !(k === 'cab' && v === 'all')) h.set(k, v); history.replaceState(null, '', '#' + h.toString()); } catch (e) {}
      redraw();
    },
    resetParams: () => { params = { cab: 'all', month: null, sid: null, day: null, q: null }; redraw(); },
    setLink: () => {}, refresh: () => {},
  };
  window.addEventListener('resize', redraw);

  // Отметки «состав уточняется»: файл data/drafts.json в репозитории.
  // Смотреть может любой; менять — только тот, кто открыл страницу с ?edit и ввёл токен GitHub.
  const REPO = 'zhalkovichad-arch/wb-postavki', PATH = 'data/drafts.json';
  const API = 'https://api.github.com/repos/' + REPO + '/contents/' + PATH;
  const KEY = 'wb_gh_token';
  let token = null;
  try { token = localStorage.getItem(KEY); } catch (e) {}
  const wantEdit = /(^|[?&])edit\b/.test(location.search.slice(1));
  if (wantEdit && !token) {
    const t = window.prompt('Режим правки отметок. Вставьте токен GitHub (сохранится только в этом браузере):');
    if (t && t.trim()) { token = t.trim(); try { localStorage.setItem(KEY, token); } catch (e) {} }
  }
  const b64 = (str) => btoa(unescape(encodeURIComponent(str)));
  const unb64 = (str) => decodeURIComponent(escape(atob(str.replace(/\n/g, ''))));
  const hdr = () => ({ Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' });
  let sha = null;
  const WB = window.WB = { drafts: new Set(), canEdit: !!token, toggle: null };
  const setDrafts = (list) => { WB.drafts = new Set(list || []); redraw(); };
  const loadPublic = () => fetch(PATH + '?t=' + Date.now(), { cache: 'no-store' })
    .then((r) => (r.ok ? r.json() : { sids: [] })).then((j) => setDrafts(j.sids)).catch(() => {});
  const loadApi = () => fetch(API + '?t=' + Date.now(), { headers: hdr(), cache: 'no-store' })
    .then((r) => { if (r.status === 401) throw new Error('auth'); return r.ok ? r.json() : null; })
    .then((j) => { if (j) { sha = j.sha; setDrafts(JSON.parse(unb64(j.content)).sids); } else { sha = null; setDrafts([]); } });
  if (token) loadApi().catch((e) => {
    if (e.message === 'auth') { alert('Токен GitHub не подошёл — режим правки выключен. Откройте страницу с ?edit, чтобы ввести новый.'); try { localStorage.removeItem(KEY); } catch (x) {} WB.canEdit = false; }
    loadPublic();
  });
  else loadPublic();
  let busy = false;
  WB.toggle = async (sid) => {
    if (!token || busy) return;
    busy = true;
    const before = new Set(WB.drafts);
    if (WB.drafts.has(sid)) WB.drafts.delete(sid); else WB.drafts.add(sid);
    redraw();
    try {
      for (let attempt = 0; attempt < 2; attempt++) {
        const body = { message: (WB.drafts.has(sid) ? 'Состав уточняется: ' : 'Состав подтверждён: ') + sid,
          content: b64(JSON.stringify({ sids: [...WB.drafts].sort() }, null, 1) + '\n') };
        if (sha) body.sha = sha;
        const r = await fetch(API, { method: 'PUT', headers: { ...hdr(), 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        if (r.ok) { sha = (await r.json()).content.sha; busy = false; return; }
        if (r.status === 409 || r.status === 422) {
          const want = new Set(WB.drafts);
          await loadApi();
          if (want.has(sid)) WB.drafts.add(sid); else WB.drafts.delete(sid);
          continue;
        }
        throw new Error('HTTP ' + r.status);
      }
      throw new Error('конфликт версий');
    } catch (e) {
      WB.drafts = before; redraw();
      alert('Не удалось сохранить отметку (' + e.message + '). Попробуйте ещё раз.');
    }
    busy = false;
  };
})();
</script>
"""

HEAD = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Поставки WB — INHOMEKA и Гротек</title>
<style>
:root {
  --font-anthropic-sans: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-anthropic-serif: Georgia, "Times New Roman", serif;
  --color-fg: #1f1e1c; --color-fg-muted: #6b6a66; --color-bg: #ffffff; --color-panel: #faf9f5;
  --color-border-line: #e4e2da; --color-ok: #2f8a4f; --color-warn: #b7791f; --color-bad: #c4362c;
  --cds-chart-reference: #2f7fd6;
  --cds-font-size-caption: 12px; --cds-font-size-body: 14px; --cds-font-size-heading: 16px; --cds-font-size-title: 26px;
  --cds-font-weight-medium: 600;
  --cds-gap-xs: 4px; --cds-gap-sm: 8px; --cds-gap-md: 12px; --cds-gap-lg: 20px; --cds-gap-xl: 32px;
  --cds-pad-xs: 4px; --cds-pad-sm: 8px; --cds-pad-md: 12px; --cds-pad-lg: 16px; --cds-pad-xl: 24px;
  --cds-radius: 8px; --cds-dur-slow: .3s;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) { :root {
  --color-fg: #ecebe6; --color-fg-muted: #a3a19a; --color-bg: #1d1d1b; --color-panel: #262624;
  --color-border-line: #3a3936; --color-ok: #5cc285; --color-warn: #e0a64a; --color-bad: #f0796e; --cds-chart-reference: #6aa8ec;
} }
html, body { margin: 0; background: var(--color-bg); }
#dash-root { padding: clamp(12px, 3vw, 32px); max-width: 1600px; margin: 0 auto; }
.wb-stamp { font-family: var(--font-anthropic-sans); font-size: 12px; color: var(--color-fg-muted); margin-top: 24px; }
</style></head><body><div id="dash-root">
"""

doc = (HEAD
       + f'<script type="application/json" id="wb-data">{blob}</script>\n'
       + SHIM
       + html
       + f'\n<p class="wb-stamp">Данные Wildberries на {updated} (МСК). Файл обновляется автоматически утром и вечером.</p>\n'
       + "</div></body></html>\n")
open(out, "w", encoding="utf-8").write(doc)
print(out, len(doc.encode()) // 1024, "КБ")

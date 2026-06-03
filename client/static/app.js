let tools      = [];
let activeTool = null;
let running    = false;

window.addEventListener('DOMContentLoaded', () => {
  pollStatus();
  loadTools();
  setInterval(pollStatus, 4000);
});

async function pollStatus() {
  try {
    const d = await get('/status');
    const ok = d.mcp === 'connected';
    const badge = id('conn-badge');
    badge.className = 'conn-badge ' + (ok ? 'ok' : 'err');
    id('cb-text').textContent = ok ? 'Connected' : 'Disconnected';
    const tb = id('tools-badge');
    tb.textContent = d.tool_count + ' tool' + (d.tool_count !== 1 ? 's' : '');
    tb.className   = 'tools-badge' + (d.tool_count > 0 ? ' has' : '');
  } catch {
    id('conn-badge').className = 'conn-badge err';
    id('cb-text').textContent  = 'Unreachable';
  }
}

async function loadTools() {
  id('tool-list').innerHTML = '<div class="placeholder">Loading…</div>';
  try {
    const d = await get('/tools');
    tools = d.tools || [];
    renderToolList();
  } catch (e) {
    id('tool-list').innerHTML = '<div class="placeholder">Error: ' + e.message + '</div>';
  }
}

function renderToolList() {
  const list = id('tool-list');
  if (!tools.length) { list.innerHTML = '<div class="placeholder">No tools found</div>'; return; }
  list.innerHTML = '';
  tools.forEach(t => {
    const el = document.createElement('div');
    el.className   = 'tool-item';
    el.dataset.name = t.name;
    el.innerHTML   = '<div class="ti-name">' + esc(t.name) + '</div><div class="ti-desc">' + esc(t.description || 'No description') + '</div>';
    el.addEventListener('click', () => selectTool(t.name));
    list.appendChild(el);
  });
}

function selectTool(name) {
  activeTool = tools.find(t => t.name === name);
  if (!activeTool) return;

  document.querySelectorAll('.tool-item').forEach(el => el.classList.toggle('active', el.dataset.name === name));
  id('runner-label').textContent = name;
  id('run-btn').style.display    = 'flex';
  id('run-btn').disabled         = false;

  const props    = (activeTool.inputSchema || {}).properties || {};
  const required = (activeTool.inputSchema || {}).required   || [];
  const names    = Object.keys(props);

  let html = '<div class="td-name">' + esc(name) + '</div><div class="td-desc">' + esc(activeTool.description || 'No description') + '</div>';

  if (!names.length) {
    html += '<div class="sec-label">ARGUMENTS</div><div class="no-args">This tool takes no arguments</div>';
  } else {
    html += '<div class="sec-label">ARGUMENTS</div><div class="arg-list">';
    names.forEach(pname => {
      const p      = props[pname];
      const isReq  = required.includes(pname);
      const defVal = p.default !== undefined ? p.default : '';
      const typ    = p.type || 'any';
      html += '<div class="arg-row">'
            + '<div class="arg-meta">'
            + '<span class="arg-name">' + esc(pname) + '</span>'
            + '<span class="arg-type">' + esc(typ) + '</span>'
            + (isReq ? '<span class="arg-req">required</span>' : '<span class="arg-default">default: ' + esc(String(defVal)) + '</span>')
            + '</div>'
            + '<input class="arg-input" id="arg-' + esc(pname) + '" data-arg="' + esc(pname) + '" data-type="' + esc(typ) + '"'
            + ' placeholder="' + (isReq ? 'required' : String(defVal)) + '"'
            + ' value="' + esc(defVal !== '' ? String(defVal) : '') + '"/>'
            + '</div>';
    });
    html += '</div>';
  }

  id('runner-body').innerHTML = html;

  const inputs = id('runner-body').querySelectorAll('.arg-input');
  inputs.forEach(inp => inp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); runTool(); } }));
  if (inputs[0]) inputs[0].focus();
}

async function runTool() {
  if (!activeTool || running) return;

  const props = (activeTool.inputSchema || {}).properties || {};
  const args  = {};
  Object.keys(props).forEach(pname => {
    const el = id('arg-' + pname);
    if (!el) return;
    const raw = el.value.trim();
    if (raw !== '') args[pname] = coerce(raw, el.dataset.type);
  });

  setRunning(true);
  showPending(activeTool.name);

  try {
    const d = await post('/call', { tool: activeTool.name, arguments: args });
    if (d.error) showResult(activeTool.name, d.error, d.duration_ms || 0, true);
    else         showResult(activeTool.name, d.result, d.duration_ms, d.isError);
    refreshHistory();
  } catch (e) {
    showResult(activeTool.name, e.message, 0, true);
  } finally {
    setRunning(false);
  }
}

function showPending(name) {
  switchTabById('response');
  id('res-empty').style.display = 'none';
  id('res-meta').style.display  = 'flex';
  id('res-name').textContent    = name;
  id('res-ms').textContent      = '';
  id('res-chip').textContent    = '';
  id('res-chip').className      = 'res-chip';
  id('res-body').style.display  = 'none';
}

function showResult(name, text, ms, isErr) {
  id('res-empty').style.display = 'none';
  id('res-meta').style.display  = 'flex';
  id('res-name').textContent    = name;
  id('res-ms').textContent      = ms + ' ms';
  id('res-chip').textContent    = isErr ? 'Error' : 'Success';
  id('res-chip').className      = 'res-chip ' + (isErr ? 'err' : 'ok');
  const b = id('res-body');
  b.style.display = 'block';
  b.className     = 'res-body' + (isErr ? ' is-err' : '');
  b.textContent   = text || '(empty response)';
}

async function refreshHistory() {
  try {
    const d = await get('/history');
    renderHistory(d.history || []);
  } catch {}
}

function renderHistory(items) {
  const list = id('hist-list');
  if (!items.length) { list.innerHTML = '<div class="placeholder">No calls yet</div>'; return; }
  list.innerHTML = '';
  items.forEach(item => {
    const isErr  = item.is_error || !!item.error;
    const el     = document.createElement('div');
    el.className = 'hist-item';
    const astr   = Object.keys(item.arguments || {}).length ? JSON.stringify(item.arguments) : 'no args';
    el.innerHTML = '<div class="hist-item-top"><span class="hist-dot ' + (isErr ? 'err' : 'ok') + '"></span>'
                 + '<span class="hist-name">' + esc(item.tool) + '</span>'
                 + '<span class="hist-time">' + esc(item.ts) + '</span>'
                 + '<span class="hist-ms">'   + item.duration_ms + 'ms</span></div>'
                 + '<div class="hist-args">'  + esc(astr) + '</div>';
    el.addEventListener('click', () => {
      switchTabById('response');
      showResult(item.tool, item.error || item.result || '(empty)', item.duration_ms, isErr);
    });
    list.appendChild(el);
  });
}

async function clearHistory() {
  await fetch('/history', { method: 'DELETE' });
  renderHistory([]);
}

function switchTab(btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  switchTabById(btn.dataset.tab);
  if (btn.dataset.tab === 'history') refreshHistory();
}

function switchTabById(tabId) {
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.add('hidden'));
  const el = id('tab-' + tabId);
  if (el) el.classList.remove('hidden');
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tabId));
}

function setRunning(on) {
  running = on;
  const btn = id('run-btn');
  btn.disabled = on;
  btn.innerHTML = on
    ? '<span class="spin"></span>Running…'
    : '<svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M3 1.5l7 4.5-7 4.5V1.5z" fill="currentColor"/></svg>Run';
}

function coerce(val, type) {
  if (type === 'number' || type === 'integer') { const n = Number(val); return isNaN(n) ? val : n; }
  if (type === 'boolean') return val === 'true' || val === '1';
  return val;
}

function id(x)  { return document.getElementById(x); }
function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
async function get(p)    { const r = await fetch(p); if (!r.ok) throw new Error(r.statusText); return r.json(); }
async function post(p,b) { const r = await fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}); return r.json(); }

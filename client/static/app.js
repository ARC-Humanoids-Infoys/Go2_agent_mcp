let tools = [];
let activeTool = null;
let running = false;

window.addEventListener('DOMContentLoaded', () => {
  pollStatus();
  loadTools();
  loadEnv();
  setInterval(pollStatus, 4000);
});

async function pollStatus() {
  try {
    const d = await get('/status');
    const badge = id('mcp-badge');
    const ok = d.mcp === 'connected';
    badge.textContent = ok ? 'Connected' : 'Disconnected';
    badge.className = 'status-badge ' + (ok ? 'badge-ok' : 'badge-err');
    
    // If disconnected, clear tools to avoid confusion
    if (!ok && tools.length > 0) {
      id('tool-list').innerHTML = '<div class="empty-state">⚠ MCP Disconnected<br/>Start server.py to continue</div>';
    }
  } catch (e) {
    id('mcp-badge').className = 'status-badge badge-err';
    id('mcp-badge').textContent = 'Unreachable';
    id('tool-list').innerHTML = '<div class="empty-state">⚠ Server Unreachable<br/>Check if uvicorn is running</div>';
  }
}

async function loadTools() {
  try {
    const d = await get('/tools');
    tools = d.tools || [];
    renderTools();
  } catch (e) {
    id('tool-list').innerHTML = '<div class="empty-state">Error loading tools</div>';
  }
}

function renderTools() {
  const list = id('tool-list');
  if (!tools.length) {
    list.innerHTML = '<div class="empty-state">No tools found</div>';
    return;
  }
  list.innerHTML = '';
  tools.forEach(t => {
    const el = document.createElement('div');
    el.className = 'tool-item';
    el.dataset.name = t.name;
    el.innerHTML = '<div class="tool-item-name">' + esc(t.name) + '</div>'
                 + '<div class="tool-item-desc">' + esc(t.description || 'No description') + '</div>';
    el.addEventListener('click', () => selectTool(t.name));
    list.appendChild(el);
  });
}

function filterTools() {
  const query = id('tool-search').value.toLowerCase();
  document.querySelectorAll('.tool-item').forEach(el => {
    const name = el.dataset.name || '';
    el.style.display = name.toLowerCase().includes(query) ? '' : 'none';
  });
}

function selectTool(name) {
  activeTool = tools.find(t => t.name === name);
  if (!activeTool) return;

  document.querySelectorAll('.tool-item').forEach(el => {
    const itemName = el.dataset.name || '';
    el.classList.toggle('active', itemName === name);
  });

  showToolInspector();
}

function showToolInspector() {
  const props = (activeTool.inputSchema || {}).properties || {};
  const required = (activeTool.inputSchema || {}).required || [];
  const names = Object.keys(props);

  const content = id('workspace-content');
  let html = '<div class="tool-inspector">'
           + '<h2>' + esc(activeTool.name) + '</h2>'
           + '<p>' + esc(activeTool.description || 'No description') + '</p>';

  if (names.length > 0) {
    html += '<div class="args-section"><h4>Parameters</h4><div class="args-grid">';
    names.forEach(pname => {
      const p = props[pname];
      const isReq = required.includes(pname);
      const typ = p.type || 'string';
      const defVal = p.default !== undefined ? p.default : '';
      html += '<div class="arg-input-group">'
            + '<label>' + esc(pname) + ' <span style="color: var(--text-tertiary);">(' + esc(typ) + ')</span></label>';
      if (!isReq && defVal !== '') {
        html += '<small>Default: ' + esc(String(defVal)) + '</small>';
      } else if (isReq) {
        html += '<small style="color: var(--danger);">Required</small>';
      }
      html += '<input class="arg-input" id="arg-' + esc(pname) + '" data-arg="' + esc(pname) + '" data-type="' + esc(typ) + '"'
            + ' placeholder="' + (isReq ? 'Required' : String(defVal)) + '"'
            + ' value="' + esc(defVal !== '' ? String(defVal) : '') + '"/>'
            + '</div>';
    });
    html += '</div></div>';
  }

  html += '<div class="actions-row">'
        + '<button class="btn-primary" onclick="runTool()">'
        + '<span>▶</span> Run Tool'
        + '</button>'
        + '</div>'
        + '</div>';

  content.innerHTML = html;
  document.querySelectorAll('.arg-input').forEach(inp => {
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') runTool(); });
  });
}

async function runTool() {
  if (!activeTool || running) return;
  
  // Check if MCP is connected first
  try {
    const status = await get('/status');
    if (status.mcp !== 'connected') {
      showResult(activeTool.name, 'Error: MCP Server not connected. Start server.py first.', 0, true);
      addToHistory({ name: activeTool.name, args: {}, result: null, error: 'MCP not connected', ms: 0, ok: false });
      return;
    }
  } catch (e) {
    showResult(activeTool.name, 'Error: Client cannot reach server. Check if uvicorn is running.', 0, true);
    addToHistory({ name: activeTool.name, args: {}, result: null, error: 'Client unreachable', ms: 0, ok: false });
    return;
  }

  const props = (activeTool.inputSchema || {}).properties || {};
  const args = {};
  Object.keys(props).forEach(pname => {
    const el = id('arg-' + pname);
    if (!el) return;
    const raw = el.value.trim();
    if (raw !== '') args[pname] = coerce(raw, el.dataset.type);
  });

  running = true;
  const t0 = Date.now();
  try {
    const d = await post('/call', { tool: activeTool.name, arguments: args });
    const isErr = d.isError || !!d.error;
    showResult(activeTool.name, d.error || d.result || '(empty)', d.duration_ms || 0, isErr);
    addToHistory({ name: activeTool.name, args, result: d.result, error: d.error, ms: d.duration_ms, ok: !isErr });
  } catch (e) {
    const ms = Date.now() - t0;
    showResult(activeTool.name, 'Error: ' + e.message, ms, true);
    addToHistory({ name: activeTool.name, args: {}, result: null, error: e.message, ms: ms, ok: false });
  } finally {
    running = false;
  }
}

function showResult(name, text, ms, isErr) {
  const panel = id('response-panel');
  panel.style.display = 'flex';
  id('response-tool').textContent = name;
  id('response-time').textContent = ms + ' ms';
  const status = id('response-status');
  status.textContent = isErr ? 'Error' : 'Success';
  status.className = 'response-status' + (isErr ? ' error' : '');
  id('response-body').textContent = text || '(empty response)';
}

function closeResponse() {
  id('response-panel').style.display = 'none';
}

function addToHistory(item) {
  const list = id('history-list');
  if (list.firstElementChild && list.firstElementChild.classList.contains('empty-state')) {
    list.innerHTML = '';
  }
  const el = document.createElement('div');
  el.className = 'history-item ' + (item.ok ? 'success' : 'error');
  el.innerHTML = '<div class="history-item-name">' + esc(item.name) + '</div>'
               + '<div class="history-item-time">' + item.ms + 'ms</div>';
  el.addEventListener('click', () => showResult(item.name, item.error || item.result || '(empty)', item.ms, !item.ok));
  list.insertBefore(el, list.firstChild);
}

async function clearHistory() {
  if (confirm('Clear history?')) {
    id('history-list').innerHTML = '<div class="empty-state">No calls yet</div>';
  }
}

async function loadEnv() {
  try {
    console.log('Loading env vars...');
    const d = await get('/env');
    console.log('Loaded env vars:', Object.keys(d.env || {}).length, 'variables');
    renderEnv(d.env || {});
  } catch (e) {
    console.error('Error loading env:', e);
    id('env-list').innerHTML = '<div class="empty-state">Error loading env</div>';
  }
}

function renderEnv(envObj) {
  const list = id('env-list');
  const keys = Object.keys(envObj).sort();

  console.log('Rendering env list with', keys.length, 'variables');

  if (!keys.length) {
    list.innerHTML = '<div class="empty-state">No env vars set<br/>Add one using the form below</div>';
    return;
  }

  list.innerHTML = '';
  keys.forEach(key => {
    const value = envObj[key];
    const el = document.createElement('div');
    el.className = 'env-item';
    const dispVal = value.length > 60 ? value.substring(0, 60) + '…' : value;
    el.innerHTML = '<div class="env-item-left">'
                 + '<div class="env-item-key">' + esc(key) + '</div>'
                 + '<div class="env-item-value" title="' + esc(value) + '">' + esc(dispVal) + '</div>'
                 + '</div>'
                 + '<div class="env-item-actions">'
                 + '<button class="env-item-btn" onclick="copyEnv(' + esc(JSON.stringify(key)) + ', ' + esc(JSON.stringify(value)) + ')">Copy</button>'
                 + '<button class="env-item-btn" onclick="delEnv(' + esc(JSON.stringify(key)) + ')">×</button>'
                 + '</div>';
    list.appendChild(el);
  });
}

function copyEnv(key, value) {
  navigator.clipboard.writeText(key + '=' + value);
}

async function addEnvVar() {
  const keyInput = id('env-key-input');
  const valInput = id('env-val-input');
  const key = keyInput.value.trim();
  const value = valInput.value.trim();

  if (!key) { 
    alert('Please enter a variable name (e.g., ROBOT_IP)');
    return; 
  }

  try {
    console.log('Adding env var:', key, '=', value);
    const result = await post('/env', { key, value });
    console.log('Server response:', result);
    
    if (result.ok) {
      console.log('✓ Variable added successfully');
      alert(`✓ Added: ${key}=${value}`);
      keyInput.value = '';
      valInput.value = '';
      await loadEnv();  // Refresh the list
    } else {
      alert('Error: ' + (result.error || 'Unknown error'));
    }
  } catch (e) {
    console.error('Error adding env var:', e);
    alert('Error adding variable: ' + e.message);
  }
}

async function delEnv(key) {
  if (!confirm('Delete ' + key + '?')) return;
  try {
    await post('/env', { key, value: '' });
    await loadEnv();
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

function openSettings() {
  console.log('Opening settings modal...');
  id('settings-modal').style.display = 'flex';
  loadEnv();
}

function closeSettings() {
  console.log('Closing settings modal');
  id('settings-modal').style.display = 'none';
}

function coerce(val, type) {
  if (type === 'number' || type === 'integer') {
    const n = Number(val);
    return isNaN(n) ? val : n;
  }
  if (type === 'boolean') return val === 'true' || val === '1';
  return val;
}

function id(x) { return document.getElementById(x); }
function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
async function get(p) { const r = await fetch(p); if (!r.ok) throw new Error(r.statusText); return r.json(); }
async function post(p,b) { const r = await fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}); return r.json(); }

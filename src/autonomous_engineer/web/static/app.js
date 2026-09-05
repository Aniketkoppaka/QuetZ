/**
 * QuetZ Chat Control Console Client Application
 * Pure ES Module, zero-dependency engineering console logic.
 */

// Global State
const state = {
  activeSessionId: 'sess-click-2419',
  sessions: [],
  activeSessionData: null,
  system: null
};

// Selectors
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// API Helpers
async function fetchJson(endpoint, options = {}) {
  try {
    const res = await fetch(endpoint, options);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error(`Fetch failed for ${endpoint}:`, err);
    return null;
  }
}

// App Initialization
async function init() {
  setupNavigation();
  setupCommandPalette();
  setupChatInput();
  await loadSessions();
  if (state.activeSessionId) {
    await selectSession(state.activeSessionId);
  }
}

// Setup Left Navigation & Supporting Context Views
function setupNavigation() {
  $$('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      const action = item.dataset.action;
      handleNavAction(action);
    });
  });

  $$('.close-context-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      handleNavAction('show-chat');
    });
  });

  // Session search filter listener
  const searchInput = $('#session-search-input');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      loadSessions(e.target.value);
    });
  }

  // Modal handlers for New Session Form (zero browser alerts)
  const newModal = $('#new-session-modal');
  const openNewModal = () => {
    newModal.classList.remove('hidden');
    $('#session-title-input').value = '';
    $('#session-title-input').focus();
  };
  const closeNewModal = () => {
    newModal.classList.add('hidden');
  };

  $('#btn-new-session').addEventListener('click', openNewModal);
  $('#btn-close-new-modal').addEventListener('click', closeNewModal);
  $('#btn-cancel-new-modal').addEventListener('click', closeNewModal);

  // Close modal when clicking outside dialog
  newModal.addEventListener('click', (e) => {
    if (e.target === newModal) closeNewModal();
  });

  // Submit custom modal form
  $('#form-new-session').addEventListener('submit', async (e) => {
    e.preventDefault();
    const title = $('#session-title-input').value.trim();
    const repo = $('#session-repo-input').value.trim();
    if (!title || !repo) return;

    closeNewModal();

    const newSess = await fetchJson('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, repo })
    });

    if (newSess) {
      await loadSessions();
      await selectSession(newSess.session_id);
    }
  });
}

function handleNavAction(action) {
  const chatFeed = $('#chat-feed-container');
  const panelRepos = $('#panel-repos');
  const panelAgents = $('#panel-agents');
  const panelArtifacts = $('#panel-artifacts');

  // Hide all context panels
  panelRepos.classList.add('hidden');
  panelAgents.classList.add('hidden');
  panelArtifacts.classList.add('hidden');
  chatFeed.classList.add('hidden');

  $$('.nav-item').forEach(i => i.classList.remove('active'));

  if (action === 'show-chat') {
    chatFeed.classList.remove('hidden');
    $(`.nav-item[data-action="show-chat"]`).classList.add('active');
  } else if (action === 'show-repos') {
    panelRepos.classList.remove('hidden');
    $(`.nav-item[data-action="show-repos"]`).classList.add('active');
    loadRepositories();
  } else if (action === 'show-agents') {
    panelAgents.classList.remove('hidden');
    $(`.nav-item[data-action="show-agents"]`).classList.add('active');
    loadAgents();
  } else if (action === 'show-artifacts') {
    panelArtifacts.classList.remove('hidden');
    $(`.nav-item[data-action="show-artifacts"]`).classList.add('active');
    loadArtifacts();
  }
}

// Load Sessions List into Sidebar (with live search filter)
async function loadSessions(filterQuery = '') {
  if (!state.sessions || state.sessions.length === 0) {
    const sessions = await fetchJson('/api/sessions');
    if (!sessions) return;
    state.sessions = sessions;
  }

  const list = $('#session-list');
  list.innerHTML = '';

  const q = filterQuery.toLowerCase().trim();
  const filtered = q
    ? state.sessions.filter(s => s.title.toLowerCase().includes(q) || s.repo.toLowerCase().includes(q))
    : state.sessions;

  if (filtered.length === 0) {
    list.innerHTML = '<li class="text-muted" style="padding: 10px 14px; font-size: 11px;">No matching sessions found.</li>';
    return;
  }

  filtered.forEach(sess => {
    const li = document.createElement('li');
    li.className = `session-item ${sess.session_id === state.activeSessionId ? 'active' : ''}`;
    li.dataset.sessionId = sess.session_id;

    const statusBadge = sess.status === 'COMPLETED' ? 'badge-success' : 'badge-failed';

    li.innerHTML = `
      <div class="session-top">
        <span class="session-name">${escapeHtml(sess.title)}</span>
        <span class="badge ${statusBadge}">${sess.status}</span>
      </div>
      <div class="session-meta">
        <span>${sess.repo}</span>
        <span>${sess.message_count} msgs</span>
      </div>
    `;

    li.addEventListener('click', () => {
      selectSession(sess.session_id);
    });

    list.appendChild(li);
  });
}

// Select a Session and Render its Conversation Thread
async function selectSession(sessionId) {
  state.activeSessionId = sessionId;

  $$('.session-item').forEach(item => {
    if (item.dataset.sessionId === sessionId) item.classList.add('active');
    else item.classList.remove('active');
  });

  const session = await fetchJson(`/api/sessions/${sessionId}`);
  if (!session) return;
  state.activeSessionData = session;

  // Header Title
  const headerTitle = $('#header-session-title');
  headerTitle.querySelector('.sess-title-text').textContent = session.title;
  const statusEl = $('#header-session-status');
  statusEl.textContent = session.status;
  statusEl.className = `badge ${session.status === 'COMPLETED' ? 'badge-success' : 'badge-failed'}`;

  // Render Chat Messages
  renderMessages(session.messages);
  handleNavAction('show-chat');
}

// Render Messages & Inline Engineering Cards
function renderMessages(messages) {
  const stream = $('#chat-messages-stream');
  stream.innerHTML = '';

  messages.forEach(msg => {
    const turn = document.createElement('div');
    const isUser = msg.sender === 'user';
    turn.className = `chat-turn ${isUser ? 'turn-user' : 'turn-agent'}`;

    let cardsHtml = '';
    if (msg.cards && msg.cards.length > 0) {
      cardsHtml = `<div class="turn-cards">`;
      msg.cards.forEach(card => {
        cardsHtml += renderCardHtml(card);
      });
      cardsHtml += `</div>`;
    }

    turn.innerHTML = `
      <div class="turn-header">
        <span class="turn-avatar ${isUser ? 'avatar-user' : 'avatar-agent'}">${isUser ? 'YOU' : 'QUETZ AGENT'}</span>
        <span class="turn-time">${msg.timestamp}</span>
      </div>
      <div class="turn-body">${escapeHtml(msg.text)}</div>
      ${cardsHtml}
    `;

    stream.appendChild(turn);
  });

  // Auto scroll to bottom
  stream.scrollTop = stream.scrollHeight;
}

// Render Individual Engineering Cards with Collapsible Accordion & Actions
function renderCardHtml(card) {
  if (card.type === 'reproduction_proof') {
    const r = card.data;
    return `
      <div class="eng-card">
        <div class="card-top" onclick="this.parentElement.classList.toggle('collapsed')">
          <div class="card-header-left">
            <span class="card-collapse-icon">▼</span>
            <span class="text-green">REPRODUCTION PROOF (FAIL-THEN-PASS)</span>
          </div>
          <div class="card-header-right">
            <span class="card-tag">VACUITY PREVENTION</span>
          </div>
        </div>
        <div class="card-body-content repro-card-body">
          <div class="repro-cmd">❯ ${escapeHtml(r.command)}</div>
          <div class="repro-panes">
            <div class="pane">
              <div class="pane-header text-red">PRE-PATCH (REPRODUCED DEFECT)</div>
              <div>${escapeHtml(r.pre_patch_output)}</div>
            </div>
            <div class="pane">
              <div class="pane-header text-green">POST-PATCH (VERIFIED PASS)</div>
              <div>${escapeHtml(r.post_patch_output)}</div>
            </div>
          </div>
        </div>
      </div>
    `;
  } else if (card.type === 'dag_plan') {
    const plan = card.data;
    let stepsHtml = '';
    plan.steps.forEach(s => {
      stepsHtml += `
        <div class="dag-step-row">
          <div class="step-row-top">
            <strong>${s.step_id} [${s.operation}]</strong>
            <span class="text-cyan">${s.target_file} ❯ ${s.target_symbol}</span>
          </div>
          <div class="step-row-desc">${escapeHtml(s.description)}</div>
          <div class="text-muted" style="font-size: 10px;">Anchor: ${s.anchor_tier}</div>
        </div>
      `;
    });
    return `
      <div class="eng-card">
        <div class="card-top" onclick="this.parentElement.classList.toggle('collapsed')">
          <div class="card-header-left">
            <span class="card-collapse-icon">▼</span>
            <span class="text-cyan">IMPLEMENTATION DAG PLAN</span>
          </div>
          <div class="card-header-right">
            <button class="btn-card-action" onclick="event.stopPropagation(); triggerSteeringAction('Approve & Execute DAG Plan');">APPROVE & EXECUTE</button>
            <span class="card-tag">ACYCLIC GRAPH</span>
          </div>
        </div>
        <div class="card-body-content dag-card-body">
          ${stepsHtml}
        </div>
      </div>
    `;
  } else if (card.type === 'anchor_diff') {
    const diffs = Array.isArray(card.data) ? card.data : [card.data];
    let diffsHtml = '';
    diffs.forEach(d => {
      let linesHtml = '';
      d.hunks.forEach(l => {
        let cls = 'diff-line';
        if (l.startsWith('@@')) cls += ' hunk-head';
        else if (l.startsWith('-')) cls += ' del';
        else if (l.startsWith('+')) cls += ' add';
        linesHtml += `<div class="${cls}">${escapeHtml(l)}</div>`;
      });
      diffsHtml += `
        <div style="margin-bottom: 6px;">
          <div style="font-size: 11px; margin-bottom: 4px; display: flex; justify-content: space-between;">
            <strong>${d.file}</strong>
            <span class="badge tier-1">${d.anchor_tier}</span>
          </div>
          <div class="diff-hunk">${linesHtml}</div>
        </div>
      `;
    });
    return `
      <div class="eng-card">
        <div class="card-top" onclick="this.parentElement.classList.toggle('collapsed')">
          <div class="card-header-left">
            <span class="card-collapse-icon">▼</span>
            <span class="text-green">DETERMINISTIC 4-TIER ANCHOR DIFFS</span>
          </div>
          <div class="card-header-right">
            <span class="card-tag">EXPLICIT BOUNDARY</span>
          </div>
        </div>
        <div class="card-body-content diff-card-body">
          ${diffsHtml}
        </div>
      </div>
    `;
  } else if (card.type === 'verification_certificate') {
    const c = card.data;
    return `
      <div class="eng-card">
        <div class="card-top" onclick="this.parentElement.classList.toggle('collapsed')">
          <div class="card-header-left">
            <span class="card-collapse-icon">▼</span>
            <span class="text-green">VERIFICATION ASSURANCE CERTIFICATE</span>
          </div>
          <div class="card-header-right">
            <button class="btn-card-action" onclick="event.stopPropagation(); navigator.clipboard.writeText('${c.evidence_hash}'); alert('SHA-256 Digest copied to clipboard!');">COPY HASH</button>
            <span class="card-tag">CRYPTOGRAPHIC PROOF</span>
          </div>
        </div>
        <div class="card-body-content cert-card-body">
          <div class="cert-row"><span>Certificate ID:</span> <strong>${c.certificate_id}</strong></div>
          <div class="cert-row"><span>Confidence Score:</span> <strong class="text-green">${(c.confidence_score * 100).toFixed(0)}%</strong></div>
          <div class="cert-row"><span>Static AST Syntax:</span> <span class="text-green">✓ PASSED</span></div>
          <div class="cert-row"><span>Targeted Test Suite:</span> <span class="text-green">✓ PASSED</span></div>
          <div class="cert-row"><span>Independent Model Review:</span> <span class="text-green">✓ APPROVED</span></div>
          <div>
            <span class="text-muted" style="font-size: 10px;">SHA-256 Digest:</span>
            <div class="cert-hash">${c.evidence_hash}</div>
          </div>
        </div>
      </div>
    `;
  } else if (card.type === 'mutation_report') {
    const m = card.data;
    let rowsHtml = '';
    m.operators.forEach(op => {
      rowsHtml += `
        <tr>
          <td>${op.name}</td>
          <td>${op.killed} / ${op.total}</td>
          <td><span class="badge ${op.status === 'KILLED' ? 'badge-success' : 'badge-failed'}">${op.status}</span></td>
        </tr>
      `;
    });
    return `
      <div class="eng-card">
        <div class="card-top" onclick="this.parentElement.classList.toggle('collapsed')">
          <div class="card-header-left">
            <span class="card-collapse-icon">▼</span>
            <span class="text-green">AST MUTATION TESTING MATRIX</span>
          </div>
          <div class="card-header-right">
            <span class="card-tag">${m.score_pct} KILL RATE</span>
          </div>
        </div>
        <div class="card-body-content mut-card-body">
          <table class="mut-table">
            <thead><tr><th>OPERATOR</th><th>KILLED</th><th>OUTCOME</th></tr></thead>
            <tbody>${rowsHtml}</tbody>
          </table>
        </div>
      </div>
    `;
  } else if (card.type === 'flight_recorder') {
    const evs = card.data;
    let evHtml = '';
    evs.forEach(e => {
      evHtml += `
        <div class="flight-line">
          <span class="text-muted">${e.timestamp}</span>
          <span class="text-cyan">[${e.phase}]</span>
          <span>${escapeHtml(e.event)}</span>
        </div>
      `;
    });
    return `
      <div class="eng-card">
        <div class="card-top" onclick="this.parentElement.classList.toggle('collapsed')">
          <div class="card-header-left">
            <span class="card-collapse-icon">▼</span>
            <span class="text-muted">FLIGHT RECORDER TRACE</span>
          </div>
          <div class="card-header-right">
            <span class="card-tag">IMMUTABLE JSONL</span>
          </div>
        </div>
        <div class="card-body-content flight-card-body">
          ${evHtml}
        </div>
      </div>
    `;
  }
  return '';
}

// Setup Chat Input Handling & Quick Action Chips
function setupChatInput() {
  const input = $('#chat-input');
  const sendBtn = $('#btn-send-message');

  const sendMessage = async (overrideText = null) => {
    const text = overrideText !== null ? overrideText.trim() : input.value.trim();
    if (!text || !state.activeSessionId) return;
    if (overrideText === null) input.value = '';

    // Optimistically render user message
    const tempUserMsg = {
      id: `temp-${Date.now()}`,
      sender: 'user',
      timestamp: new Date().toTimeString().split(' ')[0],
      text: text,
      cards: []
    };

    state.activeSessionData.messages.push(tempUserMsg);
    renderMessages(state.activeSessionData.messages);

    // Post to Server
    const response = await fetchJson(`/api/sessions/${state.activeSessionId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });

    if (response) {
      state.activeSessionData.messages.push(response);
      renderMessages(state.activeSessionData.messages);
    }
  };

  // Expose global steering trigger for card action buttons
  window.triggerSteeringAction = (actionText) => {
    sendMessage(actionText);
  };

  // Wire Quick Action Chips
  $$('.chip-btn').forEach(chip => {
    chip.addEventListener('click', () => {
      const action = chip.dataset.action;
      if (action === 'quick-plan') {
        sendMessage('Please synthesize an acyclic DAG implementation plan.');
      } else if (action === 'quick-test') {
        sendMessage('Run targeted pytest verification suite.');
      } else if (action === 'quick-mutation') {
        sendMessage('Run AST mutation testing matrix and calculate kill score.');
      } else if (action === 'quick-rollback') {
        sendMessage('Check safety boundary and verify rollback snapshot readiness.');
      }
    });
  });

  sendBtn.addEventListener('click', () => sendMessage());

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
}

// Supporting Views Loaders
async function loadRepositories() {
  const repos = await fetchJson('/api/repositories');
  if (!repos) return;
  const container = $('#repos-container');
  container.innerHTML = '';
  repos.forEach(repo => {
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <div class="card-title text-cyan">${repo.repo_name}</div>
      <div class="card-desc">AST Status: <span class="text-green">${repo.ast_status}</span></div>
      <div class="card-meta">
        <div>Files: <strong>${repo.files_indexed}</strong> | Symbols: <strong>${repo.symbols_count}</strong></div>
        <div style="margin-top: 4px;">Top Modules: ${repo.top_modules.join(', ')}</div>
      </div>
    `;
    container.appendChild(card);
  });
}

async function loadAgents() {
  const agents = await fetchJson('/api/agents');
  if (!agents) return;
  const container = $('#agents-container');
  container.innerHTML = '';
  agents.forEach(agent => {
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <div class="card-title text-green">${agent.role}</div>
      <div class="card-desc">${agent.purpose}</div>
      <div class="card-meta">
        <div><strong>Safety:</strong> ${agent.safety_boundary}</div>
        <div style="margin-top: 4px;"><strong>Capabilities:</strong> ${agent.capabilities.join(', ')}</div>
      </div>
    `;
    container.appendChild(card);
  });
}

async function loadArtifacts() {
  const artifacts = await fetchJson('/api/artifacts');
  if (!artifacts) return;
  const container = $('#artifacts-container');
  container.innerHTML = '';
  artifacts.forEach(art => {
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <div class="card-title text-cyan">${art.name}</div>
      <div class="card-desc">Type: <strong>${art.type}</strong></div>
      <div class="card-meta">
        <div>Hash: ${art.hash.substring(0, 24)}...</div>
        <div>Created: ${art.created_at}</div>
      </div>
    `;
    container.appendChild(card);
  });
}

// Command Palette (Ctrl+K)
function setupCommandPalette() {
  const modal = $('#cmd-modal');
  const input = $('#cmd-input');
  const results = $('#cmd-results');
  const launcher = $('#cmd-launcher');

  const openPalette = () => {
    modal.classList.remove('hidden');
    input.value = '';
    renderCommandResults('');
    input.focus();
  };

  const closePalette = () => {
    modal.classList.add('hidden');
  };

  launcher.addEventListener('click', openPalette);

  window.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      if (modal.classList.contains('hidden')) openPalette();
      else closePalette();
    }
    if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
      closePalette();
    }
  });

  input.addEventListener('input', () => {
    renderCommandResults(input.value.trim().toLowerCase());
  });

  function renderCommandResults(filter) {
    results.innerHTML = '';
    const actions = [
      { label: 'View: Active Chat Thread', action: () => handleNavAction('show-chat'), tag: 'VIEW' },
      { label: 'View: Indexed Repositories', action: () => handleNavAction('show-repos'), tag: 'VIEW' },
      { label: 'View: Agent Hierarchy', action: () => handleNavAction('show-agents'), tag: 'VIEW' },
      { label: 'View: Generated Artifacts', action: () => handleNavAction('show-artifacts'), tag: 'VIEW' },
      ...state.sessions.map(s => ({
        label: `Switch Session: ${s.title}`,
        action: () => selectSession(s.session_id),
        tag: 'SESSION'
      }))
    ];

    const filtered = actions.filter(a => a.label.toLowerCase().includes(filter));
    filtered.forEach((act, idx) => {
      const item = document.createElement('div');
      item.className = `cmd-item ${idx === 0 ? 'active' : ''}`;
      item.innerHTML = `
        <span>${escapeHtml(act.label)}</span>
        <span class="cmd-item-tag">${act.tag}</span>
      `;
      item.addEventListener('click', () => {
        act.action();
        closePalette();
      });
      results.appendChild(item);
    });
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

window.addEventListener('DOMContentLoaded', init);

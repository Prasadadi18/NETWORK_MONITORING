/* ===================================================================
   Network Guardian — Client-side Socket.IO + UI Logic
   =================================================================== */

// ---- Socket.IO Connection ----
const socket = io();

// ---- DOM References ----
const packetTableBody = document.getElementById('packet-table-body');
const packetCount     = document.getElementById('packet-count');
const threatList      = document.getElementById('threat-list');
const threatCount     = document.getElementById('threat-count');
const logBody         = document.getElementById('log-body');
const blockCount      = document.getElementById('block-count');
const blockedIps      = document.getElementById('blocked-ips');
const clockEl         = document.getElementById('clock');
const statusDot       = document.getElementById('status-dot');

const MAX_PACKET_ROWS = 60;
const MAX_LOG_LINES   = 30;
const MAX_THREATS     = 10;

let totalPackets = 0;

// ---- Clock ----
function updateClock() {
  const now = new Date();
  clockEl.textContent = now.toLocaleTimeString('en-US', { hour12: false });
}
setInterval(updateClock, 1000);
updateClock();

// ---- Helpers ----
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3200);
}

function classifyLogMsg(msg) {
  const lower = msg.toLowerCase();
  if (lower.includes('threat'))    return 'msg-threat';
  if (lower.includes('mitigat'))   return 'msg-mitigator';
  if (lower.includes('llm'))       return 'msg-llm';
  if (lower.includes('sniffer'))   return 'msg-sniffer';
  if (lower.includes('detector'))  return 'msg-detector';
  if (lower.includes('error') || lower.includes('fail')) return 'msg-error';
  if (lower.includes('user'))      return 'msg-user';
  if (lower.includes('system'))    return 'msg-system';
  return '';
}

function stripRichMarkup(text) {
  // Remove Rich markup like [bold red], [/], [bold green], etc.
  return text.replace(/\[\/?\s*[^\]]*\]/g, '');
}

// ---- Socket Events ----

socket.on('connect', () => {
  statusDot.style.background = 'var(--green)';
  statusDot.style.boxShadow = '0 0 8px var(--green)';

  // Clear stale UI state after a disconnect/reconnect.
  packetTableBody.innerHTML = '';
  totalPackets = 0;
  packetCount.textContent = '0';
  threatList.innerHTML = '<div class="threat-empty">🛡️ No threats detected</div>';
  threatCount.textContent = '0';
  logBody.innerHTML = '';
  blockCount.textContent = '0';
  blockedIps.textContent = '';
  blockedIps.style.display = 'none';

  showToast('Connected to Network Guardian', 'success');
});

socket.on('disconnect', () => {
  statusDot.style.background = 'var(--red)';
  statusDot.style.boxShadow = '0 0 8px var(--red)';
  showToast('Disconnected from server', 'error');
});

// --- Packet Feed ---
socket.on('packet_feed', (data) => {
  const packets = data.packets;
  if (!packets || packets.length === 0) return;

  totalPackets += packets.length;
  packetCount.textContent = totalPackets;

  packets.forEach(pkt => {
    const tr = document.createElement('tr');
    tr.className = 'packet-row';

    const time = new Date(pkt.timestamp * 1000).toLocaleTimeString('en-US', { hour12: false });
    const port = pkt.dst_port !== null && pkt.dst_port !== undefined ? escapeHtml(pkt.dst_port.toString()) : '-';

    tr.innerHTML = `
      <td class="col-time">${time}</td>
      <td class="col-ip">${escapeHtml(pkt.source_ip)}</td>
      <td class="col-ip dest">${escapeHtml(pkt.dest_ip || '-')}</td>
      <td class="col-proto">
        <span class="proto-badge proto-${escapeHtml(pkt.protocol)}">${escapeHtml(pkt.protocol)}</span>
      </td>
      <td class="col-port">${port}</td>
    `;

    // Insert at top
    if (packetTableBody.firstChild) {
      packetTableBody.insertBefore(tr, packetTableBody.firstChild);
    } else {
      packetTableBody.appendChild(tr);
    }
  });

  // Trim old rows
  while (packetTableBody.children.length > MAX_PACKET_ROWS) {
    packetTableBody.removeChild(packetTableBody.lastChild);
  }
});

// --- Threat Alerts ---
socket.on('threat_feed', (data) => {
  const threats = data.threats;
  if (!threats || threats.length === 0) return;

  threatCount.textContent = threats.length;

  // Clear and rebuild (simpler than diffing for threat cards)
  threatList.innerHTML = '';

  if (threats.length === 0) {
    threatList.innerHTML = '<div class="threat-empty">🛡️ No threats detected</div>';
    return;
  }

  // Show newest first
  threats.reverse().forEach(threat => {
    const card = document.createElement('div');
    card.className = 'threat-card';

    const time = new Date(threat.detection_time * 1000).toLocaleTimeString('en-US', { hour12: false });
    const status = threat.mitigation_status || 'PENDING';
    const reasoning = threat.llm_reasoning
      ? escapeHtml(stripRichMarkup(threat.llm_reasoning))
      : 'Analyzing...';

    card.innerHTML = `
      <div class="threat-card-header">
        <span class="threat-ip">⚠ ${escapeHtml(threat.attacker_ip)}</span>
        <span class="threat-type">${escapeHtml(threat.attack_type)}</span>
      </div>
      <div class="threat-meta">
        <span>🕐 ${time}</span>
        <span>📦 ${threat.packet_count} pkts</span>
        <span class="status-badge status-${status}">${status}</span>
      </div>
      <div class="threat-reasoning">${reasoning}</div>
    `;

    threatList.appendChild(card);
  });
});

// --- System Logs ---
socket.on('log_feed', (data) => {
  const logs = data.logs;
  if (!logs || logs.length === 0) return;

  logs.forEach(msg => {
    const cleanMsg = stripRichMarkup(msg);
    const line = document.createElement('div');
    line.className = 'log-line';

    const now = new Date().toLocaleTimeString('en-US', { hour12: false });
    const msgClass = classifyLogMsg(cleanMsg);

    line.innerHTML = `
      <span class="log-time">${now}</span>
      <span class="log-msg ${msgClass}">${escapeHtml(cleanMsg)}</span>
    `;

    logBody.appendChild(line);
  });

  // Trim
  while (logBody.children.length > MAX_LOG_LINES) {
    logBody.removeChild(logBody.firstChild);
  }

  // Auto-scroll
  logBody.scrollTop = logBody.scrollHeight;
});

// --- Status Update ---
socket.on('status_update', (data) => {
  blockCount.textContent = data.active_blocks || 0;
  if (data.blocked_ips && data.blocked_ips.length > 0) {
    blockedIps.textContent = data.blocked_ips.join(', ');
    blockedIps.style.display = 'inline';
  } else {
    blockedIps.textContent = '';
    blockedIps.style.display = 'none';
  }
});

// ---- Attack Controls ----

async function launchAttack(attackType) {
  const btn = document.querySelector(`[data-attack="${attackType}"]`);
  const rate = parseInt(document.getElementById('config-rate').value) || 150;
  const duration = parseInt(document.getElementById('config-duration').value) || 10;

  if (btn) {
    btn.classList.add('running');
    btn.style.setProperty('--duration', `${duration}s`);
  }

  showToast(`Launching ${attackType.replace('_', ' ').toUpperCase()}...`, 'info');

  try {
    const resp = await fetch('/api/attack', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        attack: attackType,
        rate: rate,
        duration: duration
      })
    });

    const result = await resp.json();

    if (result.status === 'started') {
      showToast(`${attackType.replace('_', ' ').toUpperCase()} started!`, 'success');
    } else {
      showToast(result.message || 'Attack failed', 'error');
    }
  } catch (err) {
    showToast('Failed to connect to server', 'error');
  }

  // Remove running state after duration
  if (btn) {
    setTimeout(() => btn.classList.remove('running'), duration * 1000);
  }
}

async function flushBlocks() {
  showToast('Flushing all blocks...', 'info');
  try {
    const resp = await fetch('/api/flush', { method: 'POST' });
    const result = await resp.json();
    showToast(result.message || 'Blocks flushed', 'success');
  } catch (err) {
    showToast('Failed to flush blocks', 'error');
  }
}

async function shutdownServer() {
  if (!confirm('Are you sure you want to shut down Network Guardian?')) return;

  showToast('Shutting down...', 'error');
  try {
    await fetch('/api/shutdown', { method: 'POST' });
  } catch (err) {
    // Expected — server shuts down
  }
}

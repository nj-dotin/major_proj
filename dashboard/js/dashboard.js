/**
 * NewVision Tactical Multi-Modal Dashboard Controller
 * Manages WebSocket telemetry stream, UI state updates, controls, and session exports.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Initialize Radar Canvas
  const radarRenderer = new RadarCanvasRenderer('radarCanvas');

  // Initialize Wi-Fi RSSI Chart (-90 to -30 dBm)
  const wifiChart = new RollingWaveformChart('wifiChartCanvas', {
    maxPoints: 80,
    minY: -95,
    maxY: -25,
    series: [
      { key: 'radar_rssi', color: '#00e5ff', label: 'ESP32 #1 Radar' },
      { key: 'mag_rssi', color: '#a855f7', label: 'ESP32 #2 Mag' }
    ]
  });

  // Initialize Magnetometer Waveform Chart (Auto-scaled)
  const magChart = new RollingWaveformChart('magChartCanvas', {
    maxPoints: 80,
    autoScale: true,
    series: [
      { key: 'bx', color: '#ef4444', label: 'Bx' },
      { key: 'by', color: '#10b981', label: 'By' },
      { key: 'bz', color: '#00e5ff', label: 'Bz' }
    ]
  });

  // State
  let ws = null;
  let isDemoMode = true;
  let isRecording = false;

  // DOM Elements
  const modeBadge = document.getElementById('modeBadge');
  const btnToggleMode = document.getElementById('btnToggleMode');
  const demoBanner = document.getElementById('demoBanner');
  const btnCalibrateMag = document.getElementById('btnCalibrateMag');
  const btnRecord = document.getElementById('btnRecord');
  const btnExportJson = document.getElementById('btnExportJson');
  const btnExportCsv = document.getElementById('btnExportCsv');
  const simObjectSelect = document.getElementById('simObjectSelect');
  const logFeed = document.getElementById('logFeed');

  function addLog(text) {
    if (!logFeed) return;
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    const timeStr = new Date().toLocaleTimeString();
    entry.innerHTML = `<span class="log-time">[${timeStr}]</span> <span class="log-text">${text}</span>`;
    logFeed.appendChild(entry);
    logFeed.scrollTop = logFeed.scrollHeight;
    while (logFeed.children.length > 50) {
      logFeed.removeChild(logFeed.firstChild);
    }
  }

  // WebSocket Connection
  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      addLog('Connected to NewVision telemetry stream.');
      document.getElementById('sysStatusDot').classList.remove('offline');
      document.getElementById('sysStatusText').textContent = 'CONNECTED';
    };

    ws.onmessage = (event) => {
      try {
        const state = JSON.parse(event.data);
        updateDashboard(state);
      } catch (e) {
        console.error('Error parsing telemetry frame:', e);
      }
    };

    ws.onclose = () => {
      addLog('Telemetry connection closed. Reconnecting in 2s...');
      document.getElementById('sysStatusDot').classList.add('offline');
      document.getElementById('sysStatusText').textContent = 'RECONNECTING';
      setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
      ws.close();
    };
  }

  // Update UI Elements with Latest Frame
  function updateDashboard(state) {
    isDemoMode = state.is_demo_mode;
    updateModeIndicators();

    // 1. Device Nodes
    updateNodeCard('nodeAp', state.node_ap);
    updateNodeCard('nodeRadar', state.node_radar);
    updateNodeCard('nodeMag', state.node_mag);

    // 2. Radar Tracking
    const radar = state.radar || {};
    const targets = radar.targets || [];
    radarRenderer.updateTargets(targets);

    document.getElementById('radarTargetCount').textContent = `${radar.target_count || 0} TARGETS`;
    document.getElementById('radarStatusBadge').textContent = radar.sensor_status || 'UNKNOWN';
    document.getElementById('radarErrorsBadge').textContent = `ERR: ${radar.parser_errors || 0}`;

    // Target Table
    const tableBody = document.getElementById('radarTargetTableBody');
    if (tableBody) {
      if (targets.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#666;">No targets in field of view</td></tr>';
      } else {
        tableBody.innerHTML = targets.map(t => `
          <tr>
            <td><b style="color:#00e5ff">T${t.target_id}</b></td>
            <td>(${t.x_m.toFixed(2)}m, ${t.y_m.toFixed(2)}m)</td>
            <td><b>${t.distance_m.toFixed(2)} m</b></td>
            <td style="color:${t.speed_ms > 0 ? '#f59e0b' : '#00e5ff'}">${t.speed_ms > 0 ? '+' : ''}${t.speed_ms.toFixed(2)} m/s (${t.speed_cms} cm/s)</td>
            <td><span class="brand-badge" style="background:rgba(16,185,129,0.15);color:#10b981">TRACKED</span></td>
          </tr>
        `).join('');
      }
    }

    // 3. Wi-Fi & CSI
    const wifiRadar = state.wifi_radar_node || {};
    const wifiMag = state.wifi_mag_node || {};

    wifiChart.push({
      radar_rssi: wifiRadar.rssi_dbm,
      mag_rssi: wifiMag.rssi_dbm
    });

    document.getElementById('wifiRadarRssi').textContent = wifiRadar.rssi_dbm ? `${wifiRadar.rssi_dbm} dBm` : '--';
    document.getElementById('wifiMagRssi').textContent = wifiMag.rssi_dbm ? `${wifiMag.rssi_dbm} dBm` : '--';
    document.getElementById('csiPacketRate').textContent = `${(wifiRadar.csi_packet_rate || 0).toFixed(0)} Hz`;

    const csiVariance = wifiRadar.csi_amplitude_variance;
    document.getElementById('csiVariance').textContent = csiVariance !== null && csiVariance !== undefined ? csiVariance.toFixed(2) : '--';

    const motionHeuristic = wifiRadar.motion_heuristic || 'QUIET';
    const motionElem = document.getElementById('wifiMotionHeuristic');
    motionElem.textContent = motionHeuristic;
    motionElem.style.color = motionHeuristic === 'ACTIVE' ? '#f59e0b' : (motionHeuristic === 'SUBTLE' ? '#00e5ff' : '#10b981');

    // 4. Magnetometer
    const mag = state.magnetometer || {};
    magChart.push({
      bx: mag.bx,
      by: mag.by,
      bz: mag.bz
    });

    document.getElementById('magChipLabel').textContent = mag.sensor_chip || 'UNKNOWN';
    document.getElementById('magCalibBadge').textContent = mag.calibration_status || 'UNCALIBRATED';
    document.getElementById('magCalibBadge').style.color = mag.calibration_status === 'CALIBRATED' ? '#10b981' : '#f59e0b';

    document.getElementById('magMagnitude').textContent = `${(mag.magnitude || 0).toFixed(1)} µT`;
    document.getElementById('magDelta').textContent = `Δ ${(mag.delta_magnitude || 0).toFixed(2)} µT`;
    document.getElementById('magReadout').textContent = `Bx: ${(mag.bx||0).toFixed(1)} | By: ${(mag.by||0).toFixed(1)} | Bz: ${(mag.bz||0).toFixed(1)}`;

    // 5. MTC-1 Threat Model
    const mtc = state.mtc || {};
    document.getElementById('mtcStatusBadge').textContent = mtc.status || 'UNKNOWN';
    document.getElementById('mtcStatusBadge').style.borderColor = mtc.threat_color || '#888';
    document.getElementById('mtcStatusBadge').style.color = mtc.threat_color || '#888';

    const classElem = document.getElementById('mtcPredictedClass');
    classElem.textContent = mtc.predicted_class || mtc.status || '--';
    classElem.style.color = mtc.threat_color || '#fff';

    document.getElementById('mtcConfidence').textContent = mtc.confidence_percent ? `${mtc.confidence_percent.toFixed(1)}%` : '';
    document.getElementById('mtcThreatBadge').textContent = mtc.threat_level || 'NONE';
    document.getElementById('mtcThreatBadge').style.backgroundColor = `${mtc.threat_color}22` || 'transparent';
    document.getElementById('mtcThreatBadge').style.color = mtc.threat_color || '#fff';
    document.getElementById('mtcExplanation').textContent = mtc.explanation || '';
    document.getElementById('mtcDistanceSource').textContent = mtc.distance_source || '';

    // Probability Bars
    const allProbs = mtc.all_probabilities || {};
    const probContainer = document.getElementById('probBarsContainer');
    if (probContainer && Object.keys(allProbs).length > 0) {
      probContainer.innerHTML = Object.entries(allProbs).map(([className, p]) => `
        <div class="prob-item">
          <div class="prob-label-row">
            <span>${className}</span>
            <span><b>${p.toFixed(1)}%</b></span>
          </div>
          <div class="prob-bar-track">
            <div class="prob-bar-fill" style="width:${p}%; background:${className === mtc.predicted_class ? mtc.threat_color : 'rgba(0,229,255,0.4)'}"></div>
          </div>
        </div>
      `).join('');
    }

    // 6. Sensor Fusion
    const fusion = state.fusion || {};
    const presenceElem = document.getElementById('fusionPresenceState');
    presenceElem.textContent = fusion.presence_state || 'CLEAR';
    presenceElem.style.color = fusion.presence_state.includes('TARGET') || fusion.presence_state.includes('PRESENCE') ? '#00e5ff' : '#10b981';

    const threatElem = document.getElementById('fusionThreatState');
    threatElem.textContent = fusion.threat_state || 'NONE';
    threatElem.style.color = fusion.threat_state === 'CRITICAL' ? '#ff0055' : (fusion.threat_state === 'HIGH' ? '#ef4444' : (fusion.threat_state === 'ELEVATED_FERROUS' ? '#f59e0b' : '#10b981'));

    document.getElementById('fusionSummary').textContent = fusion.explainable_summary || '';

    // Supporting List
    const supportList = document.getElementById('fusionSupportingList');
    if (supportList) {
      const items = fusion.supporting_sensors || [];
      supportList.innerHTML = items.length > 0 
        ? items.map(s => `<li>✓ ${s}</li>`).join('')
        : '<li style="background:transparent;color:#666">No active supporting evidence</li>';
    }

    // Contradicting List
    const conflictList = document.getElementById('fusionConflictingList');
    if (conflictList) {
      const items = fusion.conflicting_sensors || [];
      conflictList.innerHTML = items.length > 0
        ? items.map(c => `<li>⚠ ${c}</li>`).join('')
        : '<li style="background:transparent;color:#666">No conflicting streams</li>';
    }

    // Freshness readouts
    const freshness = fusion.freshness || {};
    document.getElementById('freshnessRadar').textContent = `Radar: ${freshness.radar_sec !== undefined ? freshness.radar_sec.toFixed(2) : '--'}s`;
    document.getElementById('freshnessWifi').textContent = `Wi-Fi: ${freshness.wifi_sec !== undefined ? freshness.wifi_sec.toFixed(2) : '--'}s`;
    document.getElementById('freshnessMag').textContent = `Mag: ${freshness.mag_sec !== undefined ? freshness.mag_sec.toFixed(2) : '--'}s`;
  }

  function updateNodeCard(prefix, nodeData) {
    const dot = document.getElementById(`${prefix}Dot`);
    const ip = document.getElementById(`${prefix}Ip`);
    const rate = document.getElementById(`${prefix}Rate`);
    const uptime = document.getElementById(`${prefix}Uptime`);

    if (!nodeData || !nodeData.wifi_connected) {
      if (dot) dot.className = 'node-status-dot offline';
      if (ip) ip.textContent = 'OFFLINE';
      if (rate) rate.textContent = '--';
      if (uptime) uptime.textContent = '--';
      return;
    }

    if (dot) dot.className = 'node-status-dot';
    if (ip) ip.textContent = nodeData.ip_address || 'Connected';
    if (rate) rate.textContent = `${(nodeData.packet_rate_hz || 0).toFixed(0)} pps`;
    if (uptime) {
      const sec = Math.floor((nodeData.uptime_ms || 0) / 1000);
      const mins = Math.floor(sec / 60);
      uptime.textContent = `${mins}m ${sec % 60}s`;
    }
  }

  function updateModeIndicators() {
    if (isDemoMode) {
      modeBadge.textContent = 'DEMO / SIMULATED DATA';
      modeBadge.className = 'brand-badge' + ' btn-mode-demo';
      btnToggleMode.className = 'btn btn-mode-demo';
      btnToggleMode.innerHTML = '<span>⚡ Mode: SIMULATED</span>';
      demoBanner.classList.remove('hidden');
      if (simObjectSelect) simObjectSelect.style.display = 'inline-block';
    } else {
      modeBadge.textContent = 'LIVE HARDWARE';
      modeBadge.className = 'brand-badge' + ' btn-mode-live';
      btnToggleMode.className = 'btn btn-mode-live';
      btnToggleMode.innerHTML = '<span>📡 Mode: LIVE HARDWARE</span>';
      demoBanner.classList.add('hidden');
      if (simObjectSelect) simObjectSelect.style.display = 'none';
    }
  }

  // Toggle Mode
  btnToggleMode.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/mode/toggle', { method: 'POST' });
      const data = await res.json();
      isDemoMode = data.is_demo_mode;
      updateModeIndicators();
      addLog(`Switched mode to: ${data.mode_label}`);
    } catch (e) {
      addLog(`Error toggling mode: ${e}`);
    }
  });

  // Zero / Calibrate Magnetometer
  btnCalibrateMag.addEventListener('click', async () => {
    try {
      btnCalibrateMag.disabled = true;
      btnCalibrateMag.textContent = 'Zeroing...';
      const res = await fetch('/api/magnetometer/calibrate', { method: 'POST' });
      const data = await res.json();
      addLog(data.message || 'Magnetometer calibrated to baseline.');
    } catch (e) {
      addLog(`Calibration error: ${e}`);
    } finally {
      btnCalibrateMag.disabled = false;
      btnCalibrateMag.textContent = 'Zero Magnetometer';
    }
  });

  // Simulator Object Selector
  if (simObjectSelect) {
    simObjectSelect.addEventListener('change', async (e) => {
      const selected = e.target.value;
      try {
        await fetch('/api/simulator/object', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ object_type: selected })
        });
        addLog(`Demo simulated object set to: ${selected.toUpperCase()}`);
      } catch (err) {
        addLog(`Error setting object: ${err}`);
      }
    });
  }

  // Session Recording Controls
  btnRecord.addEventListener('click', async () => {
    try {
      if (!isRecording) {
        const res = await fetch('/api/session/start', { method: 'POST' });
        const data = await res.json();
        isRecording = true;
        btnRecord.classList.add('recording');
        btnRecord.innerHTML = '<span>⏹ Stop Recording</span>';
        addLog('Session recording started.');
      } else {
        const res = await fetch('/api/session/stop', { method: 'POST' });
        const data = await res.json();
        isRecording = false;
        btnRecord.classList.remove('recording');
        btnRecord.innerHTML = '<span>⏺ Record Session</span>';
        addLog(`Session recording stopped (${data.sample_count} samples, ${data.duration_sec}s).`);
      }
    } catch (e) {
      addLog(`Recording error: ${e}`);
    }
  });

  btnExportJson.addEventListener('click', () => {
    window.location.href = '/api/session/export/json';
    addLog('Exporting session as JSON...');
  });

  btnExportCsv.addEventListener('click', () => {
    window.location.href = '/api/session/export/csv';
    addLog('Exporting session as CSV...');
  });

  // Initialize WebSocket connection
  connectWebSocket();
});

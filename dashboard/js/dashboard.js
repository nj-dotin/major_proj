/**
 * NewVision System Platform — Dashboard Controller
 * Manages live WebSocket telemetry ingestion, Section A-E DOM updates,
 * real-time dual-receiver RSSI/mag charts, radar canvas, and session recording.
 */

document.addEventListener('DOMContentLoaded', () => {
  // ── 1. Visualizations Initialization ─────────────────────────────────────
  const radarRenderer = new RadarCanvasRenderer('radarCanvas');

  // Dual-receiver Wi-Fi RSSI chart (-95 to -20 dBm)
  const wifiChart = new RollingWaveformChart('wifiChartCanvas', {
    maxPoints: 80,
    minY: -95,
    maxY: -20,
    series: [
      { key: 'rx1_rssi', color: '#00e5ff', label: 'Rx1 (Radar Node)' },
      { key: 'rx2_rssi', color: '#a855f7', label: 'Rx2 (Mag Node)' }
    ]
  });

  // 3-Axis Magnetometer Waveform Chart (Auto-scaled)
  const magChart = new RollingWaveformChart('magChartCanvas', {
    maxPoints: 80,
    autoScale: true,
    series: [
      { key: 'bx', color: '#ef4444', label: 'Bx' },
      { key: 'by', color: '#10b981', label: 'By' },
      { key: 'bz', color: '#00e5ff', label: 'Bz' }
    ]
  });

  // ── 2. State & Variables ─────────────────────────────────────────────────
  let ws = null;
  let isDemoMode = true;
  let isRecording = false;
  let lastPacketTime = Date.now();

  // ── 3. DOM Elements ──────────────────────────────────────────────────────
  const sysStatusDot = document.getElementById('sysStatusDot');
  const sysStatusText = document.getElementById('sysStatusText');
  const demoBanner = document.getElementById('demoBanner');
  const btnToggleMode = document.getElementById('btnToggleMode');
  const modeStatusDot = document.getElementById('modeStatusDot');
  const modeLabelText = document.getElementById('modeLabelText');
  const simObjectSelect = document.getElementById('simObjectSelect');
  const demoControlsWrapper = document.getElementById('demoControlsWrapper');

  const btnCalibrateMag = document.getElementById('btnCalibrateMag');
  const btnZeroBaselineInline = document.getElementById('btnZeroBaselineInline');
  const btnRecord = document.getElementById('btnRecord');
  const recordBtnText = document.getElementById('recordBtnText');
  const btnExportCsv = document.getElementById('btnExportCsv');
  const btnExportJson = document.getElementById('btnExportJson');
  const btnClearSession = document.getElementById('btnClearSession');
  const logFeed = document.getElementById('logFeed');

  // Helper: Log Feed
  function addLog(text) {
    if (!logFeed) return;
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    const timeStr = new Date().toLocaleTimeString();
    entry.innerHTML = `<span class="log-time">[${timeStr}]</span> <span class="log-text">${text}</span>`;
    logFeed.appendChild(entry);
    logFeed.scrollTop = logFeed.scrollHeight;
    while (logFeed.children.length > 60) {
      logFeed.removeChild(logFeed.firstChild);
    }
  }

  // ── 4. WebSocket Streaming ───────────────────────────────────────────────
  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      addLog('Connected to NewVision telemetry stream (20 Hz).');
      if (sysStatusDot) {
        sysStatusDot.className = 'status-indicator-dot online';
      }
      if (sysStatusText) sysStatusText.textContent = 'CONNECTED';
    };

    ws.onmessage = (event) => {
      try {
        const state = JSON.parse(event.data);
        lastPacketTime = Date.now();
        updateDashboard(state);
      } catch (e) {
        console.error('Error parsing telemetry frame:', e);
      }
    };

    ws.onclose = () => {
      addLog('WebSocket connection closed. Reconnecting in 2s...');
      if (sysStatusDot) {
        sysStatusDot.className = 'status-indicator-dot offline';
      }
      if (sysStatusText) sysStatusText.textContent = 'DISCONNECTED';
      setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
      ws.close();
    };
  }

  // ── 5. Main Dashboard Update Function ────────────────────────────────────
  function updateDashboard(state) {
    isDemoMode = state.is_demo_mode;
    updateModeIndicators();

    const now = new Date();
    const timestampElem = document.getElementById('lastUpdateTimestamp');
    if (timestampElem) {
      timestampElem.textContent = now.toTimeString().split(' ')[0] + '.' + String(now.getMilliseconds()).padStart(3, '0');
    }

    // A. System Overview & Health
    const latencySec = Math.max(0.01, (Date.now() - lastPacketTime) / 1000);
    const freshnessElem = document.getElementById('freshnessValue');
    if (freshnessElem) freshnessElem.textContent = `${latencySec.toFixed(2)}s`;

    const nodeAp = state.node_ap || {};
    const nodeRadar = state.node_radar || {};
    const nodeMag = state.node_mag || {};

    let activeNodes = 0;
    if (nodeAp.wifi_connected) activeNodes++;
    if (nodeRadar.wifi_connected) activeNodes++;
    if (nodeMag.wifi_connected) activeNodes++;

    const activeNodesElem = document.getElementById('activeNodesCount');
    if (activeNodesElem) activeNodesElem.textContent = `${activeNodes}/3`;

    // AP Traffic Source
    const nodeApRate = document.getElementById('nodeApRate');
    if (nodeApRate) nodeApRate.textContent = (nodeAp.packet_rate_hz || 0).toFixed(1);
    const nodeApSsid = document.getElementById('nodeApSsid');
    if (nodeApSsid) nodeApSsid.textContent = `CSI_TEST (${nodeAp.ip_address || '192.168.4.1'})`;
    const nodeApUptime = document.getElementById('nodeApUptime');
    if (nodeApUptime) {
      const sec = Math.floor((nodeAp.uptime_ms || 0) / 1000);
      nodeApUptime.textContent = `${Math.floor(sec / 60)}m ${sec % 60}s | Heap: 42KB`;
    }

    // Receiver 1 (ESP32 #1)
    const nodeRadarRate = document.getElementById('nodeRadarRate');
    if (nodeRadarRate) nodeRadarRate.textContent = (nodeRadar.packet_rate_hz || 20).toFixed(1);
    const nodeRadarIp = document.getElementById('nodeRadarIp');
    if (nodeRadarIp) nodeRadarIp.textContent = `${nodeRadar.ip_address || '192.168.4.10'}`;
    const nodeRadarErrors = document.getElementById('nodeRadarErrors');
    if (nodeRadarErrors) {
      const pErrors = state.radar ? state.radar.parser_errors || 0 : 0;
      nodeRadarErrors.textContent = `${pErrors} UART errors`;
    }

    // Receiver 2 (ESP32 #2)
    const nodeMagRate = document.getElementById('nodeMagRate');
    if (nodeMagRate) nodeMagRate.textContent = (nodeMag.packet_rate_hz || 20).toFixed(1);
    const nodeMagIp = document.getElementById('nodeMagIp');
    if (nodeMagIp) nodeMagIp.textContent = `${nodeMag.ip_address || '192.168.4.20'}`;
    const nodeMagCalib = document.getElementById('nodeMagCalibStatus');
    if (nodeMagCalib && state.magnetometer) {
      const cal = state.magnetometer.calibration_status || 'UNCALIBRATED';
      nodeMagCalib.textContent = cal;
      nodeMagCalib.className = cal === 'CALIBRATED' ? 'color-emerald' : 'color-amber';
    }

    // Session Buffer Status
    fetchSessionStatus();

    // B. Radar Monitoring
    const radar = state.radar || {};
    const targets = radar.targets || [];
    radarRenderer.updateTargets(targets);

    const radarTargetCountBadge = document.getElementById('radarTargetCountBadge');
    if (radarTargetCountBadge) {
      const cnt = targets.length;
      radarTargetCountBadge.textContent = `${cnt} TARGET${cnt === 1 ? '' : 'S'}`;
    }

    const radarQualityBadge = document.getElementById('radarQualityBadge');
    if (radarQualityBadge) {
      radarQualityBadge.textContent = radar.data_quality || 'HIGH QUALITY';
    }

    // Radar Target Table
    const tableBody = document.getElementById('radarTargetTableBody');
    if (tableBody) {
      if (targets.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="5" class="empty-state">No targets detected in radar field of view</td></tr>';
      } else {
        tableBody.innerHTML = targets.map(t => `
          <tr>
            <td><b style="color:#00e5ff">T${t.target_id}</b></td>
            <td>(${t.x_m.toFixed(2)}m, ${t.y_m.toFixed(2)}m)</td>
            <td><b>${t.distance_m.toFixed(2)} m</b></td>
            <td style="color:${t.speed_ms > 0 ? '#f59e0b' : '#00e5ff'}">${t.speed_ms > 0 ? '+' : ''}${t.speed_ms.toFixed(2)} m/s (${t.speed_cms} cm/s)</td>
            <td><span class="badge badge-emerald">ACTIVE_TRACK</span></td>
          </tr>
        `).join('');
      }
    }

    // C. Wi-Fi Sensing Streams (Rx1 & Rx2)
    const rx1 = state.wifi_radar_node || {};
    const rx2 = state.wifi_mag_node || {};

    wifiChart.push({
      rx1_rssi: rx1.rssi_dbm,
      rx2_rssi: rx2.rssi_dbm
    });

    // Rx1 DOM
    const rx1Rssi = document.getElementById('rx1Rssi');
    if (rx1Rssi) rx1Rssi.textContent = rx1.rssi_dbm ? `${rx1.rssi_dbm} dBm` : '--';
    const rx1CsiAvailable = document.getElementById('rx1CsiAvailable');
    if (rx1CsiAvailable) {
      rx1CsiAvailable.textContent = rx1.csi_available ? 'Available (64 SC)' : 'Unavailable';
      rx1CsiAvailable.className = rx1.csi_available ? 'metric-val color-emerald' : 'metric-val color-muted';
    }
    const rx1Format = document.getElementById('rx1Format');
    if (rx1Format) rx1Format.textContent = rx1.feature_format || 'SUBCA_AMP_VAR';
    const rx1Rate = document.getElementById('rx1Rate');
    if (rx1Rate) rx1Rate.textContent = `${(rx1.csi_packet_rate || 0).toFixed(0)} Hz`;
    const rx1Variance = document.getElementById('rx1Variance');
    if (rx1Variance) {
      rx1Variance.textContent = rx1.csi_amplitude_variance !== null && rx1.csi_amplitude_variance !== undefined
        ? rx1.csi_amplitude_variance.toFixed(2) : '--';
    }
    const rx1Loss = document.getElementById('rx1Loss');
    if (rx1Loss) rx1Loss.textContent = `${(rx1.packet_loss_pct || 0).toFixed(1)}%`;
    const rx1Motion = document.getElementById('rx1Motion');
    if (rx1Motion) {
      const mot = rx1.motion_heuristic || 'QUIET';
      rx1Motion.textContent = mot;
      rx1Motion.className = mot === 'ACTIVE' ? 'metric-val color-amber' : (mot === 'SUBTLE' ? 'metric-val color-cyan' : 'metric-val color-emerald');
    }

    // Rx2 DOM
    const rx2Rssi = document.getElementById('rx2Rssi');
    if (rx2Rssi) rx2Rssi.textContent = rx2.rssi_dbm ? `${rx2.rssi_dbm} dBm` : '--';
    const rx2CsiAvailable = document.getElementById('rx2CsiAvailable');
    if (rx2CsiAvailable) {
      rx2CsiAvailable.textContent = rx2.csi_available ? 'Available' : 'No Raw CSI (RSSI only)';
      rx2CsiAvailable.className = rx2.csi_available ? 'metric-val color-emerald' : 'metric-val color-muted';
    }
    const rx2Format = document.getElementById('rx2Format');
    if (rx2Format) rx2Format.textContent = rx2.feature_format || 'RAW_RSSI_ONLY';
    const rx2Rate = document.getElementById('rx2Rate');
    if (rx2Rate) rx2Rate.textContent = `${(rx2.csi_packet_rate || 0).toFixed(0)} Hz`;
    const rx2Variance = document.getElementById('rx2Variance');
    if (rx2Variance) {
      rx2Variance.textContent = rx2.csi_amplitude_variance !== null && rx2.csi_amplitude_variance !== undefined
        ? rx2.csi_amplitude_variance.toFixed(2) : '--';
    }
    const rx2Loss = document.getElementById('rx2Loss');
    if (rx2Loss) rx2Loss.textContent = `${(rx2.packet_loss_pct || 0).toFixed(1)}%`;
    const rx2Motion = document.getElementById('rx2Motion');
    if (rx2Motion) {
      const mot2 = rx2.motion_heuristic || 'QUIET';
      rx2Motion.textContent = mot2;
      rx2Motion.className = mot2 === 'ACTIVE' ? 'metric-val color-amber' : (mot2 === 'SUBTLE' ? 'metric-val color-cyan' : 'metric-val color-emerald');
    }

    // D. Fusion & Evidence Matrix
    const fusion = state.fusion || {};

    const radarEvidenceList = document.getElementById('radarEvidenceList');
    if (radarEvidenceList) {
      const rEv = fusion.radar_evidence || [];
      radarEvidenceList.innerHTML = rEv.length > 0
        ? rEv.map(e => `<li>${e}</li>`).join('')
        : '<li>No radar targets in range</li>';
    }

    const rx1EvidenceList = document.getElementById('rx1EvidenceList');
    if (rx1EvidenceList) {
      const rx1Ev = fusion.rx1_evidence || [];
      rx1EvidenceList.innerHTML = rx1Ev.length > 0
        ? rx1Ev.map(e => `<li>${e}</li>`).join('')
        : '<li>Rx1 stream quiet</li>';
    }

    const rx2EvidenceList = document.getElementById('rx2EvidenceList');
    if (rx2EvidenceList) {
      const rx2Ev = fusion.rx2_evidence || [];
      rx2EvidenceList.innerHTML = rx2Ev.length > 0
        ? rx2Ev.map(e => `<li>${e}</li>`).join('')
        : '<li>Rx2 stream quiet</li>';
    }

    const fusionConfidenceBadge = document.getElementById('fusionConfidenceBadge');
    if (fusionConfidenceBadge) {
      const score = Math.round((fusion.confidence_score || 0.85) * 100);
      fusionConfidenceBadge.textContent = `CONF: ${score}%`;
    }

    const fusionPresenceState = document.getElementById('fusionPresenceState');
    if (fusionPresenceState) {
      fusionPresenceState.textContent = fusion.presence_state || 'QUIET';
    }

    const fusionSummaryText = document.getElementById('fusionSummaryText');
    if (fusionSummaryText) {
      fusionSummaryText.textContent = fusion.explainable_summary || 'Sensor streams aligned. No active movement.';
    }

    const fusionUncertaintyText = document.getElementById('fusionUncertaintyText');
    if (fusionUncertaintyText) {
      fusionUncertaintyText.textContent = fusion.uncertainty_note || 'Wi-Fi reflects multipath distortion only; coordinates originate strictly from LD2450 radar.';
    }

    // E. Magnetometer & MTC-1
    const mag = state.magnetometer || {};
    magChart.push({
      bx: mag.bx,
      by: mag.by,
      bz: mag.bz
    });

    const magMagnitude = document.getElementById('magMagnitude');
    if (magMagnitude) magMagnitude.textContent = `${(mag.magnitude || 0).toFixed(1)} µT`;
    const magDelta = document.getElementById('magDelta');
    if (magDelta) magDelta.textContent = `${(mag.delta_magnitude || 0).toFixed(2)} µT`;
    const magBx = document.getElementById('magBx');
    if (magBx) magBx.textContent = `${(mag.bx || 0).toFixed(1)} µT`;
    const magBy = document.getElementById('magBy');
    if (magBy) magBy.textContent = `${(mag.by || 0).toFixed(1)} µT`;
    const magBz = document.getElementById('magBz');
    if (magBz) magBz.textContent = `${(mag.bz || 0).toFixed(1)} µT`;

    const magSensorChipBadge = document.getElementById('magSensorChipBadge');
    if (magSensorChipBadge) {
      magSensorChipBadge.textContent = mag.sensor_chip || 'HMC5883L';
    }

    // MTC-1 Classifier
    const mtc = state.mtc || {};
    const mtcStatusBadge = document.getElementById('mtcStatusBadge');
    if (mtcStatusBadge) mtcStatusBadge.textContent = mtc.status || 'READY';

    const mtcThreatBadge = document.getElementById('mtcThreatBadge');
    if (mtcThreatBadge) {
      const threat = mtc.threat_level || 'NONE';
      mtcThreatBadge.textContent = threat;
      mtcThreatBadge.className = threat === 'HIGH' ? 'badge badge-danger' : (threat === 'LOW' ? 'badge badge-amber' : 'badge badge-emerald');
    }

    const mtcPredictedClass = document.getElementById('mtcPredictedClass');
    if (mtcPredictedClass) {
      mtcPredictedClass.textContent = (mtc.predicted_class || 'CLEAR').toUpperCase();
    }

    const mtcConfidence = document.getElementById('mtcConfidence');
    if (mtcConfidence) {
      mtcConfidence.textContent = mtc.confidence_percent ? `${mtc.confidence_percent.toFixed(1)}%` : '--';
    }

    // Probability Bars Grid
    const probContainer = document.getElementById('probBarsContainer');
    const allProbs = mtc.all_probabilities || {};
    if (probContainer && Object.keys(allProbs).length > 0) {
      probContainer.innerHTML = Object.entries(allProbs).map(([className, p]) => `
        <div class="prob-item">
          <div class="prob-label-row">
            <span>${className}</span>
            <span><b>${p.toFixed(1)}%</b></span>
          </div>
          <div class="prob-bar-track">
            <div class="prob-bar-fill" style="width:${p}%; background:${className === mtc.predicted_class ? (mtc.threat_color || '#00e5ff') : 'rgba(0,229,255,0.3)'}"></div>
          </div>
        </div>
      `).join('');
    }
  }

  // Helper: Mode Indicator Updates
  function updateModeIndicators() {
    if (isDemoMode) {
      if (modeStatusDot) modeStatusDot.className = 'status-indicator-dot warning';
      if (modeLabelText) modeLabelText.textContent = 'DEMO / SIMULATED';
      if (demoBanner) demoBanner.classList.remove('hidden');
      if (demoControlsWrapper) demoControlsWrapper.style.display = 'flex';
    } else {
      if (modeStatusDot) modeStatusDot.className = 'status-indicator-dot online';
      if (modeLabelText) modeLabelText.textContent = 'LIVE HARDWARE';
      if (demoBanner) demoBanner.classList.add('hidden');
      if (demoControlsWrapper) demoControlsWrapper.style.display = 'none';
    }
  }

  // Helper: Session status fetch
  async function fetchSessionStatus() {
    try {
      const res = await fetch('/api/session/status');
      const data = await res.json();
      isRecording = data.recording;
      const countElem = document.getElementById('sessionSamplesCount');
      if (countElem) countElem.textContent = data.sample_count;
      const recordStateElem = document.getElementById('sessionRecordState');
      if (recordStateElem) {
        recordStateElem.textContent = isRecording ? 'RECORDING ACTIVE' : 'IDLE';
        recordStateElem.style.color = isRecording ? '#ef4444' : 'var(--text-secondary)';
      }
      const durElem = document.getElementById('sessionDuration');
      if (durElem) durElem.textContent = `${data.duration_sec.toFixed(1)}s`;

      if (btnRecord && recordBtnText) {
        if (isRecording) {
          btnRecord.classList.add('recording');
          recordBtnText.textContent = 'Stop';
        } else {
          btnRecord.classList.remove('recording');
          recordBtnText.textContent = 'Record';
        }
      }
    } catch (e) {
      // Ignore background status polling errors
    }
  }

  // ── 6. Event Listeners ───────────────────────────────────────────────────

  // Toggle Mode Button
  if (btnToggleMode) {
    btnToggleMode.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/mode/toggle', { method: 'POST' });
        const data = await res.json();
        isDemoMode = data.is_demo_mode;
        updateModeIndicators();
        addLog(`Switched platform mode to: ${data.mode_label}`);
      } catch (e) {
        addLog(`Error toggling mode: ${e}`);
      }
    });
  }

  // Zero / Calibrate Baseline
  async function zeroBaseline() {
    try {
      if (btnCalibrateMag) btnCalibrateMag.disabled = true;
      const res = await fetch('/api/magnetometer/calibrate', { method: 'POST' });
      const data = await res.json();
      addLog(data.message || 'Magnetic baseline zeroed.');
    } catch (e) {
      addLog(`Calibration error: ${e}`);
    } finally {
      if (btnCalibrateMag) btnCalibrateMag.disabled = false;
    }
  }

  if (btnCalibrateMag) btnCalibrateMag.addEventListener('click', zeroBaseline);
  if (btnZeroBaselineInline) btnZeroBaselineInline.addEventListener('click', zeroBaseline);

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
        addLog(`Demo simulated object signature set to: ${selected.toUpperCase()}`);
      } catch (err) {
        addLog(`Error setting object: ${err}`);
      }
    });
  }

  // Session Recording Controls
  if (btnRecord) {
    btnRecord.addEventListener('click', async () => {
      try {
        if (!isRecording) {
          const res = await fetch('/api/session/start', { method: 'POST' });
          const data = await res.json();
          isRecording = true;
          addLog('Session recording started.');
        } else {
          const res = await fetch('/api/session/stop', { method: 'POST' });
          const data = await res.json();
          isRecording = false;
          addLog(`Session recording saved (${data.sample_count} frames, ${data.duration_sec}s).`);
        }
        fetchSessionStatus();
      } catch (e) {
        addLog(`Recording error: ${e}`);
      }
    });
  }

  if (btnClearSession) {
    btnClearSession.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/session/clear', { method: 'POST' });
        const data = await res.json();
        addLog('Session buffer cleared.');
        fetchSessionStatus();
      } catch (e) {
        addLog(`Error clearing buffer: ${e}`);
      }
    });
  }

  if (btnExportJson) {
    btnExportJson.addEventListener('click', () => {
      window.location.href = '/api/session/export/json';
      addLog('Triggered JSON session export download.');
    });
  }

  if (btnExportCsv) {
    btnExportCsv.addEventListener('click', () => {
      window.location.href = '/api/session/export/csv';
      addLog('Triggered CSV session export download.');
    });
  }

  // Connect WebSocket on load
  connectWebSocket();
});

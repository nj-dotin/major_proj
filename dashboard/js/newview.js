/**
 * NewView Spatial Sensing & 2D/3D Tracking Workspace Controller
 * Features:
 * - 2D Radar Plan View with metric grid, radar FOV wedge, and sensor anchors.
 * - Interactive 3D Orbit View with ground plane, axis guides, 3D target capsules, and drop-lines.
 * - Hardware anchors for Radar, NodeMCU Tx AP, ESP32 #1 Rx1, and ESP32 #2 Rx2.
 * - Multimodal Wi-Fi Fresnel activity layer (transparently marked as channel perturbation).
 * - Live target trails, velocity vectors, and interactive target inspector.
 */

document.addEventListener('DOMContentLoaded', () => {
  // ── Canvas & Sizing ──────────────────────────────────────────────────────
  const canvas = document.getElementById('spatialCanvas');
  const ctx = canvas.getContext('2d');
  const container = document.getElementById('canvasContainer');

  let width = 800;
  let height = 600;

  function resizeCanvas() {
    if (!container || !canvas) return;
    const rect = container.getBoundingClientRect();
    width = rect.width;
    height = rect.height;
    canvas.width = width * window.devicePixelRatio;
    canvas.height = height * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
  }
  window.addEventListener('resize', resizeCanvas);
  resizeCanvas();

  // ── State Variables ──────────────────────────────────────────────────────
  let viewMode = '2D'; // '2D' or '3D'
  let spatialRange = 6.0; // meters
  let selectedTargetId = 1;
  let isDemoMode = true;
  let isRecording = false;

  // Layer Toggles
  const layers = {
    targets: true,
    trails: true,
    velocity: true,
    anchors: true,
    wifiActivity: true,
    grid: true
  };

  // Sensor Physical Anchors (in meters: X, Y)
  let anchors = {
    radar: { x: 0.0, y: 0.0, label: 'LD2450 Radar', type: 'RADAR' },
    tx: { x: 0.0, y: 4.0, label: 'NodeMCU AP Tx', type: 'TX' },
    rx1: { x: -1.5, y: 2.5, label: 'Rx1 (ESP32 #1)', type: 'RX1' },
    rx2: { x: 1.5, y: 2.5, label: 'Rx2 (ESP32 #2)', type: 'RX2' }
  };

  // 2D Camera (Pan & Zoom)
  const camera2D = {
    panX: 0,
    panY: 0,
    zoom: 1.0,
    isDragging: false,
    dragStartX: 0,
    dragStartY: 0
  };

  // 3D Camera (Orbit, Pitch, Distance)
  const camera3D = {
    azimuth: 0.55,    // horizontal rotation in radians
    elevation: 0.52,  // pitch angle from horizontal
    distance: 14.0,   // camera distance
    panX: 0,
    panY: 1.8,
    isOrbiting: false,
    isPanning: false,
    startX: 0,
    startY: 0
  };

  // Telemetry Cache
  let currentTelemetry = {
    is_demo_mode: true,
    radar: { targets: [], data_quality: 'HIGH QUALITY' },
    wifi_radar_node: { rssi_dbm: -46, csi_amplitude_variance: 2.45, motion_heuristic: 'ACTIVE' },
    wifi_mag_node: { rssi_dbm: -49, csi_amplitude_variance: 1.10, motion_heuristic: 'SUBTLE' },
    node_ap: { packet_rate_hz: 98.5, wifi_connected: true },
    node_radar: { packet_rate_hz: 20.0, wifi_connected: true },
    node_mag: { packet_rate_hz: 20.0, wifi_connected: true },
    fusion: {
      presence_state: 'MOVING_TARGET',
      confidence_score: 0.88,
      explainable_summary: 'Radar target active; Wi-Fi variance corroborates channel disturbance.',
      uncertainty_note: 'Wi-Fi variance indicates multipath disturbance only; coordinates originate strictly from LD2450 radar.'
    }
  };

  // Local Track History Map: target_id -> array of {x, y, z, time}
  const trackHistory = new Map();

  // ── DOM References ───────────────────────────────────────────────────────
  const btnView2D = document.getElementById('btnView2D');
  const btnView3D = document.getElementById('btnView3D');
  const rangeSelect = document.getElementById('rangeSelect');
  const btnResetCamera = document.getElementById('btnResetCamera');
  const navControlsHint = document.getElementById('navControlsHint');

  const btnToggleMode = document.getElementById('btnToggleMode');
  const modeStatusDot = document.getElementById('modeStatusDot');
  const modeLabelText = document.getElementById('modeLabelText');
  const demoBanner = document.getElementById('demoBanner');
  const sysStatusDot = document.getElementById('sysStatusDot');
  const sysStatusText = document.getElementById('sysStatusText');
  const btnRecord = document.getElementById('btnRecord');
  const recordBtnText = document.getElementById('recordBtnText');

  // Layer checkboxes
  document.getElementById('layerTargets').addEventListener('change', e => layers.targets = e.target.checked);
  document.getElementById('layerTrails').addEventListener('change', e => layers.trails = e.target.checked);
  document.getElementById('layerVelocity').addEventListener('change', e => layers.velocity = e.target.checked);
  document.getElementById('layerAnchors').addEventListener('change', e => layers.anchors = e.target.checked);
  document.getElementById('layerWifiActivity').addEventListener('change', e => layers.wifiActivity = e.target.checked);
  document.getElementById('layerGrid').addEventListener('change', e => layers.grid = e.target.checked);

  // ── WebSocket Telemetry ──────────────────────────────────────────────────
  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      if (sysStatusDot) sysStatusDot.className = 'status-indicator-dot online';
      if (sysStatusText) sysStatusText.textContent = 'CONNECTED';
    };

    ws.onmessage = (event) => {
      try {
        const state = JSON.parse(event.data);
        currentTelemetry = state;
        updateTrackHistory(state);
        updateSidebar(state);
      } catch (err) {
        console.error('Error parsing NewView telemetry:', err);
      }
    };

    ws.onclose = () => {
      if (sysStatusDot) sysStatusDot.className = 'status-indicator-dot offline';
      if (sysStatusText) sysStatusText.textContent = 'RECONNECTING';
      setTimeout(connectWebSocket, 2000);
    };
  }

  // Update track history buffer
  function updateTrackHistory(state) {
    const targets = (state.radar && state.radar.targets) || [];
    const now = Date.now();

    targets.forEach(t => {
      if (!trackHistory.has(t.target_id)) {
        trackHistory.set(t.target_id, []);
      }
      const history = trackHistory.get(t.target_id);
      history.push({ x: t.x_m, y: t.y_m, z: 0.9, speed: t.speed_ms, time: now });
      if (history.length > 80) history.shift();
    });

    // Cleanup old tracks if target not seen for > 15s
    for (const [id, points] of trackHistory.entries()) {
      if (points.length > 0 && now - points[points.length - 1].time > 15000) {
        trackHistory.delete(id);
      }
    }
  }

  // ── Sidebar Updates ──────────────────────────────────────────────────────
  function updateSidebar(state) {
    isDemoMode = state.is_demo_mode;
    if (isDemoMode) {
      if (modeStatusDot) modeStatusDot.className = 'status-indicator-dot warning';
      if (modeLabelText) modeLabelText.textContent = 'DEMO / SIMULATED';
      if (demoBanner) demoBanner.classList.remove('hidden');
    } else {
      if (modeStatusDot) modeStatusDot.className = 'status-indicator-dot online';
      if (modeLabelText) modeLabelText.textContent = 'LIVE HARDWARE';
      if (demoBanner) demoBanner.classList.add('hidden');
    }

    const radar = state.radar || {};
    const targets = radar.targets || [];

    const sideTargetCountBadge = document.getElementById('sideTargetCountBadge');
    if (sideTargetCountBadge) sideTargetCountBadge.textContent = `${targets.length} ACTIVE`;

    // Sensor health
    const sideRadarStatus = document.getElementById('sideRadarStatus');
    if (sideRadarStatus) sideRadarStatus.textContent = `TRACKING (${targets.length} targets)`;

    const rx1 = state.wifi_radar_node || {};
    const sideRx1Status = document.getElementById('sideRx1Status');
    if (sideRx1Status) sideRx1Status.textContent = `${rx1.feature_format || 'CSI ACTIVE'} (${rx1.rssi_dbm || -46} dBm)`;

    const rx2 = state.wifi_mag_node || {};
    const sideRx2Status = document.getElementById('sideRx2Status');
    if (sideRx2Status) sideRx2Status.textContent = `${rx2.feature_format || 'RAW RSSI'} (${rx2.rssi_dbm || -49} dBm)`;

    // Target Selection List
    const targetSelectList = document.getElementById('targetSelectList');
    if (targetSelectList) {
      if (targets.length === 0) {
        targetSelectList.innerHTML = '<div style="color:var(--text-muted);font-size:11px;padding:6px 0;">No radar targets in field of view</div>';
      } else {
        targetSelectList.innerHTML = targets.map(t => `
          <div class="target-card-select ${t.target_id === selectedTargetId ? 'selected' : ''}" data-target-id="${t.target_id}">
            <div>
              <b style="color: #00e5ff;">Target #${t.target_id}</b>
              <div style="font-size: 10px; color: var(--text-muted);">Range: ${t.distance_m.toFixed(2)} m | Speed: ${t.speed_ms.toFixed(2)} m/s</div>
            </div>
            <span class="badge badge-emerald">TRACKED</span>
          </div>
        `).join('');

        // Rebind clicks
        targetSelectList.querySelectorAll('.target-card-select').forEach(card => {
          card.addEventListener('click', () => {
            selectedTargetId = parseInt(card.getAttribute('data-target-id'), 10);
            updateSidebar(state);
          });
        });
      }
    }

    // Selected target details
    const selected = targets.find(t => t.target_id === selectedTargetId) || targets[0];
    if (selected) {
      document.getElementById('detailTargetId').textContent = `#${selected.target_id}`;
      document.getElementById('detailCoords').textContent = `X: ${selected.x_m.toFixed(2)}m, Y: ${selected.y_m.toFixed(2)}m`;
      document.getElementById('detailDistance').textContent = `${selected.distance_m.toFixed(2)} meters`;
      document.getElementById('detailSpeed').textContent = `${selected.speed_ms > 0 ? '+' : ''}${selected.speed_ms.toFixed(2)} m/s (${selected.speed_cms} cm/s)`;
      const trail = trackHistory.get(selected.target_id) || [];
      document.getElementById('detailTrailPoints').textContent = `${trail.length} points`;
    }

    // Fusion section
    const fusion = state.fusion || {};
    const sideFusionBadge = document.getElementById('sideFusionBadge');
    if (sideFusionBadge) {
      const conf = Math.round((fusion.confidence_score || 0.88) * 100);
      sideFusionBadge.textContent = `CONF ${conf}%`;
    }
    const sideFusionState = document.getElementById('sideFusionState');
    if (sideFusionState) sideFusionState.textContent = fusion.presence_state || 'QUIET';
    const sideFusionDesc = document.getElementById('sideFusionDesc');
    if (sideFusionDesc) sideFusionDesc.textContent = fusion.explainable_summary || '';
    const sideUncertaintyNote = document.getElementById('sideUncertaintyNote');
    if (sideUncertaintyNote) sideUncertaintyNote.textContent = fusion.uncertainty_note || '';

    // Calibration anchor positions from state if provided
    if (state.radar_position) anchors.radar = { ...anchors.radar, ...state.radar_position };
    if (state.tx_position) anchors.tx = { ...anchors.tx, ...state.tx_position };
    if (state.rx1_position) anchors.rx1 = { ...anchors.rx1, ...state.rx1_position };
    if (state.rx2_position) anchors.rx2 = { ...anchors.rx2, ...state.rx2_position };

    const calibTx = document.getElementById('calibTxPos');
    if (calibTx) calibTx.textContent = `(${anchors.tx.x.toFixed(2)}, ${anchors.tx.y.toFixed(2)}) m`;
    const calibRx1 = document.getElementById('calibRx1Pos');
    if (calibRx1) calibRx1.textContent = `(${anchors.rx1.x.toFixed(2)}, ${anchors.rx1.y.toFixed(2)}) m`;
    const calibRx2 = document.getElementById('calibRx2Pos');
    if (calibRx2) calibRx2.textContent = `(${anchors.rx2.x.toFixed(2)}, ${anchors.rx2.y.toFixed(2)}) m`;
  }

  // ── Rendering Loop ───────────────────────────────────────────────────────
  function render() {
    ctx.clearRect(0, 0, width, height);

    if (viewMode === '2D') {
      render2D();
    } else {
      render3D();
    }

    requestAnimationFrame(render);
  }

  // ── 2D Plan View Renderer ────────────────────────────────────────────────
  function render2D() {
    ctx.save();

    // Coordinate Transform: Radar at bottom center (width / 2, height - 60)
    const originX = width / 2 + camera2D.panX;
    const originY = height - 70 + camera2D.panY;
    const scale = (height * 0.75 / spatialRange) * camera2D.zoom;

    // Helper: World to Screen (X is horizontal meters, Y is forward meters)
    function worldToScreen(x, y) {
      return {
        sx: originX + x * scale,
        sy: originY - y * scale
      };
    }

    // 1. Grid & FOV Wedge
    if (layers.grid) {
      // Background FOV wedge (±60° from forward Y axis)
      ctx.beginPath();
      ctx.moveTo(originX, originY);
      const leftAngle = Math.PI * 0.5 + Math.PI / 3;
      const rightAngle = Math.PI * 0.5 - Math.PI / 3;
      const maxR = spatialRange * scale;
      ctx.arc(originX, originY, maxR, -leftAngle, -rightAngle, false);
      ctx.closePath();
      ctx.fillStyle = 'rgba(0, 229, 255, 0.025)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(0, 229, 255, 0.2)';
      ctx.lineWidth = 1;
      ctx.stroke();

      // Range Concentric Rings (1m increments)
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      ctx.font = '10px "JetBrains Mono", monospace';

      for (let r = 1; r <= spatialRange; r++) {
        const ringPx = r * scale;
        ctx.beginPath();
        ctx.arc(originX, originY, ringPx, -leftAngle, -rightAngle, false);
        ctx.strokeStyle = r % 2 === 0 ? 'rgba(0, 229, 255, 0.2)' : 'rgba(255, 255, 255, 0.06)';
        ctx.setLineDash([4, 4]);
        ctx.stroke();
        ctx.setLineDash([]);

        // Ring label
        ctx.fillStyle = 'rgba(0, 229, 255, 0.5)';
        ctx.fillText(`${r}.0m`, originX - 8, originY - ringPx);
      }

      // Azimuth Radial Rays (-60°, -30°, 0°, +30°, +60°)
      const angles = [-60, -30, 0, 30, 60];
      angles.forEach(deg => {
        const rad = (90 - deg) * Math.PI / 180;
        const ex = originX + Math.cos(rad) * maxR;
        const ey = originY - Math.sin(rad) * maxR;
        ctx.beginPath();
        ctx.moveTo(originX, originY);
        ctx.lineTo(ex, ey);
        ctx.strokeStyle = deg === 0 ? 'rgba(0, 229, 255, 0.35)' : 'rgba(255, 255, 255, 0.08)';
        ctx.stroke();

        ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
        ctx.fillText(`${deg > 0 ? '+' : ''}${deg}°`, ex + (deg >= 0 ? 12 : -12), ey - 4);
      });
    }

    // 2. Wi-Fi Activity Fresnel Ellipses (Tx to Rx1, Tx to Rx2)
    if (layers.wifiActivity) {
      renderWifiFresnel2D(worldToScreen);
    }

    // 3. Hardware Anchors (Radar, AP Tx, Rx1, Rx2)
    if (layers.anchors) {
      renderAnchors2D(worldToScreen);
    }

    // 4. Radar Targets & Trails
    const targets = (currentTelemetry.radar && currentTelemetry.radar.targets) || [];

    // Historical Trails
    if (layers.trails) {
      for (const [id, points] of trackHistory.entries()) {
        if (points.length < 2) continue;
        ctx.beginPath();
        const p0 = worldToScreen(points[0].x, points[0].y);
        ctx.moveTo(p0.sx, p0.sy);
        for (let i = 1; i < points.length; i++) {
          const pt = worldToScreen(points[i].x, points[i].y);
          ctx.lineTo(pt.sx, pt.sy);
        }
        ctx.strokeStyle = id === selectedTargetId ? 'rgba(0, 229, 255, 0.5)' : 'rgba(255, 255, 255, 0.2)';
        ctx.lineWidth = 2;
        ctx.stroke();

        // Trail dots
        points.forEach((pt, idx) => {
          if (idx % 4 === 0) {
            const sp = worldToScreen(pt.x, pt.y);
            ctx.beginPath();
            ctx.arc(sp.sx, sp.sy, 2, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(0, 229, 255, 0.4)';
            ctx.fill();
          }
        });
      }
    }

    // Target Markers & Vectors
    if (layers.targets) {
      targets.forEach(t => {
        const p = worldToScreen(t.x_m, t.y_m);
        const isSelected = t.target_id === selectedTargetId;

        // Outer pulsing ring
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, isSelected ? 14 : 10, 0, Math.PI * 2);
        ctx.strokeStyle = isSelected ? '#00e5ff' : 'rgba(0, 229, 255, 0.7)';
        ctx.lineWidth = isSelected ? 2 : 1.5;
        ctx.stroke();

        // Center dot
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#00e5ff';
        ctx.shadowColor = '#00e5ff';
        ctx.shadowBlur = 10;
        ctx.fill();
        ctx.shadowBlur = 0;

        // Target Label
        ctx.font = '11px "JetBrains Mono", monospace';
        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'left';
        ctx.fillText(`T${t.target_id} (${t.distance_m.toFixed(2)}m)`, p.sx + 14, p.sy - 4);

        // Velocity Heading Vector
        if (layers.velocity && Math.abs(t.speed_ms) > 0.05) {
          const norm = Math.hypot(t.x_m, t.y_m) || 1;
          const dirX = (t.x_m / norm) * (t.speed_ms > 0 ? 1 : -1);
          const dirY = (t.y_m / norm) * (t.speed_ms > 0 ? 1 : -1);
          const arrowLen = Math.min(60, Math.abs(t.speed_ms) * 45);

          const tipX = p.sx + dirX * arrowLen;
          const tipY = p.sy - dirY * arrowLen;

          ctx.beginPath();
          ctx.moveTo(p.sx, p.sy);
          ctx.lineTo(tipX, tipY);
          ctx.strokeStyle = '#10b981';
          ctx.lineWidth = 2;
          ctx.stroke();

          // Arrow head
          ctx.beginPath();
          ctx.arc(tipX, tipY, 3, 0, Math.PI * 2);
          ctx.fillStyle = '#10b981';
          ctx.fill();
        }
      });
    }

    ctx.restore();
  }

  // Helper: Wi-Fi Fresnel 2D Zone
  function renderWifiFresnel2D(worldToScreen) {
    const rx1 = currentTelemetry.wifi_radar_node || {};
    const rx2 = currentTelemetry.wifi_mag_node || {};

    const var1 = rx1.csi_amplitude_variance || 0;
    const var2 = rx2.csi_amplitude_variance || 0;

    // Draw link Tx -> Rx1
    drawLinkEllipse(anchors.tx, anchors.rx1, var1, '#00e5ff', 'Rx1 Channel Zone');
    // Draw link Tx -> Rx2
    drawLinkEllipse(anchors.tx, anchors.rx2, var2, '#a855f7', 'Rx2 Channel Zone');

    function drawLinkEllipse(a1, a2, variance, color, label) {
      const p1 = worldToScreen(a1.x, a1.y);
      const p2 = worldToScreen(a2.x, a2.y);

      const midX = (p1.sx + p2.sx) / 2;
      const midY = (p1.sy + p2.sy) / 2;
      const dist = Math.hypot(p2.sx - p1.sx, p2.sy - p1.sy);
      const angle = Math.atan2(p2.sy - p1.sy, p2.sx - p1.sx);

      // Semi-major axis = dist / 2, semi-minor axis based on variance perturbation
      const minorRadius = Math.max(16, Math.min(50, variance * 10));

      ctx.save();
      ctx.translate(midX, midY);
      ctx.rotate(angle);

      ctx.beginPath();
      ctx.ellipse(0, 0, dist / 2, minorRadius, 0, 0, Math.PI * 2);
      ctx.strokeStyle = variance > 2.0 ? 'rgba(245, 158, 11, 0.45)' : 'rgba(255, 255, 255, 0.12)';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = variance > 2.0 ? 'rgba(245, 158, 11, 0.08)' : 'rgba(0, 229, 255, 0.03)';
      ctx.fill();

      ctx.restore();

      // LOS Line
      ctx.beginPath();
      ctx.moveTo(p1.sx, p1.sy);
      ctx.lineTo(p2.sx, p2.sy);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  }

  // Helper: Anchors 2D
  function renderAnchors2D(worldToScreen) {
    Object.values(anchors).forEach(anc => {
      const p = worldToScreen(anc.x, anc.y);

      // Icon badge
      ctx.beginPath();
      ctx.rect(p.sx - 8, p.sy - 8, 16, 16);
      ctx.fillStyle = anc.type === 'RADAR' ? '#00e5ff' : (anc.type === 'TX' ? '#10b981' : '#a855f7');
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1;
      ctx.stroke();

      ctx.font = '10px "JetBrains Mono", monospace';
      ctx.fillStyle = '#9aa5b5';
      ctx.textAlign = 'center';
      ctx.fillText(anc.label, p.sx, p.sy + 18);
    });
  }

  // ── 3D Isometric / Orbit View Renderer ────────────────────────────────────
  function render3D() {
    ctx.save();

    const cx = width / 2 + camera3D.panX * 40;
    const cy = height / 2 + camera3D.panY * 40;

    // Camera angles
    const az = camera3D.azimuth;
    const el = camera3D.elevation;
    const cosAz = Math.cos(az);
    const sinAz = Math.sin(az);
    const cosEl = Math.cos(el);
    const sinEl = Math.sin(el);

    // 3D to 2D projection function
    // Coordinates: X = lateral meters, Y = forward meters, Z = altitude meters
    function project3D(x, y, z) {
      // Rotate around Z axis by azimuth
      const rx = x * cosAz - y * sinAz;
      const ry = x * sinAz + y * cosAz;
      const rz = z;

      // Rotate around X axis by elevation
      const px = rx;
      const py = ry * cosEl - rz * sinEl;
      const pz = ry * sinEl + rz * cosEl;

      const scale3D = (height * 0.45 / spatialRange) * (14.0 / camera3D.distance);
      return {
        sx: cx + px * scale3D,
        sy: cy - pz * scale3D,
        depth: py
      };
    }

    // 1. Ground Plane Grid (Z = 0)
    if (layers.grid) {
      ctx.lineWidth = 1;
      const maxGrid = Math.ceil(spatialRange);

      for (let x = -maxGrid; x <= maxGrid; x += 1) {
        const pStart = project3D(x, 0, 0);
        const pEnd = project3D(x, maxGrid, 0);
        ctx.beginPath();
        ctx.moveTo(pStart.sx, pStart.sy);
        ctx.lineTo(pEnd.sx, pEnd.sy);
        ctx.strokeStyle = x === 0 ? 'rgba(0, 229, 255, 0.4)' : 'rgba(255, 255, 255, 0.07)';
        ctx.stroke();
      }

      for (let y = 0; y <= maxGrid; y += 1) {
        const pStart = project3D(-maxGrid, y, 0);
        const pEnd = project3D(maxGrid, y, 0);
        ctx.beginPath();
        ctx.moveTo(pStart.sx, pStart.sy);
        ctx.lineTo(pEnd.sx, pEnd.sy);
        ctx.strokeStyle = y === 0 ? 'rgba(239, 68, 68, 0.4)' : 'rgba(255, 255, 255, 0.07)';
        ctx.stroke();
      }

      // Origin Axis Tripod
      const p0 = project3D(0, 0, 0);
      const px = project3D(1.0, 0, 0);
      const py = project3D(0, 1.0, 0);
      const pz = project3D(0, 0, 1.0);

      // X-Axis (Red)
      ctx.beginPath();
      ctx.moveTo(p0.sx, p0.sy);
      ctx.lineTo(px.sx, px.sy);
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Y-Axis (Cyan)
      ctx.beginPath();
      ctx.moveTo(p0.sx, p0.sy);
      ctx.lineTo(py.sx, py.sy);
      ctx.strokeStyle = '#00e5ff';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Z-Axis (Blue)
      ctx.beginPath();
      ctx.moveTo(p0.sx, p0.sy);
      ctx.lineTo(pz.sx, pz.sy);
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    // 2. Hardware Anchors in 3D
    if (layers.anchors) {
      Object.values(anchors).forEach(anc => {
        const ground = project3D(anc.x, anc.y, 0);
        const top = project3D(anc.x, anc.y, 0.7);

        // Ground anchor stem
        ctx.beginPath();
        ctx.moveTo(ground.sx, ground.sy);
        ctx.lineTo(top.sx, top.sy);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Top node box
        ctx.beginPath();
        ctx.arc(top.sx, top.sy, 6, 0, Math.PI * 2);
        ctx.fillStyle = anc.type === 'RADAR' ? '#00e5ff' : (anc.type === 'TX' ? '#10b981' : '#a855f7');
        ctx.fill();

        ctx.font = '9px "JetBrains Mono", monospace';
        ctx.fillStyle = '#8b949e';
        ctx.textAlign = 'center';
        ctx.fillText(anc.label, top.sx, top.sy - 10);
      });
    }

    // 3. Wi-Fi Activity Wireframe in 3D
    if (layers.wifiActivity) {
      const rx1 = currentTelemetry.wifi_radar_node || {};
      const var1 = rx1.csi_amplitude_variance || 0;
      if (var1 > 1.5) {
        const ptTx = project3D(anchors.tx.x, anchors.tx.y, 0.7);
        const ptRx1 = project3D(anchors.rx1.x, anchors.rx1.y, 0.7);
        ctx.beginPath();
        ctx.moveTo(ptTx.sx, ptTx.sy);
        ctx.lineTo(ptRx1.sx, ptRx1.sy);
        ctx.strokeStyle = 'rgba(245, 158, 11, 0.5)';
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 5]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    // 4. Targets in 3D
    const targets = (currentTelemetry.radar && currentTelemetry.radar.targets) || [];

    // 3D Trails
    if (layers.trails) {
      for (const [id, points] of trackHistory.entries()) {
        if (points.length < 2) continue;
        ctx.beginPath();
        const start = project3D(points[0].x, points[0].y, points[0].z);
        ctx.moveTo(start.sx, start.sy);
        for (let i = 1; i < points.length; i++) {
          const pt = project3D(points[i].x, points[i].y, points[i].z);
          ctx.lineTo(pt.sx, pt.sy);
        }
        ctx.strokeStyle = id === selectedTargetId ? 'rgba(0, 229, 255, 0.6)' : 'rgba(255, 255, 255, 0.25)';
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }

    // Target 3D Markers (Capsule + Drop-line to Ground)
    if (layers.targets) {
      targets.forEach(t => {
        const targetZ = 0.9; // Target approximate human torso height (meters)
        const groundPt = project3D(t.x_m, t.y_m, 0);
        const topPt = project3D(t.x_m, t.y_m, targetZ);
        const isSelected = t.target_id === selectedTargetId;

        // Ground drop-line & shadow
        ctx.beginPath();
        ctx.moveTo(groundPt.sx, groundPt.sy);
        ctx.lineTo(topPt.sx, topPt.sy);
        ctx.strokeStyle = 'rgba(0, 229, 255, 0.4)';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.stroke();
        ctx.setLineDash([]);

        // Ground shadow ring
        ctx.beginPath();
        ctx.ellipse(groundPt.sx, groundPt.sy, 8, 4, 0, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(0, 229, 255, 0.15)';
        ctx.fill();

        // 3D Target Capsule Sphere
        ctx.beginPath();
        ctx.arc(topPt.sx, topPt.sy, isSelected ? 9 : 7, 0, Math.PI * 2);
        ctx.fillStyle = '#00e5ff';
        ctx.shadowColor = '#00e5ff';
        ctx.shadowBlur = 12;
        ctx.fill();
        ctx.shadowBlur = 0;

        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // 3D Target Text Label
        ctx.font = '11px "JetBrains Mono", monospace';
        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'left';
        ctx.fillText(`T${t.target_id} (${t.distance_m.toFixed(2)}m)`, topPt.sx + 12, topPt.sy - 4);
      });
    }

    ctx.restore();
  }

  // ── Mouse & Interactivity Handlers ───────────────────────────────────────
  canvas.addEventListener('mousedown', e => {
    if (viewMode === '2D') {
      camera2D.isDragging = true;
      camera2D.dragStartX = e.clientX - camera2D.panX;
      camera2D.dragStartY = e.clientY - camera2D.panY;
    } else {
      if (e.button === 0) { // Left click: Orbit
        camera3D.isOrbiting = true;
        camera3D.startX = e.clientX;
        camera3D.startY = e.clientY;
      } else if (e.button === 2) { // Right click: Pan
        camera3D.isPanning = true;
        camera3D.startX = e.clientX;
        camera3D.startY = e.clientY;
      }
    }
  });

  window.addEventListener('mousemove', e => {
    if (viewMode === '2D' && camera2D.isDragging) {
      camera2D.panX = e.clientX - camera2D.dragStartX;
      camera2D.panY = e.clientY - camera2D.dragStartY;
    } else if (viewMode === '3D') {
      if (camera3D.isOrbiting) {
        const dx = e.clientX - camera3D.startX;
        const dy = e.clientY - camera3D.startY;
        camera3D.azimuth += dx * 0.008;
        camera3D.elevation = Math.max(0.1, Math.min(Math.PI / 2 - 0.05, camera3D.elevation + dy * 0.008));
        camera3D.startX = e.clientX;
        camera3D.startY = e.clientY;
      } else if (camera3D.isPanning) {
        const dx = e.clientX - camera3D.startX;
        const dy = e.clientY - camera3D.startY;
        camera3D.panX += dx * 0.02;
        camera3D.panY += dy * 0.02;
        camera3D.startX = e.clientX;
        camera3D.startY = e.clientY;
      }
    }
  });

  window.addEventListener('mouseup', () => {
    camera2D.isDragging = false;
    camera3D.isOrbiting = false;
    camera3D.isPanning = false;
  });

  // Prevent context menu on canvas for right click panning
  canvas.addEventListener('contextmenu', e => e.preventDefault());

  // Wheel Zoom
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    if (viewMode === '2D') {
      const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
      camera2D.zoom = Math.max(0.5, Math.min(3.0, camera2D.zoom * zoomFactor));
    } else {
      const distDelta = e.deltaY * 0.015;
      camera3D.distance = Math.max(5.0, Math.min(30.0, camera3D.distance + distDelta));
    }
  }, { passive: false });

  // Mode View Toggles
  btnView2D.addEventListener('click', () => {
    viewMode = '2D';
    btnView2D.classList.add('active');
    btnView3D.classList.remove('active');
    navControlsHint.textContent = '2D Mode: Drag to Pan | Scroll to Zoom';
  });

  btnView3D.addEventListener('click', () => {
    viewMode = '3D';
    btnView3D.classList.add('active');
    btnView2D.classList.remove('active');
    navControlsHint.textContent = '3D Mode: Left Drag to Orbit | Right Drag to Pan | Scroll to Zoom';
  });

  // Range Select
  rangeSelect.addEventListener('change', e => {
    spatialRange = parseFloat(e.target.value);
  });

  // Reset Camera View
  btnResetCamera.addEventListener('click', () => {
    if (viewMode === '2D') {
      camera2D.panX = 0;
      camera2D.panY = 0;
      camera2D.zoom = 1.0;
    } else {
      camera3D.azimuth = 0.55;
      camera3D.elevation = 0.52;
      camera3D.distance = 14.0;
      camera3D.panX = 0;
      camera3D.panY = 1.8;
    }
  });

  // Global Mode Toggle (Live vs Demo)
  if (btnToggleMode) {
    btnToggleMode.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/mode/toggle', { method: 'POST' });
        const data = await res.json();
        isDemoMode = data.is_demo_mode;
        updateSidebar(currentTelemetry);
      } catch (err) {
        console.error('Mode toggle error:', err);
      }
    });
  }

  // Record Button
  if (btnRecord) {
    btnRecord.addEventListener('click', async () => {
      try {
        if (!isRecording) {
          await fetch('/api/session/start', { method: 'POST' });
          isRecording = true;
          btnRecord.classList.add('recording');
          recordBtnText.textContent = 'Stop';
        } else {
          await fetch('/api/session/stop', { method: 'POST' });
          isRecording = false;
          btnRecord.classList.remove('recording');
          recordBtnText.textContent = 'Record';
        }
      } catch (err) {
        console.error('Record button error:', err);
      }
    });
  }

  // Reset Calibration
  const btnResetCalibration = document.getElementById('btnResetCalibration');
  if (btnResetCalibration) {
    btnResetCalibration.addEventListener('click', async () => {
      anchors.radar = { x: 0.0, y: 0.0, label: 'LD2450 Radar', type: 'RADAR' };
      anchors.tx = { x: 0.0, y: 4.0, label: 'NodeMCU AP Tx', type: 'TX' };
      anchors.rx1 = { x: -1.5, y: 2.5, label: 'Rx1 (ESP32 #1)', type: 'RX1' };
      anchors.rx2 = { x: 1.5, y: 2.5, label: 'Rx2 (ESP32 #2)', type: 'RX2' };

      await fetch('/api/calibration/spatial', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          radar_position: anchors.radar,
          tx_position: anchors.tx,
          rx1_position: anchors.rx1,
          rx2_position: anchors.rx2
        })
      });
      updateSidebar(currentTelemetry);
    });
  }

  // ── Start Up ─────────────────────────────────────────────────────────────
  connectWebSocket();
  requestAnimationFrame(render);
});

/**
 * NewVision 2D Radar Canvas Visualization
 * Renders HLK-LD2450 24 GHz millimeter-wave radar tracking data:
 * - 0 to 6 meters forward range
 * - -3m to +3m lateral coverage
 * - Distance arcs, azimuth guide rays, and Cartesian grid
 * - Accurate target position, speed vector, and fading breadcrumb trails
 */

class RadarCanvasRenderer {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');

    this.maxRangeMeters = 6.0;
    this.maxLateralMeters = 3.0;
    this.sweepAngleRad = 0;
    this.targets = [];
    this.targetTrails = {}; // id -> array of {x, y, ts}

    this.resize();
    window.addEventListener('resize', () => this.resize());
    
    // Animation loop for smooth sweep & rendering
    this.animate = this.animate.bind(this);
    requestAnimationFrame(this.animate);
  }

  resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.width = rect.width;
    this.height = rect.height;
    this.canvas.width = this.width * dpr;
    this.canvas.height = this.height * dpr;
    this.ctx.scale(dpr, dpr);
  }

  updateTargets(targets) {
    this.targets = targets || [];
    const now = performance.now();

    // Update trails
    this.targets.forEach(t => {
      if (!t.is_valid) return;
      if (!this.targetTrails[t.target_id]) {
        this.targetTrails[t.target_id] = [];
      }
      this.targetTrails[t.target_id].push({
        x_m: t.x_m,
        y_m: t.y_m,
        ts: now
      });
      // Limit trail length
      if (this.targetTrails[t.target_id].length > 25) {
        this.targetTrails[t.target_id].shift();
      }
    });

    // Clean up stale trails
    Object.keys(this.targetTrails).forEach(id => {
      const trail = this.targetTrails[id];
      if (trail.length > 0 && now - trail[trail.length - 1].ts > 4000) {
        delete this.targetTrails[id];
      }
    });
  }

  // Convert meters (x: -3 to +3, y: 0 to 6) to canvas pixels
  worldToCanvas(x_m, y_m) {
    // Sensor is located at bottom-center: (width / 2, height - 20)
    const originX = this.width / 2;
    const originY = this.height - 25;
    const scaleX = (this.width * 0.9) / (2 * this.maxLateralMeters);
    const scaleY = (this.height - 40) / this.maxRangeMeters;
    const scale = Math.min(scaleX, scaleY);

    const px = originX + (x_m * scale);
    const py = originY - (y_m * scale);
    return { px, py, originX, originY, scale };
  }

  animate() {
    this.render();
    this.sweepAngleRad += 0.025;
    if (this.sweepAngleRad > Math.PI) {
      this.sweepAngleRad = 0;
    }
    requestAnimationFrame(this.animate);
  }

  render() {
    const { ctx, width, height } = this;
    if (!ctx) return;

    // Clear
    ctx.fillStyle = '#06090e';
    ctx.fillRect(0, 0, width, height);

    const { originX, originY, scale } = this.worldToCanvas(0, 0);

    // 1. Draw Distance Arcs (1m to 6m)
    ctx.lineWidth = 1;
    for (let r = 1; r <= this.maxRangeMeters; r++) {
      const radiusPx = r * scale;
      ctx.beginPath();
      ctx.arc(originX, originY, radiusPx, Math.PI, 2 * Math.PI, false);
      ctx.strokeStyle = r === this.maxRangeMeters ? 'rgba(0, 229, 255, 0.35)' : 'rgba(0, 229, 255, 0.12)';
      ctx.stroke();

      // Range text
      ctx.font = '10px "JetBrains Mono", monospace';
      ctx.fillStyle = 'rgba(0, 229, 255, 0.45)';
      ctx.fillText(`${r}m`, originX + 6, originY - radiusPx + 12);
    }

    // 2. Azimuth Angle Rays (-60 to +60 deg)
    const anglesDeg = [-60, -45, -30, 0, 30, 45, 60];
    anglesDeg.forEach(deg => {
      const rad = (deg - 90) * (Math.PI / 180);
      const endX = originX + Math.cos(rad) * (this.maxRangeMeters * scale);
      const endY = originY + Math.sin(rad) * (this.maxRangeMeters * scale);

      ctx.beginPath();
      ctx.moveTo(originX, originY);
      ctx.lineTo(endX, endY);
      ctx.strokeStyle = deg === 0 ? 'rgba(0, 229, 255, 0.25)' : 'rgba(0, 229, 255, 0.08)';
      ctx.stroke();

      // Degree labels
      ctx.font = '9px "JetBrains Mono", monospace';
      ctx.fillStyle = 'rgba(0, 229, 255, 0.35)';
      ctx.fillText(`${deg}°`, endX - 8, endY - 6);
    });

    // 3. Rotating Sweep Line (Synthetic radar visual effect)
    const sweepAngle = Math.PI + this.sweepAngleRad;
    const sweepRadius = this.maxRangeMeters * scale;
    const sweepEndX = originX + Math.cos(sweepAngle) * sweepRadius;
    const sweepEndY = originY + Math.sin(sweepAngle) * sweepRadius;

    ctx.beginPath();
    ctx.moveTo(originX, originY);
    ctx.lineTo(sweepEndX, sweepEndY);
    ctx.strokeStyle = 'rgba(0, 229, 255, 0.4)';
    ctx.stroke();

    // 4. Sensor Origin Reticle
    ctx.beginPath();
    ctx.arc(originX, originY, 5, 0, 2 * Math.PI);
    ctx.fillStyle = '#00e5ff';
    ctx.fill();
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.fillStyle = '#8b949e';
    ctx.fillText('LD2450 RADAR', originX - 34, originY + 16);

    // 5. Draw Target Breadcrumb Trails
    Object.keys(this.targetTrails).forEach(id => {
      const trail = this.targetTrails[id];
      if (trail.length < 2) return;
      ctx.beginPath();
      trail.forEach((p, idx) => {
        const { px, py } = this.worldToCanvas(p.x_m, p.y_m);
        if (idx === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.strokeStyle = 'rgba(0, 229, 255, 0.15)';
      ctx.lineWidth = 2;
      ctx.stroke();
    });

    // 6. Draw Tracked Targets
    if (this.targets.length === 0) {
      ctx.font = '12px "JetBrains Mono", monospace';
      ctx.fillStyle = 'rgba(255, 255, 255, 0.3)';
      ctx.textAlign = 'center';
      ctx.fillText('NO RADAR TARGETS DETECTED', originX, originY - (this.maxRangeMeters * scale * 0.5));
      ctx.textAlign = 'left';
      return;
    }

    this.targets.forEach(t => {
      if (!t.is_valid) return;
      const { px, py } = this.worldToCanvas(t.x_m, t.y_m);

      // Outer pulsing ring
      ctx.beginPath();
      ctx.arc(px, py, 14, 0, 2 * Math.PI);
      ctx.strokeStyle = 'rgba(0, 229, 255, 0.4)';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Center solid pip
      ctx.beginPath();
      ctx.arc(px, py, 5, 0, 2 * Math.PI);
      ctx.fillStyle = t.speed_ms > 0.1 ? '#f59e0b' : '#00e5ff'; // amber for moving away, cyan for stationary/approaching
      ctx.fill();

      // Velocity Vector Arrow
      if (Math.abs(t.speed_ms) > 0.05) {
        // Speed in m/s: draw arrow along line to origin
        const dx = px - originX;
        const dy = py - originY;
        const distPx = Math.sqrt(dx * dx + dy * dy);
        if (distPx > 0) {
          const arrowLen = Math.min(Math.abs(t.speed_ms) * 35, 45);
          const dir = t.speed_ms > 0 ? 1 : -1; // 1 = moving away, -1 = approaching
          const vx = (dx / distPx) * arrowLen * dir;
          const vy = (dy / distPx) * arrowLen * dir;

          ctx.beginPath();
          ctx.moveTo(px, py);
          ctx.lineTo(px + vx, py + vy);
          ctx.strokeStyle = '#f59e0b';
          ctx.lineWidth = 2;
          ctx.stroke();

          // Arrowhead
          const headLen = 6;
          const angle = Math.atan2(vy, vx);
          ctx.beginPath();
          ctx.moveTo(px + vx, py + vy);
          ctx.lineTo(px + vx - headLen * Math.cos(angle - Math.PI / 6), py + vy - headLen * Math.sin(angle - Math.PI / 6));
          ctx.lineTo(px + vx - headLen * Math.cos(angle + Math.PI / 6), py + vy - headLen * Math.sin(angle + Math.PI / 6));
          ctx.fillStyle = '#f59e0b';
          ctx.fill();
        }
      }

      // Target Metadata Tag
      ctx.font = '10px "JetBrains Mono", monospace';
      ctx.fillStyle = '#ffffff';
      ctx.fillText(`T${t.target_id} (${t.distance_m}m, ${t.speed_ms}m/s)`, px + 14, py - 4);
    });
  }
}

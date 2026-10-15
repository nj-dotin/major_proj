/**
 * NewVision Lightweight Real-time Telemetry Waveform Charts
 * High-performance Canvas rolling line charts for:
 * 1. Dual Wi-Fi RSSI trend
 * 2. 3-Axis Magnetometer (Bx, By, Bz) waveform
 */

class RollingWaveformChart {
  constructor(canvasId, options = {}) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');

    this.maxPoints = options.maxPoints || 80;
    this.minY = options.minY !== undefined ? options.minY : -100;
    this.maxY = options.maxY !== undefined ? options.maxY : 100;
    this.autoScale = options.autoScale || false;
    this.seriesConfig = options.series || [
      { key: 'val', color: '#00e5ff', label: 'Value' }
    ];

    this.dataPoints = []; // Array of { [key]: number }

    this.resize();
    window.addEventListener('resize', () => this.resize());
  }

  resize() {
    if (!this.canvas) return;
    const rect = this.canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.width = rect.width;
    this.height = rect.height;
    this.canvas.width = this.width * dpr;
    this.canvas.height = this.height * dpr;
    this.ctx.scale(dpr, dpr);
    this.render();
  }

  push(dataObj) {
    this.dataPoints.push(dataObj);
    if (this.dataPoints.length > this.maxPoints) {
      this.dataPoints.shift();
    }
    this.render();
  }

  render() {
    const { ctx, width, height } = this;
    if (!ctx || width === 0 || height === 0) return;

    ctx.clearRect(0, 0, width, height);

    // Background grid lines
    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    for (let y = 0.25; y < 1.0; y += 0.25) {
      ctx.beginPath();
      ctx.moveTo(0, height * y);
      ctx.lineTo(width, height * y);
      ctx.stroke();
    }

    if (this.dataPoints.length < 2) return;

    // Determine scale
    let currentMinY = this.minY;
    let currentMaxY = this.maxY;

    if (this.autoScale) {
      let minVal = Infinity;
      let maxVal = -Infinity;
      this.dataPoints.forEach(pt => {
        this.seriesConfig.forEach(s => {
          const v = pt[s.key];
          if (v !== undefined && v !== null) {
            if (v < minVal) minVal = v;
            if (v > maxVal) maxVal = v;
          }
        });
      });
      if (minVal !== Infinity && maxVal !== -Infinity) {
        const margin = Math.max((maxVal - minVal) * 0.15, 2);
        currentMinY = minVal - margin;
        currentMaxY = maxVal + margin;
      }
    }

    const rangeY = currentMaxY - currentMinY || 1;
    const stepX = width / (this.maxPoints - 1);

    // Draw each series
    this.seriesConfig.forEach(series => {
      ctx.beginPath();
      ctx.lineWidth = 1.8;
      ctx.strokeStyle = series.color;

      let started = false;
      this.dataPoints.forEach((pt, idx) => {
        const val = pt[series.key];
        if (val === undefined || val === null) return;

        const x = idx * stepX;
        const normalizedY = 1.0 - (val - currentMinY) / rangeY;
        const y = Math.max(2, Math.min(height - 2, normalizedY * height));

        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      });

      ctx.stroke();
    });
  }
}

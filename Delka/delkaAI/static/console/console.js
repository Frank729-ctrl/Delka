/* DelkaAI Developer Console — vanilla JS helpers */

// ── Copy-to-clipboard ────────────────────────────────────────────────────────
function copyText(text) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(function () { showToast('Copied!'); });
  } else {
    var el = document.createElement('textarea');
    el.value = text;
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    document.body.removeChild(el);
    showToast('Copied!');
  }
}

// ── Toast notification ───────────────────────────────────────────────────────
function showToast(msg, type) {
  var colors = { success: '#16a34a', error: '#dc2626', default: '#6366f1' };
  var toast = document.createElement('div');
  toast.textContent = msg;
  toast.style.cssText = [
    'position:fixed', 'bottom:24px', 'right:24px',
    'background:' + (colors[type] || colors.default), 'color:#fff',
    'padding:10px 18px', 'border-radius:8px',
    'font-size:12px', 'font-weight:600',
    'box-shadow:0 4px 12px rgba(0,0,0,0.15)',
    'z-index:9999', 'opacity:1',
    'transition:opacity 0.4s'
  ].join(';');
  document.body.appendChild(toast);
  setTimeout(function () {
    toast.style.opacity = '0';
    setTimeout(function () { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 400);
  }, 2500);
}

// ── Confirm wrapper ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('[data-confirm]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      if (!confirm(el.dataset.confirm)) e.preventDefault();
    });
  });

  // Auto-focus first input on auth pages
  var first = document.querySelector('.auth-card input');
  if (first) first.focus();
});

// ── Simple bar chart (used by usage page) ───────────────────────────────────
function drawConsoleBarChart(canvasId, labels, values, opts) {
  opts = opts || {};
  var canvas = document.getElementById(canvasId);
  if (!canvas) return;
  var ctx = canvas.getContext('2d');
  var W = canvas.width, H = canvas.height;
  var pad = { top: 10, right: 10, bottom: 30, left: 36 };
  var chartW = W - pad.left - pad.right;
  var chartH = H - pad.top - pad.bottom;
  var max = Math.max.apply(null, values) || 1;

  ctx.fillStyle = opts.bg || '#f8fafc';
  ctx.fillRect(0, 0, W, H);

  // Grid
  for (var g = 0; g <= 4; g++) {
    var gy = pad.top + chartH - (g / 4) * chartH;
    ctx.strokeStyle = '#e2e8f0';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad.left, gy);
    ctx.lineTo(W - pad.right, gy);
    ctx.stroke();
    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px sans-serif';
    ctx.fillText(Math.round(max * g / 4), 2, gy + 4);
  }

  // Bars
  var bw = Math.max(12, Math.floor(chartW / labels.length) - 8);
  labels.forEach(function (lbl, i) {
    var bh = (values[i] / max) * chartH;
    var x = pad.left + i * (chartW / labels.length) + 4;
    var y = pad.top + chartH - bh;
    ctx.fillStyle = opts.color || '#6366f1';
    ctx.fillRect(x, y, bw, bh);

    // Value label
    ctx.fillStyle = '#1e293b';
    ctx.font = '10px sans-serif';
    ctx.fillText(values[i], x + 2, y - 4);

    // X label
    ctx.fillStyle = '#64748b';
    ctx.font = '9px sans-serif';
    ctx.save();
    ctx.translate(x + bw / 2, H - 4);
    ctx.rotate(-0.2);
    ctx.fillText(lbl, 0, 0);
    ctx.restore();
  });
}

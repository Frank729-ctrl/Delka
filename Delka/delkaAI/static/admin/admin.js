/* DelkaAI Admin Console — vanilla JS helpers */

// ── AUTO-REFRESH every 60s on dashboard/metrics pages ─────────────────────
(function () {
  var autoRefreshPages = ['/admin/keys', '/admin/security', '/admin/metrics'];
  var path = location.pathname;
  if (autoRefreshPages.some(function (p) { return path === p; })) {
    setTimeout(function () { location.reload(); }, 60000);
  }
})();

// ── CONFIRM before form submit with data-confirm attribute ─────────────────
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('form[data-confirm]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (!confirm(form.dataset.confirm)) {
        e.preventDefault();
      }
    });
  });
});

// ── Copy-to-clipboard helper ───────────────────────────────────────────────
function copyText(text) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(function () {
      showToast('Copied!');
    });
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

// ── Lightweight toast notification ────────────────────────────────────────
function showToast(msg) {
  var toast = document.createElement('div');
  toast.textContent = msg;
  toast.style.cssText = [
    'position:fixed', 'bottom:24px', 'right:24px',
    'background:#6366f1', 'color:#fff',
    'padding:10px 18px', 'border-radius:6px',
    'font-size:12px', 'font-weight:600',
    'z-index:9999', 'opacity:1',
    'transition:opacity 0.4s'
  ].join(';');
  document.body.appendChild(toast);
  setTimeout(function () {
    toast.style.opacity = '0';
    setTimeout(function () { document.body.removeChild(toast); }, 400);
  }, 2000);
}

// ── Draw a simple bar chart on a <canvas> given endpoint data ──────────────
function drawBarChart(canvasId, dataObj) {
  var canvas = document.getElementById(canvasId);
  if (!canvas) return;
  var ctx = canvas.getContext('2d');
  var labels = Object.keys(dataObj);
  var values = labels.map(function (k) { return dataObj[k]; });
  if (!labels.length) return;

  var W = canvas.width, H = canvas.height;
  var pad = { top: 10, right: 10, bottom: 30, left: 40 };
  var chartW = W - pad.left - pad.right;
  var chartH = H - pad.top - pad.bottom;
  var max = Math.max.apply(null, values) || 1;

  ctx.fillStyle = '#1a1a2e';
  ctx.fillRect(0, 0, W, H);

  // Grid lines
  for (var g = 0; g <= 4; g++) {
    var gy = pad.top + chartH - (g / 4) * chartH;
    ctx.strokeStyle = '#2e3347';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad.left, gy);
    ctx.lineTo(W - pad.right, gy);
    ctx.stroke();
    ctx.fillStyle = '#8892a4';
    ctx.font = '10px sans-serif';
    ctx.fillText(Math.round(max * g / 4), 2, gy + 4);
  }

  var bw = Math.max(8, Math.floor(chartW / labels.length) - 6);
  labels.forEach(function (lbl, i) {
    var bh = (values[i] / max) * chartH;
    var x = pad.left + i * (chartW / labels.length) + 3;
    var y = pad.top + chartH - bh;
    ctx.fillStyle = '#7c3aed';
    ctx.fillRect(x, y, bw, bh);
    ctx.fillStyle = '#a78bfa';
    ctx.font = '9px sans-serif';
    ctx.save();
    ctx.translate(x + bw / 2, H - 4);
    ctx.rotate(-0.3);
    ctx.fillText(lbl.replace('/v1/', '/'), 0, 0);
    ctx.restore();
  });
}

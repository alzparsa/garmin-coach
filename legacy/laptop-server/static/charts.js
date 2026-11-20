/* Tiny dependency-free SVG charts. */
(function () {
  const W = 340, H = 150, P = { l: 30, r: 8, t: 10, b: 20 };

  function niceRange(min, max) {
    if (min === max) { min -= 1; max += 1; }
    const pad = (max - min) * 0.1;
    return [min - pad, max + pad];
  }
  let SPAN = 100;
  const fmt = v => Math.abs(v) >= 1000 ? (v / 1000).toFixed(1) + 'k' : (SPAN < 12 || Math.abs(v) < 10 ? +v.toFixed(1) : Math.round(v));
  const shortDate = d => { const x = new Date(d + 'T00:00'); return (x.getMonth() + 1) + '/' + x.getDate(); };

  function axes(yMin, yMax, labels) {
    SPAN = yMax - yMin;
    let s = '';
    for (let i = 0; i <= 3; i++) {
      const v = yMin + (yMax - yMin) * i / 3;
      const y = P.t + (H - P.t - P.b) * (1 - i / 3);
      s += `<line x1="${P.l}" x2="${W - P.r}" y1="${y}" y2="${y}" stroke="#262b35" stroke-width="1"/>`;
      s += `<text x="${P.l - 5}" y="${y + 3}" text-anchor="end">${fmt(v)}</text>`;
    }
    labels.forEach(([x, t]) => { s += `<text x="${x}" y="${H - 5}" text-anchor="middle">${t}</text>`; });
    return s;
  }

  /* series: [{name, color, points:[{date, value}]}] ; opts: {band:[lo,hi], dots:true} */
  window.lineChart = function (series, opts = {}) {
    const all = series.flatMap(s => s.points.filter(p => p.value != null));
    if (all.length < 2) return '<div class="empty">Not enough data yet.</div>';
    const dates = [...new Set(all.map(p => p.date))].sort();
    const t0 = +new Date(dates[0]), t1 = +new Date(dates[dates.length - 1]) || t0 + 1;
    let [yMin, yMax] = niceRange(Math.min(...all.map(p => p.value)), Math.max(...all.map(p => p.value)));
    if (opts.band) { yMin = Math.min(yMin, opts.band[0]); yMax = Math.max(yMax, opts.band[1]); }
    const X = d => P.l + (W - P.l - P.r) * ((+new Date(d) - t0) / Math.max(1, t1 - t0));
    const Y = v => P.t + (H - P.t - P.b) * (1 - (v - yMin) / (yMax - yMin));
    const labels = [0, .5, 1].map(f => { const d = dates[Math.round((dates.length - 1) * f)]; return [X(d), shortDate(d)]; });
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}">` + axes(yMin, yMax, labels);
    if (opts.band) s += `<rect x="${P.l}" width="${W - P.l - P.r}" y="${Y(opts.band[1])}" height="${Y(opts.band[0]) - Y(opts.band[1])}" fill="#3ddc84" opacity=".08"/>`;
    series.forEach(sr => {
      const pts = sr.points.filter(p => p.value != null);
      if (!pts.length) return;
      const d = pts.map((p, i) => (i ? 'L' : 'M') + X(p.date).toFixed(1) + ',' + Y(p.value).toFixed(1)).join('');
      s += `<path d="${d}" fill="none" stroke="${sr.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" ${sr.dashed ? 'stroke-dasharray="4 4"' : ''}/>`;
      if (opts.dots || pts.length < 25) pts.forEach(p => { s += `<circle cx="${X(p.date)}" cy="${Y(p.value)}" r="2.6" fill="${sr.color}"/>`; });
      const last = pts[pts.length - 1];
      s += `<circle cx="${X(last.date)}" cy="${Y(last.value)}" r="4" fill="${sr.color}" stroke="#15181e" stroke-width="2"/>`;
    });
    s += '</svg>';
    if (series.length > 1 || opts.legend) s += '<div class="legend">' + series.map(sr => `<span><i style="background:${sr.color}"></i>${sr.name}</span>`).join('') + '</div>';
    return s;
  };

  /* bars: [{label, parts:{key:value}}]; colors: {key: color} */
  window.barChart = function (bars, colors, opts = {}) {
    const totals = bars.map(b => Object.values(b.parts).reduce((a, v) => a + (v || 0), 0));
    const max = Math.max(...totals, 1);
    const yMax = max * 1.1;
    const n = bars.length, bw = (W - P.l - P.r) / n;
    const Y = v => P.t + (H - P.t - P.b) * (1 - v / yMax);
    const labels = bars.map((b, i) => [P.l + bw * i + bw / 2, (i % Math.ceil(n / 6) === 0 || i === n - 1) ? b.label : '']);
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}">` + axes(0, yMax, labels);
    bars.forEach((b, i) => {
      let acc = 0;
      const x = P.l + bw * i + bw * 0.18, w = bw * 0.64;
      Object.keys(colors).forEach(k => {
        const v = b.parts[k] || 0;
        if (!v) return;
        const y1 = Y(acc), y2 = Y(acc + v);
        s += `<rect x="${x}" y="${y2}" width="${w}" height="${Math.max(0, y1 - y2)}" fill="${colors[k]}" rx="2"/>`;
        acc += v;
      });
      if (i === n - 1 && opts.highlightLast) s += `<rect x="${x - 2}" y="${Y(acc) - 2}" width="${w + 4}" height="${Y(0) - Y(acc) + 2}" fill="none" stroke="#eef1f5" stroke-opacity=".35" rx="3"/>`;
    });
    s += '</svg>';
    const keys = Object.keys(colors).filter(k => bars.some(b => b.parts[k]));
    if (keys.length > 1) s += '<div class="legend">' + keys.map(k => `<span><i style="background:${colors[k]}"></i>${k}</span>`).join('') + '</div>';
    return s;
  };
})();

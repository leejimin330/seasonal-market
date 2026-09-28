// 가격 추이 선 그래프. 소매가(실선)와 평년가(점선) 두 계열, y축 하나.
// 색은 CSS 변수(--series-price, --series-normal)에서 온다 — dataviz 검증을 통과한 값.
// 색만으로 계열을 구분하지 않도록 범례 + 선 끝 직접 라벨 + 점선을 함께 쓴다.

const SVG = 'http://www.w3.org/2000/svg';
const won = (v) => (v == null ? '—' : `${v.toLocaleString('ko-KR')}원`);

function el(name, attrs = {}, parent) {
  const node = document.createElementNS(SVG, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

function niceTicks(min, max, count = 4) {
  const span = max - min || max || 1;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || raw;
  const start = Math.floor(min / step) * step;
  const ticks = [];
  for (let v = start; v <= max + step * 0.001; v += step) ticks.push(Math.round(v));
  if (ticks[ticks.length - 1] < max) ticks.push(ticks[ticks.length - 1] + step);
  return ticks;
}

function shortDate(iso, withYear) {
  const [y, m, d] = iso.split('-');
  return withYear ? `${y.slice(2)}.${Number(m)}.${Number(d)}` : `${Number(m)}.${Number(d)}`;
}

export function renderTrendChart(container, points, { unit }) {
  container.innerHTML = '';
  const data = points.filter((p) => p.price != null || p.normal_price != null);
  if (data.length < 2) {
    container.innerHTML = '<p class="empty">이 기간에는 가격 기록이 부족합니다.</p>';
    return;
  }

  const legend = document.createElement('div');
  legend.className = 'legend';
  legend.innerHTML = `
    <span><i style="border-color:var(--series-price)"></i>소매가 (${unit})</span>
    <span><i class="dash" style="border-color:var(--series-normal)"></i>평년가</span>`;
  container.appendChild(legend);

  const wrap = document.createElement('div');
  wrap.className = 'chart-wrap';
  container.appendChild(wrap);

  // 실제 폭으로 그린다. 고정 폭을 줄여 보이면 휴대폰에서 글자가 읽을 수 없게 작아진다.
  const W = Math.max(300, Math.round(wrap.clientWidth || 720));
  const H = W < 500 ? 220 : 280;
  const M = { top: 12, right: 52, bottom: 28, left: W < 500 ? 48 : 64 };
  const iw = W - M.left - M.right, ih = H - M.top - M.bottom;
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': `소매가와 평년가 추이, ${data[0].date}부터 ${data[data.length - 1].date}까지` }, wrap);

  const values = data.flatMap((p) => [p.price, p.normal_price]).filter((v) => v != null);
  const ticks = niceTicks(Math.min(...values) * 0.95, Math.max(...values) * 1.03);
  const y0 = ticks[0], y1 = ticks[ticks.length - 1];
  const x = (i) => M.left + (i / (data.length - 1)) * iw;
  const y = (v) => M.top + ih - ((v - y0) / (y1 - y0)) * ih;

  const grid = el('g', {}, svg);
  for (const t of ticks) {
    el('line', { x1: M.left, x2: M.left + iw, y1: y(t), y2: y(t), stroke: 'var(--grid)', 'stroke-width': 1 }, grid);
    const label = el('text', { x: M.left - 8, y: y(t) + 4, 'text-anchor': 'end', 'font-size': 11, fill: 'var(--ink-3)' }, grid);
    label.textContent = W < 500 && t >= 10000 ? `${t / 10000}만` : t.toLocaleString('ko-KR');
  }
  const multiYear = data[0].date.slice(0, 4) !== data[data.length - 1].date.slice(0, 4);
  for (const i of [0, Math.floor((data.length - 1) / 2), data.length - 1]) {
    const label = el('text', { x: x(i), y: H - 8, 'text-anchor': i === 0 ? 'start' : i === data.length - 1 ? 'end' : 'middle',
      'font-size': 11, fill: 'var(--ink-3)' }, grid);
    label.textContent = shortDate(data[i].date, multiYear);
  }

  const path = (key) => {
    let d = '', pen = false;
    data.forEach((p, i) => {
      if (p[key] == null) { pen = false; return; }
      d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`;
      pen = true;
    });
    return d;
  };
  el('path', { d: path('normal_price'), fill: 'none', stroke: 'var(--series-normal)', 'stroke-width': 2,
    'stroke-dasharray': '5 4', 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, svg);
  el('path', { d: path('price'), fill: 'none', stroke: 'var(--series-price)', 'stroke-width': 2,
    'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, svg);

  // 선 끝 직접 라벨 — 두 라벨이 겹치면 벌린다.
  const last = (key) => { for (let i = data.length - 1; i >= 0; i--) if (data[i][key] != null) return [i, data[i][key]]; return null; };
  const ends = [['price', '소매가'], ['normal_price', '평년']].map(([key, name]) => {
    const found = last(key);
    return found && { key, name, i: found[0], v: found[1], ly: y(found[1]) };
  }).filter(Boolean);
  if (ends.length === 2 && Math.abs(ends[0].ly - ends[1].ly) < 14) {
    const [a, b] = ends[0].ly < ends[1].ly ? ends : [ends[1], ends[0]];
    const mid = (a.ly + b.ly) / 2;
    a.ly = mid - 7; b.ly = mid + 7;
  }
  for (const end of ends) {
    el('circle', { cx: x(end.i), cy: y(end.v), r: 4, fill: end.key === 'price' ? 'var(--series-price)' : 'var(--series-normal)',
      stroke: 'var(--surface)', 'stroke-width': 2 }, svg);
    const t = el('text', { x: x(end.i) + 8, y: end.ly + 4, 'font-size': 11, fill: 'var(--ink-2)', 'font-weight': 700 }, svg);
    t.textContent = end.name;
  }

  // 호버: 세로 기준선 + 두 점 + 툴팁
  const cross = el('line', { y1: M.top, y2: M.top + ih, stroke: 'var(--ink-3)', 'stroke-width': 1, visibility: 'hidden' }, svg);
  const dots = ['price', 'normal_price'].map((key) => el('circle', { r: 4.5, visibility: 'hidden',
    fill: key === 'price' ? 'var(--series-price)' : 'var(--series-normal)', stroke: 'var(--surface)', 'stroke-width': 2 }, svg));
  const tip = document.createElement('div');
  tip.className = 'tooltip';
  tip.hidden = true;
  wrap.appendChild(tip);
  const hit = el('rect', { x: M.left, y: 0, width: iw, height: H, fill: 'transparent' }, svg);

  const show = (evt) => {
    const box = svg.getBoundingClientRect();
    const sx = ((evt.clientX - box.left) / box.width) * W;
    const i = Math.max(0, Math.min(data.length - 1, Math.round(((sx - M.left) / iw) * (data.length - 1))));
    const p = data[i];
    cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('visibility', 'visible');
    ['price', 'normal_price'].forEach((key, n) => {
      if (p[key] == null) { dots[n].setAttribute('visibility', 'hidden'); return; }
      dots[n].setAttribute('cx', x(i)); dots[n].setAttribute('cy', y(p[key])); dots[n].setAttribute('visibility', 'visible');
    });
    const gap = p.price != null && p.normal_price ? Math.round((p.price / p.normal_price - 1) * 1000) / 10 : null;
    tip.innerHTML = `<b>${p.date}</b><br>
      <span class="sw" style="background:var(--series-price)"></span>소매가 ${won(p.price)}<br>
      <span class="sw" style="background:var(--series-normal)"></span>평년가 ${won(p.normal_price)}
      ${gap == null ? '' : `<br>평년 대비 ${gap > 0 ? '+' : ''}${gap}%`}`;
    tip.hidden = false;
    const px = (x(i) / W) * box.width;
    const py = (Math.min(...[p.price, p.normal_price].filter((v) => v != null).map(y)) / H) * box.height;
    tip.style.left = `${Math.max(70, Math.min(box.width - 70, px))}px`;
    tip.style.top = `${py}px`;
  };
  const hide = () => {
    cross.setAttribute('visibility', 'hidden');
    dots.forEach((d) => d.setAttribute('visibility', 'hidden'));
    tip.hidden = true;
  };
  hit.addEventListener('pointermove', show);
  hit.addEventListener('pointerdown', show);
  hit.addEventListener('pointerleave', hide);

  // 요약 문장 + 표 보기 (색을 못 보는 사람, 스크린리더용)
  const withPrice = data.filter((p) => p.price != null);
  const lo = withPrice.reduce((a, b) => (b.price < a.price ? b : a));
  const hi = withPrice.reduce((a, b) => (b.price > a.price ? b : a));
  const summary = document.createElement('p');
  summary.className = 'chart-summary';
  summary.textContent = `이 기간 최저 ${won(lo.price)} (${lo.date}), 최고 ${won(hi.price)} (${hi.date}).`;
  container.appendChild(summary);

  const details = document.createElement('details');
  details.className = 'table-view';
  const step = Math.max(1, Math.ceil(data.length / 30));
  const rows = data.filter((_, i) => i % step === 0 || i === data.length - 1)
    .map((p) => `<tr><td>${p.date}</td><td class="right num">${won(p.price)}</td><td class="right num">${won(p.normal_price)}</td></tr>`)
    .join('');
  details.innerHTML = `<summary>표로 보기</summary><div class="table-scroll"><table>
    <thead><tr><th>날짜</th><th class="right">소매가</th><th class="right">평년가</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
  container.appendChild(details);
}

// 한국 지도(시·도 경계) 위에 주산지를 표시한다. 외부 라이브러리 없이 SVG로 그린다.
//
// 경계: 통계청 센서스용 행정구역경계(2013)를 southkorea/southkorea-maps가 가공한 GeoJSON을
// 좌표 소수 셋째 자리로 줄여 web/data/korea-provinces.json에 넣어 두었다.
// 투영: 한국 정도 넓이에서는 경도에 cos(위도)를 곱한 등장방형이면 모양이 크게 틀어지지 않는다.

const SVG = 'http://www.w3.org/2000/svg';
let geojson = null;

async function loadMap() {
  if (!geojson) geojson = await (await fetch('/data/korea-provinces.json')).json();
  return geojson;
}

function el(name, attrs = {}, parent) {
  const node = document.createElementNS(SVG, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

// 울릉도·독도까지 들어가면 본토가 작아진다. 울릉도(130.9)까지만 넣고 그 너머는 자른다.
const BOUNDS = { west: 124.5, east: 131.1, south: 33.05, north: 38.65 };

export async function renderKoreaMap(container, { points = [], provinces = [] }) {
  const data = await loadMap();
  const lat0 = ((BOUNDS.north + BOUNDS.south) / 2) * (Math.PI / 180);
  const kx = Math.cos(lat0);
  const W = 300;
  const scale = W / ((BOUNDS.east - BOUNDS.west) * kx);
  const H = Math.round((BOUNDS.north - BOUNDS.south) * scale);
  const project = ([lon, lat]) => [(lon - BOUNDS.west) * kx * scale, (BOUNDS.north - lat) * scale];

  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, class: 'korea-map', role: 'img',
    'aria-label': points.length ? `주산지 지도: ${points.map((p) => p.name).join(', ')}` : '주산지 지도' });
  const highlighted = new Set(provinces);

  const ring = (coords) => coords.map((c, i) => `${i ? 'L' : 'M'}${project(c).map((v) => v.toFixed(1)).join(',')}`).join('') + 'Z';
  for (const feature of data.features) {
    const { type, coordinates } = feature.geometry;
    const polygons = type === 'Polygon' ? [coordinates] : coordinates;
    const d = polygons.map((poly) => poly.map(ring).join('')).join('');
    const on = highlighted.has(feature.properties.name);
    const path = el('path', { d, class: on ? 'province on' : 'province' }, svg);
    el('title', {}, path).textContent = feature.properties.name;
  }

  // 점과 이름. 가까운 점끼리 이름이 겹치지 않게, 이름을 점의 왼쪽·오른쪽 번갈아 둔다.
  const sorted = [...points].sort((a, b) => b.lat - a.lat);
  sorted.forEach((p, i) => {
    const [x, y] = project([p.lon, p.lat]);
    el('circle', { cx: x, cy: y, r: 6, class: 'place-dot' }, svg);
    const right = x < W * 0.62 ? i % 2 === 0 || x < W * 0.3 : false;
    const label = el('text', { x: right ? x + 9 : x - 9, y: y + 4, 'text-anchor': right ? 'start' : 'end', class: 'place-label' }, svg);
    label.textContent = p.name;
  });

  container.innerHTML = '';
  container.appendChild(svg);
}

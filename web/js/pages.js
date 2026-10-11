// 둘러보기 화면: 검색, 제철 달력, 산지 지도, 식재료 사전, 홈의 소식·추천·알림.
// 소매 품목과 도매·위판 품목을 같은 모양(record)으로 합쳐서 한 번에 다룬다.

import { api } from './api.js';
import { cart, alerts } from './mylist.js';
import { renderKoreaMap } from './koreamap.js';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const won = (v) => (v == null ? '—' : `${Math.round(v).toLocaleString('ko-KR')}원`);

const FULL = {
  서울: '서울특별시', 부산: '부산광역시', 대구: '대구광역시', 인천: '인천광역시', 광주: '광주광역시',
  대전: '대전광역시', 울산: '울산광역시', 세종: '세종특별자치시', 경기: '경기도', 강원: '강원도',
  충북: '충청북도', 충남: '충청남도', 전북: '전라북도', 전남: '전라남도', 경북: '경상북도', 경남: '경상남도',
  제주: '제주특별자치도',
};
const SHORTS = Object.keys(FULL);

// "경상남도" → "경남", "제주도" → "제주", "경기도" → "경기"
export function shortProv(name) {
  const n = String(name || '').trim();
  if (FULL[n]) return n;
  if (/^(충청|전라|경상)[남북]/.test(n)) return n[0] + n[2];
  const two = n.slice(0, 2);
  return FULL[two] ? two : '';
}

const KIND_LABEL = { item: '소매', produce: '농산물 도매', fish: '수산물 위판' };

// ── 자료 ─────────────────────────────────────────────────────

let cache = null;
let cacheAt = 0;

export function loadAll() {
  if (cache && Date.now() - cacheAt < 5 * 60 * 1000) return cache;
  cacheAt = Date.now();
  cache = Promise.all([
    api.items(),
    api.produce().catch(() => ({ species: [] })),
    api.fish().catch(() => ({ species: [] })),
  ]).then(([i, p, f]) => {
    const month = i.month;
    const list = [];
    for (const it of i.items) {
      list.push({
        kind: 'item', key: `item:${it.id}`, name: it.name, emoji: it.emoji, href: `#/item/${it.id}`,
        months: it.season_months || [], text: it.intro || '', category: it.category,
        provinces: (it.provinces || []).map(shortProv).filter(Boolean),
        price: it.stale ? null : it.price, unit: it.price_unit, vs: it.stale ? null : it.vs_normal,
        main_region: it.main_region, id: it.id,
      });
    }
    for (const [kind, data] of [['produce', p], ['fish', f]]) {
      const seen = new Set();
      for (const s of data.species) {
        if (seen.has(s.name)) continue;
        seen.add(s.name);
        list.push({
          kind, key: `${kind}:${s.code}|${s.state}`, name: s.name, emoji: s.emoji || '',
          href: `#/${kind}/${encodeURIComponent(s.code)}?state=${encodeURIComponent(s.state)}`,
          months: s.season_months || [], text: s.story || '', category: s.category || '',
          provinces: [...new Set((s.regions || []).map(shortProv).filter(Boolean))],
          price: s.kg, unit: 'kg', vs: null, main_region: (s.regions || []).join('·'),
        });
      }
    }
    return { month, records: list, items: i.items, produce: p.species, fish: f.species };
  });
  cache.catch(() => { cache = null; });
  return cache;
}

// 이번 달 기준 제철 상태. 달 목록이 없거나 열두 달 모두면 연중이라 상태가 없다.
export function phaseOf(r, month) {
  const m = r.months;
  if (!m.length || m.length >= 12) return {};
  const next = (month % 12) + 1;
  const prev = ((month + 10) % 12) + 1;
  const now = m.includes(month);
  return {
    now,
    ending: now && !m.includes(next),     // 이번 달이 마지막
    starting: now && !m.includes(prev),   // 이번 달 새로 시작
    soon: !now && m.includes(next),       // 다음 달부터
  };
}

let closedCache = null;
export function loadClosed() {
  closedCache ||= fetch('/data/closed-seasons.json').then((r) => r.json()).catch(() => ({ note: '', items: [] }));
  return closedCache;
}

const inRange = (c, month, day) => {
  const v = month * 100 + day;
  return v >= c.start[0] * 100 + c.start[1] && v <= c.end[0] * 100 + c.end[1];
};
const rangeText = (c) => `${c.start[0]}/${c.start[1]} ~ ${c.end[0]}/${c.end[1]}`;

// 이름에 해당하는 금어기가 있으면 { active, range, memo }. 없으면 null.
export async function closedStatus(name) {
  const data = await loadClosed();
  const hit = data.items.find((c) => name.includes(c.name));
  if (!hit) return null;
  const now = new Date();
  return { active: inRange(hit, now.getMonth() + 1, now.getDate()), range: rangeText(hit), memo: hit.memo || '' };
}

export async function closedNoteFor(name) {
  const data = await loadClosed();
  const hit = data.items.find((c) => name.includes(c.name));
  if (!hit) return '';
  const now = new Date();
  const active = inRange(hit, now.getMonth() + 1, now.getDate());
  return `<p class="closed-note ${active ? 'on' : ''}">🚫 금어기 ${rangeText(hit)}${hit.memo ? ` (${esc(hit.memo)})` : ''}${active ? ' · 지금 금어기예요' : ''}
    <small>${esc(data.note)}</small></p>`;
}

// 소매와 도매에 같은 이름이 있으면 하나만 (소매 우선). "갈치류"와 "갈치"도 같은 것으로 본다.
const baseName = (name) => name.split('(')[0].replace(/류$/, '').trim();
export function uniqByName(list) {
  const order = { item: 0, produce: 1, fish: 2 };
  const seen = new Set();
  return [...list].sort((a, b) => order[a.kind] - order[b.kind])
    .filter((r) => { const k = baseName(r.name); if (seen.has(k)) return false; seen.add(k); return true; });
}

// ── 카드 조각 ────────────────────────────────────────────────

function chip(r) {
  return `<a class="home-chip" href="${esc(r.href)}">${esc(r.emoji || '')} ${esc(r.name)}</a>`;
}

function card(r) {
  const price = r.price != null ? `${won(r.price)}<small> / ${esc(r.unit)}</small>` : '<small>시세 없음</small>';
  return `<a class="card" href="${esc(r.href)}">
    <div class="card-top"><h3><span class="emoji" aria-hidden="true">${esc(r.emoji || '')}</span>${esc(r.name)}</h3>
      <span class="tag">${KIND_LABEL[r.kind]}</span></div>
    <div class="price num">${price}</div>
    ${r.text ? `<p class="card-sub">${esc(r.text.length > 54 ? `${r.text.slice(0, 54)}…` : r.text)}</p>` : ''}
  </a>`;
}

const grid = (list, empty) => (list.length ? `<div class="grid">${list.map(card).join('')}</div>` : `<p class="empty">${empty}</p>`);

// ── 검색 ─────────────────────────────────────────────────────

export async function searchView(view, q) {
  const query = (q || '').trim();
  view.innerHTML = `<h1 class="page-title">🔍 검색 <small>${esc(query)}</small></h1><p class="empty">찾는 중…</p>`;
  const all = await loadAll();
  const needle = query.replace(/\s+/g, '').toLowerCase();
  const hits = needle
    ? all.records.filter((r) => `${r.name}${r.text}${r.main_region}`.replace(/\s+/g, '').toLowerCase().includes(needle))
    : [];
  // 이름이 맞는 것을 앞에 둔다
  hits.sort((a, b) => (b.name.includes(query) - a.name.includes(query)) || a.name.localeCompare(b.name, 'ko'));
  const by = (k) => hits.filter((r) => r.kind === k);
  view.innerHTML = `
    <h1 class="page-title">🔍 검색 <small>"${esc(query)}" · ${hits.length}개</small></h1>
    ${!needle ? '<p class="empty">찾을 식재료 이름을 입력해 주세요.</p>' : ''}
    ${needle && !hits.length ? '<p class="empty">일치하는 식재료가 없어요. 다른 이름으로 찾아 보세요.</p>' : ''}
    ${['item', 'produce', 'fish'].map((k) => (by(k).length ? `
      <h2 class="section-title">${KIND_LABEL[k]} <small>${by(k).length}개</small></h2>${grid(by(k))}` : '')).join('')}`;
}

// ── 제철 달력 ────────────────────────────────────────────────

export async function calendarView(view, month) {
  view.innerHTML = '<h1 class="page-title">📅 제철 달력</h1><p class="empty">불러오는 중…</p>';
  const all = await loadAll();
  const m = month >= 1 && month <= 12 ? month : all.month;
  const closed = await loadClosed();
  const here = uniqByName(all.records.filter((r) => r.months.includes(m)));
  const ending = here.filter((r) => phaseOf(r, m).ending);
  const starting = here.filter((r) => phaseOf(r, m).starting);
  const rest = here.filter((r) => !phaseOf(r, m).ending && !phaseOf(r, m).starting);
  const closedNow = closed.items.filter((c) => (c.start[0] <= m && m <= c.end[0]));

  const section = (title, list, hint) => (list.length ? `
    <section class="home-block">
      <h2 class="section-title">${title} <small>${hint} · ${list.length}개</small></h2>
      <div class="home-cal cal-free">${list.map(chip).join('')}</div>
    </section>` : '');

  view.innerHTML = `
    <h1 class="page-title">📅 제철 달력</h1>
    <div class="home-months" role="toolbar" aria-label="월 선택">
      ${Array.from({ length: 12 }, (_, n) => n + 1).map((x) => `<a class="chip" href="#/calendar?m=${x}" aria-pressed="${x === m}">${x}월</a>`).join('')}
    </div>
    ${section('새로 제철이 시작돼요', starting, `${m}월부터`)}
    ${section('이번 달까지예요', ending, `${m}월이 마지막`)}
    ${section('한창 제철이에요', rest, `${m}월`)}
    ${!here.length ? '<p class="empty">이 달 제철로 등록된 품목이 없어요.</p>' : ''}
    ${closedNow.length ? `
      <section class="home-block">
        <h2 class="section-title">금어기가 걸쳐 있어요 <small>${m}월</small></h2>
        <ul class="closed-list">${closedNow.map((c) => `<li><b>${esc(c.name)}</b> ${rangeText(c)}${c.memo ? ` · ${esc(c.memo)}` : ''}</li>`).join('')}</ul>
        <p class="top-note">${esc(closed.note)}</p>
      </section>` : ''}`;
}

// ── 산지 지도 ────────────────────────────────────────────────

export async function mapView(view, prov) {
  view.innerHTML = '<h1 class="page-title">🗺 산지 지도</h1><p class="empty">불러오는 중…</p>';
  const all = await loadAll();
  const sel = FULL[prov] ? prov : '';
  const counts = Object.fromEntries(SHORTS.map((p) => [p, all.records.filter((r) => r.provinces.includes(p)).length]));
  const list = sel ? all.records.filter((r) => r.provinces.includes(sel)) : [];
  view.innerHTML = `
    <h1 class="page-title">🗺 산지 지도 <small>${sel ? FULL[sel] : '지역을 골라 보세요'}</small></h1>
    <div class="map-layout">
      <div class="map-side">
        <div id="map-box" class="home-spot-map" aria-busy="true"></div>
        <div class="map-chips">
          ${SHORTS.map((p) => `<a class="chip" href="#/map?p=${p}" aria-pressed="${p === sel}">${p} <small class="num">${counts[p]}</small></a>`).join('')}
        </div>
      </div>
      <div class="map-main">
        ${sel ? `<h2 class="section-title">${FULL[sel]}에서 나는 식재료 <small>${list.length}개</small></h2>
          ${grid(list.slice(0, 120), '이 지역 산지로 등록된 식재료가 없어요.')}
          ${list.length > 120 ? '<p class="top-note">상위 120개만 보여 드려요.</p>' : ''}`
          : '<p class="empty">오른쪽 목록이나 지도 옆 칩에서 지역을 누르면 그 지역의 식재료가 나와요.</p>'}
      </div>
    </div>`;
  const box = view.querySelector('#map-box');
  renderKoreaMap(box, { points: [], provinces: sel ? [FULL[sel]] : [] })
    .catch(() => { box.innerHTML = ''; })
    .finally(() => box.removeAttribute('aria-busy'));
}

// ── 식재료 사전 ──────────────────────────────────────────────

export async function dictView(view, q) {
  view.innerHTML = '<h1 class="page-title">📖 식재료 사전</h1><p class="empty">불러오는 중…</p>';
  const all = await loadAll();
  const seen = new Set();
  const entries = all.records
    .filter((r) => r.text && !seen.has(r.name) && seen.add(r.name))
    .sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  view.innerHTML = `
    <h1 class="page-title">📖 식재료 사전 <small>${entries.length}개</small></h1>
    <p class="detail-intro">이름만 알던 식재료가 어떤 건지, 어떻게 먹는지 한 줄로 보여 드려요.</p>
    <div class="controls"><input class="dict-search" type="search" placeholder="이름이나 설명으로 찾기" value="${esc(q || '')}" aria-label="사전 검색"></div>
    <div id="dict-list"></div>`;
  const list = view.querySelector('#dict-list');
  const input = view.querySelector('.dict-search');
  const draw = () => {
    const needle = input.value.replace(/\s+/g, '').toLowerCase();
    const shown = entries.filter((r) => !needle || `${r.name}${r.text}`.replace(/\s+/g, '').toLowerCase().includes(needle));
    list.innerHTML = shown.length ? `<ul class="dict-items">${shown.slice(0, 200).map((r) => `
      <li><a href="${esc(r.href)}"><b>${esc(r.emoji || '')} ${esc(r.name)}</b>
        <span class="tag">${KIND_LABEL[r.kind]}</span><p>${esc(r.text)}</p></a></li>`).join('')}</ul>
      ${shown.length > 200 ? '<p class="top-note">200개까지만 보여 드려요. 검색어를 더 적어 보세요.</p>' : ''}`
      : '<p class="empty">일치하는 식재료가 없어요.</p>';
  };
  input.addEventListener('input', draw);
  draw();
}

// 홈 캐러셀의 마지막 장. 이번 달로 끝나는 것, 새로 시작하는 것, 지금 금어기인 어종을 한 장에 모은다.
export async function homeNewsSlideHtml() {
  const all = await loadAll();
  const { month } = all;
  const closed = await loadClosed();
  const closedNow = closed.items.filter((c) => inRange(c, month, new Date().getDate()));
  const retailFirst = (a, b) => (a.kind === 'item' ? 0 : 1) - (b.kind === 'item' ? 0 : 1);
  const pick = (test) => uniqByName(all.records.filter((r) => test(phaseOf(r, month)))).sort(retailFirst).slice(0, 8);
  const ending = pick((p) => p.ending);
  const starting = pick((p) => p.starting);
  const col = (title, list) => `
    <div class="home-news-col"><h3>${title}</h3>
      <div class="home-cal cal-free">${list.length ? list.map(chip).join('') : '<span class="top-note">해당하는 품목이 없어요.</span>'}</div></div>`;
  return `
    <div class="home-slide-text">
      <div class="eyebrow">이달의 소식</div>
      <h2>${month}월에 챙겨 볼 것들</h2>
      <p>끝나기 전에 먹어 둘 것, 새로 시작하는 제철, 지금 잡을 수 없는 어종이에요.</p>
      <a class="hero-cta" href="#/calendar">제철 달력 전체 보기 →</a>
    </div>
    <div class="home-news-cols">
      ${col('⏳ 이번 달이 마지막', ending)}
      ${col('🌱 새로 제철이 시작', starting)}
      <div class="home-news-col"><h3>🚫 지금 금어기</h3>
        ${closedNow.length ? `<ul class="closed-list">${closedNow.slice(0, 4).map((c) => `<li><b>${esc(c.name)}</b> ${rangeText(c)}</li>`).join('')}</ul>`
          : '<span class="top-note">지금 금어기인 대표 어종이 없어요.</span>'}</div>
    </div>`;
}

// ── 홈: 알림, 이달의 소식, 오늘의 장보기 추천 ───────────────────

export async function drawHomeExtras2(view) {
  const box = view.querySelector('#home-news');
  const picksBox = view.querySelector('#home-picks');
  const alertBox = view.querySelector('#home-alerts');
  if (!box || !picksBox || !alertBox) return;
  let all;
  try { all = await loadAll(); } catch { return; }
  const { month } = all;

  // 알림: 사이트를 열 때 조건을 확인한다 (푸시 알림이 아니다)
  const rules = alerts.list();
  const fired = rules.map((a) => {
    const r = all.records.find((x) => x.key === a.key);
    return r && r.vs != null && r.vs <= -a.pct ? { r, a } : null;
  }).filter(Boolean);
  alertBox.innerHTML = fired.length ? `
    <div class="alert-banner" role="status">
      <b>🔔 알림</b>
      ${fired.map(({ r, a }) => `<a href="${esc(r.href)}">${esc(r.emoji)} ${esc(r.name)} 평년보다 ${Math.abs(r.vs)}% 싸요 <small>(${a.pct}% 이상일 때)</small></a>`).join('')}
    </div>` : '';

  // 이달의 소식
  const closed = await loadClosed();
  const today = new Date();
  const closedNow = closed.items.filter((c) => inRange(c, month, today.getDate()));
  const ph = (r) => phaseOf(r, month);
  const retailFirst = (a, b) => (a.kind === 'item' ? 0 : 1) - (b.kind === 'item' ? 0 : 1);
  const starting = uniqByName(all.records.filter((r) => ph(r).starting)).sort(retailFirst).slice(0, 14);
  const ending = uniqByName(all.records.filter((r) => ph(r).ending)).sort(retailFirst).slice(0, 14);
  box.innerHTML = `
    <h2 class="section-title">${month}월의 소식 <small><a href="#/calendar">제철 달력 전체 보기 →</a></small></h2>
    <div class="news-grid">
      <article class="news-card ending">
        <h3>⏳ 이번 달이 마지막이에요</h3>
        <p>${ending.length ? '놓치기 전에 챙겨 보세요.' : '이번 달로 끝나는 제철 품목이 없어요.'}</p>
        <div class="home-cal cal-free">${ending.map(chip).join('')}</div>
      </article>
      <article class="news-card starting">
        <h3>🌱 새로 제철이 시작돼요</h3>
        <p>${starting.length ? `${month}월부터 맛이 오르는 재료예요.` : '이번 달 새로 시작하는 품목이 없어요.'}</p>
        <div class="home-cal cal-free">${starting.map(chip).join('')}</div>
      </article>
      <article class="news-card closed">
        <h3>🚫 지금 금어기예요</h3>
        <p>${closedNow.length ? '이 기간에는 잡거나 팔 수 없는 어종이에요.' : '지금 금어기에 걸린 대표 어종이 없어요.'}</p>
        <ul class="closed-list">${closedNow.map((c) => `<li><b>${esc(c.name)}</b> ${rangeText(c)}${c.memo ? ` · ${esc(c.memo)}` : ''}</li>`).join('')}</ul>
        <small class="top-note">${esc(closed.note)}</small>
      </article>
    </div>`;

  // 오늘의 장보기 추천: 지금 제철이면서 평년보다 싼 소매 품목
  const picks = all.records
    .filter((r) => r.kind === 'item' && phaseOf(r, month).now && r.vs != null && r.vs < 0)
    .sort((a, b) => a.vs - b.vs).slice(0, 6);
  picksBox.innerHTML = picks.length ? `
    <h2 class="section-title">오늘의 장보기 추천 <small>제철이면서 평년보다 싼 품목</small></h2>
    <div class="pick-grid">
      ${picks.map((r) => `
        <a class="pick" href="${esc(r.href)}">
          <span class="pick-emoji" aria-hidden="true">${esc(r.emoji)}</span>
          <b>${esc(r.name)}</b>
          <span class="num">${won(r.price)}<small> / ${esc(r.unit)}</small></span>
          <span class="badge">▼ ${Math.abs(r.vs)}%</span>
        </a>`).join('')}
    </div>
    <p><button type="button" class="btn" data-add-picks>🧺 추천 ${picks.length}개 한 번에 담기</button></p>` : '';
  picksBox.querySelector('[data-add-picks]')?.addEventListener('click', (e) => {
    let added = 0;
    for (const r of picks) {
      if (!cart.has(r.key)) {
        cart.toggle({ key: r.key, kind: 'item', name: r.name, emoji: r.emoji, href: r.href });
        added += 1;
      }
    }
    e.currentTarget.textContent = added ? `✓ ${added}개를 담았어요` : '이미 모두 담겨 있어요';
  });
}

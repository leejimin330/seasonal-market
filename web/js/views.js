// 화면들. 각 함수는 #view를 채운다. 사용자 상태는 main.js의 session을 받는다.

import { api, ApiError } from './api.js';
import { carousel } from './carousel.js';
import { renderTrendChart } from './chart.js';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const won = (v) => (v == null ? '—' : `${v.toLocaleString('ko-KR')}원`);
// 쇼핑몰 검색 결과로 바로 가는 링크. API가 아니라 각 사이트의 검색 주소라 신청·승인이 필요 없다.
// (네이버 쇼핑 검색 API는 2026-07-31 종료, 쿠팡 파트너스 API는 실적 승인 뒤에만 열린다)
const SHOPS = [
  ['쿠팡', (q) => `https://www.coupang.com/np/search?q=${q}`],
  ['네이버쇼핑', (q) => `https://search.shopping.naver.com/search/all?query=${q}`],
  ['컬리', (q) => `https://www.kurly.com/search?sword=${q}`],
  ['11번가', (q) => `https://search.11st.co.kr/pc/total-search?kwd=${q}`],
  ['G마켓', (q) => `https://www.gmarket.co.kr/n/search?keyword=${q}`],
];

const CATEGORY_GROUP = { 채소: '채소', 버섯: '채소', 기타: '채소', 과채: '과일', 과일: '과일', 수산: '수산' };
// 받침 유무로 이/가를 고른다 ("전통시장이", "대형마트가"). 한글이 아니면 받침 없음으로 본다.
const iGa = (word) => {
  const code = String(word).charCodeAt(String(word).length - 1) - 0xac00;
  return code >= 0 && code <= 11171 && code % 28 !== 0 ? '이' : '가';
};

function deltaBadge(pct) {
  if (pct == null) return '<span class="delta flat" title="같은 시기 과거 조사 기록이 3년치가 안 돼요">평년 자료 부족</span>';
  if (Math.abs(pct) < 1) return '<span class="delta flat">평년 수준</span>';
  return pct < 0
    ? `<span class="delta down" title="평년보다 ${Math.abs(pct)}% 쌉니다">▼ 평년보다 ${Math.abs(pct)}%</span>`
    : `<span class="delta up" title="평년보다 ${pct}% 비쌉니다">▲ 평년보다 ${pct}%</span>`;
}

function remaining(until) {
  const hours = Math.max(0, (until * 1000 - Date.now()) / 3600000);
  return hours >= 1 ? `${Math.floor(hours)}시간 남음` : `${Math.max(1, Math.round(hours * 60))}분 남음`;
}

// ── 메인 ─────────────────────────────────────────────────────

const mainState = { group: '전체', seasonOnly: true, sort: 'cheap' };

export async function mainView(view) {
  view.innerHTML = '<p class="empty">불러오는 중…</p>';
  const { month, items } = await api.items();
  const inSeason = items.filter((i) => i.in_season);

  const cheap = inSeason.filter((i) => !i.stale && i.vs_normal != null && i.vs_normal < 0)
    .sort((a, b) => a.vs_normal - b.vs_normal).slice(0, 5);

  view.innerHTML = `
    <section class="hero-carousel" id="hero"></section>
    ${cheap.length ? `
    <section class="cheap-strip">
      <h2 class="section-title">지금 싼 제철 품목 <small>평년 대비 하락률 순</small></h2>
      <div class="cheap-list">
        ${cheap.map((i, n) => `
          <a class="cheap-card" href="#/item/${i.id}">
            <span class="cheap-rank">${n + 1}</span>
            <div><b>${i.emoji} ${esc(i.name)}</b><span>▼ ${Math.abs(i.vs_normal)}%</span></div>
          </a>`).join('')}
      </div>
    </section>` : ''}
    <section>
      <div class="controls" role="toolbar" aria-label="품목 거르기">
        ${['전체', '채소', '과일', '수산'].map((g) => `<button class="chip" data-group="${g}" aria-pressed="${mainState.group === g}">${g}</button>`).join('')}
        <button class="chip" data-season aria-pressed="${mainState.seasonOnly}">제철만</button>
        <span class="spacer"></span>
        <select class="chip" data-sort aria-label="정렬">
          <option value="cheap" ${mainState.sort === 'cheap' ? 'selected' : ''}>평년보다 싼 순</option>
          <option value="name" ${mainState.sort === 'name' ? 'selected' : ''}>이름순</option>
        </select>
      </div>
      <div class="grid" id="item-grid"></div>
    </section>`;

  drawHero(view.querySelector('#hero'), { month, inSeason, cheap });

  const grid = view.querySelector('#item-grid');
  const draw = () => {
    let list = items.filter((i) => mainState.group === '전체' || CATEGORY_GROUP[i.category] === mainState.group);
    if (mainState.seasonOnly) list = list.filter((i) => i.in_season);
    list.sort(mainState.sort === 'name'
      ? (a, b) => a.name.localeCompare(b.name, 'ko')
      : (a, b) => (a.stale - b.stale) || (a.vs_normal ?? 999) - (b.vs_normal ?? 999));
    grid.innerHTML = list.length ? list.map((i) => `
      <a class="card" href="#/item/${i.id}">
        <div class="card-top">
          <h3><span class="emoji" aria-hidden="true">${i.emoji}</span>${esc(i.name)}</h3>
          ${i.in_season ? '<span class="badge">제철</span>' : `<span class="tag">${esc(i.category)}</span>`}
        </div>
        <div class="price num">${i.price == null || i.stale ? '<span class="tag">지금은 조사되지 않아요</span>' : `${won(i.price)}<small>/ ${esc(i.price_unit)}</small>`}</div>
        <div class="card-foot">
          <span>${esc(i.main_region)}</span>
          ${i.price == null || i.stale ? '' : deltaBadge(i.vs_normal)}
        </div>
      </a>`).join('') : '<p class="empty">조건에 맞는 품목이 없어요.</p>';
  };
  draw();

  view.querySelectorAll('[data-group]').forEach((b) => b.addEventListener('click', () => {
    mainState.group = b.dataset.group;
    view.querySelectorAll('[data-group]').forEach((x) => x.setAttribute('aria-pressed', x === b));
    draw();
  }));
  view.querySelector('[data-season]').addEventListener('click', (e) => {
    mainState.seasonOnly = !mainState.seasonOnly;
    e.currentTarget.setAttribute('aria-pressed', mainState.seasonOnly);
    draw();
  });
  view.querySelector('[data-sort]').addEventListener('change', (e) => { mainState.sort = e.target.value; draw(); });
}

// 메인 배너. 첫 장은 이번 달 요약, 다음 장부터 평년보다 싼 제철 품목을 한 장에 하나씩.
function drawHero(host, { month, inSeason, cheap }) {
  const { node, addSlide } = carousel({ label: '이번 달 제철 추천' });
  host.appendChild(node);

  const intro = document.createElement('div');
  intro.className = 'hero-slide hero-intro';
  intro.innerHTML = `
    <div class="eyebrow">${month}월의 장바구니</div>
    <h1>지금 제철인 ${inSeason.length}가지,<br>평년보다 얼마나 쌀까요?</h1>
    <p>현재 가격, 평년 대비 등락, 가격 추이는 무료예요.<br>전통시장·대형마트 중 어디가 싼지는 크레딧으로 볼 수 있어요.</p>
    <div class="hero-emojis" aria-hidden="true">${inSeason.slice(0, 8).map((i) => i.emoji).join(' ')}</div>`;
  addSlide(intro);

  for (const i of cheap) {
    const slide = document.createElement('a');
    slide.className = 'hero-slide hero-item';
    slide.href = `#/item/${i.id}`;
    slide.innerHTML = `
      <div class="hero-item-emoji" aria-hidden="true">${i.emoji}</div>
      <div class="hero-item-body">
        <div class="eyebrow">제철 · 평년보다 싸요</div>
        <h2>${esc(i.name)} <span class="hero-drop">▼ ${Math.abs(i.vs_normal)}%</span></h2>
        <p class="hero-price num">${won(i.price)} <small>/ ${esc(i.price_unit)} · ${esc(i.date)} 기준</small></p>
        <p class="hero-intro-text">${esc(i.intro)}</p>
        <span class="hero-cta">자세히 보기 →</span>
      </div>`;
    addSlide(slide);
  }
}

// ── 품목 상세 ────────────────────────────────────────────────

export async function itemView(view, id, session) {
  view.innerHTML = '<p class="empty">불러오는 중…</p>';
  let item;
  try {
    item = await api.item(id);
  } catch (err) {
    view.innerHTML = `<a class="back" href="#/">← 목록</a><p class="empty">${esc(err.message)}</p>`;
    return;
  }
  const month = new Date().getMonth() + 1;

  view.innerHTML = `
    <a class="back" href="#/">← 목록</a>
    <section class="detail-head">
      <div>
        <h1><span class="emoji" aria-hidden="true">${item.emoji}</span>${esc(item.name)}</h1>
        ${item.intro ? `<p class="detail-intro">${esc(item.intro)}</p>` : ''}
        <div class="detail-meta">
          ${item.in_season ? '<span class="badge">지금 제철</span>' : '<span class="tag">제철 아님</span>'}
          <span>주산지 ${esc(item.main_region) || '—'}</span>
          ${item.season_note ? `<span>· ${esc(item.season_note)}</span>` : ''}
        </div>
      </div>
      <div class="now-box">
        <div class="label">${item.stale ? `마지막 조사 · ${item.date}` : `현재 소매가 ${item.date ? `· ${item.date} 기준` : ''}`}</div>
        <div class="price num">${item.price == null ? '정보 없음' : `${won(item.price)}<small>/ ${esc(item.price_unit)}</small>`}</div>
        ${item.price == null ? '' : item.stale ? '<span class="delta flat">철이 지나 지금은 조사되지 않아요</span>' : deltaBadge(item.vs_normal)}
      </div>
    </section>
    <div class="months" aria-label="제철 달">
      ${Array.from({ length: 12 }, (_, i) => i + 1).map((m) => `<span class="${item.season_months.includes(m) ? 'on' : ''} ${m === month ? 'now' : ''}" ${m === month ? 'aria-current="true"' : ''}>${m}월</span>`).join('')}
    </div>
    <section class="shop-links" aria-label="쇼핑몰에서 찾아보기">
      <span class="shop-links-title">사러 가기</span>
      ${SHOPS.map(([name, url]) => `<a class="shop-link" href="${url(encodeURIComponent(item.name))}" target="_blank" rel="noopener noreferrer">${name} ↗</a>`).join('')}
      <span class="unlock-note">각 쇼핑몰의 "${esc(item.name)}" 검색 결과로 이동해요.</span>
    </section>
    <section class="panel" id="trend-panel"></section>
    ${item.pick || item.store ? `
    <section class="tips">
      ${item.pick ? `<div class="tip"><h3>🛒 고르는 법</h3><p>${esc(item.pick)}</p></div>` : ''}
      ${item.store ? `<div class="tip"><h3>🧊 보관법</h3><p>${esc(item.store)}</p></div>` : ''}
    </section>` : ''}
    <section class="panel" id="where-panel"></section>`;

  setupFree(view.querySelector('#trend-panel'), {
    title: '가격 변동 추이',
    empty: item.price == null ? '이 품목은 아직 가격 기록이 없어요.' : null,
    load: () => api.trend(item.id),
    render: renderTrend,
  });
  setupPaid(view.querySelector('#where-panel'), {
    title: '어디서 사면 쌀까', feature: 'where', item, session,
    disabled: item.price == null || item.stale ? '지금은 조사되지 않는 품목이라 판매처별 가격이 없어요.' : null,
    teaser: '전통시장과 대형마트 중 어디가 더 싼지, 어느 지역이 가장 싼지 전국 조사 가격으로 비교해 드려요.',
    load: () => api.where(item.id),
    render: renderWhere,
  });
}

async function setupFree(panel, { title, empty, load, render }) {
  const head = `<div class="panel-head"><h2>${title}</h2></div>`;
  if (empty) {
    panel.innerHTML = `${head}<p class="empty">${empty}</p>`;
    return;
  }
  panel.innerHTML = `${head}<p class="empty">불러오는 중…</p>`;
  try {
    const data = await load();
    panel.innerHTML = `${head}<div data-body></div>`;
    render(panel.querySelector('[data-body]'), data);
  } catch (err) {
    panel.innerHTML = `${head}<p class="empty">${esc(err.message)}</p>`;
  }
}

function setupPaid(panel, opts) {
  const { title, feature, item, session } = opts;
  const access = item.access[feature];
  const head = (note = '') => `<div class="panel-head"><h2>${title}</h2><span class="unlock-note">${note}</span></div>`;

  const locked = () => {
    if (opts.disabled) {
      panel.innerHTML = `${head()}<div class="locked"><span>${opts.disabled}</span></div>`;
      return;
    }
    const action = session.user
      ? `<button class="btn" data-unlock>🔓 ${access.cost} 크레딧으로 24시간 보기</button>
         <span class="unlock-note">보유 <span data-my-credits>${session.credits}</span> 크레딧</span>`
      : `<a class="btn" href="#/login?next=${encodeURIComponent(location.hash)}">로그인하고 보기</a>
         <span class="unlock-note">가입하면 크레딧을 드려요</span>`;
    panel.innerHTML = `${head()}<div class="locked"><span class="lock-icon" aria-hidden="true">🔒</span>
      <span>${opts.teaser}</span>${action}</div>`;
    panel.querySelector('[data-unlock]')?.addEventListener('click', async (e) => {
      if (session.credits < access.cost) {
        session.toast(`크레딧이 부족해요. (보유 ${session.credits}, 필요 ${access.cost})`);
        return;
      }
      if (!confirm(`${item.name} ${title}: ${access.cost} 크레딧을 사용합니다.\n24시간 동안 다시 차감 없이 볼 수 있어요.`)) return;
      e.currentTarget.disabled = true;
      await open();
    });
  };

  const open = async () => {
    panel.innerHTML = `${head()}<p class="empty">불러오는 중…</p>`;
    try {
      const data = await opts.load();
      session.setCredits(data.balance);
      if (data.charged) session.toast(`${data.cost} 크레딧을 사용했어요. 남은 크레딧 ${data.balance}`);
      panel.innerHTML = head(`열람 중 · ${remaining(data.unlocked_until)}`) + '<div data-body></div>';
      opts.render(panel.querySelector('[data-body]'), data, item);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) session.refresh();
      session.toast(err.message);
      locked();
    }
  };

  if (access.unlocked_until) open(); // 이용권이 살아 있으면 차감 없이 바로 연다
  else locked();
}

const RANGES = [['4주', 28], ['3개월', 91], ['1년', 366]];

function renderTrend(body, data) {
  body.innerHTML = `<div class="range-tabs" role="group" aria-label="기간">
      ${RANGES.map(([label, days], n) => `<button data-days="${days}" aria-pressed="${n === 0}">${label}</button>`).join('')}
    </div><div data-chart style="margin-top:12px"></div>`;
  const chart = body.querySelector('[data-chart]');
  const draw = (days) => {
    const last = data.series[data.series.length - 1]?.date;
    const since = new Date(new Date(last).getTime() - days * 86400000).toISOString().slice(0, 10);
    renderTrendChart(chart, data.series.filter((p) => p.date >= since), { unit: data.price_unit });
  };
  let days = 28;
  body.querySelectorAll('[data-days]').forEach((b) => b.addEventListener('click', () => {
    body.querySelectorAll('[data-days]').forEach((x) => x.setAttribute('aria-pressed', x === b));
    days = Number(b.dataset.days);
    draw(days);
  }));
  draw(days);
  // 화면 폭이 바뀌면 다시 그린다. 다른 화면으로 넘어가 그래프가 사라졌으면 리스너도 뗀다.
  let timer;
  const onResize = () => {
    clearTimeout(timer);
    timer = setTimeout(() => (chart.isConnected ? draw(days) : window.removeEventListener('resize', onResize)), 150);
  };
  window.addEventListener('resize', onResize);
}

function renderWhere(body, data) {
  const channels = Object.entries(data.channels).sort((a, b) => a[1].avg - b[1].avg);
  const regions = Object.entries(data.regions).sort((a, b) => a[1].avg - b[1].avg);
  const [cheapName, cheap] = channels[0];
  const dearest = channels[channels.length - 1];
  const gap = channels.length > 1 ? Math.round((1 - cheap.avg / dearest[1].avg) * 1000) / 10 : 0;
  const unit = esc(data.price_unit);
  const maxChannel = Math.max(...channels.map(([, c]) => c.avg));
  const bar = (v) => `<span class="bar" aria-hidden="true"><i style="width:${Math.max(4, Math.round((v / maxChannel) * 100))}%"></i></span>`;

  body.innerHTML = `
    <p class="where-headline">${channels.length > 1 && gap >= 1
      ? `<b>${esc(cheapName)}</b>${iGa(cheapName)} ${esc(dearest[0])}보다 평균 <b>${gap}%</b> 싸요.`
      : '판매처 유형 간 가격 차이가 거의 없어요.'}</p>
    <h3 class="sub-title">판매처 유형별 <small>${unit} 기준 평균 · 가장 싼 곳</small></h3>
    <ul class="rank-list">
      ${channels.map(([name, c], n) => `
        <li class="${n === 0 ? 'best' : ''}">
          <span class="rank-name">${esc(name)} <small>${c.n}곳</small></span>
          ${bar(c.avg)}
          <span class="rank-value num"><b>${won(c.avg)}</b><small>최저 ${won(c.min)}</small></span>
        </li>`).join('')}
    </ul>
    <h3 class="sub-title">가장 싼 지역 <small>지역 평균이 낮은 순</small></h3>
    <ol class="region-list">
      ${regions.slice(0, 5).map(([name, r]) => `
        <li><span>${esc(name)}</span><span class="num">${won(r.avg)} <small>(${r.n}곳)</small></span></li>`).join('')}
    </ol>
    <p class="fineprint">${esc(data.date)} 한국농수산식품유통공사(aT) 소매가격 조사 기준, 조사처 ${data.n}곳. 조사처 이름은 aT가 익명으로 공개해서 유형까지만 보여드려요.</p>`;
}

// ── 로그인 / 가입 ────────────────────────────────────────────

export function authView(view, mode, session, next) {
  const isSignup = mode === 'signup';
  view.innerHTML = `
    <form class="form-card" novalidate>
      <h1>${isSignup ? '가입하기' : '로그인'}</h1>
      <p>${isSignup ? `가입하면 ${session.status?.signup_bonus ?? ''} 크레딧을 드려요.` : '크레딧으로 가격 추이와 최저가를 볼 수 있어요.'}</p>
      <label class="field">아이디
        <input name="user_id" autocomplete="username" required minlength="3" maxlength="20" placeholder="영문 소문자·숫자·밑줄 3~20자">
      </label>
      <label class="field">비밀번호
        <input name="password" type="password" autocomplete="${isSignup ? 'new-password' : 'current-password'}" required minlength="8" placeholder="8자 이상">
      </label>
      <button class="btn" type="submit">${isSignup ? '가입하고 시작하기' : '로그인'}</button>
      <div class="form-error" role="alert"></div>
      <div class="form-switch">${isSignup
        ? `이미 계정이 있나요? <a href="#/login${next ? `?next=${encodeURIComponent(next)}` : ''}">로그인</a>`
        : `처음이신가요? <a href="#/signup${next ? `?next=${encodeURIComponent(next)}` : ''}">가입하기</a>`}</div>
    </form>`;
  const form = view.querySelector('form');
  form.user_id.focus();
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const error = form.querySelector('.form-error');
    const button = form.querySelector('button');
    error.textContent = '';
    button.disabled = true;
    try {
      const fn = isSignup ? api.signup : api.login;
      const me = await fn(form.user_id.value.trim(), form.password.value);
      session.set(me);
      if (isSignup) session.toast(`환영해요! ${me.credits} 크레딧을 드렸어요.`);
      location.hash = next || '#/';
    } catch (err) {
      error.textContent = err.message;
      button.disabled = false;
    }
  });
}

// ── 내 크레딧 ────────────────────────────────────────────────

const REASON = { signup_bonus: '가입 보너스', use: '사용', admin_grant: '지급' };
const FEATURE = { trend: '가격 추이', where: '판매처 비교', shop: '최저가' };

function ledgerRows(ledger, names) {
  return ledger.map((r) => `<tr>
    <td>${new Date(r.created_at * 1000).toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' })}</td>
    <td>${REASON[r.reason] || r.reason}${r.feature ? ` · ${FEATURE[r.feature] || r.feature}` : ''}${r.item_id ? ` · ${esc(names[r.item_id] || r.item_id)}` : ''}${r.memo ? ` · ${esc(r.memo)}` : ''}</td>
    <td class="right num ${r.delta > 0 ? 'plus' : 'minus'}">${r.delta > 0 ? '+' : ''}${r.delta}</td>
    <td class="right num">${r.balance_after}</td></tr>`).join('');
}

export async function meView(view, session) {
  if (!session.user) { location.hash = '#/login?next=%23%2Fme'; return; }
  const [{ ledger }, { items }] = await Promise.all([api.ledger(), api.items()]);
  const names = Object.fromEntries(items.map((i) => [i.id, i.name]));
  view.innerHTML = `
    <div class="eyebrow">${esc(session.user)}님의 크레딧</div>
    <div class="balance-hero"><b class="num">${session.credits}</b><span>크레딧</span></div>
    <p class="fineprint" style="margin:-8px 0 20px">한 번 연 기능은 24시간 동안 다시 차감되지 않아요. 크레딧 충전은 관리자에게 문의해 주세요.</p>
    <section class="panel">
      <div class="panel-head"><h2>사용 내역</h2></div>
      ${ledger.length ? `<div class="table-scroll"><table>
        <thead><tr><th>일시</th><th>내용</th><th class="right">변동</th><th class="right">잔액</th></tr></thead>
        <tbody>${ledgerRows(ledger, names)}</tbody></table></div>` : '<p class="empty">아직 내역이 없어요.</p>'}
    </section>`;
}

// ── 관리자 ───────────────────────────────────────────────────

export async function adminView(view, session) {
  if (!session.isAdmin) { view.innerHTML = '<p class="empty">관리자만 볼 수 있어요.</p>'; return; }
  const { users } = await api.adminUsers();
  view.innerHTML = `
    <h1 class="section-title" style="font-size:22px">관리자 · 크레딧 지급</h1>
    <section class="panel">
      <form class="grant-form">
        <input name="user_id" placeholder="아이디" required list="user-list">
        <datalist id="user-list">${users.map((u) => `<option value="${esc(u.id)}">`).join('')}</datalist>
        <input name="amount" type="number" min="1" max="10000" placeholder="크레딧" required>
        <input name="memo" placeholder="메모 (예: 테스터 지급)" maxlength="200">
        <button class="btn" type="submit">지급</button>
      </form>
      <div class="table-scroll"><table>
        <thead><tr><th>아이디</th><th class="right">잔액</th><th>가입일</th><th></th></tr></thead>
        <tbody>${users.map((u) => `<tr>
          <td>${esc(u.id)}</td><td class="right num">${u.credits}</td>
          <td>${new Date(u.created_at * 1000).toLocaleDateString('ko-KR')}</td>
          <td class="right"><button class="btn ghost small" data-pick="${esc(u.id)}">선택</button></td></tr>`).join('')}
        </tbody></table></div>
    </section>`;
  const form = view.querySelector('form');
  view.querySelectorAll('[data-pick]').forEach((b) => b.addEventListener('click', () => {
    form.user_id.value = b.dataset.pick;
    form.amount.focus();
  }));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const r = await api.adminGrant(form.user_id.value.trim(), Number(form.amount.value), form.memo.value);
      session.toast(`${r.user_id}에게 지급했어요. 잔액 ${r.balance}`);
      if (r.user_id === session.user) session.setCredits(r.balance);
      adminView(view, session);
    } catch (err) {
      session.toast(err.message);
    }
  });
}

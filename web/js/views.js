// 화면들. 각 함수는 #view를 채운다. 사용자 상태는 main.js의 session을 받는다.

import { api, ApiError } from './api.js';
import { renderTrendChart } from './chart.js';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const won = (v) => (v == null ? '—' : `${v.toLocaleString('ko-KR')}원`);
const CATEGORY_GROUP = { 채소: '채소', 과채: '과일', 과일: '과일', 수산: '수산' };

function deltaBadge(pct) {
  if (pct == null) return '<span class="delta flat">평년 정보 없음</span>';
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

  const cheap = inSeason.filter((i) => i.vs_normal != null && i.vs_normal < 0)
    .sort((a, b) => a.vs_normal - b.vs_normal).slice(0, 5);

  view.innerHTML = `
    <section class="hero">
      <div>
        <div class="eyebrow">${month}월의 장바구니</div>
        <h1>지금 제철인 ${inSeason.length}가지,<br>평년보다 얼마나 쌀까요?</h1>
        <p>현재 가격과 평년 대비 등락은 무료예요. 가격 추이와 최저가 판매처는 크레딧으로 볼 수 있어요.</p>
      </div>
    </section>
    ${cheap.length ? `
    <section class="cheap-strip">
      <h2 class="section-title">지금 싼 제철 품목 <small>평년 대비 하락률 순</small></h2>
      <div class="cheap-list">
        ${cheap.map((i, n) => `
          <a class="cheap-card" href="#/item/${i.id}">
            <span class="cheap-rank">${n + 1}</span>
            <div><b>${esc(i.name)}</b><span>▼ ${Math.abs(i.vs_normal)}%</span></div>
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

  const grid = view.querySelector('#item-grid');
  const draw = () => {
    let list = items.filter((i) => mainState.group === '전체' || CATEGORY_GROUP[i.category] === mainState.group);
    if (mainState.seasonOnly) list = list.filter((i) => i.in_season);
    list.sort(mainState.sort === 'name'
      ? (a, b) => a.name.localeCompare(b.name, 'ko')
      : (a, b) => (a.vs_normal ?? 999) - (b.vs_normal ?? 999));
    grid.innerHTML = list.length ? list.map((i) => `
      <a class="card" href="#/item/${i.id}">
        <div class="card-top">
          <h3>${esc(i.name)}</h3>
          ${i.in_season ? '<span class="badge">제철</span>' : `<span class="tag">${esc(i.category)}</span>`}
        </div>
        <div class="price num">${i.price == null ? '<span class="tag">가격 정보 없음</span>' : `${won(i.price)}<small>/ ${esc(i.price_unit)}</small>`}</div>
        <div class="card-foot">
          <span>${esc(i.main_region)}</span>
          ${i.price == null ? '' : deltaBadge(i.vs_normal)}
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
        <h1>${esc(item.name)}</h1>
        <div class="detail-meta">
          ${item.in_season ? '<span class="badge">지금 제철</span>' : '<span class="tag">제철 아님</span>'}
          <span>주산지 ${esc(item.main_region) || '—'}</span>
          ${item.season_note ? `<span>· ${esc(item.season_note)}</span>` : ''}
        </div>
      </div>
      <div class="now-box">
        <div class="label">현재 소매가 ${item.date ? `· ${item.date} 기준` : ''}</div>
        <div class="price num">${item.price == null ? '정보 없음' : `${won(item.price)}<small>/ ${esc(item.price_unit)}</small>`}</div>
        ${item.price == null ? '' : deltaBadge(item.vs_normal)}
      </div>
    </section>
    <div class="months" aria-label="제철 달">
      ${Array.from({ length: 12 }, (_, i) => i + 1).map((m) => `<span class="${item.season_months.includes(m) ? 'on' : ''} ${m === month ? 'now' : ''}" ${m === month ? 'aria-current="true"' : ''}>${m}월</span>`).join('')}
    </div>
    <section class="panel" id="trend-panel"></section>
    <section class="panel" id="shop-panel"></section>`;

  setupPaid(view.querySelector('#trend-panel'), {
    title: '가격 변동 추이', feature: 'trend', item, session,
    disabled: item.price == null ? '이 품목은 아직 가격 기록이 없어요.' : null,
    teaser: '최근 4주 · 3개월 · 1년 동안의 소매가를 평년가와 겹쳐서 보여드려요.',
    load: () => api.trend(item.id),
    render: renderTrend,
  });
  setupPaid(view.querySelector('#shop-panel'), {
    title: '가장 싸게 파는 곳', feature: 'shop', item, session,
    teaser: `온라인 쇼핑몰의 판매가를 ${esc(item.shop_label)}당 가격으로 맞춰서, 싼 순서로 5곳을 찾아드려요.`,
    load: () => api.shop(item.id),
    render: renderShop,
  });
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
         <span class="unlock-note">보유 ${session.credits} 크레딧</span>`
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

function renderShop(body, data) {
  if (!data.offers.length) {
    body.innerHTML = '<p class="empty">양을 비교할 수 있는 상품을 찾지 못했어요.</p>';
    return;
  }
  const fetched = new Date(data.fetched_at * 1000).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
  body.innerHTML = `<ol class="offers">
    ${data.offers.map((o, n) => `
      <li class="offer">
        <span class="offer-rank">${n + 1}</span>
        <div>
          <div class="offer-title">${o.link ? `<a href="${esc(o.link)}" target="_blank" rel="noopener noreferrer">${esc(o.title)}</a>` : esc(o.title)}</div>
          <div class="offer-mall">${esc(o.mall)}</div>
        </div>
        <div class="offer-price num"><b>${won(o.unit_price)}</b><span>${esc(data.shop_label)}당 · 판매가 ${won(o.price)}</span></div>
      </li>`).join('')}
  </ol>
  <p class="fineprint">${fetched} 기준 검색 결과예요. 배송비는 포함되지 않았을 수 있고, 양은 상품명에서 읽은 값이에요.</p>`;
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
const FEATURE = { trend: '가격 추이', shop: '최저가' };

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

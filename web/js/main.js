// 해시 라우터와 로그인 상태.
//   #/            메인 (제철 목록)
//   #/item/:id    품목 상세
//   #/login, #/signup, #/me, #/admin

import { maybeShowAd } from './adpopup.js';
import { api } from './api.js';
import {
  adminView, authView, fishDetailView, fishListView, homeView, itemView, mainView, meView, produceDetailView,
  produceListView,
} from './views.js';

const view = document.getElementById('view');
const nav = document.getElementById('topnav');
const toastEl = document.getElementById('toast');
let toastTimer;

const session = {
  user: null,
  credits: 0,
  isAdmin: false,
  status: null,
  set(me) {
    this.user = me.user;
    this.credits = me.credits;
    this.isAdmin = me.is_admin;
    drawNav();
  },
  setCredits(n) {
    if (typeof n !== 'number') return;
    this.credits = n;
    drawNav();
    // 다른 패널의 "보유 N 크레딧"도 같이 맞춘다 — 한쪽에서 쓰면 다른 쪽이 옛 숫자로 남는다.
    document.querySelectorAll('[data-my-credits]').forEach((el) => { el.textContent = n; });
  },
  async refresh() {
    this.set(await api.me());
  },
  toast(message) {
    toastEl.textContent = message;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toastEl.hidden = true; }, 3200);
  },
};

// 오른쪽 위 메뉴는 ☰ 하나로 모은다. 크레딧 잔액만 밖에 남긴다 — 유료 기능을 쓸 때 바로 보여야 한다.
function drawNav() {
  const links = [
    ['#/', '🏠 홈'],
    ['#/season', '🧺 제철 장바구니'],
    ['#/produce', '🥬 농산물 도매 시세'],
    ['#/fish', '🐟 수산물 산지 시세'],
  ];
  const account = session.user
    ? [['#/me', `🪙 내 크레딧 (${session.credits})`], ...(session.isAdmin ? [['#/admin', '⚙️ 관리자']] : [])]
    : [['#/login', '로그인'], ['#/signup', '가입하고 크레딧 받기']];
  nav.innerHTML = `
    ${session.user ? `<a class="credit-pill num" href="#/me" title="내 크레딧">🪙 ${session.credits}</a>` : ''}
    <div class="menu">
      <button type="button" class="menu-toggle" aria-expanded="false" aria-controls="menu-panel" aria-label="메뉴 열기">
        <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
      </button>
      <div class="menu-panel" id="menu-panel" hidden>
        ${session.user ? `<div class="menu-user">${session.user}님</div>` : ''}
        ${links.map(([href, label]) => `<a href="${href}">${label}</a>`).join('')}
        <hr>
        ${account.map(([href, label]) => `<a href="${href}">${label}</a>`).join('')}
        ${session.user ? '<button type="button" data-logout>로그아웃</button>' : ''}
      </div>
    </div>`;

  const toggle = nav.querySelector('.menu-toggle');
  const panel = nav.querySelector('.menu-panel');
  const setOpen = (open) => {
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? '메뉴 닫기' : '메뉴 열기');
    if (open) panel.querySelector('a, button')?.focus();
  };
  toggle.addEventListener('click', (e) => { e.stopPropagation(); setOpen(panel.hidden); });
  panel.addEventListener('click', (e) => { if (e.target.closest('a')) setOpen(false); });
  panel.addEventListener('keydown', (e) => { if (e.key === 'Escape') { setOpen(false); toggle.focus(); } });
  nav.querySelector('[data-logout]')?.addEventListener('click', async () => {
    setOpen(false);
    await api.logout();
    session.set({ user: null, credits: 0, is_admin: false });
    session.toast('로그아웃했어요.');
    route();
  });
}

// 메뉴 바깥을 누르면 닫는다. drawNav가 다시 그려도 한 번만 걸리게 문서에 건다.
document.addEventListener('click', (e) => {
  const panel = document.getElementById('menu-panel');
  if (panel && !panel.hidden && !e.target.closest('.menu')) {
    panel.hidden = true;
    document.querySelector('.menu-toggle')?.setAttribute('aria-expanded', 'false');
  }
});

function drawStatus(status) {
  const labels = { at: '한국농수산식품유통공사(aT) 소매가격 조사', sample: '샘플 데이터' };
  document.getElementById('price-source').textContent = labels[status.price_source];
  let note = '';
  if (status.last_collect) note += ` · 마지막 수집 ${status.last_collect.replace('T', ' ').slice(0, 16)}`;
  if (status.history && status.history.done < status.history.total) {
    note += ` · 평년가 계산용 과거 자료 받는 중 (${status.history.done}/${status.history.total})`;
  }
  document.getElementById('last-collect').textContent = note;
  const banner = document.getElementById('sample-banner');
  banner.hidden = status.price_source !== 'sample';
  banner.textContent = '⚠ 샘플 데이터 — 시세는 실제 값이 아닙니다. 공공데이터포털 키를 넣으면 실제 데이터로 바뀝니다.';
}

async function route() {
  const [path, query = ''] = location.hash.replace(/^#/, '').split('?');
  const params = new URLSearchParams(query);
  const parts = path.split('/').filter(Boolean);
  window.scrollTo(0, 0);
  try {
    if (parts[0] === 'item' && parts[1]) await itemView(view, decodeURIComponent(parts[1]), session);
    else if (parts[0] === 'fish' && parts[1]) await fishDetailView(view, decodeURIComponent(parts[1]), params.get('state'), session);
    else if (parts[0] === 'fish') await fishListView(view);
    else if (parts[0] === 'produce' && parts[1]) await produceDetailView(view, decodeURIComponent(parts[1]), params.get('state'), session);
    else if (parts[0] === 'produce') await produceListView(view);
    else if (parts[0] === 'login' || parts[0] === 'signup') authView(view, parts[0], session, params.get('next'));
    else if (parts[0] === 'me') await meView(view, session);
    else if (parts[0] === 'admin') await adminView(view, session);
    else if (parts[0] === 'season') await mainView(view);
    else await homeView(view);
  } catch (err) {
    view.innerHTML = `<p class="empty">${err.message}</p>`;
  }
}

// 첫 화면은 세지 않고, 사용자가 화면을 넘어갈 때만 광고 빈도를 센다.
window.addEventListener('hashchange', () => {
  route();
  maybeShowAd(location.hash.replace(/^#\/?/, '').split(/[/?]/)[0]);
});

(async () => {
  const [me, status] = await Promise.all([api.me().catch(() => null), api.status().catch(() => null)]);
  if (me) session.set(me); else drawNav();
  if (status) { session.status = status; drawStatus(status); }
  route();
})();

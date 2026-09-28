// 해시 라우터와 로그인 상태.
//   #/            메인 (제철 목록)
//   #/item/:id    품목 상세
//   #/login, #/signup, #/me, #/admin

import { api } from './api.js';
import { adminView, authView, itemView, mainView, meView } from './views.js';

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
    if (typeof n === 'number') { this.credits = n; drawNav(); }
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

function drawNav() {
  if (session.user) {
    nav.innerHTML = `
      ${session.isAdmin ? '<a href="#/admin">관리자</a>' : ''}
      <a class="credit-pill num" href="#/me" title="내 크레딧">🪙 ${session.credits}</a>
      <button type="button" data-logout>로그아웃</button>`;
    nav.querySelector('[data-logout]').addEventListener('click', async () => {
      await api.logout();
      session.set({ user: null, credits: 0, is_admin: false });
      session.toast('로그아웃했어요.');
      route();
    });
  } else {
    nav.innerHTML = '<a href="#/login">로그인</a><a class="credit-pill" href="#/signup">가입하고 크레딧 받기</a>';
  }
}

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
    else if (parts[0] === 'login' || parts[0] === 'signup') authView(view, parts[0], session, params.get('next'));
    else if (parts[0] === 'me') await meView(view, session);
    else if (parts[0] === 'admin') await adminView(view, session);
    else await mainView(view);
  } catch (err) {
    view.innerHTML = `<p class="empty">${err.message}</p>`;
  }
}

window.addEventListener('hashchange', route);

(async () => {
  const [me, status] = await Promise.all([api.me().catch(() => null), api.status().catch(() => null)]);
  if (me) session.set(me); else drawNav();
  if (status) { session.status = status; drawStatus(status); }
  route();
})();

// 화면을 넘어갈 때 가끔 뜨는 자체 광고 팝업.
//
// 빈도: 화면 이동 EVERY번에 1번, 한 번 뜨면 COOLDOWN 동안은 다시 안 뜬다. 매번 뜨면 사람이 떠난다.
// 로그인·가입·내 크레딧·관리자 화면으로 갈 때는 띄우지 않는다 — 하려던 일을 막으면 안 된다.
// 광고가 정해지면 AD만 바꾼다. (구글 애드센스 등 광고 네트워크는 팝업 안 게재를 금지하니 여기엔 못 넣는다)

const EVERY = 5;
const COOLDOWN_MS = 10 * 60 * 1000;
const SKIP_ROUTES = ['login', 'signup', 'me', 'admin'];
const STORAGE_KEY = 'seasonal-ad-last-shown';

const AD = {
  label: '광고',
  title: '이 자리에 광고를 실어 보세요',
  body: '광고를 신청해 이 부분을 채우세요.<br>제철 농수산물에 관심 있는 분들께 가게, 농장, 수산물 직판장을 알릴 수 있어요.',
  cta: null, // { text: '광고 신청하기', href: '…' } — 신청 창구가 정해지면 넣는다
};

let moves = 0;

function lastShown() {
  try {
    return Number(localStorage.getItem(STORAGE_KEY)) || 0;
  } catch {
    return 0; // 사생활 보호 모드 등에서 저장소를 못 쓰면 쿨다운 없이 빈도만 지킨다
  }
}

function remember() {
  try {
    localStorage.setItem(STORAGE_KEY, String(Date.now()));
  } catch {
    /* 저장 못 해도 팝업은 동작한다 */
  }
}

export function maybeShowAd(route) {
  if (SKIP_ROUTES.includes(route)) return;
  moves += 1;
  if (moves % EVERY !== 0) return;
  if (Date.now() - lastShown() < COOLDOWN_MS) return;
  remember();
  show();
}

function show() {
  const previousFocus = document.activeElement;
  const backdrop = document.createElement('div');
  backdrop.className = 'ad-backdrop';
  backdrop.innerHTML = `
    <div class="ad-dialog" role="dialog" aria-modal="true" aria-labelledby="ad-title">
      <button type="button" class="ad-close" aria-label="광고 닫기">✕</button>
      <span class="ad-label">${AD.label}</span>
      <div class="ad-slot">
        <h2 id="ad-title">${AD.title}</h2>
        <p>${AD.body}</p>
        ${AD.cta ? `<a class="btn" href="${AD.cta.href}" target="_blank" rel="noopener sponsored">${AD.cta.text}</a>` : ''}
      </div>
    </div>`;
  document.body.appendChild(backdrop);

  const close = () => {
    backdrop.remove();
    document.removeEventListener('keydown', onKey);
    previousFocus?.focus?.();
  };
  const onKey = (e) => {
    if (e.key === 'Escape') close();
    if (e.key === 'Tab') { // 팝업 안에서만 포커스가 돈다
      const focusable = backdrop.querySelectorAll('button, a[href]');
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  };
  backdrop.addEventListener('click', (e) => { if (e.target === backdrop) close(); });
  backdrop.querySelector('.ad-close').addEventListener('click', close);
  document.addEventListener('keydown', onKey);
  backdrop.querySelector('.ad-close').focus();
}

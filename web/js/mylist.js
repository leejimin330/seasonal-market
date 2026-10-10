// 내 목록: 이전에 본 식재, 장바구니. 서버에 올리지 않고 이 브라우저(localStorage)에만 둔다.
// 항목은 { key, kind, name, emoji, href } 이고 key는 "item:id" 또는 "fish:코드|상태" 꼴이다.

const RECENT_MAX = 30;

const read = (name) => {
  try { return JSON.parse(localStorage.getItem(name)) || []; } catch { return []; }
};
const write = (name, value) => {
  try { localStorage.setItem(name, JSON.stringify(value)); } catch { /* 저장 못 해도 화면은 돈다 */ }
};
const changed = () => window.dispatchEvent(new Event('mylist-change'));

export const recent = {
  list: () => read('recent'),
  add(entry) {
    const rest = read('recent').filter((e) => e.key !== entry.key);
    write('recent', [entry, ...rest].slice(0, RECENT_MAX));
    changed();
  },
  clear() { write('recent', []); changed(); },
};

export const cart = {
  list: () => read('cart'),
  has: (key) => read('cart').some((e) => e.key === key),
  toggle(entry) {
    const list = read('cart');
    const has = list.some((e) => e.key === entry.key);
    write('cart', has ? list.filter((e) => e.key !== entry.key) : [...list, { ...entry, qty: 1 }]);
    changed();
    return !has;
  },
  remove(key) { write('cart', read('cart').filter((e) => e.key !== key)); changed(); },
  setQty(key, qty) {
    write('cart', read('cart').map((e) => (e.key === key ? { ...e, qty: Math.max(1, Math.min(99, qty)) } : e)));
    changed();
  },
};

// 같은 세션에서 같은 품목을 여러 번 열어도 한 번만 서버에 알린다.
export function trackOnce(api, kind, key) {
  const id = `viewed:${kind}:${key}`;
  try {
    if (sessionStorage.getItem(id)) return;
    sessionStorage.setItem(id, '1');
  } catch { /* 저장소를 못 쓰면 그냥 센다 */ }
  api.view(kind, key);
}

// 가격 알림: "평년보다 N% 이상 싸지면". 서버에 보내지 않고 사이트를 열 때 이 브라우저에서 확인한다.
export const alerts = {
  list: () => read('alerts'),
  get: (key) => read('alerts').find((a) => a.key === key) || null,
  set(key, pct) {
    const rest = read('alerts').filter((a) => a.key !== key);
    write('alerts', pct ? [...rest, { key, pct }] : rest);
    changed();
  },
};

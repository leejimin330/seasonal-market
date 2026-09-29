// 화면들. 각 함수는 #view를 채운다. 사용자 상태는 main.js의 session을 받는다.

import { api, ApiError } from './api.js';
import { carousel } from './carousel.js';
import { renderTrendChart } from './chart.js';
import { renderKoreaMap } from './koreamap.js';

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

const CATEGORY_GROUP = { 채소: '채소', 버섯: '채소', 과채: '과일', 과일: '과일', 수산: '수산', 축산: '축산', 곡물: '곡물', 견과: '곡물', 기타: '곡물' };
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
        ${['전체', '채소', '과일', '수산', '축산', '곡물'].map((g) => `<button class="chip" data-group="${g}" aria-pressed="${mainState.group === g}">${g}</button>`).join('')}
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

function nutritionPanel(item) {
  const values = item.nutrition.values;
  const kcal = values.find((v) => v.key === 'kcal');
  const rest = values.filter((v) => v.key !== 'kcal');
  const fmt = (v) => (v.value >= 100 ? Math.round(v.value) : Math.round(v.value * 10) / 10).toLocaleString('ko-KR');
  return `
    <section class="panel nutrition">
      <div class="panel-head"><h2>영양성분 <small>100g당</small></h2></div>
      <div class="nutrition-body">
        ${kcal ? `<div class="kcal"><b class="num">${fmt(kcal)}</b><span>kcal</span></div>` : ''}
        <dl class="nutrients">
          ${rest.map((v) => `<div><dt>${v.label}</dt><dd class="num">${fmt(v)}<small>${v.unit}</small></dd></div>`).join('')}
        </dl>
      </div>
      <p class="fineprint">"${esc(item.nutrition.food_name)}" 기준 · 출처: ${esc(item.nutrition_source)}</p>
    </section>`;
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
    <section class="panel origin">
      <div class="panel-head"><h2>주산지</h2></div>
      <div class="origin-body">
        <div class="origin-map" id="origin-map" aria-busy="true"></div>
        <div class="origin-info">
          <p class="origin-regions">${esc(item.main_region) || '정보 없음'}</p>
          ${item.places.provinces.length ? `<p class="origin-provinces">${item.places.provinces.map((p) => `<span class="badge">${esc(p)}</span>`).join(' ')}</p>` : ''}
          ${item.season_note ? `<p>${esc(item.season_note)}</p>` : ''}
          ${item.story ? `<div class="origin-story"><h3>${item.story_kind === 'tip' ? '💡 알아두면 좋은 점' : '📖 산지 이야기'}</h3><p>${esc(item.story)}</p></div>` : ''}
          <p class="origin-months">제철: ${item.season_months.length ? item.season_months.map((m) => `${m}월`).join(' · ') : '연중'}</p>
        </div>
      </div>
      <p class="fineprint">지도: 통계청 센서스용 행정구역경계(2013). 점은 주요 산지의 대략적인 위치예요.</p>
    </section>
    <section class="panel" id="trend-panel"></section>
    ${item.pick || item.store ? `
    <section class="tips">
      ${item.pick ? `<div class="tip"><h3>🛒 고르는 법</h3><p>${esc(item.pick)}</p></div>` : ''}
      ${item.store ? `<div class="tip"><h3>🧊 보관법</h3><p>${esc(item.store)}</p></div>` : ''}
    </section>` : ''}
    ${item.nutrition ? nutritionPanel(item) : ''}
    <section class="panel" id="where-panel"></section>`;

  renderKoreaMap(view.querySelector('#origin-map'), item.places)
    .catch(() => { view.querySelector('#origin-map').innerHTML = '<p class="empty">지도를 불러오지 못했어요.</p>'; })
    .finally(() => view.querySelector('#origin-map')?.removeAttribute('aria-busy'));

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
    renderTrendChart(chart, data.series.filter((p) => p.date >= since), { unit: data.price_unit, priceLabel: data.priceLabel });
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

// ── 경매 시세 (수산물 산지 위판 / 농산물 도매) ─────────────────
//
// 두 화면은 모양이 같고 글과 데이터 출처만 다르다. AUCTIONS에 차이를 모아 둔다.
// 목록의 "state"는 수산물에선 활어·선어 같은 상태, 농산물에선 품종이다.

const PRODUCE_GROUPS = {
  과일: ['과실류', '과일과채류', '수실류'],
  채소: ['엽경채류', '과채류', '조미채소류', '양채류', '근채류', '서류'],
  버섯: ['버섯류'],
  산나물: ['산채류'],
};

const AUCTIONS = {
  fish: {
    path: 'fish',
    title: '수산물 산지 시세',
    back: '← 수산물 시세',
    eyebrow: '전국 수협 위판장',
    unitWord: '어종',
    desc: `어민이 위판장 경매에서 판 kg당 가격이에요. 마트 소매가보다 훨씬 싸고, 유통을 거치며 값이 붙어요.<br>
      쥐치·쏨뱅이·물메기처럼 마트 조사에 없는 어종도 여기서 볼 수 있어요.`,
    placeholder: '어종 검색 (예: 쥐치, 볼락)',
    chips: [['전체', null], ...['활어', '선어', '냉동', '건어'].map((s) => [s, (x) => x.state === s])],
    priceLabel: '산지 위판가',
    originTitle: '어디서 잡혔나',
    marketTitle: '위판장별 가격',
    monthWord: '주로 잡히는 달',
    source: '해양수산부 위판장별 위탁판매 현황 (공공데이터포털). 위판가는 산지 경매가라 소매가와 다릅니다.',
    list: () => api.fish(),
    detail: (code, state) => api.fishDetail(code, state),
  },
  produce: {
    path: 'produce',
    title: '농산물 도매 시세',
    back: '← 농산물 도매 시세',
    eyebrow: '전국 공영도매시장 경매',
    unitWord: '품목',
    desc: `가락시장 등 전국 공영도매시장 경매에서 낙찰된 kg당 가격이에요. 소매가보다 싸고, 유통을 거치며 값이 붙어요.<br>
      가지·부추·무화과·연근처럼 소매 조사에 없는 품목도, 품종별로 볼 수 있어요.`,
    placeholder: '품목 검색 (예: 무화과, 연근)',
    chips: [['전체', null], ...Object.entries(PRODUCE_GROUPS).map(([label, cats]) => [label, (x) => cats.includes(x.category)])],
    priceLabel: '도매 경락가',
    originTitle: '어디서 왔나',
    marketTitle: '도매시장별 가격',
    monthWord: '주로 거래되는 달',
    source: '한국농수산식품유통공사 전국 공영도매시장 실시간 경매정보 (공공데이터포털). 오늘 자료만 제공돼, 서버가 켜져 있던 날부터 쌓입니다.',
    list: () => api.produce(),
    detail: (code, state) => api.produceDetail(code, state),
  },
};

const listState = {
  fish: { query: '', chip: '전체', sort: 'weight' },
  produce: { query: '', chip: '전체', sort: 'weight' },
};

// 카드에는 시·도 이름을 줄여 쓴다 ("전라남도" → "전남"). 지도에는 원래 이름이 필요해 화면에서만 줄인다.
const SHORT_PROVINCE = {
  서울특별시: '서울', 부산광역시: '부산', 대구광역시: '대구', 인천광역시: '인천', 광주광역시: '광주', 대전광역시: '대전',
  울산광역시: '울산', 세종특별자치시: '세종', 경기도: '경기', 강원도: '강원', 충청북도: '충북', 충청남도: '충남',
  전라북도: '전북', 전라남도: '전남', 경상북도: '경북', 경상남도: '경남', 제주특별자치도: '제주',
};
const shortProvince = (name) => SHORT_PROVINCE[name] || name;
const changeBadge = (pct) => (pct == null ? '<span class="delta flat">비교 자료 없음</span>'
  : Math.abs(pct) < 1 ? '<span class="delta flat">지난주와 비슷</span>'
    : pct < 0 ? `<span class="delta down">▼ 지난주보다 ${Math.abs(pct)}%</span>`
      : `<span class="delta up">▲ 지난주보다 ${pct}%</span>`);

// 1~12월 중 주로 잡히는(거래되는) 달을 칠한 작은 막대. 제목에 달 이름을 적어 색만으로 전달하지 않는다.
function monthStrip(months, word) {
  if (!months || !months.length) return '';
  const on = new Set(months);
  const names = months.map((m) => `${m}월`).join(', ');
  return `<div class="month-strip" title="${word}: ${names}" aria-label="${word}: ${names}">
    ${Array.from({ length: 12 }, (_, i) => `<i class="${on.has(i + 1) ? 'on' : ''}"></i>`).join('')}
    <span>${months.length <= 4 ? months.map((m) => `${m}월`).join('·') : `${months[0]}~${months[months.length - 1]}월 중`}</span>
  </div>`;
}

export const fishListView = (view) => auctionListView(view, 'fish');
export const fishDetailView = (view, code, state) => auctionDetailView(view, 'fish', code, state);
export const produceListView = (view) => auctionListView(view, 'produce');
export const produceDetailView = (view, code, state) => auctionDetailView(view, 'produce', code, state);

async function auctionListView(view, kind) {
  const cfg = AUCTIONS[kind];
  const st = listState[kind];
  view.innerHTML = '<p class="empty">불러오는 중…</p>';
  const { latest, species, quiet, months_covered: covered } = await cfg.list();
  if (!latest) {
    view.innerHTML = `<h1 class="page-title">${cfg.title}</h1>
      <p class="empty">아직 자료를 받는 중이에요. 잠시 후 다시 열어 주세요.</p>`;
    return;
  }
  const href = (s) => `#/${cfg.path}/${encodeURIComponent(s.code)}?state=${encodeURIComponent(s.state)}`;
  view.innerHTML = `
    <section class="page-head">
      <div class="eyebrow">${cfg.eyebrow} · ${esc(latest)} 기준 최근 7일</div>
      <h1 class="page-title">${cfg.title} <small>지금 거래 중 ${species.length} · 뜸한 ${cfg.unitWord} ${quiet.length}</small></h1>
      <p class="page-desc">${cfg.desc}</p>
    </section>
    <div class="controls">
      <input class="search" type="search" placeholder="${cfg.placeholder}" value="${esc(st.query)}" aria-label="${cfg.unitWord} 검색">
      ${cfg.chips.map(([label]) => `<button class="chip" data-chip="${label}" aria-pressed="${st.chip === label}">${label}</button>`).join('')}
      <span class="spacer"></span>
      <select class="chip" data-sort aria-label="정렬">
        <option value="weight">거래량 많은 순</option>
        <option value="down">지난주보다 내린 순</option>
        <option value="up">지난주보다 오른 순</option>
        <option value="name">이름순</option>
      </select>
    </div>
    <div class="grid" id="auction-grid"></div>
    <h2 class="section-title quiet-title">요즘 거래가 뜸한 ${cfg.unitWord} <small>최근 7일 거래가 적거나 없어요 · 마지막 거래일 순</small></h2>
    <div class="grid" id="quiet-grid"></div>
    <p class="fineprint">"${cfg.monthWord}"은 받아 둔 ${covered}개월 치 자료로 계산했어요. 1년치가 쌓이면 더 정확해져요.</p>
    <p class="fineprint">출처: ${cfg.source} 한 주 거래가 5kg 미만이면 가격이 튀어서 목록에서 뺐어요.</p>`;
  view.querySelector('[data-sort]').value = st.sort;

  const grid = view.querySelector('#auction-grid');
  const quietGrid = view.querySelector('#quiet-grid');
  const draw = () => {
    const q = st.query.trim();
    const test = cfg.chips.find(([label]) => label === st.chip)?.[1];
    const keep = (s) => (!test || test(s)) && (!q || s.name.includes(q) || s.state.includes(q));
    const list = species.filter(keep);
    // 변동률이 없는 것은 어느 정렬에서든 뒤로 보낸다.
    const byChange = (sign) => (a, b) => (a.change == null) - (b.change == null) || (a.change - b.change) * sign;
    list.sort({
      weight: (a, b) => b.weight - a.weight,
      down: byChange(1),
      up: byChange(-1),
      name: (a, b) => a.name.localeCompare(b.name, 'ko'),
    }[st.sort]);
    grid.innerHTML = list.length ? list.map((s) => `
      <a class="card" href="${href(s)}">
        <div class="card-top"><h3>${esc(s.name)}</h3><span class="tag">${esc(s.state)}</span></div>
        <div class="price num">${won(s.kg)}<small>/ kg</small></div>
        <div class="card-foot"><span>${esc(s.regions.map(shortProvince).join('·'))}</span>${changeBadge(s.change)}</div>
        <div class="card-sub num">최근 7일 ${s.weight.toLocaleString('ko-KR')}kg · 시장 ${s.markets}곳</div>
        ${monthStrip(s.peak_months, cfg.monthWord)}
      </a>`).join('') : `<p class="empty">조건에 맞는 ${cfg.unitWord}이 없어요.</p>`;

    const quietList = quiet.filter(keep);
    if (st.sort === 'name') quietList.sort((a, b) => a.name.localeCompare(b.name, 'ko'));
    quietGrid.innerHTML = quietList.length ? quietList.map((s) => `
      <a class="card quiet" href="${href(s)}">
        <div class="card-top"><h3>${esc(s.name)}</h3><span class="tag">${esc(s.state)}</span></div>
        <div class="price num">${won(s.last_kg)}<small>/ kg</small></div>
        <div class="card-sub">마지막 거래 ${esc(s.last_date)} · 그 주 평균</div>
        ${monthStrip(s.peak_months, cfg.monthWord)}
      </a>`).join('') : '<p class="empty">없어요.</p>';
  };
  draw();
  view.querySelector('.search').addEventListener('input', (e) => { st.query = e.target.value; draw(); });
  view.querySelectorAll('[data-chip]').forEach((b) => b.addEventListener('click', () => {
    st.chip = b.dataset.chip;
    view.querySelectorAll('[data-chip]').forEach((x) => x.setAttribute('aria-pressed', x === b));
    draw();
  }));
  view.querySelector('[data-sort]').addEventListener('change', (e) => { st.sort = e.target.value; draw(); });
}

async function auctionDetailView(view, kind, code, state) {
  const cfg = AUCTIONS[kind];
  view.innerHTML = '<p class="empty">불러오는 중…</p>';
  let d;
  try {
    d = await cfg.detail(code, state);
  } catch (err) {
    view.innerHTML = `<a class="back" href="#/${cfg.path}">${cfg.back}</a><p class="empty">${esc(err.message)}</p>`;
    return;
  }
  const provinces = d.regions.map((r) => r.name);
  const maxRegion = Math.max(...d.regions.map((r) => r.weight), 1);
  const searchName = encodeURIComponent(d.name.split('(')[0]);
  view.innerHTML = `
    <a class="back" href="#/${cfg.path}">${cfg.back}</a>
    <section class="detail-head">
      <div>
        <h1>${esc(d.name)}</h1>
        <div class="detail-meta">
          ${d.states.map((s) => `<a class="chip" href="#/${cfg.path}/${encodeURIComponent(code)}?state=${encodeURIComponent(s)}" aria-pressed="${s === d.state}">${esc(s)}</a>`).join(' ')}
        </div>
      </div>
      <div class="now-box">
        <div class="label">${d.is_quiet ? '요즘 거래가 뜸해요 · 마지막 거래 주 평균' : `${cfg.priceLabel} · 최근 7일 평균`} (${esc(d.latest)}까지)</div>
        <div class="price num">${won(d.kg)}<small>/ kg</small></div>
        <div class="card-sub num">거래 ${d.weight.toLocaleString('ko-KR')}kg · 낙찰가 ${won(d.min_kg)} ~ ${won(d.max_kg)}</div>
      </div>
    </section>
    ${d.peak_months.length ? `
    <div class="months" aria-label="${cfg.monthWord}">
      ${Array.from({ length: 12 }, (_, i) => i + 1).map((m) => `<span class="${d.peak_months.includes(m) ? 'on' : ''}">${m}월</span>`).join('')}
    </div>
    <p class="fineprint" style="margin:-16px 0 16px">${cfg.monthWord} — 받아 둔 ${d.months_covered}개월 치 거래량 기준</p>` : ''}
    <div class="shop-links">
      <span class="shop-links-title">사러 가기</span>
      ${SHOPS.map(([name, url]) => `<a class="shop-link" href="${url(searchName)}" target="_blank" rel="noopener noreferrer">${name} ↗</a>`).join('')}
    </div>
    <section class="panel origin">
      <div class="panel-head"><h2>${cfg.originTitle}</h2><span class="unlock-note">최근 7일 거래량 기준</span></div>
      <div class="origin-body">
        <div class="origin-map" id="origin-map"></div>
        <div class="origin-info">
          <ul class="rank-list">
            ${d.regions.slice(0, 6).map((r, n) => `
              <li class="${n === 0 ? 'best' : ''}">
                <span class="rank-name">${esc(r.name)}</span>
                <span class="bar" aria-hidden="true"><i style="width:${Math.max(4, Math.round((r.weight / maxRegion) * 100))}%"></i></span>
                <span class="rank-value num"><b>${r.weight.toLocaleString('ko-KR')}kg</b><small>${won(r.kg)}/kg</small></span>
              </li>`).join('')}
          </ul>
        </div>
      </div>
    </section>
    <section class="panel" id="auction-trend"></section>
    ${d.markets.length ? `
    <section class="panel">
      <div class="panel-head"><h2>${cfg.marketTitle}</h2><span class="unlock-note">최근 7일 · kg당 싼 순</span></div>
      <ol class="region-list">
        ${d.markets.map((m) => `<li><span>${esc(m.name)}</span> <span class="num">${won(m.kg)}/kg <small>(${m.weight.toLocaleString('ko-KR')}kg)</small></span></li>`).join('')}
      </ol>
    </section>` : ''}
    ${d.nutrition ? nutritionPanel({ nutrition: d.nutrition, nutrition_source: '식품의약품안전처 식품영양성분DB (100g 기준)' }) : ''}
    <p class="fineprint">출처: ${cfg.source}</p>`;

  renderKoreaMap(view.querySelector('#origin-map'), { points: [], provinces })
    .catch(() => { view.querySelector('#origin-map').innerHTML = ''; });
  const trend = view.querySelector('#auction-trend');
  trend.innerHTML = `<div class="panel-head"><h2>${cfg.priceLabel} 추이</h2></div><div data-body></div>`;
  renderTrend(trend.querySelector('[data-body]'), { series: d.series, price_unit: 'kg', priceLabel: cfg.priceLabel });
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

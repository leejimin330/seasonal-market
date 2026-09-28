// 가로로 넘기는 슬라이드(캐러셀). 메인 배너가 쓴다. 헤아림(malice-dashboard)의 carousel.js를 옮겨왔다.
//
// 한 장뿐이면 화살표·점을 숨긴다 — 넘길 게 없는데 조작 도구만 보이면 고장처럼 보인다.

const SWIPE_PX = 40;

function h(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'onclick') node.addEventListener('click', value);
    else if (key === 'text') node.textContent = value;
    else node.setAttribute(key, value);
  }
  node.append(...children);
  return node;
}

export function carousel({ label, interval = 6000 }) {
  const track = h('div', { class: 'carousel-track' });
  const dots = h('div', { class: 'carousel-dots' });
  const prev = h('button', { type: 'button', class: 'carousel-arrow', 'aria-label': '이전 슬라이드', text: '‹', onclick: () => go(index - 1) });
  const next = h('button', { type: 'button', class: 'carousel-arrow', 'aria-label': '다음 슬라이드', text: '›', onclick: () => go(index + 1) });
  const node = h('div', { class: 'carousel carousel-single', role: 'region', 'aria-roledescription': 'carousel', 'aria-label': label },
    [h('div', { class: 'carousel-viewport' }, [track]), h('div', { class: 'carousel-controls' }, [prev, dots, next])]);

  const slides = [];
  let index = 0;
  let hovered = false;
  let focused = false;

  function render() {
    track.style.transform = `translateX(-${index * 100}%)`;
    slides.forEach((slide, i) => {
      const current = i === index;
      slide.setAttribute('aria-hidden', String(!current));
      // 안 보이는 장의 링크가 Tab으로 잡히면 화면 밖에서 포커스가 헤맨다.
      slide.inert = !current;
      dots.children[i]?.setAttribute('aria-current', String(current));
    });
    node.classList.toggle('carousel-single', slides.length < 2);
  }

  function go(to) {
    if (!slides.length) return;
    index = (to + slides.length) % slides.length;
    render();
  }

  function addSlide(content) {
    const position = slides.length;
    const slide = h('div', { class: 'carousel-slide', role: 'group', 'aria-roledescription': 'slide' }, [content]);
    slides.push(slide);
    track.append(slide);
    dots.append(h('button', { type: 'button', class: 'carousel-dot', 'aria-label': `${position + 1}번째 슬라이드`, onclick: () => go(position) }));
    slides.forEach((s, i) => s.setAttribute('aria-label', `${i + 1} / ${slides.length}`));
    render();
  }

  // 마우스가 올라가 있거나 안에 포커스가 있으면 멈춘다 — 읽는 중이거나 누르려는 참에 넘어가면 안 된다.
  node.addEventListener('mouseenter', () => { hovered = true; });
  node.addEventListener('mouseleave', () => { hovered = false; });
  node.addEventListener('focusin', () => { focused = true; });
  node.addEventListener('focusout', (event) => { focused = node.contains(event.relatedTarget); });

  // 휴대폰에서는 옆으로 밀어 넘긴다.
  let startX = null;
  node.addEventListener('pointerdown', (event) => { if (event.pointerType === 'touch') startX = event.clientX; });
  node.addEventListener('pointerup', (event) => {
    if (startX === null) return;
    const dx = event.clientX - startX;
    startX = null;
    if (Math.abs(dx) >= SWIPE_PX) go(index + (dx < 0 ? 1 : -1));
  });

  // "움직임 줄이기"를 켠 사람에게는 저절로 넘기지 않는다(전환 효과는 CSS가 끈다).
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  if (!reduceMotion) {
    const timer = setInterval(() => {
      // 다른 화면으로 넘어가 캐러셀이 사라지면 타이머도 끝낸다.
      if (!node.isConnected) return clearInterval(timer);
      if (!hovered && !focused && slides.length > 1) go(index + 1);
    }, interval);
  }

  return { node, addSlide };
}

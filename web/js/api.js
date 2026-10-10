// 서버 API 호출. 오류는 status와 서버가 준 detail을 담은 ApiError로 던진다.

export class ApiError extends Error {
  constructor(status, detail) {
    const message = typeof detail === 'string' ? detail : detail?.message || `요청 실패 (${status})`;
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function request(method, path, body) {
  const options = { method, headers: {}, credentials: 'same-origin' };
  if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(`/api${path}`, options);
  } catch {
    throw new ApiError(0, '서버에 연결할 수 없습니다.');
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    let detail = data.detail;
    if (Array.isArray(detail)) detail = '입력값을 확인해 주세요.';
    throw new ApiError(response.status, detail);
  }
  return data;
}

export const api = {
  status: () => request('GET', '/status'),
  items: () => request('GET', '/items'),
  item: (id) => request('GET', `/items/${encodeURIComponent(id)}`),
  trend: (id) => request('POST', `/items/${encodeURIComponent(id)}/trend`),
  where: (id) => request('POST', `/items/${encodeURIComponent(id)}/where`),
  fish: () => request('GET', '/fish'),
  rank: (by, kind) => request('GET', `/rank?by=${encodeURIComponent(by)}&kind=${encodeURIComponent(kind)}`),
  view: (kind, key) => request('POST', '/view', { kind, key }).catch(() => null),
  fishDetail: (code, state) => request('GET', `/fish/${encodeURIComponent(code)}${state ? `?state=${encodeURIComponent(state)}` : ''}`),
  produce: () => request('GET', '/produce'),
  produceDetail: (code, state) => request('GET', `/produce/${encodeURIComponent(code)}${state ? `?state=${encodeURIComponent(state)}` : ''}`),
  fishTrend: (code, state) => request('POST', `/fish/${encodeURIComponent(code)}/trend?state=${encodeURIComponent(state)}`),
  produceTrend: (code, state) => request('POST', `/produce/${encodeURIComponent(code)}/trend?state=${encodeURIComponent(state)}`),
  me: () => request('GET', '/me'),
  ledger: () => request('GET', '/me/ledger'),
  signup: (user_id, password) => request('POST', '/signup', { user_id, password }),
  login: (user_id, password) => request('POST', '/login', { user_id, password }),
  logout: () => request('POST', '/logout'),
  adminUsers: () => request('GET', '/admin/users'),
  adminGrant: (user_id, amount, memo) => request('POST', '/admin/grant', { user_id, amount, memo }),
};

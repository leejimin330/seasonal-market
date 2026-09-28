"""HTTP API.

무료: 품목 목록·현재 가격·평년 대비 등락률. 유료: 가격 추이, 어디서 살까(판매처 유형별 비교).
유료 요청은 POST다 — 크레딧이 움직이는 요청이 링크 미리보기나 새로고침으로
일어나지 않게, 그리고 SameSite=Lax 쿠키가 다른 사이트의 요청에 실리지 않게.
"""

from __future__ import annotations

import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app import auth, config
from app.credits import InsufficientCredits
from app.prices import today_kst

router = APIRouter(prefix="/api")


# ── 공통 ────────────────────────────────────────────────────

def client_ip(request: Request) -> str:
    # 서버는 127.0.0.1에만 열고 Cloudflare 터널로만 밖에 나간다. 그래서 이 헤더는 터널이 붙인 값이다.
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")


def optional_user(request: Request) -> str | None:
    state = request.app.state
    user_id = auth.read_token(request.cookies.get(auth.COOKIE_NAME, ""), state.secret)
    if user_id is None or state.db.get_user(user_id) is None:
        return None  # 지워진 계정의 쿠키는 서명이 맞아도 통과시키지 않는다
    return user_id


def require_user(user_id: str | None = Depends(optional_user)) -> str:
    if user_id is None:
        raise HTTPException(401, "로그인이 필요합니다.")
    return user_id


def require_admin(request: Request, user_id: str = Depends(require_user)) -> str:
    if user_id not in request.app.state.admins:
        raise HTTPException(403, "관리자만 쓸 수 있습니다.")
    return user_id


def _item_or_404(request: Request, item_id: str):
    item = request.app.state.catalog.get(item_id)
    if item is None:
        raise HTTPException(404, "없는 품목입니다.")
    return item


def _item_json(item, summary: dict, month: int) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "category": item.category,
        "price_unit": item.price_unit,
        "has_normal": summary.get("vs_normal") is not None,
        "in_season": item.in_season(month),
        "season_months": sorted(item.season_months),
        "main_region": item.main_region,
        "season_note": item.season_note,
        "has_price": summary.get("price") is not None,
        **summary,
    }


def _access(request: Request, user_id: str | None, item_id: str) -> dict:
    credits = request.app.state.credits
    result = {}
    for feature in ("trend", "where"):
        until = credits.unlocked_until(user_id, feature, item_id) if user_id else None
        result[feature] = {"cost": credits.cost(feature), "unlocked_until": until}
    return result


def _charge(request: Request, user_id: str, feature: str, item_id: str):
    try:
        return request.app.state.credits.use(user_id, feature, item_id)
    except InsufficientCredits as exc:
        raise HTTPException(
            402, {"message": "크레딧이 부족합니다.", "balance": exc.balance, "cost": exc.cost}
        ) from exc


def _charge_json(charge) -> dict:
    return {
        "charged": charge.charged,
        "cost": charge.cost,
        "unlocked_until": charge.expires_at,
        "balance": charge.balance,
    }


# ── 조회 (무료) ─────────────────────────────────────────────

@router.get("/status")
def status(request: Request):
    state = request.app.state
    return {
        "price_source": state.prices.source,
        "last_collect": state.db.get_meta("last_collect"),
        "history": state.prices.history_progress(),
        "today": today_kst(state.clock).isoformat(),
        "costs": {"trend": state.credits.cost("trend"), "where": state.credits.cost("where")},
        "unlock_hours": state.credits.unlock_hours,
        "signup_bonus": state.signup_bonus,
    }


@router.get("/items")
def list_items(request: Request):
    state = request.app.state
    month = today_kst(state.clock).month
    summaries = state.prices.summaries()
    return {"month": month, "items": [_item_json(i, summaries[i.id], month) for i in state.catalog]}


@router.get("/items/{item_id}")
def item_detail(request: Request, item_id: str, user_id: str | None = Depends(optional_user)):
    state = request.app.state
    item = _item_or_404(request, item_id)
    month = today_kst(state.clock).month
    summary = state.prices.summaries()[item.id]
    return {**_item_json(item, summary, month), "access": _access(request, user_id, item.id)}


# ── 유료 ────────────────────────────────────────────────────

@router.post("/items/{item_id}/trend")
def trend(request: Request, item_id: str, user_id: str = Depends(require_user)):
    """1년치를 한 번에 준다. 4주/3개월/1년 전환은 화면에서 자른다 — 기간을 바꿀 때마다
    요청하지 않게, 그리고 이용권 하나로 모든 기간을 보게."""
    state = request.app.state
    item = _item_or_404(request, item_id)
    series = state.prices.series(item.id)
    if not any(point["price"] for point in series):
        # 보여줄 게 없는데 돈을 받지 않는다.
        raise HTTPException(404, "이 품목은 아직 가격 기록이 없습니다.")
    charge = _charge(request, user_id, "trend", item.id)
    return {"series": series, "price_unit": item.price_unit, **_charge_json(charge)}


@router.post("/items/{item_id}/where")
def where(request: Request, item_id: str, user_id: str = Depends(require_user)):
    """가장 최근 조사일의 판매처 유형별·지역별 평균과 최저가."""
    state = request.app.state
    item = _item_or_404(request, item_id)
    breakdown = state.prices.breakdown(item.id)
    if not breakdown or not breakdown.get("channels"):
        raise HTTPException(404, "이 품목은 아직 판매처별 가격이 없습니다.")
    charge = _charge(request, user_id, "where", item.id)
    return {**breakdown, "price_unit": item.price_unit, **_charge_json(charge)}


# ── 계정 ────────────────────────────────────────────────────

class Credentials(BaseModel):
    user_id: str = Field(max_length=40)
    password: str = Field(max_length=200)


def _set_session(request: Request, response: Response, user_id: str) -> None:
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(
        auth.COOKIE_NAME,
        auth.make_token(user_id, request.app.state.secret),
        max_age=auth.DEFAULT_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=secure,
    )


def _me(request: Request, user_id: str) -> dict:
    state = request.app.state
    return {"user": user_id, "credits": state.credits.balance(user_id), "is_admin": user_id in state.admins}


@router.post("/signup")
def signup(request: Request, body: Credentials, response: Response):
    state = request.app.state
    ip = client_ip(request)
    if state.signup_throttle.blocked(ip):
        raise HTTPException(429, "오늘은 이 곳에서 더 가입할 수 없습니다. 내일 다시 시도해 주세요.")
    user_id = body.user_id.strip().lower()
    problem = auth.validate_signup(user_id, body.password)
    if problem:
        raise HTTPException(400, problem)
    if user_id in state.admins:
        raise HTTPException(409, "이미 있는 아이디입니다.")  # 관리자 아이디는 가입으로 만들 수 없다
    created = state.db.create_user(
        user_id, auth.hash_password(body.password), bonus=state.signup_bonus, now=state.clock()
    )
    if not created:
        raise HTTPException(409, "이미 있는 아이디입니다.")
    state.signup_throttle.record_failure(ip)  # "실패"가 아니라 가입 횟수를 센다
    _set_session(request, response, user_id)
    return _me(request, user_id)


@router.post("/login")
def login(request: Request, body: Credentials, response: Response):
    state = request.app.state
    ip = client_ip(request)
    if state.login_throttle.blocked(ip):
        raise HTTPException(429, "로그인 시도가 너무 많습니다. 5분 뒤에 다시 시도해 주세요.")
    user_id = body.user_id.strip().lower()
    user = state.db.get_user(user_id)
    stored = user["password_hash"] if user else auth.DUMMY_HASH
    if not auth.verify_password(body.password, stored) or user is None:
        state.login_throttle.record_failure(ip)
        raise HTTPException(401, "아이디 또는 비밀번호가 맞지 않습니다.")
    _set_session(request, response, user_id)
    return _me(request, user_id)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME)
    return {"ok": True}


@router.get("/me")
def me(request: Request, user_id: str | None = Depends(optional_user)):
    if user_id is None:
        return {"user": None, "credits": 0, "is_admin": False}
    return _me(request, user_id)


@router.get("/me/ledger")
def my_ledger(request: Request, user_id: str = Depends(require_user)):
    return {"ledger": request.app.state.credits.history(user_id)}


# ── 관리자 ──────────────────────────────────────────────────

@router.get("/admin/users")
def admin_users(request: Request, _: str = Depends(require_admin)):
    return {"users": request.app.state.db.list_users()}


class Grant(BaseModel):
    user_id: str = Field(max_length=40)
    amount: int = Field(ge=1, le=10_000)
    memo: str = Field(default="", max_length=200)


@router.post("/admin/grant")
def admin_grant(request: Request, body: Grant, admin_id: str = Depends(require_admin)):
    try:
        balance = request.app.state.credits.grant(
            body.user_id.strip().lower(), body.amount, actor=admin_id, memo=body.memo.strip()
        )
    except KeyError:
        raise HTTPException(404, "없는 사용자입니다.") from None
    return {"user_id": body.user_id, "balance": balance}


@router.get("/admin/ledger/{target}")
def admin_ledger(request: Request, target: str, _: str = Depends(require_admin)):
    return {"ledger": request.app.state.credits.history(target)}

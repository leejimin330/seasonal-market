"""관리 명령.

    python -m app.cli create-user jimin            비밀번호를 물어보고 계정을 만든다
    python -m app.cli create-user jimin --random   비밀번호를 만들어서 보여준다
    python -m app.cli set-password jimin
    python -m app.cli collect                      가격 수집을 지금 한 번 돌린다

관리자 권한은 계정이 아니라 .env의 SEASONAL_ADMIN_USERS로 준다.
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys
import time

from app import auth, config
from app.db import Database


def _password(args) -> str:
    if args.random:
        password = secrets.token_urlsafe(9)
        print(f"비밀번호: {password}")
        return password
    password = getpass.getpass("비밀번호: ")
    if getpass.getpass("한 번 더: ") != password:
        sys.exit("두 비밀번호가 다릅니다.")
    return password


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("create-user", "set-password"):
        p = sub.add_parser(name)
        p.add_argument("user_id")
        p.add_argument("--random", action="store_true", help="비밀번호를 자동으로 만든다")
    sub.add_parser("collect")
    args = parser.parse_args(argv)

    db = Database(config.DB_PATH)
    if args.command == "collect":
        from app.main import build_default_app

        print(build_default_app().state.prices.collect())
        return

    user_id = args.user_id.strip().lower()
    if not auth.USER_ID_PATTERN.match(user_id):
        sys.exit("아이디는 영문 소문자, 숫자, 밑줄로 3~20자여야 합니다.")
    password = _password(args)
    if len(password) < auth.MIN_PASSWORD_LENGTH:
        sys.exit(f"비밀번호는 {auth.MIN_PASSWORD_LENGTH}자 이상이어야 합니다.")

    if args.command == "create-user":
        if not db.create_user(user_id, auth.hash_password(password), bonus=config.SIGNUP_BONUS, now=time.time()):
            sys.exit("이미 있는 아이디입니다.")
        print(f"{user_id} 계정을 만들었습니다.")
        if user_id not in config.ADMIN_USERS:
            print("관리자로 쓰려면 .env의 SEASONAL_ADMIN_USERS에 이 아이디를 넣으세요.")
    else:
        if db.get_user(user_id) is None:
            sys.exit("없는 아이디입니다.")
        db.set_password(user_id, auth.hash_password(password))
        print("비밀번호를 바꿨습니다.")


if __name__ == "__main__":
    main()

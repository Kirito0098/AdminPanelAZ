#!/usr/bin/env python3
"""Интерактивный сброс паролей пользователей панели AdminPanelAZ."""

from __future__ import annotations

import argparse
import os
import secrets
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / "backend" / ".venv"
VENV_PYTHON = VENV_DIR / "bin" / "python"
if VENV_PYTHON.is_file() and Path(sys.prefix).resolve() != VENV_DIR.resolve():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

BACKEND = ROOT / "backend"
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))
(BACKEND / "data").mkdir(parents=True, exist_ok=True)

from app.auth import get_password_hash  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import User, UserRole, WebAuthnCredential  # noqa: E402
from app.services.refresh_token import revoke_all_user_tokens  # noqa: E402
from app.services.webauthn_service import user_has_passkeys  # noqa: E402

ROLE_LABELS = {
    UserRole.admin: "администратор",
    UserRole.user: "пользователь",
}

PASSWORD_ALPHABET = string.ascii_letters + string.digits


def generate_password(length: int = 12) -> str:
    while True:
        password = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))
        if any(char.isalpha() for char in password) and any(char.isdigit() for char in password):
            return password


def load_users(db) -> list[User]:
    return db.query(User).order_by(User.username.asc()).all()


def load_passkey_user_ids(db) -> set[int]:
    rows = db.query(WebAuthnCredential.user_id).distinct().all()
    return {row[0] for row in rows}


def user_has_totp_2fa(user: User) -> bool:
    return bool(user.totp_enabled)


def user_has_passkey_auth(db, user: User, passkey_user_ids: set[int] | None = None) -> bool:
    if passkey_user_ids is not None:
        return user.id in passkey_user_ids
    return user_has_passkeys(db, user.id)


def user_requires_second_factor(
    db,
    user: User,
    *,
    passkey_user_ids: set[int] | None = None,
) -> bool:
    return user_has_totp_2fa(user) or user_has_passkey_auth(db, user, passkey_user_ids)


def format_user_line(index: int, user: User, *, second_factor_labels: list[str]) -> str:
    role = ROLE_LABELS.get(user.role, user.role.value)
    status = "активен" if user.is_active else "отключён"
    if second_factor_labels:
        status = f"{status}, {', '.join(second_factor_labels)}"
    return f"  {index:>2}. {user.username:<24} {role:<14} {status}"


def parse_selection(raw: str, max_index: int) -> list[int]:
    value = raw.strip().lower()
    if not value:
        return []
    if value in {"q", "quit", "exit", "выход"}:
        raise SystemExit(0)

    selected: set[int] = set()
    for part in value.replace(";", ",").split(","):
        token = part.strip()
        if not token:
            continue
        if token == "all" or token == "все":
            return list(range(1, max_index + 1))
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start = int(start_text.strip())
            end = int(end_text.strip())
            if start > end:
                start, end = end, start
            for number in range(start, end + 1):
                if number < 1 or number > max_index:
                    raise ValueError(f"номер вне диапазона: {number}")
                selected.add(number)
            continue
        number = int(token)
        if number < 1 or number > max_index:
            raise ValueError(f"номер вне диапазона: {number}")
        selected.add(number)
    return sorted(selected)


def second_factor_labels_for_user(
    db,
    user: User,
    *,
    passkey_user_ids: set[int] | None = None,
) -> list[str]:
    labels: list[str] = []
    if user_has_totp_2fa(user):
        labels.append("2FA")
    if user_has_passkey_auth(db, user, passkey_user_ids):
        labels.append("passkey")
    return labels


def prompt_selection(users: list[User], db) -> list[User]:
    if not users:
        print("Пользователи не найдены.")
        raise SystemExit(1)

    passkey_user_ids = load_passkey_user_ids(db)
    print("Пользователи панели:")
    for index, user in enumerate(users, start=1):
        labels = second_factor_labels_for_user(db, user, passkey_user_ids=passkey_user_ids)
        print(format_user_line(index, user, second_factor_labels=labels))
    print()
    print("Введите номера через запятую, диапазон (например 2-4), all/все для всех, q для выхода.")

    while True:
        try:
            raw = input("Выбор: ")
            indexes = parse_selection(raw, len(users))
            if not indexes:
                print("Ничего не выбрано. Повторите ввод.")
                continue
            return [users[index - 1] for index in indexes]
        except ValueError as exc:
            print(f"Некорректный ввод: {exc}")
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit(130) from None


def confirm_reset(users: list[User]) -> bool:
    names = ", ".join(user.username for user in users)
    print()
    print(f"Будут сброшены пароли для: {names}")
    try:
        answer = input("Продолжить? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in {"y", "yes", "д", "да"}


def users_with_second_factor(
    db,
    users: list[User],
    *,
    passkey_user_ids: set[int] | None = None,
) -> list[User]:
    return [user for user in users if user_requires_second_factor(db, user, passkey_user_ids=passkey_user_ids)]


def prompt_disable_second_factor(db, users: list[User]) -> bool:
    passkey_user_ids = load_passkey_user_ids(db)
    with_second_factor = users_with_second_factor(db, users, passkey_user_ids=passkey_user_ids)
    if not with_second_factor:
        return False

    print()
    print("У пользователей настроен второй фактор входа:")
    for user in with_second_factor:
        labels = second_factor_labels_for_user(db, user, passkey_user_ids=passkey_user_ids)
        print(f"  - {user.username}: {', '.join(labels)}")
    try:
        answer = input("Сбросить и отключить 2FA и passkey? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in {"y", "yes", "д", "да"}


def disable_user_totp(row: User) -> bool:
    if not row.totp_enabled and not row.totp_secret_encrypted and not row.totp_backup_codes_encrypted:
        return False
    row.totp_enabled = False
    row.totp_secret_encrypted = None
    row.totp_backup_codes_encrypted = None
    return True


def disable_user_passkeys(db, user_id: int) -> int:
    return int(
        db.query(WebAuthnCredential)
        .filter(WebAuthnCredential.user_id == user_id)
        .delete(synchronize_session=False)
        or 0
    )


def reset_passwords(
    users: list[User],
    *,
    password_length: int,
    disable_second_factor: bool,
) -> tuple[list[tuple[str, str]], list[str]]:
    db = SessionLocal()
    results: list[tuple[str, str]] = []
    disabled_second_factor: list[str] = []
    try:
        for user in users:
            row = db.query(User).filter(User.id == user.id).first()
            if row is None:
                continue
            password = generate_password(password_length)
            row.password_hash = get_password_hash(password)
            row.must_change_password = True
            revoke_all_user_tokens(db, row.id)
            if disable_second_factor:
                totp_disabled = disable_user_totp(row)
                passkeys_removed = disable_user_passkeys(db, row.id)
                if totp_disabled or passkeys_removed:
                    parts: list[str] = []
                    if totp_disabled:
                        parts.append("2FA")
                    if passkeys_removed:
                        parts.append(f"passkey ({passkeys_removed})")
                    disabled_second_factor.append(f"{row.username} ({', '.join(parts)})")
            results.append((row.username, password))
        db.commit()
    finally:
        db.close()
    return results, disabled_second_factor


def resolve_users_by_usernames(db, usernames: list[str]) -> list[User]:
    requested = [name.strip() for name in usernames if name.strip()]
    if not requested:
        raise SystemExit("Не указаны имена пользователей.")

    users = load_users(db)
    by_name = {user.username: user for user in users}
    missing = [name for name in requested if name not in by_name]
    if missing:
        raise SystemExit(f"Пользователи не найдены: {', '.join(missing)}")
    return [by_name[name] for name in requested]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Сброс паролей пользователей панели с генерацией случайного пароля.",
    )
    parser.add_argument(
        "-u",
        "--username",
        action="append",
        dest="usernames",
        metavar="NAME",
        help="Сбросить пароль конкретному пользователю (можно указать несколько раз).",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Не спрашивать подтверждение (только с --username).",
    )
    parser.add_argument(
        "--disable-2fa",
        action="store_true",
        help="Также отключить 2FA и удалить passkey (без запроса, только с --username).",
    )
    parser.add_argument(
        "--length",
        type=int,
        default=12,
        help="Длина генерируемого пароля (по умолчанию: 12).",
    )
    args = parser.parse_args()

    if args.length < 8:
        print("Длина пароля должна быть не меньше 8 символов.", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        passkey_user_ids = load_passkey_user_ids(db)
        if args.usernames:
            selected = resolve_users_by_usernames(db, args.usernames)
        else:
            selected = prompt_selection(load_users(db), db)
    finally:
        db.close()

    if not args.yes and not confirm_reset(selected):
        print("Отменено.")
        return 0

    disable_second_factor = args.disable_2fa
    if not disable_second_factor:
        db = SessionLocal()
        try:
            has_second_factor = bool(users_with_second_factor(db, selected, passkey_user_ids=passkey_user_ids))
        finally:
            db.close()
        if has_second_factor:
            if args.yes:
                disable_second_factor = False
            else:
                db = SessionLocal()
                try:
                    disable_second_factor = prompt_disable_second_factor(db, selected)
                finally:
                    db.close()

    results, disabled_second_factor = reset_passwords(
        selected,
        password_length=args.length,
        disable_second_factor=disable_second_factor,
    )
    if not results:
        print("Ни один пароль не был изменён.")
        return 1

    print()
    print("Новые пароли:")
    for username, password in results:
        print(f"  {username}: {password}")
    print()
    print("Пользователям назначен флаг смены пароля при следующем входе.")
    if disabled_second_factor:
        print("Второй фактор отключён:")
        for item in disabled_second_factor:
            print(f"  - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

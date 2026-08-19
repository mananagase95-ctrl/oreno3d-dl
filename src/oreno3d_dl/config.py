from __future__ import annotations

import base64
import getpass
import json
import os
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from oreno3d_dl import FatalError

APP_DIR = Path.home() / ".config" / "oreno3d-dl"
CONFIG_PATH = APP_DIR / "config.toml"
TOKENS_PATH = APP_DIR / "tokens.json"
JWT_SKEW_SECONDS = 120


@dataclass(frozen=True)
class Credentials:
    email: str
    password: str


def _write_private(path: Path, data: str) -> None:
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            payload = data.encode("utf-8")
            written = 0
            while written < len(payload):
                written += os.write(fd, payload[written:])
        finally:
            os.close(fd)
        os.chmod(path, 0o600)
    except OSError as exc:
        raise FatalError(f"无法写入 {path}: {exc}") from exc


def _toml_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def write_credentials(email: str, password: str) -> None:
    body = (
        f"email = {_toml_string(email)}\n"
        f"password = {_toml_string(password)}\n"
    )
    _write_private(CONFIG_PATH, body)


def prompt_credentials() -> Credentials:
    email = input("Iwara 邮箱: ").strip()
    password = getpass.getpass("Iwara 密码: ")
    if not email or not password:
        raise FatalError("邮箱和密码不能为空")
    return Credentials(email=email, password=password)


def login_interactive() -> Credentials:
    creds = prompt_credentials()
    write_credentials(creds.email, creds.password)
    return creds


def _from_env() -> Credentials | None:
    email = os.environ.get("IWARA_EMAIL")
    password = os.environ.get("IWARA_PASSWORD")
    if email and password:
        return Credentials(email=email, password=password)
    return None


def _from_file() -> Credentials | None:
    if not CONFIG_PATH.is_file():
        return None
    try:
        data = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise FatalError(f"无法读取配置文件: {exc}") from exc
    email = data.get("email")
    password = data.get("password")
    if isinstance(email, str) and isinstance(password, str) and email and password:
        return Credentials(email=email, password=password)
    return None


def load_credentials() -> Credentials:
    creds = _from_env()
    if creds is not None:
        return creds
    creds = _from_file()
    if creds is not None:
        return creds
    return login_interactive()


def jwt_is_expired(token: str, skew_seconds: int = JWT_SKEW_SECONDS) -> bool:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return True
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        exp = data.get("exp")
        if not isinstance(exp, (int, float)):
            return True
        return float(exp) <= time.time() + skew_seconds
    except (ValueError, json.JSONDecodeError, OSError):
        return True


def load_tokens() -> tuple[str | None, str | None]:
    if not TOKENS_PATH.is_file():
        return None, None
    try:
        data = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    user = data.get("user_token")
    access = data.get("access_token")
    user_token = user if isinstance(user, str) and user else None
    access_token = access if isinstance(access, str) and access else None
    return user_token, access_token


def save_tokens(user_token: str, access_token: str) -> None:
    body = json.dumps(
        {"user_token": user_token, "access_token": access_token},
        indent=2,
    )
    _write_private(TOKENS_PATH, body + "\n")


def clear_tokens() -> None:
    try:
        TOKENS_PATH.unlink(missing_ok=True)
    except OSError:
        pass

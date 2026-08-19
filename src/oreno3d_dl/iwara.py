from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx

from oreno3d_dl import FatalError, ItemError
from oreno3d_dl.config import (
    Credentials,
    clear_tokens,
    jwt_is_expired,
    load_tokens,
    save_tokens,
)

API_BASE = "https://api.iwara.tv"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
# Iwara fileUrl signing salt; change only this if the API rotates it.
X_VERSION_SALT = "mSvL05GfEmeEmsEYfGCnVpEjYgTJraJN"


@dataclass(frozen=True)
class VideoMeta:
    id: str
    title: str
    author: str
    file_url: str


def absolute_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return url


def compute_x_version(file_url: str) -> str:
    parsed = urlparse(file_url)
    last = parsed.path.rstrip("/").split("/")[-1]
    expires = (parse_qs(parsed.query).get("expires") or [""])[0]
    raw = f"{last}_{expires}_{X_VERSION_SALT}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def pick_source_url(files: list[object]) -> str | None:
    for item in files:
        if not isinstance(item, dict):
            continue
        if item.get("name") != "Source":
            continue
        src = item.get("src") or {}
        if not isinstance(src, dict):
            return None
        url = src.get("download") or src.get("view")
        if isinstance(url, str) and url:
            return absolute_url(url)
        return None
    return None


def _message_text(data: object) -> str:
    if not isinstance(data, dict):
        return str(data or "")
    message = data.get("message")
    if isinstance(message, list):
        return " ".join(str(part) for part in message)
    if message is None:
        return ""
    return str(message)


class IwaraClient:
    def __init__(self, http: httpx.Client, credentials: Credentials):
        self.http = http
        self.credentials = credentials
        self.user_token: str | None = None
        self.access_token: str | None = None

    def ensure_ready(self) -> None:
        self.user_token, self.access_token = load_tokens()
        self._ensure_media_token()

    def _persist(self) -> None:
        if self.user_token and self.access_token:
            save_tokens(self.user_token, self.access_token)

    def _login(self) -> None:
        try:
            response = self.http.post(
                f"{API_BASE}/user/login",
                json={
                    "email": self.credentials.email,
                    "password": self.credentials.password,
                },
            )
        except httpx.TimeoutException as exc:
            raise FatalError("Iwara 登录失败：网络超时") from exc
        except httpx.HTTPError as exc:
            raise FatalError("Iwara 登录失败：网络错误") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise FatalError("Iwara 登录失败：无法解析响应") from exc
        token = data.get("token") if isinstance(data, dict) else None
        if isinstance(token, str) and token:
            self.user_token = token
            self.access_token = None
            return
        message = _message_text(data)
        if "invalidLogin" in message:
            clear_tokens()
            raise FatalError("Iwara 登录失败：账号或密码错误")
        raise FatalError(f"Iwara 登录失败: {message or response.status_code}")

    def _refresh_media(self) -> None:
        if not self.user_token:
            raise FatalError("Iwara 登录失败：缺少用户 token")
        try:
            response = self.http.post(
                f"{API_BASE}/user/token",
                headers={
                    "Authorization": f"Bearer {self.user_token}",
                    "Content-Type": "application/json",
                },
                content=b"",
            )
        except httpx.TimeoutException as exc:
            raise FatalError("Iwara 登录失败：网络超时") from exc
        except httpx.HTTPError as exc:
            raise FatalError("Iwara 登录失败：网络错误") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise FatalError("Iwara 登录失败：无法解析响应") from exc
        token = data.get("accessToken") if isinstance(data, dict) else None
        if isinstance(token, str) and token:
            self.access_token = token
            return
        message = _message_text(data)
        raise FatalError(f"Iwara 登录失败: {message or response.status_code}")

    def _ensure_media_token(self) -> None:
        if not self.user_token or jwt_is_expired(self.user_token):
            self._login()
        if not self.access_token or jwt_is_expired(self.access_token):
            try:
                self._refresh_media()
            except FatalError:
                self._login()
                self._refresh_media()
        self._persist()

    def _auth_headers(self) -> dict[str, str]:
        self._ensure_media_token()
        assert self.access_token is not None
        return {"Authorization": f"Bearer {self.access_token}"}

    def get_video(self, video_id: str) -> VideoMeta:
        try:
            response = self.http.get(
                f"{API_BASE}/video/{video_id}",
                headers=self._auth_headers(),
            )
        except httpx.TimeoutException as exc:
            raise ItemError("网络超时") from exc
        except httpx.HTTPError as exc:
            raise ItemError("网络错误") from exc
        if response.status_code >= 500:
            raise ItemError(f"服务器错误: HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise ItemError("无法解析 Iwara 视频信息") from exc

        message = _message_text(data)
        if "errors.notFound" in message:
            raise ItemError("视频不存在或已删除")
        if "errors.privateVideo" in message:
            raise ItemError("私密视频，当前账号无权访问")

        file_url = data.get("fileUrl") if isinstance(data, dict) else None
        embed_url = data.get("embedUrl") if isinstance(data, dict) else None
        if not file_url:
            if embed_url:
                raise ItemError("外链视频，本工具不下")
            raise ItemError("没有 Source 画质")

        title = ""
        author = ""
        if isinstance(data, dict):
            raw_title = data.get("title")
            if isinstance(raw_title, str):
                title = raw_title.strip()
            user = data.get("user") or {}
            if isinstance(user, dict):
                raw_author = user.get("name")
                if isinstance(raw_author, str):
                    author = raw_author.strip()
        return VideoMeta(
            id=video_id,
            title=title or video_id,
            author=author or "unknown",
            file_url=absolute_url(str(file_url)),
        )

    def get_source_url(self, file_url: str) -> str:
        file_url = absolute_url(file_url)
        headers = {"X-Version": compute_x_version(file_url)}
        try:
            response = self.http.get(file_url, headers=headers)
        except httpx.TimeoutException as exc:
            raise ItemError("网络超时") from exc
        except httpx.HTTPError as exc:
            raise ItemError("网络错误") from exc
        if response.status_code >= 500:
            raise ItemError(f"服务器错误: HTTP {response.status_code}")
        if response.status_code != 200:
            raise ItemError(f"获取清晰度列表失败: HTTP {response.status_code}")
        try:
            files = response.json()
        except ValueError as exc:
            raise ItemError("无法解析清晰度列表") from exc
        if not isinstance(files, list):
            raise ItemError("无法解析清晰度列表")
        url = pick_source_url(files)
        if not url:
            raise ItemError("没有 Source 画质")
        return url

from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup, Tag

from oreno3d_dl import ItemError

ORENO3D_MOVIE_RE = re.compile(
    r"^https?://(?:www\.)?oreno3d\.com/movies/\d+(?:[/?#].*)?$",
    re.IGNORECASE,
)
IWARA_VIDEO_RE = re.compile(
    r"https?://(?:www\.)?iwara\.tv/video/([A-Za-z0-9]+)",
    re.IGNORECASE,
)
WATCH_SELECTORS = (
    'a.pop_separate[href*="iwara.tv/video"]',
    'a.video-watch-btn2[href*="iwara.tv/video"]',
)


def is_oreno3d_movie_url(url: str) -> bool:
    return bool(ORENO3D_MOVIE_RE.match(url))


def _class_id_text(tag: Tag) -> str:
    classes = tag.get("class") or []
    if isinstance(classes, str):
        class_text = classes
    else:
        class_text = " ".join(str(c) for c in classes)
    ident = tag.get("id") or ""
    return f"{class_text} {ident}".lower()


def _should_ignore(tag: Tag) -> bool:
    current: Tag | None = tag
    while isinstance(current, Tag):
        if current.name == "blockquote":
            return True
        if "related" in _class_id_text(current):
            return True
        parent = current.parent
        current = parent if isinstance(parent, Tag) else None
    return False


def extract_iwara_id(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for selector in WATCH_SELECTORS:
        for anchor in soup.select(selector):
            if _should_ignore(anchor):
                continue
            href = anchor.get("href") or ""
            match = IWARA_VIDEO_RE.search(str(href))
            if match:
                return match.group(1)
    return None


def fetch_iwara_id(client: httpx.Client, url: str) -> str:
    try:
        response = client.get(url)
    except httpx.TimeoutException as exc:
        raise ItemError("网络超时") from exc
    except httpx.HTTPError as exc:
        raise ItemError("网络错误") from exc
    if response.status_code >= 500:
        raise ItemError(f"服务器错误: HTTP {response.status_code}")
    if response.status_code != 200:
        raise ItemError(f"oreno3d 页面请求失败: HTTP {response.status_code}")
    video_id = extract_iwara_id(response.text)
    if not video_id:
        raise ItemError("页面没有 Iwara 视频链接")
    return video_id

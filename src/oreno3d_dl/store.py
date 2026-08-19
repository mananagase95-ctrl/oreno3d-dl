from __future__ import annotations

import errno
import re
from collections.abc import Iterator
from pathlib import Path

import httpx

from oreno3d_dl import FatalError, ItemError

_ILLEGAL = re.compile(r'[/\\:*?"<>|\x00-\x1f\x7f]')
_MAX_FILENAME = 180


def sanitize_segment(name: str) -> str:
    cleaned = _ILLEGAL.sub("_", name)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" .")


def build_filename(title: str, video_id: str) -> str:
    suffix = f" [{video_id}].mp4"
    raw = title.strip() if title else ""
    if not raw:
        raw = video_id
    title_part = sanitize_segment(raw)
    max_title = max(0, _MAX_FILENAME - len(suffix))
    if len(title_part) > max_title:
        title_part = title_part[:max_title].rstrip(" .")
    if not title_part:
        fallback = sanitize_segment(video_id)[:max_title].rstrip(" .")
        title_part = fallback or "video"
    return title_part + suffix


def dest_path(root: Path, author: str, title: str, video_id: str) -> Path:
    author_part = sanitize_segment(author) if author else ""
    if not author_part:
        author_part = "unknown"
    return Path(root) / author_part / build_filename(title, video_id)


def part_path(dest: Path) -> Path:
    return Path(str(dest) + ".part")


def iter_existing(root: Path, video_id: str) -> Iterator[Path]:
    token = f"[{video_id}]"
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name.endswith(".part"):
            continue
        if token in path.name:
            yield path


def find_existing(root: Path, video_id: str) -> Path | None:
    return next(iter_existing(root, video_id), None)


def _raise_io(exc: OSError) -> None:
    if exc.errno == errno.ENOSPC:
        raise FatalError("磁盘空间不足") from exc
    raise FatalError(f"写入失败: {exc}") from exc


def download_with_resume(client: httpx.Client, url: str, dest: Path) -> None:
    dest = Path(dest)
    part = part_path(dest)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _raise_io(exc)

    existing = 0
    if part.is_file():
        existing = part.stat().st_size

    headers: dict[str, str] = {}
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"

    try:
        with client.stream("GET", url, headers=headers) as response:
            if response.status_code >= 500:
                raise ItemError(f"服务器错误: HTTP {response.status_code}")
            if existing > 0 and response.status_code == 200:
                part.unlink(missing_ok=True)
                existing = 0
                mode = "wb"
            elif response.status_code == 206 and existing > 0:
                mode = "ab"
            elif response.status_code == 200:
                mode = "wb"
            else:
                raise ItemError(f"下载失败: HTTP {response.status_code}")

            try:
                with open(part, mode) as fh:
                    for chunk in response.iter_bytes(256 * 1024):
                        if chunk:
                            fh.write(chunk)
            except OSError as exc:
                _raise_io(exc)
    except ItemError:
        raise
    except FatalError:
        raise
    except httpx.TimeoutException as exc:
        raise ItemError("网络超时") from exc
    except httpx.HTTPError as exc:
        raise ItemError("网络错误") from exc

    try:
        part.replace(dest)
    except OSError as exc:
        _raise_io(exc)


def remove_stale(old_paths: list[Path], dest: Path) -> None:
    dest_resolved = dest.resolve()
    for old in old_paths:
        try:
            if old.resolve() != dest_resolved and old.is_file():
                old.unlink()
        except OSError as exc:
            _raise_io(exc)

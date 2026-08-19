from __future__ import annotations

import errno
import re
import sys
import time
from pathlib import Path

import httpx

from oreno3d_dl import FatalError, ItemError

_ILLEGAL = re.compile(r'[/\\:*?"<>|\x00-\x1f\x7f]')
_MAX_FILENAME = 180


def sanitize_segment(name: str) -> str:
    cleaned = _ILLEGAL.sub("_", name)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" .")


def build_filename(author: str, title: str) -> str:
    author_part = sanitize_segment(author) if author else ""
    if not author_part:
        author_part = "unknown"
    if len(author_part) > 80:
        author_part = author_part[:80].rstrip(" .") or "unknown"
    title_part = sanitize_segment(title) if title else ""
    if not title_part:
        title_part = "video"
    prefix = f"[{author_part}]"
    suffix = ".mp4"
    max_title = max(1, _MAX_FILENAME - len(prefix) - len(suffix))
    if len(title_part) > max_title:
        title_part = title_part[:max_title].rstrip(" .")
    if not title_part:
        title_part = "video"[:max_title]
    return f"{prefix}{title_part}{suffix}"


def dest_path(root: Path, author: str, title: str) -> Path:
    return Path(root) / build_filename(author, title)


def part_path(dest: Path) -> Path:
    return Path(str(dest) + ".part")


def find_existing(root: Path, author: str, title: str) -> Path | None:
    dest = dest_path(root, author, title)
    if dest.is_file():
        return dest
    return None


def _raise_io(exc: OSError) -> None:
    if exc.errno == errno.ENOSPC:
        raise FatalError("磁盘空间不足") from exc
    raise FatalError(f"写入失败: {exc}") from exc


def content_total(response: httpx.Response, existing: int) -> int | None:
    content_range = response.headers.get("content-range") or ""
    if "/" in content_range:
        total_text = content_range.rsplit("/", 1)[-1].strip()
        if total_text.isdigit():
            return int(total_text)
    length_text = response.headers.get("content-length") or ""
    if length_text.isdigit():
        length = int(length_text)
        if response.status_code == 206:
            return existing + length
        return length
    return None


def _format_mb(n: int) -> str:
    return f" {n / (1024 * 1024):.1f} MB"


def _print_progress(done: int, total: int | None, speed: float) -> None:
    speed_text = f"  {speed / (1024 * 1024):.1f} MB/s"
    if total and total > 0:
        pct = min(100.0, done * 100 / total)
        line = f"\r下载中{_format_mb(done)} /{_format_mb(total)} ({pct:.0f}%){speed_text}"
    else:
        line = f"\r下载中{_format_mb(done)}{speed_text}"
    print(line, end="", flush=True, file=sys.stderr)


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

            total = content_total(response, existing)
            done = existing
            started = time.monotonic()
            last_report = 0.0
            _print_progress(done, total, 0.0)
            try:
                with open(part, mode) as fh:
                    for chunk in response.iter_bytes(256 * 1024):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        done += len(chunk)
                        now = time.monotonic()
                        if now - last_report >= 0.4:
                            elapsed = max(now - started, 1e-6)
                            _print_progress(done, total, (done - existing) / elapsed)
                            last_report = now
            except OSError as exc:
                print(file=sys.stderr)
                _raise_io(exc)
            elapsed = max(time.monotonic() - started, 1e-6)
            _print_progress(done, total or done, (done - existing) / elapsed)
            print(file=sys.stderr)
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

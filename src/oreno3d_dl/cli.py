from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

import httpx

from oreno3d_dl import FatalError, ItemError
from oreno3d_dl.config import CONFIG_PATH, load_credentials, login_interactive
from oreno3d_dl.iwara import USER_AGENT, IwaraClient
from oreno3d_dl.oreno3d import fetch_iwara_id, is_oreno3d_movie_url
from oreno3d_dl.store import dest_path, download_with_resume

INVALID_URL_REASON = "不是有效的 oreno3d 视频地址"
USAGE_HINT = "请提供 oreno3d 视频地址（命令行、文件或标准输入）。"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oreno3d-dl",
        description="从 oreno3d 视频页下载对应的 Iwara Source 画质文件。",
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="oreno3d 地址，或包含地址的文本文件；省略则从标准输入读取",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="./downloads",
        help="输出根目录（默认 ./downloads）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="已存在的成品也重新下载",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="只写入或更新账号，不下载",
    )
    return parser


def parse_url_lines(text: str) -> list[str]:
    urls: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        urls.append(stripped)
    return urls


def looks_like_url(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def load_url_lines(
    inputs: list[str] | None,
    *,
    stdin: TextIO | None = None,
) -> list[str]:
    if not inputs:
        stream = stdin if stdin is not None else sys.stdin
        return parse_url_lines(stream.read())

    urls: list[str] = []
    for item in inputs:
        if looks_like_url(item):
            urls.append(item)
            continue
        path = Path(item)
        if not path.is_file():
            raise FatalError(f"找不到文件，也不是网址: {item}")
        try:
            urls.extend(parse_url_lines(path.read_text(encoding="utf-8")))
        except OSError as exc:
            raise FatalError(f"无法读取 URL 文件: {exc}") from exc
    return urls


def log(message: str) -> None:
    print(message, flush=True)


def process_one(
    http: httpx.Client,
    iwara: IwaraClient,
    url: str,
    output_root: Path,
    force: bool,
) -> str:
    log("正在打开 oreno3d 页面...")
    iwara_id = fetch_iwara_id(http, url)
    log(f"Iwara: https://www.iwara.tv/video/{iwara_id}")
    log("正在获取视频信息...")
    meta = iwara.get_video(iwara_id)
    log(f"{meta.author} / {meta.title}")
    dest = dest_path(output_root, meta.author, meta.title)
    if dest.is_file() and not force:
        log(f"已存在，跳过: {dest}")
        return "skip"
    log("正在获取 Source 地址...")
    source_url = iwara.get_source_url(meta.file_url)
    log(f"开始下载 -> {dest}")
    download_with_resume(http, source_url, dest)
    log(f"下载完成: {dest}")
    return "success"


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.login:
        try:
            login_interactive()
        except FatalError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"已保存到 {CONFIG_PATH}")
        return 0

    try:
        urls = load_url_lines(args.inputs)
    except FatalError as exc:
        print(exc, file=sys.stderr)
        return 1

    if not urls:
        parser.print_usage(sys.stderr)
        print(USAGE_HINT, file=sys.stderr)
        return 2

    try:
        credentials = load_credentials()
    except FatalError as exc:
        print(exc, file=sys.stderr)
        return 1

    timeout = httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=15.0)
    success = 0
    skipped = 0
    failed = 0
    failures: list[tuple[str, str]] = []
    output_root = Path(args.output)

    try:
        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        ) as http:
            iwara = IwaraClient(http, credentials)
            log("正在登录 Iwara...")
            iwara.ensure_ready()
            log("登录成功")

            for url in urls:
                log(url)
                if not is_oreno3d_movie_url(url):
                    failed += 1
                    failures.append((url, INVALID_URL_REASON))
                    log(f"失败: {INVALID_URL_REASON}")
                    continue
                try:
                    result = process_one(
                        http,
                        iwara,
                        url,
                        output_root,
                        args.force,
                    )
                except ItemError as exc:
                    failed += 1
                    failures.append((url, exc.reason))
                    log(f"失败: {exc.reason}")
                    continue
                if result == "skip":
                    skipped += 1
                else:
                    success += 1
    except FatalError as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"成功 {success}，跳过 {skipped}，失败 {failed}")
    for url, reason in failures:
        print(f"{url}  {reason}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> None:
    try:
        raise SystemExit(run(argv))
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__ == "__main__":
    main()

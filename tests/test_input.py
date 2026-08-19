from io import StringIO
from pathlib import Path

import pytest

from oreno3d_dl import FatalError
from oreno3d_dl.cli import load_url_lines, looks_like_url, parse_url_lines

SAMPLE = """
# comment
https://oreno3d.com/movies/123

  https://www.oreno3d.com/movies/456?x=1
#https://oreno3d.com/movies/999
https://oreno3d.com/movies/789
"""


def test_parse_drops_blank_and_comment_lines():
    assert parse_url_lines(SAMPLE) == [
        "https://oreno3d.com/movies/123",
        "https://www.oreno3d.com/movies/456?x=1",
        "https://oreno3d.com/movies/789",
    ]


def test_load_from_file(tmp_path: Path):
    path = tmp_path / "urls.txt"
    path.write_text(SAMPLE, encoding="utf-8")
    assert load_url_lines([str(path)]) == [
        "https://oreno3d.com/movies/123",
        "https://www.oreno3d.com/movies/456?x=1",
        "https://oreno3d.com/movies/789",
    ]


def test_load_from_stdin():
    stdin = StringIO(SAMPLE)
    assert load_url_lines([], stdin=stdin) == [
        "https://oreno3d.com/movies/123",
        "https://www.oreno3d.com/movies/456?x=1",
        "https://oreno3d.com/movies/789",
    ]


def test_load_direct_urls():
    urls = [
        "https://oreno3d.com/movies/329977",
        "https://www.oreno3d.com/movies/123",
    ]
    assert load_url_lines(urls) == urls


def test_load_mixes_file_and_urls(tmp_path: Path):
    path = tmp_path / "urls.txt"
    path.write_text("https://oreno3d.com/movies/1\n", encoding="utf-8")
    assert load_url_lines([str(path), "https://oreno3d.com/movies/2"]) == [
        "https://oreno3d.com/movies/1",
        "https://oreno3d.com/movies/2",
    ]


def test_missing_file_is_not_opened_as_url():
    with pytest.raises(FatalError, match="找不到文件"):
        load_url_lines(["urls-that-do-not-exist.txt"])


def test_looks_like_url():
    assert looks_like_url("https://oreno3d.com/movies/329977")
    assert looks_like_url("http://oreno3d.com/movies/1")
    assert not looks_like_url("urls.txt")

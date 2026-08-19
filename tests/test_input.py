from io import StringIO
from pathlib import Path

from oreno3d_dl.cli import load_url_lines, parse_url_lines

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
    assert load_url_lines(str(path)) == [
        "https://oreno3d.com/movies/123",
        "https://www.oreno3d.com/movies/456?x=1",
        "https://oreno3d.com/movies/789",
    ]


def test_load_from_stdin():
    stdin = StringIO(SAMPLE)
    assert load_url_lines(None, stdin=stdin) == [
        "https://oreno3d.com/movies/123",
        "https://www.oreno3d.com/movies/456?x=1",
        "https://oreno3d.com/movies/789",
    ]

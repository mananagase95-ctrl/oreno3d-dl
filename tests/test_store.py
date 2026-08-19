from pathlib import Path

import httpx

from oreno3d_dl.store import (
    build_filename,
    content_total,
    dest_path,
    find_existing,
    sanitize_segment,
)


def test_illegal_chars_replaced():
    cleaned = sanitize_segment('a/b\\c:d*e?f"g<h>i|j')
    assert cleaned == "a_b_c_d_e_f_g_h_i_j"
    path = dest_path(Path("/tmp/out"), "foo/bar", 'title: "x"')
    assert path == Path("/tmp/out") / '[foo_bar]title_ _x_.mp4'


def test_whitespace_and_dots_stripped():
    assert sanitize_segment("  ..hello   world..  ") == "hello world"


def test_filename_is_author_then_title():
    assert build_filename("Author", "My Video") == "[Author]My Video.mp4"


def test_filename_has_no_id_and_stays_within_limit():
    title = "あ" * 400
    name = build_filename("作者", title)
    assert name.startswith("[作者]")
    assert name.endswith(".mp4")
    assert "[" not in name[name.find("]") + 1 :]
    assert len(name) == 180


def test_existing_dest_is_skip(tmp_path: Path):
    finished = dest_path(tmp_path, "author", "old title")
    finished.write_bytes(b"done")
    found = find_existing(tmp_path, "author", "old title")
    assert found == finished


def test_part_file_is_not_downloaded(tmp_path: Path):
    dest = dest_path(tmp_path, "author", "title")
    part = Path(str(dest) + ".part")
    part.write_bytes(b"partial")
    assert find_existing(tmp_path, "author", "title") is None


def test_content_total_from_range_and_length():
    ranged = httpx.Response(
        206,
        headers={"content-range": "bytes 100-199/1000", "content-length": "100"},
    )
    assert content_total(ranged, 100) == 1000
    full = httpx.Response(200, headers={"content-length": "500"})
    assert content_total(full, 0) == 500
    unknown = httpx.Response(200)
    assert content_total(unknown, 0) is None

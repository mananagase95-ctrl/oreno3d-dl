from pathlib import Path

from oreno3d_dl.store import build_filename, dest_path, find_existing, sanitize_segment


def test_illegal_chars_replaced():
    cleaned = sanitize_segment('a/b\\c:d*e?f"g<h>i|j')
    assert cleaned == "a_b_c_d_e_f_g_h_i_j"
    path = dest_path(Path("/tmp/out"), "foo/bar", 'title: "x"', "id1")
    assert path.parent.name == "foo_bar"
    assert path.name == 'title_ _x_ [id1].mp4'


def test_whitespace_and_dots_stripped():
    assert sanitize_segment("  ..hello   world..  ") == "hello world"


def test_filename_keeps_id_suffix_when_truncated():
    title = "あ" * 400
    name = build_filename(title, "abc123")
    assert name.endswith(" [abc123].mp4")
    assert len(name) == 180


def test_existing_id_is_skip(tmp_path: Path):
    finished = tmp_path / "author" / "old title [vid99].mp4"
    finished.parent.mkdir(parents=True)
    finished.write_bytes(b"done")
    found = find_existing(tmp_path, "vid99")
    assert found == finished


def test_part_file_is_not_downloaded(tmp_path: Path):
    part = tmp_path / "author" / "title [vid99].mp4.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(b"partial")
    assert find_existing(tmp_path, "vid99") is None

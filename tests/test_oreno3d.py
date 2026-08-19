from pathlib import Path

from oreno3d_dl.oreno3d import extract_iwara_id, is_oreno3d_movie_url

FIXTURES = Path(__file__).parent / "fixtures"


def test_official_watch_button_extracts_id():
    html = (FIXTURES / "official_watch.html").read_text(encoding="utf-8")
    assert extract_iwara_id(html) == "CaKzOLvffDnjGF"


def test_comment_and_related_links_are_ignored():
    html = (FIXTURES / "comment_related_only.html").read_text(encoding="utf-8")
    assert extract_iwara_id(html) is None


def test_no_iwara_link_is_failure():
    html = (FIXTURES / "no_iwara_link.html").read_text(encoding="utf-8")
    assert extract_iwara_id(html) is None


def test_oreno3d_url_validation():
    assert is_oreno3d_movie_url("https://oreno3d.com/movies/231935")
    assert is_oreno3d_movie_url("http://www.oreno3d.com/movies/1/extra?x=1")
    assert not is_oreno3d_movie_url("https://oreno3d.com/movies/")
    assert not is_oreno3d_movie_url("https://oreno3d.com/authors/1")
    assert not is_oreno3d_movie_url("https://iwara.tv/video/abc")

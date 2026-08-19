from oreno3d_dl.iwara import pick_source_url


def test_pick_source_not_preview_or_lower():
    files = [
        {
            "name": "preview",
            "src": {"view": "//cdn.example/preview", "download": "//cdn.example/preview-dl"},
        },
        {
            "name": "360",
            "src": {"view": "//cdn.example/360", "download": "//cdn.example/360-dl"},
        },
        {
            "name": "540",
            "src": {"view": "//cdn.example/540", "download": "//cdn.example/540-dl"},
        },
        {
            "name": "Source",
            "src": {"view": "//cdn.example/source", "download": "//cdn.example/source-dl"},
        },
    ]
    assert pick_source_url(files) == "https://cdn.example/source-dl"


def test_pick_source_falls_back_to_view():
    files = [
        {"name": "360", "src": {"view": "//cdn.example/360", "download": "//cdn.example/360-dl"}},
        {"name": "Source", "src": {"view": "//cdn.example/source-view"}},
    ]
    assert pick_source_url(files) == "https://cdn.example/source-view"


def test_pick_source_missing():
    files = [
        {"name": "preview", "src": {"view": "//cdn.example/preview"}},
        {"name": "360", "src": {"view": "//cdn.example/360"}},
        {"name": "540", "src": {"view": "//cdn.example/540"}},
    ]
    assert pick_source_url(files) is None

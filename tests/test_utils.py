"""Tests for utils.py helpers."""

from scraper.utils import (
    normalize_keyword,
    get_search_keywords,
    build_search_url,
    extract_video_id,
    is_shorts_url,
    is_video_url,
    clean_text,
    truncate_text,
    ensure_csv_dir,
    get_csv_filename,
)


def test_normalize_keyword_music_appended():
    assert normalize_keyword("Hardtekk") == "Hardtekk music"
    assert normalize_keyword("Sigma") == "Sigma music"
    assert normalize_keyword("Jumpstyle") == "Jumpstyle music"


def test_normalize_keyword_obviously_music():
    assert normalize_keyword("Remix") == "Remix"
    assert normalize_keyword("Acapella") == "Acapella"
    assert normalize_keyword("Suno AI") == "Suno AI"
    assert normalize_keyword("slowed + reverb") == "slowed + reverb"


def test_get_search_keywords():
    keywords = get_search_keywords()
    assert "Remix" in keywords
    assert "Hardtekk music" in keywords
    assert "Sigma music" in keywords
    assert len(keywords) == len(set(keywords))  # duplicates not possible here


def test_build_search_url():
    url = build_search_url("Hardtekk music")
    assert url.startswith("https://www.youtube.com/results?")
    assert (
        "search_query=Hardtekk+music" in url or "search_query=Hardtekk%20music" in url
    )
    assert "sp=EgQIARgB" in url


def test_extract_video_id():
    assert (
        extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    )
    assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert (
        extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    )
    assert extract_video_id("https://www.youtube.com/watch?v=INVALID") is None


def test_is_shorts_url():
    assert is_shorts_url("https://www.youtube.com/shorts/dQw4w9WgXcQ")
    assert not is_shorts_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


def test_is_video_url():
    assert is_video_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert not is_video_url("https://www.google.com")


def test_clean_text():
    assert clean_text("  hello   world  ") == "hello world"
    assert clean_text(None) == ""
    assert clean_text("\n\t  text  \n") == "text"


def test_truncate_text():
    assert truncate_text("hello world", 100) == "hello world"
    truncated = truncate_text("a" * 500, 300)
    assert len(truncated) <= 300
    assert truncated.endswith("...")


def test_ensure_csv_dir(tmp_path):
    path = tmp_path / "out" / "file.csv"
    result = ensure_csv_dir(str(path))
    assert result.parent.exists()


def test_get_csv_filename():
    assert get_csv_filename().startswith("youtube_music_scrape_")
    assert get_csv_filename().endswith(".csv")

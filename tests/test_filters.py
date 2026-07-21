"""Tests for filters.py."""

from scraper.models import SearchResult, Video, ScraperConfig
from scraper.filters import (
    title_contains_banned_words,
    is_valid_video_type,
    pre_filter_results,
    post_filter_video,
)


def test_title_contains_banned_words():
    assert title_contains_banned_words("FL Studio Tutorial")
    assert title_contains_banned_words("Live Stream Tonight")
    assert title_contains_banned_words("Gaming Walkthrough")
    assert title_contains_banned_words("How to make beats")
    assert not title_contains_banned_words("New Chill Lofi Beat")
    assert not title_contains_banned_words("Remix 2024")


def test_is_valid_video_type():
    assert is_valid_video_type(
        SearchResult("t", "u", "c", "cu", "0", "1 hour ago", "3:00")
    )
    assert not is_valid_video_type(
        SearchResult("t", "u", "c", "cu", "0", "1 hour ago", "3:00", is_short=True)
    )
    assert not is_valid_video_type(
        SearchResult("t", "u", "c", "cu", "0", "1 hour ago", "3:00", is_live=True)
    )
    assert not is_valid_video_type(
        SearchResult("t", "u", "c", "cu", "0", "1 hour ago", "3:00", is_premiere=True)
    )


def test_pre_filter_results():
    config = ScraperConfig()
    results = [
        SearchResult(
            "Beat",
            "http://watch?v=A",
            "Ch",
            "http://ch",
            "1.2K views",
            "2 hours ago",
            "3:00",
            source_keyword="k",
        ),
        SearchResult(
            "Tutorial",
            "http://watch?v=B",
            "Ch",
            "http://ch",
            "1.2K views",
            "2 hours ago",
            "3:00",
            source_keyword="k",
        ),
        SearchResult(
            "Beat",
            "http://watch?v=C",
            "Ch",
            "http://ch",
            "100 views",
            "2 hours ago",
            "3:00",
            source_keyword="k",
        ),
        SearchResult(
            "Beat",
            "http://watch?v=D",
            "Ch",
            "http://ch",
            "1.2K views",
            "30 minutes ago",
            "3:00",
            source_keyword="k",
        ),
        SearchResult(
            "Beat",
            "http://watch?v=E",
            "Ch",
            "http://ch",
            "1.2K views",
            "2 hours ago",
            "10:00",
            source_keyword="k",
        ),
    ]
    accepted = pre_filter_results(results, config)
    assert len(accepted) == 1
    assert accepted[0].url == "http://watch?v=A"


def test_pre_filter_results_rejects_shorts():
    config = ScraperConfig()
    results = [
        SearchResult(
            "Beat",
            "http://watch?v=A",
            "Ch",
            "http://ch",
            "1.2K views",
            "2 hours ago",
            "3:00",
            is_short=True,
            source_keyword="k",
        ),
    ]
    assert pre_filter_results(results, config) == []


def test_post_filter_video():
    config = ScraperConfig()
    video = Video(
        title="Beat",
        url="http://watch?v=A",
        channel_name="Ch",
        channel_url="http://ch",
        subscriber_count=1000,
        duration_seconds=180,
        description_snippet="",
        views=1200,
        original_view_text="1.2K views",
        likes=100,
        comment_count=10,
        comments_enabled=True,
        top_comments=[],
        matched_keywords=["k"],
        source_keyword="k",
        release_date="2024-01-01",
        scraped_at="2024-01-01T12:00:00Z",
        hours_since_upload=2.0,
        velocity=600.0,
        is_topic_channel=False,
    )
    assert post_filter_video(video, config)


def test_post_filter_video_rejects_banned_title():
    config = ScraperConfig()
    video = Video(
        title="Tutorial: How to make beats",
        url="http://watch?v=A",
        channel_name="Ch",
        channel_url="http://ch",
        subscriber_count=1000,
        duration_seconds=180,
        description_snippet="",
        views=1200,
        original_view_text="1.2K views",
        likes=100,
        comment_count=10,
        comments_enabled=True,
        top_comments=[],
        matched_keywords=["k"],
        source_keyword="k",
        release_date="2024-01-01",
        scraped_at="2024-01-01T12:00:00Z",
        hours_since_upload=2.0,
        velocity=600.0,
        is_topic_channel=False,
    )
    assert not post_filter_video(video, config)


def test_post_filter_video_rejects_too_old():
    config = ScraperConfig()
    video = Video(
        title="Beat",
        url="http://watch?v=A",
        channel_name="Ch",
        channel_url="http://ch",
        subscriber_count=1000,
        duration_seconds=180,
        description_snippet="",
        views=1200,
        original_view_text="1.2K views",
        likes=100,
        comment_count=10,
        comments_enabled=True,
        top_comments=[],
        matched_keywords=["k"],
        source_keyword="k",
        release_date="2024-01-01",
        scraped_at="2024-01-01T12:00:00Z",
        hours_since_upload=25.0,
        velocity=48.0,
        is_topic_channel=False,
    )
    assert not post_filter_video(video, config)


def test_post_filter_video_rejects_too_short_duration():
    config = ScraperConfig()
    video = Video(
        title="Beat",
        url="http://watch?v=A",
        channel_name="Ch",
        channel_url="http://ch",
        subscriber_count=1000,
        duration_seconds=600,
        description_snippet="",
        views=1200,
        original_view_text="1.2K views",
        likes=100,
        comment_count=10,
        comments_enabled=True,
        top_comments=[],
        matched_keywords=["k"],
        source_keyword="k",
        release_date="2024-01-01",
        scraped_at="2024-01-01T12:00:00Z",
        hours_since_upload=2.0,
        velocity=600.0,
        is_topic_channel=False,
    )
    assert not post_filter_video(video, config)


def test_post_filter_video_rejects_low_views():
    config = ScraperConfig()
    video = Video(
        title="Beat",
        url="http://watch?v=A",
        channel_name="Ch",
        channel_url="http://ch",
        subscriber_count=1000,
        duration_seconds=180,
        description_snippet="",
        views=100,
        original_view_text="100 views",
        likes=100,
        comment_count=10,
        comments_enabled=True,
        top_comments=[],
        matched_keywords=["k"],
        source_keyword="k",
        release_date="2024-01-01",
        scraped_at="2024-01-01T12:00:00Z",
        hours_since_upload=2.0,
        velocity=50.0,
        is_topic_channel=False,
    )
    assert not post_filter_video(video, config)


def test_post_filter_video_rejects_less_than_one_hour():
    config = ScraperConfig()
    video = Video(
        title="Beat",
        url="http://watch?v=A",
        channel_name="Ch",
        channel_url="http://ch",
        subscriber_count=1000,
        duration_seconds=180,
        description_snippet="",
        views=1200,
        original_view_text="1.2K views",
        likes=100,
        comment_count=10,
        comments_enabled=True,
        top_comments=[],
        matched_keywords=["k"],
        source_keyword="k",
        release_date="2024-01-01",
        scraped_at="2024-01-01T12:00:00Z",
        hours_since_upload=0.5,
        velocity=2400.0,
        is_topic_channel=False,
    )
    assert not post_filter_video(video, config)

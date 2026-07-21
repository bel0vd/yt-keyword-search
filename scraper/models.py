"""Data models for the YouTube Music scraper."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ScraperConfig:
    """Configuration for the scraping run."""

    min_views: int = 500
    max_duration_seconds: int = 360  # 6 minutes
    min_hours_since_upload: float = 1.0
    max_hours_since_upload: float = 24.0

    min_delay_between_searches: float = 2.4
    max_delay_between_searches: float = 5.6

    min_delay_between_videos: float = 3.6
    max_delay_between_videos: float = 8.4

    min_delay_between_scrolls: float = 0.9
    max_delay_between_scrolls: float = 2.1

    max_scrolls_per_search: int = 5
    scrolls_after_stall: int = 2

    max_comments: int = 10
    max_video_retries: int = 2
    request_timeout: int = 30_000

    concurrent_contexts: int = 2
    requests_per_pause: int = 80
    pause_duration: float = 300.0  # 5 minutes


@dataclass
class SearchResult:
    """Candidate video found on a YouTube search results page."""

    title: str
    url: str
    channel_name: str
    channel_url: str
    views_text: str
    upload_time_text: str
    duration_text: str
    is_short: bool = False
    is_live: bool = False
    is_premiere: bool = False
    source_keyword: str = ""


@dataclass
class Video:
    """Fully scraped and validated YouTube music video."""

    title: str
    url: str
    channel_name: str
    channel_url: str
    subscriber_count: int | None
    duration_seconds: int
    description_snippet: str
    views: int
    original_view_text: str
    likes: int | None
    comment_count: int
    comments_enabled: bool
    top_comments: list[str]
    matched_keywords: list[str]
    source_keyword: str
    release_date: str
    scraped_at: str
    hours_since_upload: float
    velocity: float
    is_topic_channel: bool

    def merge_keywords(self, keywords: list[str]) -> "Video":
        """Return a new video with merged, deduplicated keywords."""
        merged = list(dict.fromkeys(self.matched_keywords + keywords))
        return Video(
            title=self.title,
            url=self.url,
            channel_name=self.channel_name,
            channel_url=self.channel_url,
            subscriber_count=self.subscriber_count,
            duration_seconds=self.duration_seconds,
            description_snippet=self.description_snippet,
            views=self.views,
            original_view_text=self.original_view_text,
            likes=self.likes,
            comment_count=self.comment_count,
            comments_enabled=self.comments_enabled,
            top_comments=self.top_comments,
            matched_keywords=merged,
            source_keyword=self.source_keyword,
            release_date=self.release_date,
            scraped_at=self.scraped_at,
            hours_since_upload=self.hours_since_upload,
            velocity=self.velocity,
            is_topic_channel=self.is_topic_channel,
        )

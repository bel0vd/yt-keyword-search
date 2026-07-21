"""CSV output, deduplication, and velocity calculation."""

import csv
import json
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from scraper.models import Video
from scraper.utils import ensure_csv_dir


CSV_COLUMNS = [
    "title",
    "url",
    "channel_name",
    "channel_url",
    "subscriber_count",
    "duration_seconds",
    "description_snippet",
    "views",
    "likes",
    "comment_count",
    "comments_enabled",
    "top_comments",
    "matched_keywords",
    "source_keyword",
    "release_date",
    "scraped_at",
    "hours_since_upload",
    "velocity",
    "is_topic_channel",
]


def deduplicate_videos(videos: list[Video]) -> list[Video]:
    """Deduplicate videos by URL, merging matched_keywords.

    The first video found for a URL is preserved as the base; additional
    keywords from later duplicates are merged into matched_keywords.
    """
    by_url: OrderedDict[str, Video] = OrderedDict()

    for video in videos:
        if video.url in by_url:
            existing = by_url[video.url]
            by_url[video.url] = existing.merge_keywords(video.matched_keywords)
        else:
            by_url[video.url] = video

    return list(by_url.values())


def sort_by_velocity(videos: list[Video]) -> list[Video]:
    """Sort videos by velocity (views per hour) in descending order."""
    return sorted(videos, key=lambda v: v.velocity, reverse=True)


def _video_to_row(video: Video) -> dict[str, str]:
    """Convert a Video dataclass into a CSV row dictionary."""
    return {
        "title": video.title,
        "url": video.url,
        "channel_name": video.channel_name,
        "channel_url": video.channel_url,
        "subscriber_count": str(video.subscriber_count)
        if video.subscriber_count is not None
        else "",
        "duration_seconds": str(video.duration_seconds),
        "description_snippet": video.description_snippet,
        "views": str(video.views),
        "likes": str(video.likes) if video.likes is not None else "",
        "comment_count": str(video.comment_count),
        "comments_enabled": str(video.comments_enabled).lower(),
        "top_comments": json.dumps(video.top_comments, ensure_ascii=False),
        "matched_keywords": json.dumps(video.matched_keywords, ensure_ascii=False),
        "source_keyword": video.source_keyword,
        "release_date": video.release_date,
        "scraped_at": video.scraped_at,
        "hours_since_upload": str(video.hours_since_upload),
        "velocity": str(video.velocity),
        "is_topic_channel": str(video.is_topic_channel).lower(),
    }


def write_csv(videos: list[Video], filename: str) -> Path:
    """Write a sorted, deduplicated video list to CSV.

    Returns the path to the written file.
    """
    path = ensure_csv_dir(filename)

    deduped = deduplicate_videos(videos)
    sorted_videos = sort_by_velocity(deduped)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for video in sorted_videos:
            writer.writerow(_video_to_row(video))

    return path


def write_csv_report(videos: list[Video], filename: str) -> tuple[Path, int]:
    """Write CSV and return (path, count)."""
    path = write_csv(videos, filename)
    return path, len(deduplicate_videos(videos))

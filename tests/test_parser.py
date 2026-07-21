"""Tests for parser.py helper functions."""

import pytest
from datetime import datetime, timezone

from scraper.parser import (
    parse_views,
    parse_subscribers,
    parse_likes,
    parse_comment_count,
    parse_duration,
    parse_upload_time,
    parse_iso_date,
    hours_since,
)


def test_parse_views():
    assert parse_views("500 views") == 500
    assert parse_views("1.2K views") == 1200
    assert parse_views("3.5M views") == 3500000
    assert parse_views("1.2B views") == 1200000000
    assert parse_views("1,234 views") == 1234
    assert parse_views("1.2K") == 1200
    assert parse_views("0 views") == 0
    assert parse_views("No views") is None
    assert parse_views("") is None


def test_parse_subscribers():
    assert parse_subscribers("1.2K subscribers") == 1200
    assert parse_subscribers("3.5M subscribers") == 3500000
    assert parse_subscribers("500") == 500
    assert parse_subscribers("") is None


def test_parse_likes():
    assert parse_likes("1.2K") == 1200
    assert parse_likes("3.5M likes") == 3500000
    assert parse_likes("500") == 500
    assert parse_likes("") is None


def test_parse_comment_count():
    assert parse_comment_count("1.2K Comments") == 1200
    assert parse_comment_count("3.5M") == 3500000
    assert parse_comment_count("500 comments") == 500
    assert parse_comment_count("") is None


def test_parse_duration():
    assert parse_duration("3:45") == 225
    assert parse_duration("1:02:30") == 3750
    assert parse_duration("0:45") == 45
    assert parse_duration("12:34") == 754
    assert parse_duration("6:00") == 360
    assert parse_duration("") is None
    assert parse_duration("not a duration") is None


def test_parse_upload_time():
    assert parse_upload_time("35 minutes ago") == 0.58
    assert parse_upload_time("5 hours ago") == 5.0
    assert parse_upload_time("1 day ago") == 24.0
    assert parse_upload_time("Streamed 5 hours ago") == 5.0
    assert parse_upload_time("Premiered 5 hours ago") == 5.0
    assert parse_upload_time("just now") == 0.0
    assert parse_upload_time("") is None


def test_parse_iso_date():
    dt = parse_iso_date("2024-01-01T12:00:00Z")
    assert dt is not None
    assert dt.year == 2024
    assert dt.hour == 12
    assert parse_iso_date("invalid") is None


def test_hours_since():
    ref = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert hours_since(ref, now) == 2.0


def test_hours_since_naive():
    ref = datetime(2024, 1, 1, 10, 0, 0)
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert hours_since(ref, now) == 2.0


def test_parse_views_no_views():
    assert parse_views("No views") is None


def test_parse_upload_time_boundary():
    assert parse_upload_time("1 hour ago") == 1.0
    assert parse_upload_time("24 hours ago") == 24.0
    assert parse_upload_time("25 hours ago") == 25.0


def test_parse_duration_hour_format():
    assert parse_duration("6:00") == 360
    assert parse_duration("6:01") == 361
    assert parse_duration("0:00") == 0


def test_parse_views_with_plus():
    assert parse_views("1.2K+") == 1200
    assert parse_views("1.2K + views") == 1200


def test_parse_comment_count_variants():
    assert parse_comment_count("Comments 1.2K") == 1200
    assert parse_comment_count("1.2K") == 1200


def test_parse_upload_time_weeks():
    assert parse_upload_time("1 week ago") == 168.0
    assert parse_upload_time("1 month ago") == 720.0


def test_parse_upload_time_streamed():
    assert parse_upload_time("Streamed 5 hours ago") == 5.0


def test_parse_upload_time_published():
    assert parse_upload_time("Published 5 hours ago") == 5.0


def test_parse_upload_time_started():
    assert parse_upload_time("Started 5 hours ago") == 5.0


def test_parse_iso_date_with_z():
    assert parse_iso_date("2024-01-01T12:00:00Z") is not None


def test_parse_iso_date_with_offset():
    assert parse_iso_date("2024-01-01T12:00:00+05:30") is not None

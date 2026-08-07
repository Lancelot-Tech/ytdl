"""Tests de la configuration applicative."""

from __future__ import annotations

from ytdl.config import AppConfig


def test_archive_path_lives_in_download_dir():
    config = AppConfig(download_dir="/tmp/out")
    assert config.archive_path() == "/tmp/out/.ytdl_archive.txt"


def test_archive_path_follows_download_dir_changes():
    config = AppConfig(download_dir="/tmp/a")
    assert config.archive_path() == "/tmp/a/.ytdl_archive.txt"
    config.download_dir = "/tmp/b"
    assert config.archive_path() == "/tmp/b/.ytdl_archive.txt"

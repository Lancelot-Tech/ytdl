"""Tests du scan de bibliothèque locale (lecteur intégré)."""

from __future__ import annotations

from pathlib import Path

from ytdl.library import Track, scan_library


def test_scan_library_filters_to_media_extensions(tmp_path: Path) -> None:
    (tmp_path / "chanson.mp3").write_bytes(b"")
    (tmp_path / "clip.mp4").write_bytes(b"")
    (tmp_path / "notes.txt").write_bytes(b"")
    (tmp_path / "cover.jpg").write_bytes(b"")

    tracks = scan_library(str(tmp_path))

    assert {t.title for t in tracks} == {"chanson", "clip"}


def test_scan_library_is_not_recursive(tmp_path: Path) -> None:
    (tmp_path / "racine.mp3").write_bytes(b"")
    sub = tmp_path / "sous-dossier"
    sub.mkdir()
    (sub / "cache.mp3").write_bytes(b"")

    tracks = scan_library(str(tmp_path))

    assert [t.title for t in tracks] == ["racine"]


def test_scan_library_sorted_case_insensitively(tmp_path: Path) -> None:
    (tmp_path / "Zebra.mp3").write_bytes(b"")
    (tmp_path / "alpha.mp3").write_bytes(b"")
    (tmp_path / "Beta.mp3").write_bytes(b"")

    tracks = scan_library(str(tmp_path))

    assert [t.title for t in tracks] == ["alpha", "Beta", "Zebra"]


def test_scan_library_missing_folder_returns_empty() -> None:
    assert scan_library("/tmp/ce-dossier-ne-devrait-pas-exister-ytdl-test") == []


def test_scan_library_flags_video_extensions(tmp_path: Path) -> None:
    (tmp_path / "audio.mp3").write_bytes(b"")
    (tmp_path / "video.mp4").write_bytes(b"")

    tracks = {t.title: t for t in scan_library(str(tmp_path))}

    assert tracks["audio"].is_video is False
    assert tracks["video"].is_video is True


def test_track_duration_str_formats_minutes_seconds() -> None:
    track = Track(path=Path("/tmp/x.mp3"), title="x", is_video=False, duration=125.7)
    assert track.duration_str == "2:05"


def test_track_duration_str_empty_when_unknown() -> None:
    track = Track(path=Path("/tmp/x.mp3"), title="x", is_video=False, duration=None)
    assert track.duration_str == ""

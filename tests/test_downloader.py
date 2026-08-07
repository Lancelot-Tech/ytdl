"""Tests du Downloader avec un yt-dlp mocké (aucun accès réseau)."""

from __future__ import annotations

import pytest

from ytdl.downloader import Downloader, DownloadError
from ytdl.models import DownloadJob, DownloadOptions, JobStatus, MediaFormat
from tests.conftest import FakeYDL, FakePlaylistYDL


def _downloader(info=None) -> Downloader:
    return Downloader(ydl_factory=lambda opts: FakeYDL(opts, info=info))


# --------------------------------------------------------------------------- #
# probe
# --------------------------------------------------------------------------- #
def test_probe_returns_media_info():
    dl = _downloader({"title": "Bonjour", "uploader": "Chaîne", "duration": 42})
    info = dl.probe("http://example.com/v")
    assert info.title == "Bonjour"
    assert info.duration == 42


def test_probe_detects_playlist(playlist_info):
    info = _downloader(playlist_info).probe("http://example.com/list")
    assert info.is_playlist
    assert len(info.entries) == 3


def test_probe_raises_download_error_on_failure():
    def boom(opts):
        raise RuntimeError("réseau coupé")

    with pytest.raises(DownloadError):
        Downloader(ydl_factory=boom).probe("http://x")


def test_probe_without_cookies_by_default():
    _downloader().probe("http://example.com/v")
    assert "cookiesfrombrowser" not in FakeYDL.last_opts


def test_probe_passes_cookies_browser_when_set():
    _downloader().probe("http://example.com/v", cookies_browser="chrome")
    assert FakeYDL.last_opts["cookiesfrombrowser"] == ("chrome",)


# --------------------------------------------------------------------------- #
# download
# --------------------------------------------------------------------------- #
def test_download_progresses_to_done():
    dl = _downloader()
    job = DownloadJob(id="1", url="http://x", options=DownloadOptions(fmt=MediaFormat.MP4))
    updates: list[float] = []
    dl.download(job, on_progress=lambda j: updates.append(j.progress))

    assert job.status == JobStatus.DONE
    assert job.progress == 100.0
    assert job.filepath.endswith(".mp4")
    # On a bien reçu une progression intermédiaire.
    assert any(0 < p < 100 for p in updates)


def test_job_starts_in_probing_before_first_real_hook():
    # Avant le premier octet, yt-dlp résout l'URL (et, avec une archive,
    # vérifie chaque piste déjà connue) sans appeler le moindre hook — sur
    # une grosse playlist reprise, ça peut prendre un moment. Le job doit
    # refléter cette phase plutôt que d'afficher "Téléchargement" alors que
    # rien n'a encore commencé.
    dl = _downloader()
    job = DownloadJob(id="1", url="http://x", options=DownloadOptions())
    statuses: list[JobStatus] = []
    dl.download(job, on_progress=lambda j: statuses.append(j.status))
    assert statuses[0] == JobStatus.PROBING
    assert job.status == JobStatus.DONE


def test_download_sets_speed_and_eta_during_transfer():
    dl = _downloader()
    seen = {}
    job = DownloadJob(id="1", url="http://x", options=DownloadOptions())

    def on_progress(j: DownloadJob) -> None:
        if j.status == JobStatus.DOWNLOADING and j.speed:
            seen["speed"] = j.speed
            seen["speed_bps"] = j.speed_bps
            seen["eta"] = j.eta

    dl.download(job, on_progress=on_progress)
    assert seen.get("speed") == "1.0MiB/s"
    assert seen.get("speed_bps") == 1048576.0
    # Une fois le téléchargement fini (post-traitement), plus de vitesse à afficher.
    assert job.speed_bps == 0.0


# --------------------------------------------------------------------------- #
# download — playlists (suivi par piste)
# --------------------------------------------------------------------------- #
def test_playlist_download_tracks_each_entry():
    dl = Downloader(ydl_factory=lambda opts: FakePlaylistYDL(opts, titles=("A", "B", "C")))
    job = DownloadJob(
        id="1", url="http://x", options=DownloadOptions(fmt=MediaFormat.MP3, is_playlist=True)
    )
    dl.download(job)

    assert job.status == JobStatus.DONE
    assert job.playlist_total == 3
    assert job.playlist_completed == 3
    assert [e.title for e in job.playlist_entries] == ["A", "B", "C"]
    assert all(e.status == JobStatus.DONE for e in job.playlist_entries)
    assert job.playlist_entries[0].filepath == "/tmp/A.mp3"


def test_playlist_progress_reflects_completed_tracks_not_stuck_at_100():
    dl = Downloader(ydl_factory=lambda opts: FakePlaylistYDL(opts, titles=("A", "B", "C")))
    job = DownloadJob(id="1", url="http://x", options=DownloadOptions(is_playlist=True))
    progress_seen: list[float] = []
    dl.download(job, on_progress=lambda j: progress_seen.append(j.progress))

    # La progression doit avancer par paliers (1/3, 2/3, 3/3), jamais se
    # figer à 100% avant que toutes les pistes ne soient terminées.
    assert any(abs(p - 100 / 3) < 0.1 for p in progress_seen)
    assert any(abs(p - 200 / 3) < 0.1 for p in progress_seen)
    assert progress_seen[-1] == 100.0


def test_playlist_entry_shows_processing_stage_before_move_files():
    dl = Downloader(ydl_factory=lambda opts: FakePlaylistYDL(opts, titles=("A",)))
    job = DownloadJob(
        id="1", url="http://x", options=DownloadOptions(fmt=MediaFormat.MP3, is_playlist=True)
    )
    seen_statuses: list[JobStatus] = []
    seen_stages: list[str] = []

    def on_progress(j: DownloadJob) -> None:
        if j.playlist_entries:
            seen_statuses.append(j.playlist_entries[0].status)
            seen_stages.append(j.playlist_entries[0].stage)

    dl.download(job, on_progress=on_progress)

    # La piste passe par DOWNLOADING puis PROCESSING (avec un libellé) avant
    # d'atteindre DONE — jamais DONE directement après le téléchargement brut.
    assert JobStatus.DOWNLOADING in seen_statuses
    assert JobStatus.PROCESSING in seen_statuses
    processing_idx = seen_statuses.index(JobStatus.PROCESSING)
    assert seen_stages[processing_idx] != ""
    assert job.playlist_entries[0].status == JobStatus.DONE
    assert job.playlist_entries[0].stage == ""


def test_non_playlist_job_has_no_playlist_entries():
    dl = _downloader()
    job = DownloadJob(id="1", url="http://x", options=DownloadOptions(is_playlist=False))
    dl.download(job)
    assert job.playlist_entries == []
    assert job.playlist_total == 0


def test_download_error_marks_job_and_raises():
    def factory(opts):
        class Boom(FakeYDL):
            def extract_info(self, url, download=False):
                raise RuntimeError("format indisponible")

        return Boom(opts)

    dl = Downloader(ydl_factory=factory)
    job = DownloadJob(id="1", url="http://x", options=DownloadOptions())
    with pytest.raises(DownloadError):
        dl.download(job)
    assert job.status == JobStatus.ERROR
    assert "format indisponible" in job.error

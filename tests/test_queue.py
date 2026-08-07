"""Tests de la file d'attente : ajout, progression, annulation, callbacks."""

from __future__ import annotations

import threading
import time

from ytdl.downloader import Downloader
from ytdl.models import DownloadOptions, JobStatus, MediaFormat, SpotifyDownloadOptions
from ytdl.queue import DownloadQueue
from tests.conftest import BlockingFakeYDL, FakeYDL, FlakyFakeYDL


def _queue(max_concurrent: int = 2) -> DownloadQueue:
    downloader = Downloader(ydl_factory=lambda opts: FakeYDL(opts))
    return DownloadQueue(downloader=downloader, max_concurrent=max_concurrent)


def _wait(predicate, timeout: float = 3.0) -> None:
    """Attend qu'une condition devienne vraie (jobs exécutés en threads)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Condition non atteinte dans le délai imparti.")


def test_add_creates_job_and_completes():
    q = _queue()
    try:
        job = q.add("http://x", DownloadOptions(fmt=MediaFormat.MP4), title="Ma vidéo")
        assert job.title == "Ma vidéo"
        _wait(lambda: q.get(job.id).status == JobStatus.DONE)
        assert q.get(job.id).progress == 100.0
    finally:
        q.shutdown()


def test_spotify_job_is_routed_to_spotify_backend_not_ytdlp():
    calls = {"ytdlp": 0, "spotify": 0}

    class FakeDownloader(Downloader):
        def download(self, job, on_progress=None):
            calls["ytdlp"] += 1
            job.status = JobStatus.DONE
            job.progress = 100.0
            return job

    class FakeSpotifyBackend:
        def download(self, job, on_progress=None):
            calls["spotify"] += 1
            job.status = JobStatus.DONE
            job.progress = 100.0
            return job

    q = DownloadQueue(downloader=FakeDownloader(), spotify_downloader=FakeSpotifyBackend(), max_concurrent=1)
    try:
        job = q.add("http://open.spotify.com/track/x", SpotifyDownloadOptions(), title="Un titre")
        _wait(lambda: q.get(job.id).status == JobStatus.DONE)
        assert calls == {"ytdlp": 0, "spotify": 1}
    finally:
        q.shutdown()


def test_subscribe_receives_notifications():
    q = _queue()
    calls = {"n": 0}
    q.subscribe(lambda: calls.__setitem__("n", calls["n"] + 1))
    try:
        job = q.add("http://x", DownloadOptions())
        _wait(lambda: q.get(job.id).status == JobStatus.DONE)
        assert calls["n"] > 0
    finally:
        q.shutdown()


def test_clear_finished_removes_terminal_jobs():
    q = _queue()
    try:
        job = q.add("http://x", DownloadOptions())
        _wait(lambda: q.get(job.id).status.is_terminal)
        q.clear_finished()
        assert q.jobs == []
    finally:
        q.shutdown()


def test_cancel_unknown_job_returns_false():
    q = _queue()
    try:
        assert q.cancel("inexistant") is False
    finally:
        q.shutdown()


def test_ids_are_unique_and_incrementing():
    q = _queue()
    try:
        a = q.add("http://a", DownloadOptions())
        b = q.add("http://b", DownloadOptions())
        assert a.id != b.id
    finally:
        q.shutdown()


def test_set_max_concurrent_updates_without_restart():
    q = _queue(max_concurrent=2)
    try:
        assert q.max_concurrent == 2
        q.set_max_concurrent(5)
        assert q.max_concurrent == 5

        # La file reste utilisable : les jobs soumis après le changement
        # s'exécutent bien sur le nouveau pool.
        job = q.add("http://x", DownloadOptions())
        _wait(lambda: q.get(job.id).status == JobStatus.DONE)
    finally:
        q.shutdown()


def test_set_max_concurrent_noop_when_unchanged():
    q = _queue(max_concurrent=3)
    try:
        executor_before = q._executor  # noqa: SLF001 - vérifie l'absence de recréation inutile
        q.set_max_concurrent(3)
        assert q._executor is executor_before  # noqa: SLF001
    finally:
        q.shutdown()


def test_jobs_in_flight_survive_concurrency_change():
    q = _queue(max_concurrent=1)
    try:
        job1 = q.add("http://a", DownloadOptions())
        job2 = q.add("http://b", DownloadOptions())
        q.set_max_concurrent(4)
        _wait(lambda: q.get(job1.id).status == JobStatus.DONE)
        _wait(lambda: q.get(job2.id).status == JobStatus.DONE)
    finally:
        q.shutdown()


# --------------------------------------------------------------------------- #
# Annulation/pause d'un job réellement en cours (état intermédiaire immédiat)
# --------------------------------------------------------------------------- #
def _blocking_queue(max_concurrent: int = 2) -> tuple[DownloadQueue, threading.Event, threading.Event]:
    ready = threading.Event()
    resume_signal = threading.Event()
    downloader = Downloader(ydl_factory=lambda opts: BlockingFakeYDL(opts, ready, resume_signal))
    return DownloadQueue(downloader=downloader, max_concurrent=max_concurrent), ready, resume_signal


def test_cancel_running_job_shows_cancelling_immediately_then_cancelled():
    q, ready, resume_signal = _blocking_queue()
    try:
        job = q.add("http://x", DownloadOptions())
        assert ready.wait(timeout=3)

        assert q.cancel(job.id) is True
        # Retour immédiat, avant même que le thread n'ait pu s'arrêter : c'est
        # ce qui manquait pour que le bouton "Annuler" réponde tout de suite.
        assert q.get(job.id).status == JobStatus.CANCELLING

        resume_signal.set()
        _wait(lambda: q.get(job.id).status == JobStatus.CANCELLED)
    finally:
        q.shutdown()


def test_cancel_paused_job_is_immediate_no_active_thread():
    q, ready, resume_signal = _blocking_queue()
    try:
        job = q.add("http://x", DownloadOptions())
        assert ready.wait(timeout=3)
        assert q.pause(job.id) is True
        resume_signal.set()
        _wait(lambda: q.get(job.id).status == JobStatus.PAUSED)

        assert q.cancel(job.id) is True
        assert q.get(job.id).status == JobStatus.CANCELLED
    finally:
        q.shutdown()


def test_pause_then_resume_completes():
    q, ready, resume_signal = _blocking_queue()
    try:
        job = q.add("http://x", DownloadOptions())
        assert ready.wait(timeout=3)

        assert q.pause(job.id) is True
        assert q.get(job.id).status == JobStatus.PAUSING
        resume_signal.set()
        _wait(lambda: q.get(job.id).status == JobStatus.PAUSED)
        assert not q.get(job.id).status.is_terminal  # reste dans la file, reprenable

        assert q.resume(job.id) is True
        _wait(lambda: q.get(job.id).status == JobStatus.DONE)
    finally:
        q.shutdown()


def test_pause_unknown_or_inactive_job_returns_false():
    q = _queue()
    try:
        assert q.pause("inexistant") is False
        job = q.add("http://x", DownloadOptions())
        _wait(lambda: q.get(job.id).status == JobStatus.DONE)
        assert q.pause(job.id) is False  # déjà terminé, rien à mettre en pause
    finally:
        q.shutdown()


def test_restart_reruns_a_failed_job():
    attempts: list[int] = []
    downloader = Downloader(ydl_factory=lambda opts: FlakyFakeYDL(opts, attempts))
    q = DownloadQueue(downloader=downloader, max_concurrent=2)
    try:
        job = q.add("http://x", DownloadOptions())
        _wait(lambda: q.get(job.id).status == JobStatus.ERROR)

        assert q.restart(job.id) is True
        _wait(lambda: q.get(job.id).status == JobStatus.DONE)
        assert len(attempts) == 2
        assert q.get(job.id).error == ""
    finally:
        q.shutdown()


def test_restart_refuses_active_or_done_job():
    q = _queue()
    try:
        job = q.add("http://x", DownloadOptions())
        assert q.restart(job.id) is False  # encore actif
        _wait(lambda: q.get(job.id).status == JobStatus.DONE)
        assert q.restart(job.id) is False  # terminé avec succès, rien à relancer
    finally:
        q.shutdown()

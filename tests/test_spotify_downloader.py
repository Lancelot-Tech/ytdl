"""Tests du SpotifyDownloader avec un ``spotdl`` mocké (aucun accès réseau)."""

from __future__ import annotations

import json
from typing import Any, Optional

import pytest

from ytdl.downloader import DownloadError
from ytdl.models import DownloadJob, JobStatus, SpotifyDownloadOptions
from ytdl.spotify_downloader import CancelToken, ProbeCancelled, SpotifyDownloader

SINGLE_SONG = [
    {"name": "Choosin' Texas", "artist": "Ella Langley", "cover_url": "http://img", "duration": 232},
]

PLAYLIST_SONGS = [
    {"name": "Song A", "artist": "Artist 1", "list_name": "My Playlist", "cover_url": "http://img"},
    {"name": "Song B", "artist": "Artist 2", "list_name": "My Playlist", "cover_url": "http://img"},
]


class FakeStdout:
    """Imite un flux ``stdout`` de sous-processus : itérable de lignes + ``close()``."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self.closed = False

    def __iter__(self):
        return iter(self._lines)

    def close(self) -> None:
        self.closed = True


class FakePopen:
    """Imite un ``Popen`` — sert à la fois pour ``download`` (lignes de
    ``stdout`` + ``wait()``) et pour ``save`` (``communicate()``)."""

    def __init__(
        self,
        lines: Optional[list[str]] = None,
        returncode: int = 0,
        save_stdout: str = "",
        save_stderr: str = "",
    ) -> None:
        self.stdout = FakeStdout(lines or [])
        self.returncode = returncode
        self._save_stdout = save_stdout
        self._save_stderr = save_stderr
        self.terminated = False
        self.killed = False

    def wait(self, timeout: Optional[float] = None) -> int:
        return self.returncode

    def communicate(self, timeout: Optional[float] = None) -> tuple[str, str]:
        return self._save_stdout, self._save_stderr

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


class CancellingFakePopen(FakePopen):
    """Simule une annulation demandée *pendant* que ``communicate()`` tourne
    (depuis un autre thread, dans le vrai code) : appelle elle-même
    ``cancel_token.cancel()`` avant de renvoyer une sortie par ailleurs valide."""

    def __init__(self, cancel_token: CancelToken, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._cancel_token = cancel_token

    def communicate(self, timeout: Optional[float] = None) -> tuple[str, str]:
        self._cancel_token.cancel()
        return super().communicate(timeout)


def _downloader(
    songs: list[dict[str, Any]] = SINGLE_SONG,
    popen_lines: Optional[list[str]] = None,
    popen_returncode: int = 0,
    save_returncode: int = 0,
    save_stderr: str = "",
    exe: Optional[str] = "/usr/bin/spotdl",
) -> tuple[SpotifyDownloader, list[FakePopen]]:
    created_popens: list[FakePopen] = []

    def popen_fn(args: list[str], **kwargs: Any) -> FakePopen:
        if "save" in args:
            stdout = "" if save_returncode != 0 else json.dumps(songs)
            popen = FakePopen(returncode=save_returncode, save_stdout=stdout, save_stderr=save_stderr)
        else:
            popen = FakePopen(popen_lines or [], returncode=popen_returncode)
        created_popens.append(popen)
        return popen

    dl = SpotifyDownloader(spotdl_path_fn=lambda: exe, popen_fn=popen_fn)
    return dl, created_popens


# --------------------------------------------------------------------------- #
# probe
# --------------------------------------------------------------------------- #
def test_probe_returns_media_info_for_single_track():
    dl, _ = _downloader(songs=SINGLE_SONG)
    info = dl.probe("http://open.spotify.com/track/x")
    assert info.title == "Choosin' Texas"
    assert info.uploader == "Ella Langley"
    assert info.duration == 232
    assert not info.is_playlist


def test_probe_detects_playlist():
    dl, _ = _downloader(songs=PLAYLIST_SONGS)
    info = dl.probe("http://open.spotify.com/playlist/x")
    assert info.is_playlist
    assert info.title == "My Playlist"
    assert len(info.entries) == 2


def test_probe_raises_download_error_on_failure():
    dl, _ = _downloader(save_returncode=1, save_stderr="réseau coupé")
    with pytest.raises(DownloadError):
        dl.probe("http://x")


def test_probe_raises_when_spotdl_missing():
    dl, _ = _downloader(exe=None)
    with pytest.raises(DownloadError):
        dl.probe("http://x")


# --------------------------------------------------------------------------- #
# probe — annulation
# --------------------------------------------------------------------------- #
def test_probe_cancelled_before_start_terminates_immediately():
    created: list[FakePopen] = []

    def popen_fn(args: list[str], **kwargs: Any) -> FakePopen:
        popen = FakePopen(save_stdout=json.dumps(SINGLE_SONG))
        created.append(popen)
        return popen

    dl = SpotifyDownloader(spotdl_path_fn=lambda: "/usr/bin/spotdl", popen_fn=popen_fn)
    token = CancelToken()
    token.cancel()  # annulé avant même que le sous-processus existe

    with pytest.raises(ProbeCancelled):
        dl.probe("http://x", cancel_token=token)
    assert created[0].terminated is True


def test_probe_cancelled_mid_flight_raises_probe_cancelled():
    token = CancelToken()
    created: list[CancellingFakePopen] = []

    def popen_fn(args: list[str], **kwargs: Any) -> CancellingFakePopen:
        popen = CancellingFakePopen(token, save_stdout=json.dumps(SINGLE_SONG))
        created.append(popen)
        return popen

    dl = SpotifyDownloader(spotdl_path_fn=lambda: "/usr/bin/spotdl", popen_fn=popen_fn)
    with pytest.raises(ProbeCancelled):
        dl.probe("http://x", cancel_token=token)
    assert created[0].terminated is True


# --------------------------------------------------------------------------- #
# download — titre unique
# --------------------------------------------------------------------------- #
def test_download_single_track_progresses_to_done():
    lines = [
        "Ella Langley - Choosin' Texas: Searching for song\n",
        "Ella Langley - Choosin' Texas: Getting audio meta\n",
        "Ella Langley - Choosin' Texas: Downloading\n",
        "Ella Langley - Choosin' Texas: Embedding metadata\n",
        "Ella Langley - Choosin' Texas: Done\n",
        "1/1 complete\n",
    ]
    dl, popens = _downloader(songs=SINGLE_SONG, popen_lines=lines)
    job = DownloadJob(id="1", url="http://x", options=SpotifyDownloadOptions())
    progress_seen: list[float] = []
    dl.download(job, on_progress=lambda j: progress_seen.append(j.progress))

    assert job.status == JobStatus.DONE
    assert job.progress == 100.0
    assert any(0 < p < 100 for p in progress_seen)
    assert popens[0].terminated is False


def test_download_error_when_process_fails_without_any_track():
    dl, _ = _downloader(songs=SINGLE_SONG, popen_lines=[], popen_returncode=1)
    job = DownloadJob(id="1", url="http://x", options=SpotifyDownloadOptions())
    with pytest.raises(DownloadError):
        dl.download(job)
    assert job.status == JobStatus.ERROR


# --------------------------------------------------------------------------- #
# download — playlists (suivi par piste)
# --------------------------------------------------------------------------- #
def test_playlist_download_tracks_each_entry():
    lines = [
        "Artist 1 - Song A: Searching for song\n",
        "Artist 1 - Song A: Downloading\n",
        "Artist 1 - Song A: Done\n",
        "Artist 2 - Song B: Searching for song\n",
        "Artist 2 - Song B: Downloading\n",
        "Artist 2 - Song B: Done\n",
        "2/2 complete\n",
    ]
    dl, _ = _downloader(songs=PLAYLIST_SONGS, popen_lines=lines)
    job = DownloadJob(id="1", url="http://x", options=SpotifyDownloadOptions(is_playlist=True))
    dl.download(job)

    assert job.status == JobStatus.DONE
    assert job.playlist_total == 2
    assert job.playlist_completed == 2
    assert [e.title for e in job.playlist_entries] == ["Artist 1 - Song A", "Artist 2 - Song B"]
    assert all(e.status == JobStatus.DONE for e in job.playlist_entries)


def test_playlist_entry_marked_error_does_not_block_others():
    lines = [
        "Artist 1 - Song A: Searching for song\n",
        "Artist 1 - Song A: Error\n",
        "Artist 2 - Song B: Searching for song\n",
        "Artist 2 - Song B: Downloading\n",
        "Artist 2 - Song B: Done\n",
        "2/2 complete\n",
    ]
    dl, _ = _downloader(songs=PLAYLIST_SONGS, popen_lines=lines)
    job = DownloadJob(id="1", url="http://x", options=SpotifyDownloadOptions(is_playlist=True))
    dl.download(job)

    entry_a = job.playlist_entries[0]
    entry_b = job.playlist_entries[1]
    assert entry_a.status == JobStatus.ERROR
    assert entry_b.status == JobStatus.DONE
    # Une piste en échec ne bloque pas les autres ni le statut final du job.
    assert job.status == JobStatus.DONE
    assert job.playlist_completed == 1


def test_non_playlist_job_has_no_playlist_entries():
    lines = ["Ella Langley - Choosin' Texas: Done\n"]
    dl, _ = _downloader(songs=SINGLE_SONG, popen_lines=lines)
    job = DownloadJob(id="1", url="http://x", options=SpotifyDownloadOptions(is_playlist=False))
    dl.download(job)
    assert job.playlist_entries == []
    assert job.playlist_total == 0


def test_playlist_tracks_from_preview_avoid_a_second_save_call():
    # ``download`` ne doit jamais rappeler ``save`` : la liste de pistes vient
    # de l'aperçu (``playlist_tracks``), déjà connue avant même de démarrer le
    # téléchargement — refaire cette analyse (lente, ~2s/piste) doublerait
    # l'attente pour rien sur une grosse playlist.
    lines = [
        "Artist 1 - Song A: Searching for song\n",
        "Artist 1 - Song A: Done\n",
        "Artist 2 - Song B: Searching for song\n",
        "Artist 2 - Song B: Done\n",
        "2/2 complete\n",
    ]

    def popen_fn(args: list[str], **kwargs: Any) -> FakePopen:
        assert "save" not in args, "save ne doit pas être rappelé pendant download()"
        return FakePopen(lines, returncode=0)

    dl = SpotifyDownloader(spotdl_path_fn=lambda: "/usr/bin/spotdl", popen_fn=popen_fn)
    options = SpotifyDownloadOptions(is_playlist=True, playlist_tracks=["Artist 1 - Song A", "Artist 2 - Song B"])
    job = DownloadJob(id="1", url="http://x", options=options)

    totals_seen: list[int] = []
    dl.download(job, on_progress=lambda j: totals_seen.append(j.playlist_total))

    # Le total est connu dès le tout premier appel (avant la moindre ligne de
    # progression), puisqu'il vient de ``playlist_tracks`` et non d'une ligne
    # "N/M complete" apprise au fil de l'eau.
    assert totals_seen[0] == 2
    assert job.status == JobStatus.DONE
    assert job.playlist_completed == 2


# --------------------------------------------------------------------------- #
# download — annulation coopérative
# --------------------------------------------------------------------------- #
def test_cancel_terminates_subprocess():
    lines = [
        "Ella Langley - Choosin' Texas: Searching for song\n",
        "Ella Langley - Choosin' Texas: Downloading\n",
        "Ella Langley - Choosin' Texas: Done\n",
    ]
    dl, popens = _downloader(songs=SINGLE_SONG, popen_lines=lines)
    job = DownloadJob(id="1", url="http://x", options=SpotifyDownloadOptions())

    def on_progress(j: DownloadJob) -> None:
        # Ignore le premier signal DOWNLOADING (avant même le lancement du
        # sous-processus) : on veut annuler une fois le téléchargement
        # réellement démarré (une ligne de progression déjà lue).
        if j.status == JobStatus.DOWNLOADING and j.progress > 0:
            raise KeyboardInterrupt("annulé par l'utilisateur")

    with pytest.raises(KeyboardInterrupt):
        dl.download(job, on_progress=on_progress)

    assert popens[0].terminated is True

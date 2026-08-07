"""Fixtures partagées : faux yt-dlp et données d'exemple (aucun accès réseau)."""

from __future__ import annotations

import threading
from typing import Any

import pytest


class FakeYDL:
    """Imitation minimale de ``yt_dlp.YoutubeDL`` pour les tests.

    Enregistre les options reçues, renvoie une info préprogrammée et joue une
    petite séquence de ``progress_hooks`` lors d'un « téléchargement ».
    """

    #: Dernier jeu d'options passé au constructeur (pratique pour les assertions).
    last_opts: dict[str, Any] | None = None

    def __init__(self, opts: dict[str, Any], info: dict[str, Any] | None = None) -> None:
        self.opts = opts
        FakeYDL.last_opts = opts
        self._info = info or {"title": "Vidéo de test", "uploader": "Chaîne", "duration": 65}
        self.downloaded = False

    def __enter__(self) -> "FakeYDL":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
        info = dict(self._info)
        info.setdefault("webpage_url", url)
        if download:
            self.downloaded = True
            for hook in self.opts.get("progress_hooks", []):
                hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100,
                      "speed": 1048576.0, "_speed_str": "1.0MiB/s", "_eta_str": "00:05"})
                hook({"status": "downloading", "downloaded_bytes": 100, "total_bytes": 100,
                      "speed": 1048576.0, "_speed_str": "1.0MiB/s", "_eta_str": "00:00"})
                hook({"status": "finished", "downloaded_bytes": 100, "total_bytes": 100})
            info["requested_downloads"] = [{"filepath": "/tmp/Vidéo de test.mp4"}]
        return info

    def prepare_filename(self, info: dict[str, Any]) -> str:
        return "/tmp/" + info.get("title", "out")


class BlockingFakeYDL:
    """Imitation de yt-dlp dont le "téléchargement" attend un signal externe.

    Sert à tester l'annulation/la pause d'un job réellement en cours (donc
    entre deux hooks), sans dépendre du timing : le test attend ``ready``
    (premier hook envoyé, le job est bien "actif") avant d'agir, puis
    débloque via ``resume_signal`` pour laisser le second hook s'exécuter
    (c'est là que l'annulation/la pause coopérative se déclenche).
    """

    def __init__(self, opts: dict[str, Any], ready: threading.Event, resume_signal: threading.Event) -> None:
        self.opts = opts
        self._ready = ready
        self._resume_signal = resume_signal

    def __enter__(self) -> "BlockingFakeYDL":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
        info: dict[str, Any] = {"title": "Vidéo bloquante"}
        if download:
            for hook in self.opts.get("progress_hooks", []):
                hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100,
                      "_speed_str": "1.0MiB/s", "_eta_str": "00:05"})
                self._ready.set()
                self._resume_signal.wait(timeout=5)
                hook({"status": "downloading", "downloaded_bytes": 100, "total_bytes": 100,
                      "_speed_str": "1.0MiB/s", "_eta_str": "00:00"})
                hook({"status": "finished", "downloaded_bytes": 100, "total_bytes": 100})
            info["requested_downloads"] = [{"filepath": "/tmp/Vidéo bloquante.mp4"}]
        return info

    def prepare_filename(self, info: dict[str, Any]) -> str:
        return "/tmp/" + info.get("title", "out")


class FlakyFakeYDL(FakeYDL):
    """Échoue au premier appel, réussit ensuite — pour tester ``restart()``."""

    def __init__(self, opts: dict[str, Any], attempts: list[int]) -> None:
        super().__init__(opts)
        self._attempts = attempts

    def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
        self._attempts.append(1)
        if len(self._attempts) == 1:
            raise RuntimeError("échec temporaire")
        return super().extract_info(url, download=download)


class FakePlaylistYDL:
    """Imitation de yt-dlp pour un téléchargement de playlist (plusieurs pistes).

    Rejoue, pour chaque piste, la séquence de hooks ``downloading``/``finished``
    avec un ``info_dict`` incluant ``playlist_index``/``n_entries``/``title``,
    comme le fait réellement yt-dlp lors du téléchargement d'une playlist.
    """

    def __init__(self, opts: dict[str, Any], titles: tuple[str, ...] = ("Piste 1", "Piste 2", "Piste 3")) -> None:
        self.opts = opts
        self.titles = titles

    def __enter__(self) -> "FakePlaylistYDL":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
        n = len(self.titles)
        if download:
            progress_hooks = self.opts.get("progress_hooks", [])
            pp_hooks = self.opts.get("postprocessor_hooks", [])
            for i, title in enumerate(self.titles, start=1):
                info_dict = {"playlist_index": i, "n_entries": n, "title": title}
                # Comme le vrai yt-dlp : le hook de téléchargement brut voit le
                # fichier avant conversion (.webm), le hook de post-traitement
                # voit le fichier final une fois converti (.mp3) — vérifié
                # empiriquement contre un vrai téléchargement.
                raw_filename = f"/tmp/{title}.webm"
                final_filepath = f"/tmp/{title}.mp3"
                for hook in progress_hooks:
                    hook({
                        "status": "downloading", "downloaded_bytes": 50, "total_bytes": 100,
                        "info_dict": info_dict, "filename": raw_filename,
                        "_speed_str": "1.0MiB/s", "_eta_str": "00:02",
                    })
                    hook({
                        "status": "finished", "downloaded_bytes": 100, "total_bytes": 100,
                        "info_dict": info_dict, "filename": raw_filename,
                    })
                # yt-dlp exécute toujours un déplacement final ("MoveFiles"),
                # avec ou sans post-traitement explicite (conversion, etc.).
                pp_info_dict = {**info_dict, "filepath": final_filepath}
                for pp_hook in pp_hooks:
                    pp_hook({"status": "started", "postprocessor": "MoveFiles", "info_dict": pp_info_dict})
                    pp_hook({"status": "finished", "postprocessor": "MoveFiles", "info_dict": pp_info_dict})
        return {"_type": "playlist", "title": "Ma playlist", "entries": [{"title": t} for t in self.titles]}

    def prepare_filename(self, info: dict[str, Any]) -> str:
        return "/tmp/playlist"


@pytest.fixture
def fake_playlist_ydl_factory():
    """Fabrique de ``FakePlaylistYDL``, utilisable comme ``ydl_factory``."""

    def factory(opts: dict[str, Any]):
        return FakePlaylistYDL(opts)

    return factory


@pytest.fixture
def fake_ydl_factory():
    """Fabrique de ``FakeYDL`` capturant les options, utilisable comme ``ydl_factory``."""

    def factory(opts: dict[str, Any]):
        return FakeYDL(opts)

    return factory


@pytest.fixture
def playlist_info() -> dict[str, Any]:
    """Info yt-dlp représentant une playlist de trois éléments."""
    return {
        "_type": "playlist",
        "title": "Ma playlist",
        "entries": [
            {"title": "Piste 1"},
            {"title": "Piste 2"},
            {"title": "Piste 3"},
        ],
    }

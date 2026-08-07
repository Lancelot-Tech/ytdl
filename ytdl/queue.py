"""File d'attente de téléchargements (multi-threads).

``yt-dlp`` étant bloquant, chaque job s'exécute dans un worker d'un
``ThreadPoolExecutor``. L'UI n'appelle jamais directement le ``Downloader`` :
elle passe par :class:`DownloadQueue` et lit l'état des jobs via un timer.
"""

from __future__ import annotations

import itertools
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Optional

from .downloader import Downloader
from .models import DownloadJob, DownloadOptionsLike, JobStatus, SpotifyDownloadOptions
from .spotify_downloader import SpotifyDownloader

# Callback appelé chaque fois que l'état de la file change (ajout, progression, fin).
ChangeCallback = Callable[[], None]


class DownloadQueue:
    """Orchestre plusieurs :class:`DownloadJob` en parallèle.

    Thread-safe pour les opérations d'ajout/annulation/lecture. Les callbacks
    ``on_change`` sont invoqués depuis les threads workers : côté NiceGUI, on se
    contente de lire l'état via un ``ui.timer`` plutôt que de manipuler l'UI ici.
    """

    def __init__(
        self,
        downloader: Optional[Downloader] = None,
        spotify_downloader: Optional[SpotifyDownloader] = None,
        max_concurrent: int = 2,
    ) -> None:
        """
        Args:
            downloader: Instance de :class:`Downloader` (injectable pour les tests).
            spotify_downloader: Instance de :class:`SpotifyDownloader` (injectable
                pour les tests), utilisée pour les jobs dont ``options`` est un
                :class:`~ytdl.models.SpotifyDownloadOptions` (voir :meth:`_backend_for`).
            max_concurrent: Nombre de téléchargements simultanés.
        """
        self._downloader = downloader or Downloader()
        self._spotify_downloader = spotify_downloader or SpotifyDownloader()
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent)
        self._max_concurrent = max_concurrent
        self._jobs: list[DownloadJob] = []
        self._futures: dict[str, Future] = {}
        self._cancelled: set[str] = set()
        self._paused: set[str] = set()
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._on_change: list[ChangeCallback] = []

    # ------------------------------------------------------------------ #
    # Réglages à chaud
    # ------------------------------------------------------------------ #
    @property
    def max_concurrent(self) -> int:
        """Nombre de téléchargements simultanés actuellement configuré."""
        return self._max_concurrent

    def set_max_concurrent(self, max_concurrent: int) -> None:
        """Change le nombre de téléchargements simultanés, sans redémarrage.

        Remplace le pool de threads par un nouveau, dimensionné différemment ;
        les jobs déjà en cours sur l'ancien pool se terminent normalement (on
        ne les interrompt pas), seuls les *nouveaux* jobs utilisent le nouveau
        pool. ``shutdown(wait=False)`` ne bloque pas et laisse l'ancien pool
        s'éteindre proprement une fois ses tâches en cours terminées.
        """
        if max_concurrent == self._max_concurrent:
            return
        with self._lock:
            old_executor = self._executor
            self._executor = ThreadPoolExecutor(max_workers=max_concurrent)
            self._max_concurrent = max_concurrent
        old_executor.shutdown(wait=False)

    # ------------------------------------------------------------------ #
    # Observateurs
    # ------------------------------------------------------------------ #
    def subscribe(self, callback: ChangeCallback) -> None:
        """Enregistre un callback appelé à chaque changement d'état."""
        self._on_change.append(callback)

    def _notify(self) -> None:
        for cb in list(self._on_change):
            try:
                cb()
            except Exception:  # pragma: no cover - un observateur ne doit pas casser la file
                pass

    # ------------------------------------------------------------------ #
    # Lecture
    # ------------------------------------------------------------------ #
    @property
    def jobs(self) -> list[DownloadJob]:
        """Copie de la liste des jobs (ordre d'ajout)."""
        with self._lock:
            return list(self._jobs)

    def get(self, job_id: str) -> Optional[DownloadJob]:
        """Renvoie le job d'identifiant donné, ou ``None``."""
        with self._lock:
            return next((j for j in self._jobs if j.id == job_id), None)

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    def add(self, url: str, options: DownloadOptionsLike, title: str = "") -> DownloadJob:
        """Crée un job et le planifie pour téléchargement.

        Args:
            url: URL source.
            options: Options de téléchargement.
            title: Titre pré-rempli (issu du probe), facultatif.

        Returns:
            Le job créé (déjà soumis au pool).
        """
        job = DownloadJob(id=str(next(self._ids)), url=url, options=options, title=title)
        with self._lock:
            self._jobs.append(job)
            self._submit(job)
        self._notify()
        return job

    def _submit(self, job: DownloadJob) -> None:
        """Soumet (ou resoumet) un job au pool. Appelant : tenir ``_lock``."""
        future = self._executor.submit(self._run, job)
        self._futures[job.id] = future

    def cancel(self, job_id: str) -> bool:
        """Demande l'annulation d'un job.

        Un job encore en attente (jamais démarré) ou déjà en pause (aucun
        thread actif) est annulé immédiatement. Un job réellement en cours
        d'exécution ne peut être interrompu qu'à son prochain point de
        contrôle coopératif (un hook yt-dlp) : il passe par un état
        intermédiaire ``CANCELLING`` — sans lui, l'UI ne change pas pendant
        ce court délai et l'utilisateur a l'impression que le bouton ne fait
        rien.

        Returns:
            ``True`` si l'annulation a été prise en compte.
        """
        with self._lock:
            job = next((j for j in self._jobs if j.id == job_id), None)
            if job is None or job.status.is_terminal:
                return False
            self._paused.discard(job_id)
            self._cancelled.add(job_id)
            future = self._futures.get(job_id)
            if (future is not None and future.cancel()) or not job.is_active:
                # Jamais démarré, ou déjà arrêté (en pause) : pas de thread à
                # interrompre, on peut trancher tout de suite.
                job.status = JobStatus.CANCELLED
            else:
                job.status = JobStatus.CANCELLING
        self._notify()
        return True

    def pause(self, job_id: str) -> bool:
        """Demande la mise en pause d'un job en cours.

        Même logique d'état intermédiaire que :meth:`cancel` (``PAUSING``
        avant ``PAUSED``) : l'arrêt réel n'a lieu qu'au prochain hook yt-dlp.

        Returns:
            ``True`` si la demande a été prise en compte (job réellement actif).
        """
        with self._lock:
            job = next((j for j in self._jobs if j.id == job_id), None)
            if job is None or not job.is_active:
                return False
            self._paused.add(job_id)
            job.status = JobStatus.PAUSING
        self._notify()
        return True

    def resume(self, job_id: str) -> bool:
        """Reprend un job en pause.

        S'appuie sur la reprise partielle native de yt-dlp (fichier ``.part``
        déjà sur disque) pour la piste interrompue, et sur l'archive anti-
        doublons (voir :attr:`ytdl.models.DownloadOptions.archive_path`) pour
        sauter instantanément tout ce qui était déjà terminé — sans reprendre
        toute la playlist depuis le début.

        Returns:
            ``True`` si la reprise a été déclenchée.
        """
        with self._lock:
            job = next((j for j in self._jobs if j.id == job_id), None)
            if job is None or job.status != JobStatus.PAUSED:
                return False
            self._reset_for_rerun(job)
            self._submit(job)
        self._notify()
        return True

    def restart(self, job_id: str) -> bool:
        """Relance un job en erreur ou annulé, sur les mêmes bases que :meth:`resume`.

        Returns:
            ``True`` si la relance a été déclenchée.
        """
        with self._lock:
            job = next((j for j in self._jobs if j.id == job_id), None)
            if job is None or job.status not in (JobStatus.ERROR, JobStatus.CANCELLED):
                return False
            self._reset_for_rerun(job)
            self._submit(job)
        self._notify()
        return True

    @staticmethod
    def _reset_for_rerun(job: DownloadJob) -> None:
        """Remet un job à zéro avant une reprise/relance (appelant : tenir ``_lock``)."""
        job.status = JobStatus.PENDING
        job.progress = 0.0
        job.speed = ""
        job.eta = ""
        job.error = ""
        job.filepath = ""
        job.playlist_entries = []
        job.playlist_total = 0
        job.playlist_completed = 0

    def clear_finished(self) -> None:
        """Retire de la file les jobs terminés (done/error/cancelled)."""
        with self._lock:
            self._jobs = [j for j in self._jobs if not j.status.is_terminal]
        self._notify()

    def shutdown(self) -> None:
        """Arrête proprement le pool de threads."""
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------ #
    # Worker
    # ------------------------------------------------------------------ #
    def _backend_for(self, job: DownloadJob) -> "Downloader | SpotifyDownloader":
        """Choisit le moteur de téléchargement adapté aux options du job."""
        if isinstance(job.options, SpotifyDownloadOptions):
            return self._spotify_downloader
        return self._downloader

    def _run(self, job: DownloadJob) -> None:
        """Exécute un job dans un thread worker."""
        if job.id in self._cancelled:
            job.status = JobStatus.CANCELLED
            self._notify()
            return
        try:
            self._backend_for(job).download(job, on_progress=self._make_progress(job))
        except Exception as exc:  # l'erreur est déjà consignée dans job.error
            if job.status not in (JobStatus.CANCELLED, JobStatus.PAUSED):
                job.status = JobStatus.ERROR
                job.error = job.error or str(exc)
        finally:
            self._notify()

    def _make_progress(self, job: DownloadJob):
        """Fabrique un callback de progression qui gère l'annulation/la pause coopératives."""

        def on_progress(updated: DownloadJob) -> None:
            if job.id in self._cancelled and not job.status.is_terminal:
                job.status = JobStatus.CANCELLED
                # Interrompt yt-dlp proprement à la prochaine occasion.
                raise KeyboardInterrupt("Téléchargement annulé par l'utilisateur.")
            if job.id in self._paused and job.status != JobStatus.PAUSED:
                job.status = JobStatus.PAUSED
                self._paused.discard(job.id)
                raise KeyboardInterrupt("Téléchargement mis en pause par l'utilisateur.")
            self._notify()

        return on_progress

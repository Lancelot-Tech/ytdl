"""Enveloppe autour du CLI ``spotdl`` — cœur métier Spotify, sans dépendance à l'UI.

Contrairement à :mod:`ytdl.downloader` (yt-dlp, utilisé comme bibliothèque
Python), ``spotdl`` est ici invoqué comme un **processus externe** — jamais
importé en Python. Son propre jeu de dépendances (fastapi/starlette/uvicorn
bien plus anciens que ceux requis par NiceGUI) casse l'application au
runtime s'il est installé dans le même environnement virtuel — voir
:mod:`ytdl.spotify_check`. L'utilisateur l'installe séparément (ex. ``pipx
install spotdl``) ; on se contente de le trouver dans le ``PATH``.

Le format des lignes de progression (``"<Artiste> - <Titre>: <Étape>"`` puis
``"N/M complete"``) est stable : lu directement dans les sources de spotdl
(``spotdl/download/progress_handler.py``, méthodes ``notify_*`` et
``report_progress``), pas documenté publiquement mais fixe (vocabulaire
d'étapes fermé, toujours appelées avec leurs arguments par défaut).
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
from typing import Any, Callable, Optional

from .downloader import DownloadError, ProgressCallback
from .ffmpeg_check import ffmpeg_path
from .models import DownloadJob, JobStatus, MediaInfo, PlaylistEntry, SpotifyDownloadOptions
from .spotify_check import spotdl_path


class ProbeCancelled(DownloadError):
    """Levée quand une analyse (:meth:`SpotifyDownloader.probe`) est annulée par l'utilisateur."""


class CancelToken:
    """Jeton annulable, partagé entre l'UI et un appel à :meth:`SpotifyDownloader.probe`.

    ``spotdl save`` est un unique appel bloquant, sans sortie exploitable
    avant d'avoir terminé (contrairement à ``download``, dont chaque ligne de
    progression offre un point de contrôle coopératif naturel) : la seule
    façon d'interrompre une analyse en cours est de terminer directement le
    sous-processus depuis un autre thread, ce que permet ce jeton — posé une
    fois par appel, jetable ensuite.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: Any = None
        self._cancelled = False

    def _attach(self, proc: Any) -> None:
        with self._lock:
            if self._cancelled:
                self._terminate(proc)
            else:
                self._proc = proc

    def _detach(self) -> None:
        with self._lock:
            self._proc = None

    def cancel(self) -> None:
        """Demande l'annulation — termine le sous-processus s'il tourne déjà."""
        with self._lock:
            self._cancelled = True
            proc = self._proc
        if proc is not None:
            self._terminate(proc)

    @staticmethod
    def _terminate(proc: Any) -> None:
        """``SIGTERM`` d'abord, puis ``SIGKILL`` de secours si ignoré.

        Constaté en pratique : le process spotdl (ou l'une de ses dépendances
        réseau) ignore ``SIGTERM`` — sans ce filet, l'annulation ne fait
        strictement rien et l'analyse continue jusqu'à sa fin naturelle. Lancé
        dans un thread à part : ``cancel()`` est appelé depuis le thread
        d'interface (clic sur « Annuler ») et ne doit jamais bloquer.
        """
        proc.terminate()

        def _escalate() -> None:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

        threading.Thread(target=_escalate, daemon=True).start()

    @property
    def cancelled(self) -> bool:
        return self._cancelled


# Pourcentage et libellé (UI) associés à chaque étape rapportée par spotdl en
# mode ``--simple-tui`` (vocabulaire fermé, voir le docstring du module).
_STAGE_INFO: dict[str, tuple[float, str]] = {
    "Searching for song": (25.0, "Recherche…"),
    "Getting audio meta": (40.0, "Métadonnées…"),
    "Downloading": (70.0, "Téléchargement…"),
    "Converting": (85.0, "Conversion…"),
    "Embedding metadata": (95.0, "Finalisation…"),
    "Done": (100.0, ""),
    "Skipped": (100.0, "Déjà présent"),
    "Error": (100.0, "Erreur"),
}
_DONE_STAGES = ("Done", "Skipped")
_PROCESSING_STAGES = ("Converting", "Embedding metadata")

_TRACK_LINE_RE = re.compile(
    r"^(?P<name>.+): (?P<stage>" + "|".join(re.escape(s) for s in _STAGE_INFO) + r")\s*$"
)
# Ligne récapitulative émise après chaque piste terminée (voir
# ``report_progress`` dans les sources de spotdl) — sert de repli pour
# connaître le total de pistes si ``SpotifyDownloadOptions.playlist_tracks``
# n'a pas été renseigné (voir :meth:`SpotifyDownloader.download`).
_OVERALL_LINE_RE = re.compile(r"^\d+/(?P<total>\d+) complete\s*$")

# Filet de sécurité seulement (processus manifestement bloqué) : le vrai
# contrôle utilisateur, c'est le bouton d'annulation (voir CancelToken) — pas
# ce délai. ``save`` interroge l'API Spotify piste par piste, pas de flux —
# mesuré à ~2 secondes/piste en pratique. Sur une playlist de plusieurs
# milliers de titres, ça peut légitimement prendre plus d'une heure.
_PROBE_TIMEOUT = 3 * 3600


class SpotifyDownloader:
    """Analyse et télécharge depuis Spotify via le CLI ``spotdl`` (sous-processus).

    Sans état propre : partageable entre plusieurs jobs/threads (chaque appel
    lance son propre sous-processus).
    """

    def __init__(
        self,
        spotdl_path_fn: Optional[Callable[[], Optional[str]]] = None,
        popen_fn: Optional[Callable[..., Any]] = None,
    ) -> None:
        """
        Args:
            spotdl_path_fn: Callable renvoyant le chemin de l'exécutable
                ``spotdl`` (ou ``None``). Par défaut :func:`ytdl.spotify_check.spotdl_path`.
            popen_fn: Fabrique de processus, pour ``save`` comme ``download``
                (injectable pour les tests). Par défaut ``subprocess.Popen``.
                Un ``Popen`` partout (plutôt que ``subprocess.run`` pour
                ``save``) est ce qui permet d'exposer le processus à un
                :class:`CancelToken` pour l'annulation.
        """
        self._spotdl_path_fn = spotdl_path_fn or spotdl_path
        self._popen_fn = popen_fn or subprocess.Popen

    def _require_exe(self) -> str:
        exe = self._spotdl_path_fn()
        if not exe:
            raise DownloadError(
                "spotdl introuvable. Installez-le séparément (ex. pipx install spotdl), "
                "voir la section Aide."
            )
        return exe

    # ------------------------------------------------------------------ #
    # Analyse (probe) — sans téléchargement
    # ------------------------------------------------------------------ #
    def probe(self, url: str, cancel_token: Optional[CancelToken] = None) -> MediaInfo:
        """Récupère les métadonnées d'une URL Spotify sans rien télécharger.

        Args:
            url: URL d'un titre, d'une playlist ou d'un album Spotify.
            cancel_token: Si fourni, permet d'interrompre l'analyse en cours
                depuis un autre thread via ``cancel_token.cancel()`` (voir
                :class:`CancelToken` — utile pour un bouton « Annuler » côté
                UI sur une grosse playlist, l'analyse pouvant prendre
                plusieurs dizaines de minutes).

        Returns:
            Les informations média extraites.

        Raises:
            ProbeCancelled: si ``cancel_token.cancel()`` a été appelé.
            DownloadError: si l'extraction échoue ou si ``spotdl`` est absent.
        """
        songs = self._fetch_songs(url, cancel_token)
        return MediaInfo.from_spotdl_songs(songs, url)

    def _fetch_songs(self, url: str, cancel_token: Optional[CancelToken] = None) -> list[dict[str, Any]]:
        exe = self._require_exe()
        try:
            proc = self._popen_fn(
                [exe, "--log-level", "ERROR", "save", url, "--save-file", "-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
            )
        except OSError as exc:
            raise DownloadError(f"Impossible de lancer spotdl : {exc}") from exc
        if cancel_token is not None:
            cancel_token._attach(proc)
        try:
            try:
                stdout, stderr = proc.communicate(timeout=_PROBE_TIMEOUT)
            except subprocess.TimeoutExpired as exc:
                proc.kill()
                proc.communicate()
                raise DownloadError(f"Impossible d'analyser l'URL Spotify : {exc}") from exc
        finally:
            if cancel_token is not None:
                cancel_token._detach()

        if cancel_token is not None and cancel_token.cancelled:
            raise ProbeCancelled("Analyse annulée.")
        if proc.returncode != 0:
            detail = (stderr or stdout or "").strip()
            raise DownloadError(f"Échec de l'analyse Spotify : {detail or 'erreur inconnue'}")
        try:
            songs = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise DownloadError("Réponse de spotdl illisible.") from exc
        if not songs:
            raise DownloadError("Aucune piste trouvée pour cette URL Spotify.")
        return songs

    # ------------------------------------------------------------------ #
    # Téléchargement
    # ------------------------------------------------------------------ #
    def download(self, job: DownloadJob, on_progress: Optional[ProgressCallback] = None) -> DownloadJob:
        """Télécharge le(s) titre(s) Spotify d'un job (appel bloquant).

        Met à jour ``job`` au fil de l'avancement et appelle ``on_progress`` à
        chaque étape. Coopérativement annulable/pausable : si ``on_progress``
        lève ``KeyboardInterrupt`` (contrat de :class:`ytdl.queue.DownloadQueue`),
        le sous-processus ``spotdl`` est terminé puis l'exception se propage
        telle quelle (volontairement pas capturée par ``except Exception`` —
        voir :mod:`ytdl.downloader` pour la même logique côté yt-dlp).

        Args:
            job: Le job à traiter (modifié en place). ``job.options`` doit
                être un :class:`~ytdl.models.SpotifyDownloadOptions`.
            on_progress: Callback appelé à chaque mise à jour.

        Returns:
            Le job, terminé.
        """
        options: SpotifyDownloadOptions = job.options  # type: ignore[assignment]

        # La liste des pistes vient de l'aperçu (``probe``, déjà appelé côté
        # UI) plutôt que d'un nouvel appel à ``save`` ici : cette analyse est
        # lente (~2s/piste côté spotdl), la refaire au démarrage du
        # téléchargement doublerait l'attente pour rien sur une grosse
        # playlist. Repli sur une création à la volée (voir ``_apply_line``)
        # si elle n'a pas été fournie (job ajouté sans passer par l'aperçu).
        if options.is_playlist and options.playlist_tracks:
            job.playlist_total = len(options.playlist_tracks)
            job.playlist_entries = [
                PlaylistEntry(index=i, title=title)
                for i, title in enumerate(options.playlist_tracks, start=1)
            ]

        exe = self._require_exe()
        args = [
            exe,
            "download",
            job.url,
            "--output",
            options.output_template(),
            "--format",
            options.fmt.value,
            "--bitrate",
            _bitrate_arg(options.bitrate),
            "--simple-tui",
        ]
        if not options.embed_cover:
            args.append("--skip-album-art")
        if options.archive_path:
            args += ["--archive", options.archive_path]
        ffmpeg = ffmpeg_path()
        if ffmpeg:
            args += ["--ffmpeg", ffmpeg]

        job.status = JobStatus.DOWNLOADING
        if on_progress:
            on_progress(job)

        proc = self._popen_fn(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, bufsize=1
        )
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                self._apply_line(job, line, options)
                if on_progress:
                    on_progress(job)
        except BaseException:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            raise
        finally:
            if proc.stdout is not None:
                proc.stdout.close()
        returncode = proc.wait()

        if returncode != 0 and job.playlist_completed == 0 and not job.playlist_entries:
            job.status = JobStatus.ERROR
            job.error = f"spotdl a échoué (code {returncode})."
            if on_progress:
                on_progress(job)
            raise DownloadError(job.error)

        job.status = JobStatus.DONE
        job.progress = 100.0
        if options.is_playlist and job.playlist_total:
            job.playlist_completed = max(job.playlist_completed, sum(
                1 for e in job.playlist_entries if e.status == JobStatus.DONE
            ))
        if on_progress:
            on_progress(job)
        return job

    # ------------------------------------------------------------------ #
    # Détails internes
    # ------------------------------------------------------------------ #
    @staticmethod
    def _apply_line(job: DownloadJob, line: str, options: SpotifyDownloadOptions) -> None:
        """Traduit une ligne de sortie ``--simple-tui`` en mise à jour de job."""
        line = line.rstrip()
        if not line:
            return

        if options.is_playlist and not job.playlist_total:
            # Repli : le total n'était pas connu à l'avance (voir
            # ``download``), on l'apprend de cette ligne récapitulative dès
            # qu'elle apparaît (après la toute première piste terminée).
            overall = _OVERALL_LINE_RE.match(line)
            if overall:
                job.playlist_total = int(overall.group("total"))
                return

        match = _TRACK_LINE_RE.match(line)
        if not match:
            return
        name, stage = match.group("name"), match.group("stage")
        pct, label = _STAGE_INFO[stage]

        if options.is_playlist:
            entry = next((e for e in job.playlist_entries if e.title == name), None)
            if entry is None:
                # Piste jamais vue (liste non pré-remplie, voir ``download``) :
                # créée à la volée, dans l'ordre d'apparition.
                entry = PlaylistEntry(index=len(job.playlist_entries) + 1, title=name)
                job.playlist_entries.append(entry)
            if stage in _DONE_STAGES:
                entry.status = JobStatus.DONE
                entry.stage = ""
            elif stage == "Error":
                entry.status = JobStatus.ERROR
                entry.stage = "Erreur"
            else:
                entry.status = JobStatus.PROCESSING if stage in _PROCESSING_STAGES else JobStatus.DOWNLOADING
                entry.stage = label
            job.playlist_completed = sum(1 for e in job.playlist_entries if e.status == JobStatus.DONE)
            job.status = JobStatus.DOWNLOADING
            if job.playlist_total:
                job.progress = job.playlist_completed / job.playlist_total * 100.0
        else:
            job.status = JobStatus.PROCESSING if stage in _PROCESSING_STAGES else JobStatus.DOWNLOADING
            job.progress = pct


def _bitrate_arg(bitrate: str) -> str:
    """Traduit une valeur de :data:`ytdl.models.SPOTIFY_BITRATES` en argument ``--bitrate``."""
    if bitrate == "auto":
        return "auto"
    return f"{bitrate}k"

"""Enveloppe autour de ``yt_dlp`` — cœur métier, sans aucune dépendance à l'UI.

Cette couche est volontairement synchrone/bloquante : la concurrence et le suivi
temps réel sont gérés au-dessus par :mod:`ytdl.queue`.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .models import YTDLP_JS_CHALLENGE_OPTS, DownloadJob, JobStatus, MediaInfo, PlaylistEntry


class DownloadError(Exception):
    """Erreur levée lorsqu'un téléchargement ou une analyse échoue."""


# Signature du callback de progression : reçoit le job mis à jour.
ProgressCallback = Callable[[DownloadJob], None]


def _import_ytdl():
    """Importe ``yt_dlp`` paresseusement (évite de le charger pour les tests unitaires)."""
    try:
        import yt_dlp  # noqa: WPS433 (import local volontaire)
    except ImportError as exc:  # pragma: no cover - dépend de l'environnement
        raise DownloadError(
            "yt-dlp n'est pas installé. Exécutez : pip install -r requirements.txt"
        ) from exc
    return yt_dlp


class Downloader:
    """Analyse et télécharge des médias via yt-dlp.

    L'objet est sans état : il peut être partagé entre plusieurs jobs/threads.
    """

    def __init__(self, ydl_factory: Optional[Callable[[dict[str, Any]], Any]] = None) -> None:
        """
        Args:
            ydl_factory: Fabrique de ``YoutubeDL`` (injectable pour les tests).
                Par défaut, ``yt_dlp.YoutubeDL``.
        """
        self._ydl_factory = ydl_factory

    def _make_ydl(self, opts: dict[str, Any]):
        if self._ydl_factory is not None:
            return self._ydl_factory(opts)
        return _import_ytdl().YoutubeDL(opts)

    # ------------------------------------------------------------------ #
    # Analyse (probe) — sans téléchargement
    # ------------------------------------------------------------------ #
    def probe(self, url: str, cookies_browser: str = "") -> MediaInfo:
        """Récupère les métadonnées d'une URL sans rien télécharger.

        Args:
            url: URL de la vidéo ou de la playlist.
            cookies_browser: Navigateur dont utiliser les cookies de session
                (voir :data:`ytdl.models.COOKIE_BROWSERS`), pour analyser une
                playlist privée (« Liked videos », « Watch Later »…). Vide =
                pas d'authentification.

        Returns:
            Les informations média extraites.

        Raises:
            DownloadError: si l'extraction échoue.
        """
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist",
            **YTDLP_JS_CHALLENGE_OPTS,
        }
        if cookies_browser:
            opts["cookiesfrombrowser"] = (cookies_browser,)
        try:
            ydl = self._make_ydl(opts)
            with ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:  # yt-dlp lève des exceptions variées
            raise DownloadError(f"Impossible d'analyser l'URL : {exc}") from exc
        if not info:
            raise DownloadError("Aucune information récupérée pour cette URL.")
        return MediaInfo.from_ydl_info(info)

    # ------------------------------------------------------------------ #
    # Téléchargement
    # ------------------------------------------------------------------ #
    def download(self, job: DownloadJob, on_progress: Optional[ProgressCallback] = None) -> DownloadJob:
        """Télécharge le média d'un job (appel bloquant).

        Met à jour ``job`` au fil de l'avancement et appelle ``on_progress`` à
        chaque étape. En cas d'échec, ``job.status`` passe à
        :attr:`~ytdl.models.JobStatus.ERROR` et l'exception est propagée.

        Args:
            job: Le job à traiter (modifié en place).
            on_progress: Callback appelé à chaque mise à jour.

        Returns:
            Le job, terminé.
        """

        def hook(d: dict[str, Any]) -> None:
            self._apply_hook(job, d, on_progress)

        def pp_hook(d: dict[str, Any]) -> None:
            self._apply_pp_hook(job, d, on_progress)

        opts = job.options.to_ydl_opts(progress_hook=hook, postprocessor_hook=pp_hook)
        # Avant le premier octet, yt-dlp résout l'URL/la playlist (et, avec
        # une archive, vérifie chaque piste déjà connue — silencieux, sans
        # hook, ce qui peut prendre un moment sur une grosse playlist reprise
        # : sans cet état, la carte semblait figée pendant tout ce temps).
        job.status = JobStatus.PROBING
        job.progress = 0.0
        if on_progress:
            on_progress(job)

        try:
            ydl = self._make_ydl(opts)
            with ydl:
                info = ydl.extract_info(job.url, download=True)
            job.filepath = self._resolved_filepath(ydl, info)
            job.status = JobStatus.DONE
            job.progress = 100.0
            if job.options.is_playlist and job.playlist_total:
                job.playlist_completed = job.playlist_total
        except Exception as exc:
            job.status = JobStatus.ERROR
            job.error = str(exc)
            if on_progress:
                on_progress(job)
            raise DownloadError(str(exc)) from exc

        if on_progress:
            on_progress(job)
        return job

    # ------------------------------------------------------------------ #
    # Détails internes
    # ------------------------------------------------------------------ #
    @staticmethod
    def _apply_hook(job: DownloadJob, d: dict[str, Any], on_progress: Optional[ProgressCallback]) -> None:
        """Traduit un événement de ``progress_hooks`` en mise à jour de job.

        Pour une playlist, un seul appel à ``extract_info`` télécharge toutes
        les pistes : ce hook est donc invoqué une fois par piste. On en
        profite pour maintenir :attr:`DownloadJob.playlist_entries` et faire
        refléter la progression globale (pistes terminées / total) plutôt que
        la seule progression en octets de la piste en cours — sans quoi la
        barre semble « bloquée à 100 % » entre deux pistes.
        """
        status = d.get("status")

        if job.options.is_playlist:
            Downloader._update_playlist_entry(job, d)

        if status == "downloading":
            job.status = JobStatus.DOWNLOADING
            if job.options.is_playlist and job.playlist_total:
                job.progress = job.playlist_completed / job.playlist_total * 100.0
            else:
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes")
                if total and downloaded is not None:
                    job.progress = max(0.0, min(100.0, downloaded / total * 100.0))
            job.speed = (d.get("_speed_str") or "").strip()
            job.speed_bps = float(d.get("speed") or 0.0)
            job.eta = (d.get("_eta_str") or "").strip()
        elif status == "finished":
            # Le fichier est téléchargé ; un éventuel post-traitement suit.
            job.status = JobStatus.PROCESSING
            if not (job.options.is_playlist and job.playlist_total):
                job.progress = 100.0
            job.speed = ""
            job.speed_bps = 0.0
            job.eta = ""
        if on_progress:
            on_progress(job)

    @staticmethod
    def _update_playlist_entry(job: DownloadJob, d: dict[str, Any]) -> None:
        """Crée/actualise l'entrée de :attr:`DownloadJob.playlist_entries` visée par ce hook."""
        info = d.get("info_dict") or {}
        status = d.get("status")

        total = info.get("n_entries") or info.get("playlist_count")
        if total:
            job.playlist_total = int(total)

        index = info.get("playlist_index")
        if not index:
            return

        entry = next((e for e in job.playlist_entries if e.index == index), None)
        if entry is None:
            entry = PlaylistEntry(index=int(index), title=info.get("title") or f"Piste {index}")
            job.playlist_entries.append(entry)
            job.playlist_entries.sort(key=lambda e: e.index)
        elif info.get("title"):
            entry.title = info["title"]

        if status == "downloading":
            if entry.status != JobStatus.DONE:
                entry.status = JobStatus.DOWNLOADING
        elif status == "finished":
            # Le fichier brut est récupéré, mais le post-traitement (conversion,
            # métadonnées, miniature...) n'a pas encore eu lieu : on ne marque
            # la piste DONE que plus tard, via _apply_pp_hook, sans quoi une
            # piste encore en conversion apparaît à tort comme terminée.
            entry.status = JobStatus.PROCESSING
            entry.stage = "Traitement…"
            entry.filepath = d.get("filename") or ""

        job.playlist_completed = sum(1 for e in job.playlist_entries if e.status == JobStatus.DONE)

    # Libellé affiché pendant le post-traitement, par nom interne de
    # postprocessor yt-dlp (``pp_key()`` — voir yt_dlp/postprocessor/*.py).
    _PP_STAGE_LABELS: dict[str, str] = {
        "MetadataParser": "Nettoyage du titre…",
        "ExtractAudio": "Conversion audio…",
        "FFmpegMetadata": "Écriture des métadonnées…",
        "EmbedThumbnail": "Intégration de la miniature…",
        "EmbedSubtitle": "Intégration des sous-titres…",
        "MoveFiles": "Finalisation…",
    }

    @classmethod
    def _apply_pp_hook(
        cls, job: DownloadJob, d: dict[str, Any], on_progress: Optional[ProgressCallback]
    ) -> None:
        """Traduit un événement de ``postprocessor_hooks`` en mise à jour de piste.

        Seul le post-traitement final (``MoveFiles``, toujours exécuté en
        dernier par yt-dlp, avec ou sans post-traitement explicite) marque la
        piste comme réellement terminée ; les autres ne font qu'affiner le
        libellé affiché (« Conversion audio… », etc.).
        """
        if job.options.is_playlist:
            info = d.get("info_dict") or {}
            index = info.get("playlist_index")
            entry = next((e for e in job.playlist_entries if e.index == index), None) if index else None
            if entry is not None:
                status = d.get("status")
                pp_name = d.get("postprocessor") or ""
                if status == "finished" and pp_name == "MoveFiles":
                    entry.status = JobStatus.DONE
                    entry.stage = ""
                    # À ce stade, les post-traitements (conversion, etc.) ont
                    # déjà tourné : info["filepath"] reflète le fichier final
                    # (ex. .mp3), pas le fichier brut téléchargé (ex. .webm)
                    # que retenait le hook de progression brut — sans ça, le
                    # bouton « Lire » pointait vers un fichier qui n'existe
                    # plus une fois la conversion terminée.
                    entry.filepath = info.get("filepath") or entry.filepath
                    job.playlist_completed = sum(
                        1 for e in job.playlist_entries if e.status == JobStatus.DONE
                    )
                elif status == "started":
                    entry.status = JobStatus.PROCESSING
                    entry.stage = cls._PP_STAGE_LABELS.get(pp_name, "Traitement…")
        if on_progress:
            on_progress(job)

    @staticmethod
    def _resolved_filepath(ydl: Any, info: dict[str, Any] | None) -> str:
        """Meilleure estimation du chemin final produit par yt-dlp."""
        if not info:
            return ""
        # Pour une playlist, on ne renvoie pas de fichier unique.
        if info.get("_type") == "playlist" or "entries" in info:
            return ""
        requested = info.get("requested_downloads")
        if requested:
            return requested[0].get("filepath", "") or ""
        try:
            return ydl.prepare_filename(info)
        except Exception:  # pragma: no cover - défensif
            return ""

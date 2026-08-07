"""Modèles de données du cœur (sans dépendance à l'UI).

Le point le plus important est :meth:`DownloadOptions.to_ydl_opts`, qui traduit les
choix de l'utilisateur en dictionnaire d'options compréhensible par ``yt_dlp.YoutubeDL``.
C'est cette traduction qui est couverte par les tests unitaires.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Union


# --------------------------------------------------------------------------- #
# Formats
# --------------------------------------------------------------------------- #
class MediaFormat(str, Enum):
    """Format de sortie demandé.

    Les formats « audio » passent par un post-traitement ffmpeg (extraction),
    les formats « vidéo » sélectionnent un conteneur puis fusionnent vidéo+audio.
    """

    MP4 = "mp4"                # vidéo, conteneur mp4 (le plus compatible)
    WEBM = "webm"              # vidéo, conteneur webm (souvent meilleure qualité/taille)
    MP3 = "mp3"                # audio, ré-encodé en mp3 (universel)
    M4A = "m4a"                # audio, conteneur aac (meilleure qualité à débit égal)
    BEST_VIDEO = "best_video"  # meilleure vidéo dispo, conteneur laissé libre
    BEST_AUDIO = "best_audio"  # meilleur audio dispo, sans ré-encodage

    @property
    def is_audio(self) -> bool:
        """``True`` si le format ne produit que de l'audio."""
        return self in (MediaFormat.MP3, MediaFormat.M4A, MediaFormat.BEST_AUDIO)

    @property
    def label(self) -> str:
        """Libellé lisible pour l'interface."""
        return {
            MediaFormat.MP4: "MP4 (vidéo)",
            MediaFormat.WEBM: "WebM (vidéo)",
            MediaFormat.MP3: "MP3 (audio)",
            MediaFormat.M4A: "M4A (audio)",
            MediaFormat.BEST_VIDEO: "Meilleure vidéo",
            MediaFormat.BEST_AUDIO: "Meilleur audio",
        }[self]


# Qualités proposées dans l'UI selon le type de média.
VIDEO_QUALITIES = ["best", "2160", "1440", "1080", "720", "480", "360"]
AUDIO_QUALITIES = ["best", "320", "256", "192", "128"]


class SpotifyFormat(str, Enum):
    """Format de sortie audio demandé pour un téléchargement Spotify (via ``spotdl``)."""

    MP3 = "mp3"
    FLAC = "flac"
    OGG = "ogg"
    OPUS = "opus"
    M4A = "m4a"
    WAV = "wav"

    @property
    def label(self) -> str:
        """Libellé lisible pour l'interface."""
        return {
            SpotifyFormat.MP3: "MP3 (audio)",
            SpotifyFormat.FLAC: "FLAC (sans perte)",
            SpotifyFormat.OGG: "OGG (audio)",
            SpotifyFormat.OPUS: "Opus (audio)",
            SpotifyFormat.M4A: "M4A (audio)",
            SpotifyFormat.WAV: "WAV (brut)",
        }[self]


# Débits proposés dans l'UI pour un téléchargement Spotify (« auto » = débit
# de la source, sans ré-encodage forcé — voir la doc ``--bitrate`` de spotdl).
SPOTIFY_BITRATES = ["auto", "320", "256", "192", "128", "96"]

# Navigateurs dont yt-dlp sait extraire les cookies de session (voir
# ``yt_dlp.cookies.SUPPORTED_BROWSERS``). Recopié ici pour ne pas dépendre de
# yt-dlp au niveau du cœur/UI tant que la fonctionnalité n'est pas utilisée.
COOKIE_BROWSERS = ["brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi", "whale"]

# Paramètre d'URL YouTube indiquant une playlist (y compris les playlists
# spéciales "LL" = vidéos aimées, "WL" = à regarder plus tard, propres au
# compte connecté et donc inaccessibles sans cookies).
_PLAYLIST_URL_PARAM = re.compile(r"[?&]list=")


def url_has_playlist_param(url: str) -> bool:
    """``True`` si l'URL contient un paramètre ``list=`` (playlist YouTube)."""
    return bool(_PLAYLIST_URL_PARAM.search(url))


# URL Spotify pointant vers plusieurs pistes (playlist, album ou artiste,
# dont la page liste tous les albums) plutôt qu'un titre isolé.
_SPOTIFY_MULTI_TRACK_URL_RE = re.compile(r"open\.spotify\.com/(?:intl-\w+/)?(playlist|album|artist)/")


def spotify_url_is_multi_track(url: str) -> bool:
    """``True`` si l'URL Spotify désigne une playlist/un album/un artiste (pas un titre isolé)."""
    return bool(_SPOTIFY_MULTI_TRACK_URL_RE.search(url))


# yt-dlp doit résoudre un « défi » JavaScript posé par YouTube pour déchiffrer
# les URLs de flux ; sans ça, la plupart des formats disparaissent et tout
# échoue avec « Requested format is not available », même avec des cookies
# valides. Par défaut, yt-dlp n'active que "deno" (rarement installé) et ne
# télécharge pas le script solveur — on élargit explicitement aux runtimes JS
# courants (Node, présent le plus souvent) et on autorise le téléchargement du
# solveur officiel (dépôt yt-dlp/yt-dlp), comme yt-dlp le recommande lui-même
# dans son message d'erreur. Voir https://github.com/yt-dlp/yt-dlp/wiki/EJS
YTDLP_JS_CHALLENGE_OPTS: dict[str, Any] = {
    "js_runtimes": {"deno": {}, "node": {}, "bun": {}},
    "remote_components": {"ejs:github"},
}


# --------------------------------------------------------------------------- #
# Nettoyage des titres
# --------------------------------------------------------------------------- #
# Mentions parasites fréquentes dans les titres YouTube, à retirer quand elles
# apparaissent entre parenthèses ou crochets (ex. « Titre (Official Video) »,
# « Titre (Clip Officiel) »).
_TITLE_CLEAN_PHRASES = [
    r"official\s+music\s+video",
    r"official\s+lyric\s+video",
    r"official\s+visualizer",
    r"official\s+video",
    r"official\s+audio",
    r"official\s+clip",
    r"clip\s+officiel",
    r"clip\s+official",
    r"lyric\s+video",
    r"music\s+video",
    r"audio\s+officiel",
    r"visualizer",
]
TITLE_CLEAN_REGEX = re.compile(
    r"[\(\[]\s*(?:" + "|".join(_TITLE_CLEAN_PHRASES) + r")\s*[\)\]]",
    re.IGNORECASE,
)


def clean_title(title: str) -> str:
    """Retire les mentions du type « (Official Video) » / « (Clip Officiel) » d'un titre.

    Utilisé à la fois pour l'aperçu affiché et (via un post-traitement yt-dlp
    équivalent) pour le nom de fichier et les métadonnées enregistrées.
    """
    cleaned = TITLE_CLEAN_REGEX.sub("", title)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s*[-|]\s*$", "", cleaned)
    return cleaned.strip()


def _title_clean_actions() -> list[tuple[Any, ...]]:
    """Actions ``MetadataParserPP`` équivalentes à :func:`clean_title` pour yt-dlp.

    Import différé de ``yt_dlp`` pour ne pas l'exiger tant que l'option n'est
    pas utilisée (même logique que :mod:`ytdl.downloader`).
    """
    from yt_dlp.postprocessor import MetadataParserPP

    replace = MetadataParserPP.Actions.REPLACE
    return [
        (replace, "title", "(?i)" + TITLE_CLEAN_REGEX.pattern, ""),
        (replace, "title", r"\s{2,}", " "),
        (replace, "title", r"\s*[-|]\s*$", ""),
        (replace, "title", r"^\s+", ""),
    ]


class JobStatus(str, Enum):
    """Cycle de vie d'un téléchargement.

    ``PAUSING``/``CANCELLING`` sont des états transitoires, affichés dès le
    clic sur le bouton correspondant : le thread qui exécute yt-dlp ne peut
    être interrompu qu'à son prochain point de contrôle coopératif (un hook
    de progression), pas instantanément — sans cet état intermédiaire,
    l'utilisateur ne voit aucun changement pendant ce court délai et a
    l'impression que le bouton ne répond pas.
    """

    PENDING = "pending"
    PROBING = "probing"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"   # post-traitement ffmpeg
    PAUSING = "pausing"         # arrêt demandé, en attente du prochain hook
    PAUSED = "paused"
    CANCELLING = "cancelling"   # arrêt demandé, en attente du prochain hook
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """``True`` si le job ne changera plus d'état de lui-même.

        ``PAUSED`` n'est volontairement pas terminal : le job reste dans la
        file (pas balayé par « Nettoyer les terminés ») et peut reprendre.
        """
        return self in (JobStatus.DONE, JobStatus.ERROR, JobStatus.CANCELLED)


# --------------------------------------------------------------------------- #
# Options de téléchargement
# --------------------------------------------------------------------------- #
@dataclass
class DownloadOptions:
    """Choix de l'utilisateur pour un téléchargement.

    Attributes:
        fmt: Format de sortie (:class:`MediaFormat`).
        quality: ``"best"`` ou une valeur numérique (hauteur en px pour la vidéo,
            débit en kbps pour l'audio).
        output_dir: Dossier de destination.
        filename_template: Gabarit de nommage yt-dlp.
        subtitles: Télécharger et intégrer les sous-titres.
        sub_langs: Langues de sous-titres (codes ISO, ex. ``["fr", "en"]``).
        embed_metadata: Écrire titre/artiste/… dans le fichier.
        embed_thumbnail: Intégrer la miniature comme pochette.
        playlist_items: Sélection d'éléments d'une playlist (ex. ``"1-5,8"``);
            ``None`` = tout ; chaîne vide gérée comme ``None``.
        is_playlist: Indique si l'URL doit être traitée comme une playlist.
        clean_title: Retire du titre les mentions « (Official Video) »,
            « (Clip Officiel) », etc. avant de nommer le fichier / d'écrire les
            métadonnées. Voir :func:`clean_title`.
        sleep_interval: Pause en secondes avant chaque requête/téléchargement,
            pour limiter le risque de throttling/blocage par IP (0 = désactivé).
        rate_limit_kbps: Débit maximal en Ko/s (0 = illimité).
        cookies_browser: Nom d'un navigateur (voir :data:`COOKIE_BROWSERS`) dont
            les cookies de session sont utilisés, pour accéder aux playlists
            privées (« Liked videos », « Watch Later »…) ou au contenu réservé
            aux abonnés. Chaîne vide = désactivé.
        archive_path: Chemin d'un fichier d'archive yt-dlp (un identifiant
            vidéo par ligne). Si renseigné, toute piste déjà présente dans ce
            fichier est ignorée sans être re-téléchargée — reconnue par son
            identifiant, pas par son nom de fichier (donc fiable même après
            nettoyage de titre). ``None``/vide = désactivé.
    """

    fmt: MediaFormat = MediaFormat.MP4
    quality: str = "1080"
    output_dir: str = "."
    filename_template: str = "%(uploader)s - %(title)s.%(ext)s"
    subtitles: bool = False
    sub_langs: list[str] = field(default_factory=lambda: ["fr", "en"])
    embed_metadata: bool = True
    embed_thumbnail: bool = False
    playlist_items: Optional[str] = None
    is_playlist: bool = False
    clean_title: bool = False
    sleep_interval: float = 0.0
    rate_limit_kbps: int = 0
    cookies_browser: str = ""
    archive_path: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Traduction vers yt-dlp
    # ------------------------------------------------------------------ #
    def format_selector(self) -> str:
        """Construit le sélecteur de format yt-dlp correspondant aux choix."""
        if self.fmt == MediaFormat.BEST_AUDIO:
            return "bestaudio/best"
        if self.fmt.is_audio:
            # On récupère le meilleur audio, la conversion se fait en post-traitement.
            return "bestaudio/best"
        if self.fmt == MediaFormat.BEST_VIDEO:
            return "bestvideo*+bestaudio/best"

        # Formats vidéo avec conteneur imposé (mp4 / webm).
        container = self.fmt.value  # "mp4" ou "webm"
        audio_pref = "m4a" if container == "mp4" else "webm"
        if self.quality == "best":
            height = ""
        else:
            height = f"[height<={self.quality}]"
        return (
            f"bestvideo{height}[ext={container}]+bestaudio[ext={audio_pref}]/"
            f"bestvideo{height}+bestaudio/"
            f"best{height}[ext={container}]/"
            f"best{height}/best"
        )

    def _postprocessors(self) -> list[dict[str, Any]]:
        """Liste des post-traitements ffmpeg dérivés des options."""
        pps: list[dict[str, Any]] = []

        if self.clean_title:
            # Doit tourner avant la détermination du nom de fichier ("pre_process"),
            # pour que le titre nettoyé soit utilisé à la fois dans %(title)s et
            # dans les métadonnées embarquées.
            pps.append(
                {
                    "key": "MetadataParser",
                    "when": "pre_process",
                    "actions": _title_clean_actions(),
                }
            )

        if self.fmt.is_audio and self.fmt != MediaFormat.BEST_AUDIO:
            pp: dict[str, Any] = {
                "key": "FFmpegExtractAudio",
                "preferredcodec": self.fmt.value,  # "mp3" ou "m4a"
            }
            if self.quality != "best":
                pp["preferredquality"] = self.quality
            pps.append(pp)

        if self.embed_metadata:
            pps.append({"key": "FFmpegMetadata", "add_metadata": True})

        if self.embed_thumbnail:
            # Sans ce flag, yt-dlp suppose que le fichier de miniature n'a été
            # écrit que pour l'incorporation et le supprime juste après —
            # ``already_have_thumbnail`` lui dit qu'on veut aussi le garder
            # (déplacé vers le sous-dossier ``Miniatures/``, voir to_ydl_opts).
            pps.append({"key": "EmbedThumbnail", "already_have_thumbnail": True})

        if self.subtitles:
            pps.append({"key": "FFmpegEmbedSubtitle"})

        return pps

    def to_ydl_opts(
        self, progress_hook: Optional[Any] = None, postprocessor_hook: Optional[Any] = None
    ) -> dict[str, Any]:
        """Traduit ces options en dictionnaire ``yt_dlp.YoutubeDL``.

        Args:
            progress_hook: Callable branché sur ``progress_hooks`` (optionnel) —
                avancement du téléchargement brut.
            postprocessor_hook: Callable branché sur ``postprocessor_hooks``
                (optionnel) — avancement du post-traitement (conversion,
                métadonnées, miniature...), qui suit le téléchargement brut.

        Returns:
            Le dictionnaire d'options prêt à passer à ``YoutubeDL(...)``.
        """
        opts: dict[str, Any] = {
            "format": self.format_selector(),
            "outtmpl": os.path.join(self.output_dir, self.filename_template),
            "postprocessors": self._postprocessors(),
            "noplaylist": not self.is_playlist,
            "ignoreerrors": self.is_playlist,  # une entrée qui échoue ne bloque pas la playlist
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "no_color": True,
            **YTDLP_JS_CHALLENGE_OPTS,
        }

        # Conteneur de fusion pour les formats vidéo.
        if not self.fmt.is_audio and self.fmt in (MediaFormat.MP4, MediaFormat.WEBM):
            opts["merge_output_format"] = self.fmt.value

        if self.embed_thumbnail:
            opts["writethumbnail"] = True
            # yt-dlp accepte un gabarit par type de fichier ; on garde le même
            # nom que le média (donc le même titre) mais dans un sous-dossier
            # dédié plutôt que mélangé aux fichiers audio/vidéo.
            opts["outtmpl"] = {
                "default": os.path.join(self.output_dir, self.filename_template),
                "thumbnail": os.path.join(self.output_dir, "Miniatures", self.filename_template),
            }

        if self.subtitles:
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = True
            opts["subtitleslangs"] = list(self.sub_langs)

        if self.is_playlist and self.playlist_items:
            opts["playlist_items"] = self.playlist_items

        if self.sleep_interval > 0:
            # Pause avant chaque téléchargement ET chaque requête d'extraction :
            # c'est surtout cette dernière qui protège contre le throttling sur
            # les playlists (une requête par piste avant même de télécharger).
            opts["sleep_interval"] = self.sleep_interval
            opts["max_sleep_interval"] = self.sleep_interval
            opts["sleep_interval_requests"] = self.sleep_interval

        if self.rate_limit_kbps > 0:
            opts["ratelimit"] = self.rate_limit_kbps * 1024  # yt-dlp attend des octets/s

        if self.cookies_browser:
            opts["cookiesfrombrowser"] = (self.cookies_browser,)

        if self.archive_path:
            opts["download_archive"] = self.archive_path

        if progress_hook is not None:
            opts["progress_hooks"] = [progress_hook]

        if postprocessor_hook is not None:
            opts["postprocessor_hooks"] = [postprocessor_hook]

        return opts


# --------------------------------------------------------------------------- #
# Options de téléchargement Spotify (via ``spotdl``, invoqué en sous-processus)
# --------------------------------------------------------------------------- #
@dataclass
class SpotifyDownloadOptions:
    """Choix de l'utilisateur pour un téléchargement Spotify.

    Bien plus réduit que :class:`DownloadOptions` : ``spotdl`` n'expose pas
    d'équivalent à ``noplaylist``/``playlist_items`` (une URL de playlist
    télécharge toujours tout), et embarque toujours les métadonnées — seule
    la pochette est optionnelle.

    Attributes:
        fmt: Format de sortie (:class:`SpotifyFormat`).
        bitrate: Une valeur de :data:`SPOTIFY_BITRATES` (``"auto"`` = débit
            de la source, sans ré-encodage forcé).
        output_dir: Dossier de destination.
        embed_cover: Intègre la pochette d'album (``True`` par défaut, comme
            spotdl lui-même).
        is_playlist: Renseigné automatiquement depuis l'aperçu (probe), pas
            un choix de l'utilisateur — juste utilisé pour l'affichage.
        playlist_tracks: Liste ordonnée ``"Artiste - Titre"`` des pistes,
            reprise telle quelle de l'aperçu (:attr:`MediaInfo.entries`).
            Interroger Spotify piste par piste via ``spotdl save`` est lent
            (~2 secondes/piste) : la réutiliser évite de refaire cette
            analyse une seconde fois au démarrage du téléchargement (voir
            :meth:`ytdl.spotify_downloader.SpotifyDownloader.download`).
        archive_path: Chemin d'un fichier d'archive spotdl (une URL de piste
            Spotify par ligne, format propre à spotdl — distinct de celui de
            yt-dlp, voir :meth:`ytdl.config.AppConfig.archive_path_spotify`).
            ``None`` = désactivé.
    """

    fmt: SpotifyFormat = SpotifyFormat.MP3
    bitrate: str = "320"
    output_dir: str = "."
    embed_cover: bool = True
    is_playlist: bool = False
    playlist_tracks: list[str] = field(default_factory=list)
    archive_path: Optional[str] = None

    def output_template(self) -> str:
        """Gabarit de nom de fichier passé à ``--output`` (fixe, non configurable)."""
        return os.path.join(self.output_dir, "{artists} - {title}.{output-ext}")


# --------------------------------------------------------------------------- #
# Informations média (résultat d'un « probe »)
# --------------------------------------------------------------------------- #
@dataclass
class MediaInfo:
    """Métadonnées d'une URL, obtenues sans téléchargement.

    Pour une playlist, ``is_playlist`` vaut ``True`` et ``entries`` contient les titres.
    """

    title: str
    uploader: str = ""
    duration: Optional[int] = None          # secondes
    thumbnail: Optional[str] = None
    is_playlist: bool = False
    entries: list[str] = field(default_factory=list)
    webpage_url: str = ""

    @property
    def duration_str(self) -> str:
        """Durée formatée ``H:MM:SS`` / ``M:SS`` (vide si inconnue)."""
        if self.duration is None:
            return ""
        h, rem = divmod(int(self.duration), 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    @classmethod
    def from_ydl_info(cls, info: dict[str, Any]) -> "MediaInfo":
        """Construit un :class:`MediaInfo` à partir du dict renvoyé par yt-dlp."""
        is_playlist = info.get("_type") == "playlist" or "entries" in info
        entries: list[str] = []
        if is_playlist:
            for e in info.get("entries") or []:
                if e:
                    entries.append(e.get("title") or e.get("url") or "?")
        return cls(
            title=info.get("title") or "Sans titre",
            uploader=info.get("uploader") or info.get("channel") or "",
            duration=info.get("duration"),
            thumbnail=info.get("thumbnail"),
            is_playlist=is_playlist,
            entries=entries,
            webpage_url=info.get("webpage_url") or info.get("original_url") or "",
        )

    @classmethod
    def from_spotdl_songs(cls, songs: list[dict[str, Any]], url: str) -> "MediaInfo":
        """Construit un :class:`MediaInfo` à partir du JSON renvoyé par ``spotdl save``.

        ``songs`` est toujours une liste (une seule entrée pour un titre isolé) ;
        une playlist/album se reconnaît soit à plusieurs entrées, soit — cas
        d'une playlist ne contenant qu'un seul titre — au champ ``list_name``
        renseigné par spotdl.
        """
        first = songs[0]
        is_playlist = len(songs) > 1 or bool(first.get("list_name"))
        if is_playlist:
            title = first.get("list_name") or "Playlist Spotify"
            uploader = ""
            duration = None
            entries = [f'{s.get("artist", "?")} - {s.get("name", "?")}' for s in songs]
        else:
            title = first.get("name") or "Sans titre"
            uploader = first.get("artist") or ""
            duration = first.get("duration")
            entries = []
        return cls(
            title=title,
            uploader=uploader,
            duration=duration,
            thumbnail=first.get("cover_url"),
            is_playlist=is_playlist,
            entries=entries,
            webpage_url=url,
        )


# --------------------------------------------------------------------------- #
# Suivi par piste, pour les téléchargements de playlist
# --------------------------------------------------------------------------- #
@dataclass
class PlaylistEntry:
    """État d'une piste individuelle au sein d'un job de playlist.

    Attributes:
        index: Position dans la playlist (1-based, ordre de yt-dlp).
        title: Titre de la piste (peut être mis à jour une fois connu).
        status: État de cette piste (``PENDING``, ``DOWNLOADING``, ``PROCESSING``
            ou ``DONE``). ``PROCESSING`` couvre tout post-traitement après le
            téléchargement brut (conversion de format, métadonnées, miniature,
            sous-titres...).
        stage: Libellé lisible du post-traitement en cours (ex. « Conversion
            audio… »), vide hors ``PROCESSING``. Purement informatif pour l'UI.
        filepath: Chemin du fichier produit, une fois terminé.
    """

    index: int
    title: str
    status: JobStatus = JobStatus.PENDING
    stage: str = ""
    filepath: str = ""


# Un job peut porter des options yt-dlp (YouTube) ou spotdl (Spotify) — le
# reste du code générique (file d'attente, cartes de l'UI) n'accède qu'aux
# attributs communs aux deux (``fmt.label``, ``is_playlist``, ``output_dir``).
DownloadOptionsLike = Union[DownloadOptions, SpotifyDownloadOptions]


# --------------------------------------------------------------------------- #
# Job de téléchargement
# --------------------------------------------------------------------------- #
@dataclass
class DownloadJob:
    """Un téléchargement suivi par la file d'attente.

    Attributes:
        id: Identifiant unique.
        url: URL source.
        options: Options de téléchargement.
        title: Titre affiché (rempli après le probe).
        status: État courant.
        progress: Avancement 0.0–100.0. Pour une playlist, reflète la
            proportion de pistes terminées plutôt que la progression en
            octets de la piste en cours (voir :attr:`playlist_entries`).
        speed: Débit lisible (ex. ``"1.2MiB/s"``).
        speed_bps: Le même débit en octets/s, brut — pour tracer un graphe,
            pas pour l'affichage direct (voir :attr:`speed`).
        eta: Temps restant lisible (ex. ``"00:42"``).
        error: Message d'erreur éventuel.
        filepath: Chemin du fichier produit (une fois terminé). Vide pour un
            job de playlist (chaque piste a son propre fichier, voir
            :attr:`playlist_entries`).
        playlist_entries: État de chaque piste, rempli au fil du
            téléchargement (liste vide si ce n'est pas une playlist).
        playlist_total: Nombre de pistes à télécharger (0 si inconnu/non-playlist).
        playlist_completed: Nombre de pistes terminées.
    """

    id: str
    url: str
    options: DownloadOptionsLike
    title: str = ""
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    speed: str = ""
    speed_bps: float = 0.0
    eta: str = ""
    error: str = ""
    filepath: str = ""
    playlist_entries: list[PlaylistEntry] = field(default_factory=list)
    playlist_total: int = 0
    playlist_completed: int = 0

    @property
    def is_active(self) -> bool:
        """``True`` si un thread est réellement en train d'exécuter ce job.

        Inclut les états transitoires ``PAUSING``/``CANCELLING`` : le thread
        tourne encore, seul l'arrêt est en attente de confirmation.
        """
        return self.status in (
            JobStatus.PROBING,
            JobStatus.DOWNLOADING,
            JobStatus.PROCESSING,
            JobStatus.PAUSING,
            JobStatus.CANCELLING,
        )

"""Configuration applicative (valeurs par défaut, persistance légère).

Les valeurs par défaut peuvent être surchargées par des variables
d'environnement (``YTDL_DOWNLOAD_DIR``, ``YTDL_PORT``, ``YTDL_CONFIG_DIR``),
ce qui permet de configurer le conteneur/l'exécutable sans toucher au code —
utile pour Docker ou tout déploiement où l'on ne veut pas dépendre d'un
dossier utilisateur (``~``) particulier.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def default_download_dir() -> str:
    """Dossier de téléchargement par défaut.

    Priorité à la variable d'environnement ``YTDL_DOWNLOAD_DIR`` (pratique pour
    monter un volume Docker) ; sinon ``~/Downloads`` s'il existe, sinon ``~``.
    """
    env_dir = os.environ.get("YTDL_DOWNLOAD_DIR")
    if env_dir:
        return env_dir
    downloads = Path.home() / "Downloads"
    return str(downloads if downloads.is_dir() else Path.home())


def default_port() -> int:
    """Port par défaut du serveur web, surchageable via ``YTDL_PORT``."""
    try:
        return int(os.environ.get("YTDL_PORT", "8080"))
    except ValueError:
        return 8080


def _config_path() -> Path:
    """Emplacement du fichier de config utilisateur (créé à la volée).

    La variable d'environnement ``YTDL_CONFIG_DIR`` permet de choisir un
    dossier différent de ``~/.config/ytdl`` (utile pour monter un volume
    Docker et conserver les réglages entre redémarrages du conteneur).
    """
    base = os.environ.get("YTDL_CONFIG_DIR") or str(Path.home() / ".config" / "ytdl")
    return Path(base) / "config.json"


@dataclass
class AppConfig:
    """Réglages persistants de l'application.

    Attributes:
        download_dir: Dossier où enregistrer les fichiers.
        filename_template: Gabarit de nommage yt-dlp (voir la doc des « output templates »).
        dark_mode: Thème sombre activé.
        max_concurrent: Nombre de téléchargements simultanés. Modifiable à
            chaud (voir :meth:`ytdl.queue.DownloadQueue.set_max_concurrent`) :
            pas besoin de redémarrer l'application pour l'appliquer.
        port: Port du serveur web NiceGUI.
        clean_titles: Retire des titres les mentions « (Official Video) »,
            « (Clip Officiel) », etc. avant l'enregistrement.
        sleep_interval: Pause en secondes avant chaque requête/téléchargement,
            pour limiter le risque de throttling/blocage par IP (0 = désactivé).
        rate_limit_kbps: Débit maximal en Ko/s (0 = illimité).
        cookies_browser: Navigateur dont utiliser les cookies de session (voir
            :data:`ytdl.models.COOKIE_BROWSERS`), pour accéder aux playlists
            privées (« Liked videos », « Watch Later »…). Vide = désactivé.
        skip_archived: Ne pas re-télécharger une piste déjà obtenue (repérée
            par son identifiant vidéo, pas par son nom de fichier — fiable
            même si le titre a été nettoyé/renommé). Indispensable pour
            reprendre une grosse playlist interrompue sans tout retélécharger.
        player_folder: Dernier dossier chargé dans le lecteur intégré (mode
            natif). Vide = aucun dossier chargé pour l'instant.
        theme: Clé de la palette de couleurs choisie (voir
            :data:`ytdl.ui.theme.THEMES`), indépendante du réglage clair/sombre.
    """

    download_dir: str = field(default_factory=default_download_dir)
    filename_template: str = "%(uploader)s - %(title)s.%(ext)s"
    dark_mode: bool = True
    max_concurrent: int = 2
    port: int = field(default_factory=default_port)
    clean_titles: bool = True
    sleep_interval: float = 0.0
    rate_limit_kbps: int = 0
    cookies_browser: str = ""
    skip_archived: bool = True
    player_folder: str = ""
    theme: str = "violet"

    # ------------------------------------------------------------------ #
    # Archive des téléchargements (anti-doublons)
    # ------------------------------------------------------------------ #
    def archive_path(self) -> str:
        """Fichier d'archive yt-dlp (un identifiant vidéo par ligne) pour ce dossier.

        Colocalisé avec les fichiers téléchargés : si l'on change de dossier
        de destination, on change aussi d'archive (cohérent avec « déjà
        présent dans CE dossier »).
        """
        return str(Path(self.download_dir) / ".ytdl_archive.txt")

    def archive_path_spotify(self) -> str:
        """Fichier d'archive spotdl (une URL de piste Spotify par ligne) pour ce dossier.

        Fichier distinct de :meth:`archive_path` : le format d'archive de
        spotdl (URLs Spotify) n'est pas compatible avec celui de yt-dlp
        (identifiants vidéo).
        """
        return str(Path(self.download_dir) / ".ytdl_archive_spotify.txt")

    # ------------------------------------------------------------------ #
    # Persistance
    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls) -> "AppConfig":
        """Charge la config depuis le disque, ou renvoie les valeurs par défaut."""
        path = _config_path()
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        # On ne garde que les clés connues pour rester robuste aux évolutions.
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        """Écrit la config sur le disque (best-effort, silencieux en cas d'échec)."""
        path = _config_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except OSError:
            pass

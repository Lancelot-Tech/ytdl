"""Détection de ``ffmpeg``.

``ffmpeg`` est indispensable pour :

* extraire/convertir l'audio (MP3, M4A) ;
* fusionner les flux vidéo + audio séparés (nécessaire au-delà de 720p sur YouTube) ;
* intégrer la miniature et les métadonnées.

Sans lui, seuls les téléchargements « progressifs » basse définition fonctionnent.
"""

from __future__ import annotations

import shutil
from functools import lru_cache

INSTALL_HINTS = {
    "darwin": "brew install ffmpeg",
    "linux": "sudo apt install ffmpeg  (ou l'équivalent de votre distribution)",
    "win32": "winget install ffmpeg  (ou https://www.gyan.dev/ffmpeg/builds/)",
}


@lru_cache(maxsize=1)
def ffmpeg_path() -> str | None:
    """Renvoie le chemin de l'exécutable ``ffmpeg`` s'il est trouvé, sinon ``None``."""
    return shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    """``True`` si ``ffmpeg`` est disponible dans le PATH."""
    return ffmpeg_path() is not None


def install_hint(platform: str) -> str:
    """Message d'installation adapté à la plateforme (``sys.platform``)."""
    return INSTALL_HINTS.get(platform, "Installez ffmpeg depuis https://ffmpeg.org/download.html")

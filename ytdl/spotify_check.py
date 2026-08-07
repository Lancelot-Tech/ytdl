"""Détection de ``spotdl``.

``spotdl`` est un outil externe (jamais une dépendance pip du projet — voir
:mod:`ytdl.spotify_downloader`) requis pour télécharger depuis Spotify. Sans
lui, seule la source YouTube fonctionne.
"""

from __future__ import annotations

import shutil
from functools import lru_cache

INSTALL_HINTS = {
    "darwin": "pipx install spotdl  (ou brew install spotdl)",
    "linux": "pipx install spotdl",
    "win32": "pipx install spotdl  (ou pip install --user spotdl)",
}


@lru_cache(maxsize=1)
def spotdl_path() -> str | None:
    """Renvoie le chemin de l'exécutable ``spotdl`` s'il est trouvé, sinon ``None``."""
    return shutil.which("spotdl")


def spotdl_available() -> bool:
    """``True`` si ``spotdl`` est disponible dans le PATH."""
    return spotdl_path() is not None


def install_hint(platform: str) -> str:
    """Message d'installation adapté à la plateforme (``sys.platform``)."""
    return INSTALL_HINTS.get(platform, "Installez spotdl : https://spotdl.readthedocs.io/en/latest/")

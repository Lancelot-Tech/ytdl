"""Détection d'un runtime JavaScript (Node, Deno ou Bun) pour yt-dlp.

YouTube pose un défi JavaScript pour déchiffrer les liens de flux vidéo/audio ;
yt-dlp a besoin d'un runtime JS pour le résoudre (voir
:data:`ytdl.models.YTDLP_JS_CHALLENGE_OPTS`). Sans lui, la plupart des formats
disparaissent et les téléchargements échouent avec « Requested format is not
available », même avec des cookies valides.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from functools import lru_cache

# Version minimale supportée par yt-dlp pour chaque runtime (voir
# yt_dlp.utils._jsruntime.*JsRuntime.MIN_SUPPORTED_VERSION) : en dessous,
# yt-dlp l'ignore silencieusement, comme s'il n'était pas installé.
_MIN_VERSIONS: dict[str, tuple[int, int, int]] = {
    "node": (22, 0, 0),
    "deno": (2, 3, 0),
    "bun": (1, 2, 11),
}

INSTALL_HINTS = {
    "darwin": "brew install node",
    "linux": "sudo apt install nodejs  (ou l'équivalent de votre distribution ; version >= 22 requise)",
    "win32": "winget install OpenJS.NodeJS.LTS",
}


def _version_tuple(text: str) -> tuple[int, ...]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(g) for g in match.groups()) if match else ()


@lru_cache(maxsize=1)
def js_runtime_name() -> str | None:
    """Nom du premier runtime JS trouvé et assez récent pour yt-dlp, sinon ``None``."""
    for name, min_version in _MIN_VERSIONS.items():
        path = shutil.which(name)
        if not path:
            continue
        try:
            result = subprocess.run(
                [path, "--version"], capture_output=True, text=True, timeout=5, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if _version_tuple(result.stdout) >= min_version:
            return name
    return None


def js_runtime_available() -> bool:
    """``True`` si un runtime JS suffisant pour yt-dlp est disponible."""
    return js_runtime_name() is not None


def install_hint(platform: str) -> str:
    """Message d'installation adapté à la plateforme (``sys.platform``)."""
    return INSTALL_HINTS.get(platform, "Installez Node.js (>= 22) depuis https://nodejs.org/")

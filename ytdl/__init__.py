"""ytdl — téléchargeur vidéo/audio moderne (NiceGUI + yt-dlp).

Le paquet est organisé en deux couches nettement séparées :

* **Cœur** (sans UI, testable) : :mod:`ytdl.models`, :mod:`ytdl.downloader`,
  :mod:`ytdl.queue`, :mod:`ytdl.config`, :mod:`ytdl.ffmpeg_check`.
* **Interface** : le sous-paquet :mod:`ytdl.ui` (NiceGUI).

Lancer l'application ::

    python -m ytdl            # web (navigateur)
    python -m ytdl --native   # fenêtre native
"""

from __future__ import annotations

__version__ = "2.0.0"

__all__ = ["__version__"]

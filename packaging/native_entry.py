"""Point d'entrée dédié au binaire packagé (Windows/macOS/Linux).

Contrairement à ``python -m ytdl`` (mode web par défaut, flexible en CLI), un
exécutable double-cliqué doit ouvrir directement une fenêtre, sans terminal ni
navigateur. C'est pourquoi ce script — et non ``main.py`` — est celui passé à
``nicegui-pack`` dans :mod:`packaging.build_binary`.
"""

from __future__ import annotations

from ytdl.ui import run

if __name__ == "__main__":
    run(native=True)

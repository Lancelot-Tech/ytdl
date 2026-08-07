"""Compatibilité ascendante : ``python main.py`` lance la nouvelle appli.

L'application a été réorganisée en paquet :mod:`ytdl`. Ce fichier ne fait que
rediriger vers son point d'entrée pour ne pas casser l'ancienne commande.

    python main.py            # web (navigateur)
    python main.py --native   # fenêtre native

Équivalent moderne : ``python -m ytdl`` (voir le README).
"""

from __future__ import annotations

from ytdl.__main__ import main

if __name__ == "__main__":
    main()

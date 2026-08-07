"""Point d'entrée en ligne de commande : ``python -m ytdl``.

Options :
    --native        Ouvre une fenêtre native au lieu du navigateur.
    --port PORT     Port du serveur web (défaut : celui de la config, 8080).
    --no-show       Ne pas ouvrir automatiquement le navigateur (mode web).
"""

from __future__ import annotations

import argparse

from . import __version__
from .ui import run


def build_parser() -> argparse.ArgumentParser:
    """Construit l'analyseur d'arguments de la CLI."""
    parser = argparse.ArgumentParser(
        prog="ytdl",
        description="Téléchargeur vidéo/audio moderne (NiceGUI + yt-dlp).",
    )
    parser.add_argument("--native", action="store_true", help="Ouvrir une fenêtre native (pywebview).")
    parser.add_argument("--port", type=int, default=None, help="Port du serveur web.")
    parser.add_argument("--no-show", action="store_true", help="Ne pas ouvrir le navigateur automatiquement.")
    parser.add_argument("--version", action="version", version=f"ytdl {__version__}")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Analyse les arguments et lance l'interface."""
    args = build_parser().parse_args(argv)
    run(native=args.native, port=args.port, show=not args.no_show)


if __name__ == "__main__":
    main()

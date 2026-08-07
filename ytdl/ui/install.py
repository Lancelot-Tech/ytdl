"""Contenu de la section « Installation » : comment déployer ytdl ailleurs.

Même présentation que le centre d'aide (cartes + popup), pour permettre de
partager rapidement comment lancer l'application sur une autre machine —
Docker, AppImage (Linux), exécutable natif ou depuis les sources.
"""

from __future__ import annotations

from nicegui import ui

from . import components

DOCKER_RUN = """docker build -t ytdl .
docker run -d --name ytdl -p 8080:8080 \\
  -v ~/Downloads:/downloads \\
  -v ytdl-config:/config \\
  ytdl"""

DOCKER_COMPOSE = "docker compose up -d"

APPIMAGE_BUILD = """# Sur une machine Linux, depuis les sources :
./packaging/build-appimage.sh
chmod +x dist/ytdl-*.AppImage
./dist/ytdl-*.AppImage"""

BINARY_BUILD = """# Sur la machine cible (Windows, macOS ou Linux) :
python -m venv .venv && source .venv/bin/activate  # Windows : .venv\\Scripts\\activate
pip install -r requirements.txt
python packaging/build_binary.py
# Résultat : dist/ytdl/ (dossier à distribuer, ou dist/ytdl.app sur macOS)"""

FROM_SOURCE = """git clone <url-du-repo> ytdl && cd ytdl
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m ytdl              # mode web
python -m ytdl --native     # fenêtre native"""


def _render_docker() -> None:
    ui.markdown(
        "Le plus simple pour un serveur, un NAS ou toute machine avec Docker : "
        "**ffmpeg et Node.js sont déjà inclus** dans l'image, rien d'autre à installer."
    )
    ui.code(DOCKER_RUN, language="bash").classes("w-full")
    ui.markdown("Ou avec **docker-compose** (persistance automatique des téléchargements et réglages) :")
    ui.code(DOCKER_COMPOSE, language="bash").classes("w-full")
    ui.markdown(
        "Réglages via variables d'environnement : `YTDL_DOWNLOAD_DIR`, `YTDL_CONFIG_DIR`, `YTDL_PORT`."
    )


def _render_appimage() -> None:
    ui.markdown(
        "Sur Linux, un seul fichier exécutable, sans installation ni gestionnaire de paquets."
    )
    ui.code(APPIMAGE_BUILD, language="bash").classes("w-full")
    ui.markdown("Le script télécharge `appimagetool` si besoin et construit l'AppImage à partir des sources.")


def _render_binaries() -> None:
    ui.markdown("Binaire autonome pour Windows, macOS ou Linux — pas besoin d'installer Python sur la machine cible.")
    ui.code(BINARY_BUILD, language="bash").classes("w-full")
    ui.markdown(
        "S'appuie sur `nicegui-pack` (PyInstaller préconfiguré). Le binaire s'ouvre "
        "directement en fenêtre native, sans terminal."
    )


def _render_source() -> None:
    ui.markdown("Pour développer, personnaliser ou simplement lancer l'application telle quelle.")
    ui.code(FROM_SOURCE, language="bash").classes("w-full")
    ui.markdown(
        "Nécessite Python 3.9+, `ffmpeg` et un runtime JS (Node.js 22+, Deno ou Bun) "
        "installés sur le système (voir la section **Aide**)."
    )


INSTALL_SECTIONS: list[tuple[str, str, str, "ui.element"]] = [
    ("Docker", "layers", "Conteneurisé, ffmpeg + Node.js inclus — idéal pour un serveur.", _render_docker),
    ("AppImage (Linux)", "terminal", "Un seul fichier exécutable, sans installation.", _render_appimage),
    ("Exécutable natif", "apps", "Binaire autonome Windows, macOS ou Linux.", _render_binaries),
    ("Depuis les sources", "code", "Pour développer ou personnaliser l'application.", _render_source),
]


def build_install_panel() -> None:
    """Construit le contenu de la section « Installation » : une grille de cartes."""
    with ui.column().classes("w-full gap-4 ytdl-fade-in"):
        with ui.grid(columns=2).classes("w-full gap-4"):
            for title, icon, teaser, render in INSTALL_SECTIONS:
                components.popup_card(title, icon, teaser, render)

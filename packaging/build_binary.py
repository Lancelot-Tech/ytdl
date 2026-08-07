"""Construit un exécutable autonome pour la plateforme courante.

Usage ::

    python packaging/build_binary.py

Produit un binaire natif dans ``dist/`` — pas de multiplateforme (Windows
produit un ``.exe``, macOS une ``.app``, Linux un binaire ELF) : ce script
doit être exécuté séparément sur chaque OS cible. Sous le capot, il appelle
``nicegui-pack`` (fourni par NiceGUI, un wrapper autour de PyInstaller
préconfiguré pour embarquer ses assets statiques).
"""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "packaging" / "native_entry.py"
ICON = ROOT / "assets" / "shuba-duck-dance-pixel-pixelated.ico"


def main() -> None:
    cmd = [
        sys.executable, "-m", "nicegui.scripts.pack",
        "--name", "ytdl",
        "--onedir",       # démarrage plus rapide que --onefile ; à zipper pour distribuer
        "--windowed",     # pas de console, cohérent avec le mode natif
        "--noconfirm",
        str(ENTRY),
    ]
    # PyInstaller attend un .icns sur macOS ; on ne fournit l'icône que sur
    # Windows (.ico) où le format correspond, pour éviter un échec de build.
    if platform.system() == "Windows" and ICON.is_file():
        cmd[-1:-1] = ["--icon", str(ICON)]

    print("→", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)
    print("\nTerminé. Résultat dans dist/ytdl/ (voir dist/ytdl/ytdl[.exe]).")


if __name__ == "__main__":
    main()

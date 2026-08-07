#!/usr/bin/env bash
# Construit un AppImage Linux à partir des sources. Doit tourner sur Linux
# (télécharge appimagetool, un binaire Linux). Résultat : dist/ytdl-<arch>.AppImage
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Ce script doit être exécuté sur Linux (pour produire un AppImage)." >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
ARCH="$(uname -m)"

echo "==> 1/4 Build de l'exécutable (PyInstaller via nicegui-pack)"
python packaging/build_binary.py

echo "==> 2/4 Assemblage de l'AppDir"
APPDIR="$ROOT_DIR/build/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -r dist/ytdl/. "$APPDIR/usr/bin/"
cp packaging/ytdl.desktop "$APPDIR/ytdl.desktop"

ICON_SRC="assets/shuba-duck-dance-pixel-pixelated.ico"
ICON_DST="$APPDIR/ytdl.png"
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -y -loglevel error -i "$ICON_SRC" "$ICON_DST"
else
  echo "!! ffmpeg introuvable : l'AppImage sera construite sans icône." >&2
fi

cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "$HERE/usr/bin/ytdl" "$@"
EOF
chmod +x "$APPDIR/AppRun"

echo "==> 3/4 Récupération d'appimagetool (si absent)"
APPIMAGETOOL="$ROOT_DIR/build/appimagetool"
if [[ ! -x "$APPIMAGETOOL" ]]; then
  curl -L -o "$APPIMAGETOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
  chmod +x "$APPIMAGETOOL"
fi

echo "==> 4/4 Construction de l'AppImage"
mkdir -p dist
# --appimage-extract-and-run : fonctionne même sans FUSE (CI, conteneurs).
"$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" "dist/ytdl-${ARCH}.AppImage"

echo
echo "Terminé : dist/ytdl-${ARCH}.AppImage"
echo "Rendez-la exécutable puis lancez-la :"
echo "  chmod +x dist/ytdl-${ARCH}.AppImage && ./dist/ytdl-${ARCH}.AppImage"

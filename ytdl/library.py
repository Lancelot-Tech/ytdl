"""Bibliothèque locale pour le lecteur intégré (mode natif uniquement).

Scanne un dossier choisi par l'utilisateur et liste ses fichiers audio/vidéo
lisibles directement dans l'app — indépendant du reste du cœur (aucun lien
avec le téléchargement), volontairement simple : pas de récursion dans les
sous-dossiers, pas de base de données, juste un scan à la demande.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus", ".aac", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v"}
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


@dataclass
class Track:
    """Une piste locale trouvée dans le dossier chargé."""

    path: Path
    title: str
    is_video: bool
    duration: Optional[float] = None  # secondes ; None si indéterminée

    @property
    def id(self) -> str:
        """Identifiant stable pour cette session (le chemin absolu suffit)."""
        return str(self.path)

    @property
    def duration_str(self) -> str:
        """Durée formatée ``M:SS`` (vide si inconnue)."""
        if self.duration is None:
            return ""
        minutes, seconds = divmod(int(self.duration), 60)
        return f"{minutes}:{seconds:02d}"


def _probe_duration(path: Path) -> Optional[float]:
    """Meilleure estimation de la durée d'un fichier (best-effort, jamais fatal)."""
    try:
        import mutagen

        info = mutagen.File(path)
        if info is not None and info.info is not None:
            return float(info.info.length)
    except Exception:  # pragma: no cover - dépend des formats/fichiers réels
        pass
    return None


def extract_cover_data_uri(path: Path) -> Optional[str]:
    """Pochette embarquée dans le fichier (ID3 APIC pour MP3, ``covr`` pour
    MP4/M4A), en data URI directement affichable par :func:`ui.image`.

    Best-effort : ``None`` si le format n'a pas de pochette embarquée ou n'en
    contient pas (assez fréquent, ce n'est pas une erreur).
    """
    try:
        import base64

        import mutagen

        audio = mutagen.File(path)
        if audio is None:
            return None

        tags = getattr(audio, "tags", None)
        if tags is not None and hasattr(tags, "getall"):
            apics = tags.getall("APIC")
            if apics:
                mime = apics[0].mime or "image/jpeg"
                data = base64.b64encode(apics[0].data).decode("ascii")
                return f"data:{mime};base64,{data}"

        covers = audio.get("covr") if hasattr(audio, "get") else None
        if covers:
            from mutagen.mp4 import MP4Cover

            cover = covers[0]
            mime = "image/png" if cover.imageformat == MP4Cover.FORMAT_PNG else "image/jpeg"
            data = base64.b64encode(bytes(cover)).decode("ascii")
            return f"data:{mime};base64,{data}"
    except Exception:  # pragma: no cover - dépend des formats/fichiers réels
        pass
    return None


def scan_library(folder: str) -> list[Track]:
    """Liste les pistes audio/vidéo d'un dossier (non récursif), triées par nom.

    Args:
        folder: Chemin du dossier à scanner.

    Returns:
        Les pistes trouvées, ou une liste vide si le dossier est invalide.
    """
    root = Path(folder).expanduser()
    if not root.is_dir():
        return []
    tracks: list[Track] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_file():
            continue
        ext = entry.suffix.lower()
        if ext not in MEDIA_EXTENSIONS:
            continue
        tracks.append(
            Track(
                path=entry,
                title=entry.stem,
                is_video=ext in VIDEO_EXTENSIONS,
                duration=_probe_duration(entry),
            )
        )
    return tracks

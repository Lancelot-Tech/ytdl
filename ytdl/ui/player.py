"""Lecteur audio/vidéo intégré (mode natif uniquement) : charge un dossier
local et lit ses pistes, façon Spotify — indépendant du téléchargement.

La lecture s'appuie sur les éléments HTML5 natifs de NiceGUI (:func:`ui.audio`
/:func:`ui.video`), qui savent servir un fichier local directement (avec
support des requêtes de plage HTTP, donc de l'avance/recul) sans qu'on ait à
écrire de route de streaming nous-mêmes.

L'état de lecture (:class:`PlayerController`) est séparé de son affichage :
le mode natif est une page unique où l'on bascule des sections plutôt que de
naviguer entre plusieurs pages (voir ``ytdl.ui.app``), justement pour que
l'élément ``<audio>`` — et donc la musique — survive au changement de section.
Ça permet aussi d'avoir de mini-contrôles dans la nav, en plus de la barre
complète de la section Lecteur, pilotant tous les deux le même lecteur.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import webview
from nicegui import app as ng_app
from nicegui import ui

from .. import library
from ..config import AppConfig
from . import components


def _format_seconds(seconds: float) -> str:
    minutes, secs = divmod(max(0, int(seconds)), 60)
    return f"{minutes}:{secs:02d}"


class PlayerController:
    """État de lecture + logique, sans affichage.

    Créé une seule fois par session native ; plusieurs morceaux d'UI (barre
    complète de la page Lecteur, mini-contrôles de la nav) s'y abonnent via
    :meth:`on_change` pour rester synchronisés entre eux.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.tracks: list[library.Track] = (
            library.scan_library(config.player_folder) if config.player_folder else []
        )
        self.index = -1
        self.playing = False
        self.volume = 0.8
        self.element: Optional[ui.audio] = None
        # Conteneur stable pour l'élément <audio>/<video> actif : construit une
        # fois, en dehors des sections basculées, pour ne jamais être détruit
        # (donc jamais couper le son) quand on change de section.
        self.media_holder = ui.column().classes("hidden")
        self._listeners: list[Callable[[], None]] = []

    def on_change(self, callback: Callable[[], None]) -> None:
        """Enregistre un callback appelé à chaque changement d'état (piste, lecture/pause...)."""
        self._listeners.append(callback)

    def _notify(self) -> None:
        for cb in self._listeners:
            cb()

    # ------------------------------------------------------------------ #
    # Lecture
    # ------------------------------------------------------------------ #
    def current_track(self) -> Optional[library.Track]:
        return self.tracks[self.index] if 0 <= self.index < len(self.tracks) else None

    def load_folder(self, folder: str) -> None:
        self.config.player_folder = folder
        self.config.save()
        self.tracks = library.scan_library(folder)
        self.index = -1
        self._stop_playback()
        self._notify()

    def play_index(self, i: int) -> None:
        if not 0 <= i < len(self.tracks):
            return
        self.index = i
        track = self.tracks[i]
        self.media_holder.clear()
        with self.media_holder:
            element = (ui.video if track.is_video else ui.audio)(track.path, controls=False, autoplay=True)
            element.props("id=ytdl-player-media")
            element.on("ended", lambda: self.skip(1))
        self.element = element
        self.playing = True
        # Chaque piste recrée un tout nouvel élément <audio>/<video> (repart
        # donc du volume par défaut du navigateur, 100%) : on réapplique le
        # volume choisi, sans quoi il "s'oublie" à chaque changement de piste.
        self.set_volume(self.volume * 100)
        self._notify()

    def toggle_play(self) -> None:
        if self.element is None:
            if self.tracks:
                self.play_index(0)
            return
        if self.playing:
            self.element.pause()
        else:
            self.element.play()
        self.playing = not self.playing
        self._notify()

    def skip(self, delta: int) -> None:
        if not self.tracks:
            return
        new_index = self.index + delta
        if 0 <= new_index < len(self.tracks):
            self.play_index(new_index)
        elif delta > 0:
            self._stop_playback()  # fin de la liste : on s'arrête plutôt que de boucler
            self._notify()

    def _stop_playback(self) -> None:
        self.media_holder.clear()
        self.element = None
        self.playing = False

    def set_volume(self, value: float) -> None:
        self.volume = max(0.0, min(1.0, value / 100))
        ui.run_javascript(
            f"const el = document.getElementById('ytdl-player-media'); if (el) el.volume = {self.volume};"
        )

    def seek_to_fraction(self, fraction: float) -> None:
        track = self.current_track()
        if self.element is not None and track is not None and track.duration:
            self.element.seek(max(0.0, min(1.0, fraction)) * track.duration)

    async def poll_current_time(self) -> float:
        """Position de lecture actuelle (secondes), mesurée côté navigateur."""
        if self.element is None:
            return 0.0
        try:
            return await ui.run_javascript(
                "document.getElementById('ytdl-player-media')?.currentTime || 0", timeout=2.0
            )
        except Exception:
            return 0.0


# --------------------------------------------------------------------------- #
# Mini-lecteur flottant (visible sur n'importe quelle section)
# --------------------------------------------------------------------------- #
def build_mini_controls(controller: PlayerController) -> None:
    """Précédent/lecture-pause/suivant compacts, en pastille flottante à part
    (même traitement que le bouton jour/nuit — pas fondu dans la pilule de
    nav principale, voir ``.ytdl-player-mini`` dans theme.py).

    N'apparaît que si une piste a déjà été chargée — pas de contrôles
    « morts » tant qu'on n'a rien lancé depuis la section Lecteur.
    """
    with ui.column().classes("ytdl-player-mini gap-0.5") as controls:
        with ui.row().classes("items-center gap-0.5"):
            ui.button(icon="skip_previous", on_click=lambda: controller.skip(-1)).props("flat round dense size=sm")
            play_btn = ui.button(icon="play_arrow", on_click=lambda: controller.toggle_play()).props(
                "flat round dense size=sm color=primary"
            )
            ui.button(icon="skip_next", on_click=lambda: controller.skip(1)).props("flat round dense size=sm")
        # Titre en défilement (façon bandeau) : sous les boutons, pour que la
        # pastille retrouve à peu près la même hauteur que la pilule de nav
        # (icône + libellé) au lieu de paraître écrasée à côté.
        with ui.element("div").classes("ytdl-marquee"):
            title_label = ui.label("").classes("ytdl-marquee-text")

    def refresh() -> None:
        # Pas de contrôles "morts" tant qu'aucune piste n'a été lancée.
        track = controller.current_track()
        controls.set_visibility(track is not None)
        play_btn.props(f"icon={'pause' if controller.playing else 'play_arrow'}")
        if track is not None:
            title_label.set_text(track.title)

    controller.on_change(refresh)
    refresh()


# --------------------------------------------------------------------------- #
# Section complète (liste de pistes + barre de contrôle détaillée)
# --------------------------------------------------------------------------- #
def build_player_section(controller: PlayerController) -> None:
    """Construit le contenu de la section Lecteur : liste + barre détaillée."""
    config = controller.config
    row_handles: dict[str, ui.row] = {}

    with ui.column().classes("w-full gap-4 pb-28"):
        with ui.row().classes("w-full items-center gap-3 flex-wrap"):
            components.section_title("Lecteur")
            ui.space()
            folder_label = ui.label(config.player_folder or "Aucun dossier chargé").classes(
                "text-xs opacity-60 truncate max-w-[20rem]"
            )
            ui.button("Choisir un dossier", icon="folder_open", on_click=lambda: choose_folder()).props(
                "unelevated color=primary"
            )

        empty_state = ui.column().classes("w-full items-center py-16 gap-2 opacity-60")
        with empty_state:
            ui.icon("library_music").classes("text-5xl")
            ui.label("Choisis un dossier pour voir tes pistes ici.")

        # Hauteur bornée + défilement propre à la liste (comme la file
        # d'attente) : la page ne défile pas dans son ensemble en mode
        # natif, mais une liste de plusieurs centaines de pistes doit quand
        # même pouvoir être parcourue.
        track_container = ui.column().classes("w-full gap-1 max-h-[52vh] overflow-y-auto pr-1")

    # Trois cartes détachées sur une même ligne plutôt qu'une seule barre
    # continue : lecture en cours (pochette + titre) | contrôles + progression
    # (la plus large) | volume.
    with ui.row().classes("ytdl-player-bar items-stretch") as player_bar:
        with ui.card().classes("ytdl-glass p-3 items-center justify-center gap-2 no-wrap shrink-0 w-56"):
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                cover_image = ui.image().classes("w-10 h-10 rounded-lg object-cover shrink-0")
                cover_placeholder = ui.icon("album").classes("text-2xl opacity-40 shrink-0")
                now_label = ui.label("Aucune piste sélectionnée").classes("text-sm font-medium truncate min-w-0")
        cover_image.set_visibility(False)

        with ui.card().classes("ytdl-glass p-3 justify-center gap-1 flex-grow"):
            with ui.row().classes("w-full items-center gap-3 no-wrap"):
                ui.button(icon="skip_previous", on_click=lambda: controller.skip(-1)).props("flat round dense")
                play_btn = ui.button(icon="play_arrow", on_click=lambda: controller.toggle_play()).props(
                    "unelevated round color=primary"
                )
                ui.button(icon="skip_next", on_click=lambda: controller.skip(1)).props("flat round dense")
                time_label = ui.label("0:00").classes("ytdl-mono text-xs opacity-60 shrink-0")
                seek_slider = ui.slider(min=0, max=100, value=0, on_change=lambda e: on_seek(e.value)).props(
                    "dense"
                ).classes("flex-grow")
                duration_label = ui.label("0:00").classes("ytdl-mono text-xs opacity-60 shrink-0")

        # items-center + justify-center : sans les deux, la ligne icône+curseur
        # (plus courte que les cartes voisines une fois la rangée étirée à la
        # même hauteur) restait collée en haut de la carte au lieu d'être
        # centrée dedans.
        with ui.card().classes("ytdl-glass p-3 items-center justify-center gap-2 no-wrap shrink-0"):
            with ui.row().classes("items-center gap-2 no-wrap"):
                ui.icon("volume_up").classes("text-lg opacity-70")
                ui.slider(
                    min=0,
                    max=100,
                    value=round(controller.volume * 100),
                    on_change=lambda e: controller.set_volume(e.value),
                ).props("dense").classes("w-28")

    # ------------------------------------------------------------------ #
    # Rendu de la liste
    # ------------------------------------------------------------------ #
    def render_tracks() -> None:
        track_container.clear()
        row_handles.clear()
        tracks = controller.tracks
        empty_state.set_visibility(not tracks)
        player_bar.set_visibility(bool(tracks))
        with track_container:
            for i, track in enumerate(tracks):
                with ui.row().classes(
                    "w-full items-center gap-3 px-3 py-2 rounded-lg cursor-pointer ytdl-track-row no-wrap"
                ).on("click", lambda _, i=i: controller.play_index(i)) as row:
                    ui.icon("music_video" if track.is_video else "music_note").classes(
                        "text-lg opacity-70 shrink-0"
                    )
                    ui.label(track.title).classes("flex-grow truncate text-sm")
                    ui.label(track.duration_str).classes("ytdl-mono text-xs opacity-60 shrink-0")
                row_handles[track.id] = row
        highlight_current()

    def highlight_current() -> None:
        for row in row_handles.values():
            row.classes(remove="ytdl-track-row-active")
        track = controller.current_track()
        if track is not None and track.id in row_handles:
            row_handles[track.id].classes(add="ytdl-track-row-active")

    render_tracks()

    # ------------------------------------------------------------------ #
    # Choix du dossier
    # ------------------------------------------------------------------ #
    async def choose_folder() -> None:
        if not ng_app.native.main_window:
            ui.notify("Le sélecteur de dossier n'est disponible qu'en mode fenêtre native.", type="warning")
            return
        result = await ng_app.native.main_window.create_file_dialog(
            dialog_type=webview.FileDialog.FOLDER,
            directory=config.player_folder or str(Path.home()),
        )
        if not result:
            return
        controller.load_folder(result[0])
        folder_label.set_text(result[0])
        render_tracks()
        if not controller.tracks:
            ui.notify("Aucun fichier audio/vidéo trouvé dans ce dossier.", type="warning")

    # ``seek_slider.value = ...`` (mise à jour programmatique, pour refléter la
    # position de lecture) déclenche le même événement ``on_change`` qu'un
    # vrai glissement de l'utilisateur — sans ce garde-fou, la mise à jour de
    # la position (chaque seconde, voir poll_progress) rappelait `.seek()` en
    # continu sur l'élément audio, ce qui causait la lecture saccadée.
    suppressing_seek_echo = False

    def set_seek_value(value: float) -> None:
        nonlocal suppressing_seek_echo
        suppressing_seek_echo = True
        seek_slider.value = value
        suppressing_seek_echo = False

    def on_seek(value: float) -> None:
        if suppressing_seek_echo:
            return
        controller.seek_to_fraction(value / 100)

    # ------------------------------------------------------------------ #
    # Réaction aux changements d'état du contrôleur
    # ------------------------------------------------------------------ #
    def refresh() -> None:
        track = controller.current_track()
        play_btn.props(f"icon={'pause' if controller.playing else 'play_arrow'}")
        highlight_current()
        if track is None:
            now_label.set_text("Aucune piste sélectionnée")
            time_label.set_text("0:00")
            duration_label.set_text("0:00")
            set_seek_value(0)
            cover_image.set_visibility(False)
            cover_placeholder.set_visibility(True)
            return
        now_label.set_text(track.title)
        time_label.set_text("0:00")
        duration_label.set_text(track.duration_str or "?")
        set_seek_value(0)
        cover = library.extract_cover_data_uri(track.path)
        cover_image.set_visibility(cover is not None)
        cover_placeholder.set_visibility(cover is None)
        if cover:
            cover_image.set_source(cover)

    controller.on_change(refresh)
    refresh()

    async def poll_progress() -> None:
        track = controller.current_track()
        if track is None:
            return
        current = await controller.poll_current_time()
        time_label.set_text(_format_seconds(current))
        if track.duration:
            set_seek_value(max(0.0, min(100.0, current / track.duration * 100)))

    ui.timer(1.0, poll_progress)

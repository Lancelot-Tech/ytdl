"""Assemblage de l'interface NiceGUI et lancement (web ou natif).

Le point d'entrée public est :func:`run`. La logique métier vit dans le cœur
(:mod:`ytdl.downloader`, :mod:`ytdl.queue`) ; ce module ne fait que présenter
l'état et transmettre les actions de l'utilisateur.

Dans les deux modes, l'interface tient sur une seule page NiceGUI (jamais de
vrai rechargement) : en web c'est un portfolio à sections ancrées et
défilement classique ; en natif, la nav bascule entre des sections cachées/
affichées en Python plutôt que de naviguer entre des ancres — indispensable
pour que le lecteur audio intégré (:mod:`ytdl.ui.player`) continue de jouer
quand on change de section, ce qu'un vrai rechargement de page couperait.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from nicegui import app as ng_app
from nicegui import run as ng_run
from nicegui import ui

from ..config import AppConfig
from ..downloader import Downloader
from ..ffmpeg_check import ffmpeg_available, install_hint
from ..jsruntime_check import install_hint as js_install_hint, js_runtime_available
from ..models import (
    AUDIO_QUALITIES,
    COOKIE_BROWSERS,
    SPOTIFY_BITRATES,
    VIDEO_QUALITIES,
    DownloadOptions,
    JobStatus,
    MediaFormat,
    SpotifyDownloadOptions,
    SpotifyFormat,
    spotify_url_is_multi_track,
    url_has_playlist_param,
)
from ..queue import DownloadQueue
from ..spotify_check import install_hint as spotify_install_hint, spotdl_available
from ..spotify_downloader import CancelToken, ProbeCancelled, SpotifyDownloader
from . import components, help as help_ui, install as install_ui, player as player_ui, theme

_ASSET_ICON = Path(__file__).resolve().parent.parent.parent / "assets" / "shuba-duck-dance-pixel-pixelated.ico"

# Icône Material + libellé pour chaque tuile de la grille de formats.
_FORMAT_TILES: list[tuple[MediaFormat, str]] = [
    (MediaFormat.MP4, "movie"),
    (MediaFormat.WEBM, "theaters"),
    (MediaFormat.MP3, "music_note"),
    (MediaFormat.M4A, "audiotrack"),
    (MediaFormat.BEST_VIDEO, "high_quality"),
    (MediaFormat.BEST_AUDIO, "graphic_eq"),
]

# Icône Material + libellé pour chaque tuile de la grille de formats Spotify.
_SPOTIFY_FORMAT_TILES: list[tuple[SpotifyFormat, str]] = [
    (SpotifyFormat.MP3, "music_note"),
    (SpotifyFormat.FLAC, "high_quality"),
    (SpotifyFormat.OGG, "audiotrack"),
    (SpotifyFormat.OPUS, "graphic_eq"),
    (SpotifyFormat.M4A, "audiotrack"),
    (SpotifyFormat.WAV, "waves"),
]

# Icône, libellé, clé de section de chaque item de la nav (partagée par les
# deux modes : ancre + scroll-spy en web, bascule de section en natif).
# « Télécharger » mène à une section qui contient à la fois le formulaire et
# la file d'attente (pas d'entrée séparée : elles sont au même niveau).
_NAV_ITEMS: list[tuple[str, str, str, str]] = [
    ("home", "Accueil", "home", "home"),
    ("download", "Télécharger", "download", "workspace"),
    ("settings", "Réglages", "settings", "settings"),
    ("help", "Aide", "help", "help"),
    ("cloud_download", "Installation", "install", "install"),
]

# Le lecteur intégré n'a de sens qu'en fenêtre native (accès direct au
# système de fichiers via le sélecteur de dossier natif) : absent du mode web.
_NATIVE_ONLY_NAV_ITEMS: list[tuple[str, str, str, str]] = [
    ("library_music", "Lecteur", "player", "player"),
]


def _open_folder(path: str) -> None:
    """Ouvre le dossier contenant ``path`` dans l'explorateur de fichiers du système."""
    folder = str(Path(path).expanduser().parent if Path(path).suffix else Path(path).expanduser())
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", folder], check=False)
        elif sys.platform.startswith("win"):
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", folder], check=False)
    except Exception:
        ui.notify("Impossible d'ouvrir le dossier.", type="warning")


def _play_file(filepath: str) -> None:
    """Ouvre ``filepath`` avec l'application par défaut du système (lecture)."""
    if not filepath:
        ui.notify("Fichier introuvable.", type="warning")
        return
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", filepath], check=False)
        elif sys.platform.startswith("win"):
            os.startfile(filepath)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", filepath], check=False)
    except Exception:
        ui.notify("Impossible de lire ce fichier.", type="warning")


def build_page(
    config: AppConfig,
    downloader: Downloader,
    spotify_downloader: SpotifyDownloader,
    queue: DownloadQueue,
    native: bool = False,
) -> None:
    """Construit la page complète de l'application pour un client connecté.

    En mode web : une seule page défilante, nav flottante + sections ancrées
    (Accueil, Espace de travail, Réglages, Aide, Installation), à la manière
    d'un portfolio.

    En mode natif (fenêtre pywebview) : toujours une seule page, mais la nav
    bascule entre des sections cachées/affichées en Python (voir
    :func:`_build_native_page`) plutôt que de défiler ou de naviguer entre
    plusieurs pages — indispensable pour que le lecteur intégré continue de
    jouer quand on change de section.
    """
    theme.apply(config.dark_mode, theme_key=config.theme, native=native)

    if native:
        _build_native_page(config, downloader, spotify_downloader, queue)
        return

    # État local de la page (aperçu du dernier « probe »).
    preview: dict[str, object] = {"info": None}
    spotify_preview: dict[str, object] = {"info": None}

    with ui.column().classes("ytdl-bg w-full items-center gap-0 p-0"):
        _build_nav(config)
        with ui.column().classes(_page_wrapper_classes(False)):
            _build_hero()
            _build_workspace(config, downloader, spotify_downloader, queue, preview, spotify_preview)
            _build_settings_section(config, queue)
            _build_help_section()
            _build_install_section()


def _build_native_page(
    config: AppConfig, downloader: Downloader, spotify_downloader: SpotifyDownloader, queue: DownloadQueue
) -> None:
    """Page unique du mode natif : nav + mini-contrôles du lecteur, sections
    basculées en Python (jamais de rechargement — voir le docstring du module).
    """
    preview: dict[str, object] = {"info": None}
    spotify_preview: dict[str, object] = {"info": None}
    controller = player_ui.PlayerController(config)
    sections: dict[str, ui.element] = {}
    nav_buttons: dict[str, ui.element] = {}
    # Incrémenté à chaque appel de show_section (utilisateur ou automatique) :
    # sert à _autofit_native_window_once pour détecter si l'utilisateur a
    # cliqué pendant la mesure au démarrage, auquel cas elle ne doit pas
    # écraser ce choix en revenant à l'accueil (voir son docstring).
    nav_state = {"version": 0}

    def show_section(key: str) -> None:
        nav_state["version"] += 1
        for section_key, element in sections.items():
            element.set_visibility(section_key == key)
        for nav_key, button in nav_buttons.items():
            button.classes(add="active" if nav_key == key else None, remove=None if nav_key == key else "active")

    with ui.column().classes("ytdl-bg w-full items-center gap-0 p-0"):
        with ui.row().classes("ytdl-nav"):
            for icon, label, key, _section_key in _NAV_ITEMS + _NATIVE_ONLY_NAV_ITEMS:
                nav_buttons[key] = components.nav_button(icon, label, lambda k=key: show_section(k))
        # Pastille à part (comme le bouton jour/nuit), pas fondue dans la nav.
        player_ui.build_mini_controls(controller)
        theme_state = _build_theme_controls(config)

        with ui.column().classes(_page_wrapper_classes(True)):
            with ui.column().classes("w-full gap-8") as home_section:
                _build_hero()
                _build_native_home_extras(config, queue, show_section, theme_state)
            sections["home"] = home_section

            # Contrairement aux autres sections natives, celle-ci peut désormais
            # dépasser la hauteur de la fenêtre (deux cartes de téléchargement
            # empilées, YouTube + Spotify, à côté de la file d'attente) — sans
            # défilement propre, tout ce qui dépasse serait purement inaccessible
            # (la page elle-même ne défile jamais en mode natif, voir
            # `.ytdl-native` dans ytdl/ui/theme.py). Même recette que la liste
            # de pistes du Lecteur : un `max-height` en `vh` (indépendant de la
            # hauteur `auto` des ancêtres) + `overflow-y-auto` local.
            with ui.column().classes(
                "w-full max-h-[calc(100vh-9rem)] overflow-y-auto pr-1"
            ) as download_section:
                _build_workspace(config, downloader, spotify_downloader, queue, preview, spotify_preview)
            sections["download"] = download_section

            with ui.column().classes("w-full") as player_section:
                player_ui.build_player_section(controller)
            sections["player"] = player_section

            with ui.column().classes("w-full") as settings_section:
                _build_settings_section(config, queue)
            sections["settings"] = settings_section

            with ui.column().classes("w-full") as help_section:
                _build_help_section()
            sections["help"] = help_section

            with ui.column().classes("w-full") as install_section:
                _build_install_section()
            sections["install"] = install_section

    show_section("home")
    ui.timer(0.4, lambda: _autofit_native_window_once(show_section, nav_state), once=True)


def _build_native_home_extras(
    config: AppConfig,
    queue: DownloadQueue,
    show_section: Callable[[str], None],
    theme_state: dict[str, object],
) -> None:
    """Contenu supplémentaire de l'accueil natif : sans lui, cette page ne
    contient que le logo (elle ne sert de point d'entrée qu'au sens
    « navigation », voir :func:`_build_native_page`) — un peu triste pour une
    page à part entière. On y ajoute des raccourcis vers les autres sections
    et un aperçu de l'activité en cours (chiffres, un vu-mètre de débit et un
    graphe des résultats cumulés).

    ``theme_state`` (posé par :func:`_build_theme_controls`) est relu à
    chaque rafraîchissement pour reteinter le graphe Highcharts : contrairement
    au reste de l'app (couleur posée en variable CSS, suit un changement de
    palette tout seul), un graphe Highcharts fige ses couleurs dans le JSON
    envoyé au client — il faut donc explicitement les renvoyer à jour.
    """
    with ui.column().classes("w-full flex-grow gap-6"):
        # Pas de `columns=` ici : ce style raccourci met un style CSS "inline"
        # dont la spécificité écraserait la classe Tailwind ci-dessous, qui
        # ne s'appliquerait donc jamais. Fenêtre native de largeur fixe :
        # pas besoin de repli responsive, les 5 tiennent toujours sur une ligne.
        with ui.grid().classes("w-full gap-3 grid-cols-5"):
            components.nav_card("download", "Télécharger", lambda: show_section("download"))
            components.nav_card("library_music", "Lecteur", lambda: show_section("player"))
            components.nav_card("settings", "Réglages", lambda: show_section("settings"))
            components.nav_card("help", "Aide", lambda: show_section("help"))
            components.nav_card("cloud_download", "Installation", lambda: show_section("install"))

        # flex-grow : comble l'espace restant sous la ligne de cartes plutôt
        # que de laisser du vide en bas de la fenêtre.
        with ui.card().classes("ytdl-glass w-full flex-grow p-5 gap-3"):
            components.section_title("Activité")
            stats_row = ui.row().classes("w-full justify-center gap-3 flex-wrap")

            with ui.grid().classes("w-full gap-4 grid-cols-1 sm:grid-cols-2"):
                update_meter = _build_speed_meter()
                status_chart = ui.highchart(
                    _status_chart_options(theme.colors_for(theme_state["key"], theme_state["dark"]), theme_state["dark"])
                ).classes("w-full")

            session_max_mbps = {"value": 0.01}

            def refresh() -> None:
                jobs = queue.jobs
                active = sum(1 for j in jobs if j.is_active)
                done = sum(1 for j in jobs if j.status == JobStatus.DONE)
                errors = sum(1 for j in jobs if j.status == JobStatus.ERROR)
                cancelled = sum(1 for j in jobs if j.status == JobStatus.CANCELLED)

                stats_row.clear()
                with stats_row:
                    components.status_pill(f"{active} en cours", "download", "primary")
                    components.status_pill(f"{done} terminés", "check_circle", "positive")
                    components.status_pill(f"{len(jobs)} dans la file", "queue_music", "secondary")

                total_mbps = sum(j.speed_bps for j in jobs if j.is_active) / (1024 * 1024)
                session_max_mbps["value"] = max(session_max_mbps["value"], total_mbps)
                update_meter(total_mbps, session_max_mbps["value"])

                colors = theme.colors_for(theme_state["key"], theme_state["dark"])
                grid_color = "rgba(255, 255, 255, 0.12)" if theme_state["dark"] else "rgba(0, 0, 0, 0.08)"
                status_chart.options["title"]["style"]["color"] = colors.text
                status_chart.options["xAxis"]["labels"]["style"]["color"] = colors.subtext
                status_chart.options["xAxis"]["lineColor"] = grid_color
                status_chart.options["yAxis"]["labels"]["style"]["color"] = colors.subtext
                status_chart.options["yAxis"]["gridLineColor"] = grid_color
                status_chart.options["series"][0]["data"] = [
                    {"y": done, "color": theme.POSITIVE},
                    {"y": errors, "color": theme.NEGATIVE},
                    {"y": cancelled, "color": theme.WARNING},
                ]
                status_chart.update()

            refresh()
            ui.timer(2.0, refresh)


_VU_SEGMENTS = 20


def _build_speed_meter() -> Callable[[float, float], None]:
    """Vu-mètre du débit total : signe distinctif de l'accueil (voir
    ``.ytdl-vu-meter`` dans :mod:`ytdl.ui.theme`) à la place d'un graphe en
    ligne générique. Une rangée de segments s'allume de l'accent (bas débit)
    au secondaire (haut débit), le nombre allumé reflétant le débit courant
    relatif au maximum observé depuis le lancement — sans dépendance
    Highcharts.

    Chaque segment est teinté via ``color-mix(var(--ytdl-accent), ...)``
    plutôt qu'une couleur Python figée : comme toute couleur de l'app posée
    en variable CSS, il suit donc tout seul un changement de palette en
    direct (voir le bouton palette dans :func:`_build_native_page`), sans
    reconstruire le vu-mètre ni connaître la palette active.

    Renvoie une fonction ``update(current_mbps, max_mbps)`` à rappeler à
    chaque rafraîchissement.
    """
    with ui.column().classes("w-full gap-2"):
        ui.label("Débit total").classes("ytdl-section-title text-xs")
        segments: list[ui.element] = []
        with ui.row().classes("ytdl-vu-meter w-full"):
            for i in range(_VU_SEGMENTS):
                pct = round(100 * i / (_VU_SEGMENTS - 1))
                seg = ui.element("div").classes("ytdl-vu-segment")
                seg.style(
                    f"--ytdl-vu-color: color-mix(in srgb, var(--ytdl-secondary) {pct}%, var(--ytdl-accent))"
                )
                segments.append(seg)
        value_label = ui.label("0,00 Mo/s").classes("ytdl-mono text-sm opacity-80")

    def update(current_mbps: float, max_mbps: float) -> None:
        ratio = 0.0 if max_mbps <= 0 else min(1.0, current_mbps / max_mbps)
        lit_count = round(ratio * _VU_SEGMENTS)
        for i, seg in enumerate(segments):
            if i < lit_count:
                seg.classes(add="lit")
            else:
                seg.classes(remove="lit")
        value_label.set_text(f"{current_mbps:.2f} Mo/s".replace(".", ","))

    return update


def _status_chart_options(colors: theme.ThemeColors, dark_mode: bool) -> dict:
    """Résultats cumulés par issue — une couleur par statut, cohérente avec
    les badges des cartes de téléchargement (voir components._STATUS_STYLE).

    Contrairement au reste de l'app, un graphe Highcharts fige ses couleurs
    dans le JSON envoyé au client plutôt que de lire des variables CSS : sans
    ça, il utilise du texte sombre par défaut, illisible sur fond sombre —
    d'où ``colors``/``dark_mode`` explicites, à refournir à jour à chaque
    fois que la palette ou le mode change (voir le rappel dans
    :func:`_build_native_home_extras`).
    """
    grid_color = "rgba(255, 255, 255, 0.12)" if dark_mode else "rgba(0, 0, 0, 0.08)"
    return {
        "title": {"text": "Résultats", "style": {"color": colors.text}},
        "chart": {"type": "column", "backgroundColor": "transparent", "height": 180},
        "credits": {"enabled": False},
        "legend": {"enabled": False},
        "xAxis": {
            "categories": ["Terminés", "Erreurs", "Annulés"],
            "lineColor": grid_color,
            "labels": {"style": {"color": colors.subtext}},
        },
        "yAxis": {
            "title": {"text": None},
            "allowDecimals": False,
            "min": 0,
            "labels": {"style": {"color": colors.subtext}},
            "gridLineColor": grid_color,
        },
        "series": [{"name": "Pistes", "data": [0, 0, 0]}],
    }


def _page_wrapper_classes(native: bool) -> str:
    """Classes de la colonne qui enveloppe le contenu d'une page.

    Le mode web garde son espacement généreux façon portfolio (``gap-20
    pt-36 pb-24``), pensé pour un long site à défilement. En mode natif,
    une seule section est visible à la fois dans une fenêtre de taille
    modeste : cette marge XXL créait à elle seule un débordement même sur
    des sections avec très peu de contenu réel — d'où un espacement resserré.
    """
    if native:
        return "w-full max-w-5xl mx-auto px-4 sm:px-8 gap-8 pt-24 pb-10 relative z-10"
    return "w-full max-w-5xl mx-auto px-4 sm:px-8 gap-20 pt-36 pb-24 relative z-10"


async def _autofit_native_window_once(show_section: Callable[[str], None], nav_state: dict[str, int]) -> None:
    """Dimensionne la fenêtre native une seule fois, au démarrage — jamais
    plus ensuite (voir la demande : une fenêtre stable, pas un
    redimensionnement à chaque changement de section).

    Basé sur la section « Aide », la plus dense (grille de cartes + contenu
    détaillé) : on l'affiche brièvement pour la mesurer, puis on revient à
    l'accueil. Le bref changement de section n'est visible qu'au tout début
    du lancement de l'app, pas pendant l'utilisation normale.

    Si l'utilisateur clique sur un item de la nav pendant cette mesure (un
    aller-retour vers "help" qui prend une fraction de seconde), on ne doit
    surtout pas écraser son choix en revenant à "home" ensuite — d'où le
    suivi de version : on ne revient à l'accueil que si personne n'a changé
    de section entre-temps (sans quoi il fallait cliquer deux fois pour que
    la navigation "tienne").
    """
    if not ng_app.native.main_window:
        return
    show_section("help")
    version_after_help = nav_state["version"]
    height: Optional[float] = None
    try:
        height = await ui.run_javascript(
            "return document.fonts.ready.then(() => Math.ceil(document.documentElement.scrollHeight))",
            timeout=3.0,
        )
        width, _current_height = await ng_app.native.main_window.get_size()
    except Exception:  # client déconnecté avant la fin de la mesure, etc.
        width = None
    if nav_state["version"] == version_after_help:
        show_section("home")
    if height and width:
        target = max(560, min(int(height) + 32, 1200))
        ng_app.native.main_window.resize(width, target)


def _build_theme_controls(config: AppConfig) -> dict[str, object]:
    """Bouton jour/nuit + bouton palette (menu de swatches, voir
    :data:`ytdl.ui.theme.THEMES`) — un premier choix de palette imposé
    n'ayant pas plu, l'utilisateur choisit désormais lui-même parmi plusieurs
    directions plutôt que d'en subir une nouvelle.

    Renvoie un état partagé ``{"key": ..., "dark": ...}``, tenu à jour à
    chaque bascule. La plupart de l'UI suit un changement de palette/mode
    tout seule (elle ne lit que des variables CSS) ; les quelques éléments
    qui ne le peuvent pas — les graphes Highcharts — ont besoin de cet état
    pour se reteinter au prochain rafraîchissement (voir
    :func:`_build_native_home_extras`).
    """
    theme_state: dict[str, object] = {"key": config.theme, "dark": config.dark_mode}
    dark = ui.dark_mode(config.dark_mode)

    def sync_quasar_colors() -> None:
        # ui.colors() (appelé une fois dans theme.apply()) ne pose les
        # variables --q-primary/--q-secondary/--q-accent qu'au montage
        # initial du composant (voir colors.js dans le paquet nicegui) : pas
        # de watcher côté client, donc rappeler ui.colors()/modifier ses
        # props ensuite ne les mettrait PAS à jour. Seuls les composants
        # Quasar natifs (boutons/badges `color=primary`...) en dépendent — le
        # reste de l'app suit déjà --ytdl-accent en direct — mais sans ce
        # correctif ils resteraient bloqués sur la toute première palette
        # après un changement de thème ou de mode clair/sombre.
        colors = theme.colors_for(theme_state["key"], theme_state["dark"])
        ui.run_javascript(
            f"document.body.style.setProperty('--q-primary', '{colors.accent}');"
            f"document.body.style.setProperty('--q-secondary', '{colors.secondary}');"
            f"document.body.style.setProperty('--q-accent', '{colors.accent}');"
        )

    def toggle_dark() -> None:
        config.dark_mode = not config.dark_mode
        theme_state["dark"] = config.dark_mode
        dark.toggle()
        config.save()
        sync_quasar_colors()

    def pick_theme(key: str) -> None:
        old_key = theme_state["key"]
        if key != old_key:
            theme_state["key"] = key
            config.theme = key
            config.save()
            ui.query("body").classes(add=f"ytdl-theme-{key}", remove=f"ytdl-theme-{old_key}")
            sync_quasar_colors()

    with ui.row().classes("ytdl-theme-controls"):
        ui.button(icon="dark_mode", on_click=toggle_dark).props("flat round color=primary").tooltip(
            "Basculer clair / sombre"
        )
        # Le menu doit être imbriqué DANS le bouton (pas construit à côté puis
        # ouvert via on_click=menu.open) : c'est ce qui le fait s'ancrer au
        # bouton côté Quasar. Construit à côté, il s'ouvrait sans ancre —
        # positionné par défaut en haut de la page plutôt que sous le bouton,
        # ce qui le rendait quasi impossible à utiliser.
        with ui.button(icon="palette").props("flat round color=primary").tooltip("Palette de couleurs"):
            with ui.menu():
                for key, theme_def in theme.THEMES.items():
                    swatch = theme.colors_for(key, True)
                    with ui.menu_item(on_click=lambda k=key: pick_theme(k)):
                        with ui.row().classes("items-center gap-2 no-wrap"):
                            ui.element("div").classes("w-4 h-4 rounded-full shrink-0").style(
                                f"background: linear-gradient(135deg, {swatch.accent} 50%, {swatch.secondary} 50%)"
                            )
                            ui.label(theme_def.label)

    return theme_state


# --------------------------------------------------------------------------- #
# Nav + hero
# --------------------------------------------------------------------------- #
def _build_nav(config: AppConfig) -> None:
    """Nav flottante du mode web : ancres vers les sections de la page à défilement."""
    with ui.row().classes("ytdl-nav"):
        for icon, label, anchor, section_key in _NAV_ITEMS:
            components.nav_link(icon, label, anchor, section_key)
    _build_theme_controls(config)


def _build_hero() -> None:
    with ui.column().classes("w-full items-center text-center gap-3") as hero:
        hero.props("id=home data-nav-section=home")
        if _ASSET_ICON.is_file():
            ui.image(str(_ASSET_ICON)).classes(
                "w-20 h-20 rounded-full ytdl-float shadow-lg border-2 border-accent/40 object-cover"
            )
        else:
            ui.icon("smart_display").classes("text-6xl ytdl-float text-primary")

        ui.label("ytdl").classes("ytdl-heading text-5xl md:text-6xl font-bold tracking-tight mt-2")
        ui.label("Téléchargeur vidéo & audio moderne — MP4, MP3, playlists, sous-titres.").classes(
            "opacity-70 max-w-lg"
        )

        with ui.row().classes("items-center gap-2 flex-wrap justify-center"):
            if ffmpeg_available():
                components.status_pill("ffmpeg détecté", "check_circle", "positive")
            else:
                components.status_pill(
                    f"ffmpeg manquant — {install_hint(sys.platform)}", "warning", "warning"
                )

            if js_runtime_available():
                components.status_pill("Runtime JS détecté", "check_circle", "positive")
            else:
                components.status_pill(
                    "Node.js manquant — les téléchargements YouTube échoueront "
                    f"souvent (« Requested format is not available ») — {js_install_hint(sys.platform)}",
                    "warning",
                    "warning",
                )

            if spotdl_available():
                components.status_pill("spotdl détecté", "check_circle", "positive")
            else:
                components.status_pill(
                    f"spotdl manquant (Spotify) — {spotify_install_hint(sys.platform)}",
                    "info",
                    "warning",
                )


# --------------------------------------------------------------------------- #
# Espace de travail : Télécharger + File d'attente, côte à côte
# --------------------------------------------------------------------------- #
def _build_workspace(
    config: AppConfig,
    downloader: Downloader,
    spotify_downloader: SpotifyDownloader,
    queue: DownloadQueue,
    preview: dict[str, object],
    spotify_preview: dict[str, object],
) -> None:
    with ui.column().classes("w-full gap-4") as section:
        section.props("data-nav-section=workspace")
        components.section_header(
            "Espace de travail", "Ajoutez une URL et suivez son téléchargement en direct, sans changer de vue."
        )
        with ui.row().classes("w-full gap-6 items-start flex-wrap md:flex-nowrap"):
            with ui.column().classes("w-full md:flex-1 min-w-0 gap-4") as download_col:
                download_col.props("id=download")
                _build_download_card(config, downloader, queue, preview)
                _build_spotify_download_card(config, spotify_downloader, queue, spotify_preview)
            with ui.column().classes("w-full md:flex-1 min-w-0"):
                _build_queue_card(queue)


def _build_download_card(
    config: AppConfig,
    downloader: Downloader,
    queue: DownloadQueue,
    preview: dict[str, object],
) -> None:
    with ui.card().classes("ytdl-glass w-full p-5 gap-4"):
        components.section_title("Nouveau téléchargement")

        # --- URL + analyse ---------------------------------------------------
        with ui.row().classes("w-full items-center no-wrap gap-2"):
            url_input = (
                ui.input(placeholder="https://www.youtube.com/watch?v=...")
                .props("clearable outlined")
                .classes("flex-grow")
            )
            help_ui.help_icon("url")
            analyze_btn = ui.button("Analyser", icon="search").props("unelevated")

        # --- Aperçu (rempli après analyse) ----------------------------------
        def clear_preview() -> None:
            preview["info"] = None
            preview_card.refresh()
            playlist_cb.value = False

        @ui.refreshable
        def preview_card() -> None:
            info = preview.get("info")
            if info is None:
                return
            with ui.card().classes("ytdl-glass w-full p-3 ytdl-fade-in"):
                with ui.row().classes("w-full items-center no-wrap gap-3"):
                    if getattr(info, "thumbnail", None):
                        ui.image(info.thumbnail).classes("w-40 rounded-lg shrink-0").props("no-spinner")
                    with ui.column().classes("gap-1 min-w-0 flex-grow"):
                        ui.label(info.title).classes("font-semibold break-words w-full")
                        meta = " · ".join(
                            x for x in (info.uploader, info.duration_str) if x
                        )
                        if meta:
                            ui.label(meta).classes("text-xs opacity-70")
                        if info.is_playlist:
                            ui.badge(f"Playlist · {len(info.entries)} éléments", color="secondary").classes(
                                "ytdl-mono"
                            )
                    ui.button(icon="close", on_click=clear_preview).props("flat round dense").tooltip(
                        "Supprimer l'aperçu"
                    )

        preview_card()

        # --- Grille de formats -------------------------------------------------
        with ui.row().classes("items-center gap-2"):
            ui.label("Format").classes("text-sm font-medium opacity-80")
            help_ui.help_icon("format")
        selected_fmt: dict[str, MediaFormat] = {"value": MediaFormat.MP4}
        tiles: dict[MediaFormat, ui.column] = {}

        with ui.grid(columns=3).classes("w-full gap-2"):
            for fmt, icon in _FORMAT_TILES:
                def make_handler(f: MediaFormat) -> Callable[[], None]:
                    def handler() -> None:
                        select_format(f)

                    return handler

                tiles[fmt] = components.format_tile(
                    icon, fmt.label, fmt == selected_fmt["value"], make_handler(fmt)
                )

        with ui.row().classes("w-full items-end gap-3 no-wrap"):
            quality_select = (
                ui.select(VIDEO_QUALITIES, value=config_default_quality(MediaFormat.MP4), label="Qualité")
                .props("outlined")
                .classes("w-40")
            )
            help_ui.help_icon("quality")

        def select_format(fmt: MediaFormat) -> None:
            for f, tile in tiles.items():
                if f == fmt:
                    tile.classes(add="ytdl-tile-active")
                else:
                    tile.classes(remove="ytdl-tile-active")
            selected_fmt["value"] = fmt
            options = AUDIO_QUALITIES if fmt.is_audio else VIDEO_QUALITIES
            quality_select.set_options(options, value=config_default_quality(fmt))

        with ui.row().classes("w-full items-center gap-4 flex-wrap"):
            subs_cb = ui.checkbox("Sous-titres", value=False)
            help_ui.help_icon("subtitles")
            meta_cb = ui.checkbox("Métadonnées", value=True)
            help_ui.help_icon("metadata")
            thumb_cb = ui.checkbox("Miniature", value=False)
            help_ui.help_icon("thumbnail")
            playlist_cb = ui.checkbox("Traiter comme une playlist", value=False)
            help_ui.help_icon("playlist_items")

        playlist_items = (
            ui.input(placeholder="ex. 1-5,8  (vide = tout)")
            .props("outlined dense")
            .classes("w-full")
            .bind_visibility_from(playlist_cb, "value")
        )

        # --- Action ----------------------------------------------------------
        add_btn = ui.button("Ajouter à la file", icon="add").props("unelevated color=primary").classes(
            "w-full"
        )

        # --- Comportements ---------------------------------------------------
        async def analyze() -> None:
            url = (url_input.value or "").strip()
            if not url:
                ui.notify("Entrez d'abord une URL.", type="warning")
                return
            analyze_btn.props("loading")
            try:
                info = await ng_run.io_bound(downloader.probe, url, config.cookies_browser)
                preview["info"] = info
                preview_card.refresh()
                if info.is_playlist:
                    playlist_cb.value = True
                elif url_has_playlist_param(url):
                    # yt-dlp bascule silencieusement en « vidéo seule » quand la
                    # playlist est privée (Liked videos, Watch Later, playlist
                    # personnelle...) et qu'aucun cookie n'est fourni.
                    ui.notify(
                        "Cette URL contient une playlist, mais elle est privée : "
                        "seule la vidéo a été analysée. Activez « Cookies navigateur » "
                        "dans Réglages → Authentification pour y accéder.",
                        type="warning",
                        multi_line=True,
                        timeout=8000,
                    )
                else:
                    ui.notify("Analyse réussie.", type="positive")
            except Exception as exc:
                ui.notify(f"Échec de l'analyse : {exc}", type="negative", multi_line=True)
            finally:
                analyze_btn.props(remove="loading")

        def add_to_queue() -> None:
            url = (url_input.value or "").strip()
            if not url:
                ui.notify("Entrez une URL à télécharger.", type="warning")
                return
            if preview.get("info") is None and url_has_playlist_param(url):
                # Sans analyse préalable, on ne sait pas si cette playlist est
                # publique/privée ni combien d'éléments elle contient : mieux
                # vaut le demander explicitement plutôt que de télécharger
                # silencieusement une seule vidéo (is_playlist resterait False).
                ui.notify(
                    "Cette URL contient une playlist. Cliquez d'abord sur « Analyser » "
                    "pour la détecter correctement avant de l'ajouter à la file.",
                    type="warning",
                    multi_line=True,
                    timeout=6000,
                )
                return
            options = DownloadOptions(
                fmt=selected_fmt["value"],
                quality=quality_select.value,
                output_dir=config.download_dir,
                filename_template=config.filename_template,
                subtitles=subs_cb.value,
                embed_metadata=meta_cb.value,
                embed_thumbnail=thumb_cb.value,
                playlist_items=(playlist_items.value or "").strip() or None,
                is_playlist=playlist_cb.value,
                clean_title=config.clean_titles,
                sleep_interval=config.sleep_interval,
                rate_limit_kbps=config.rate_limit_kbps,
                cookies_browser=config.cookies_browser,
                archive_path=config.archive_path() if config.skip_archived else None,
            )
            info = preview.get("info")
            title = getattr(info, "title", "") if info else ""
            queue.add(url, options, title=title)
            ui.notify("Ajouté à la file — suivez sa progression ci-contre.", type="positive")

        analyze_btn.on_click(analyze)
        add_btn.on_click(add_to_queue)


def _build_spotify_download_card(
    config: AppConfig,
    spotify_downloader: SpotifyDownloader,
    queue: DownloadQueue,
    preview: dict[str, object],
) -> None:
    with ui.card().classes("ytdl-glass w-full p-5 gap-4"):
        components.section_title("Nouveau téléchargement Spotify")

        if not spotdl_available():
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                ui.icon("warning").classes("text-warning")
                ui.label(
                    f"spotdl introuvable — {spotify_install_hint(sys.platform)}. "
                    "Voir la section Aide pour plus de détails."
                ).classes("text-xs opacity-80")

        # --- URL + analyse ---------------------------------------------------
        with ui.row().classes("w-full items-center no-wrap gap-2"):
            url_input = (
                ui.input(placeholder="https://open.spotify.com/playlist/...")
                .props("clearable outlined")
                .classes("flex-grow")
            )
            analyze_btn = ui.button("Analyser", icon="search").props("unelevated")
            analyzing_spinner = ui.spinner(size="1.5rem")
            analyzing_spinner.set_visibility(False)
        ui.label(
            "spotdl interroge Spotify piste par piste : l'analyse d'une grosse "
            "playlist peut prendre plusieurs minutes (pas de quoi s'inquiéter)."
        ).classes("text-xs opacity-60 -mt-2")

        # --- Aperçu (rempli après analyse) ----------------------------------
        def clear_preview() -> None:
            preview["info"] = None
            preview_card.refresh()

        @ui.refreshable
        def preview_card() -> None:
            info = preview.get("info")
            if info is None:
                return
            with ui.card().classes("ytdl-glass w-full p-3 ytdl-fade-in"):
                with ui.row().classes("w-full items-center no-wrap gap-3"):
                    if getattr(info, "thumbnail", None):
                        ui.image(info.thumbnail).classes("w-40 rounded-lg shrink-0").props("no-spinner")
                    with ui.column().classes("gap-1 min-w-0 flex-grow"):
                        ui.label(info.title).classes("font-semibold break-words w-full")
                        if info.uploader:
                            ui.label(info.uploader).classes("text-xs opacity-70")
                        if info.is_playlist:
                            ui.badge(f"Playlist · {len(info.entries)} éléments", color="secondary").classes(
                                "ytdl-mono"
                            )
                    ui.button(icon="close", on_click=clear_preview).props("flat round dense").tooltip(
                        "Supprimer l'aperçu"
                    )

        preview_card()

        # --- Grille de formats -------------------------------------------------
        with ui.row().classes("items-center gap-2"):
            ui.label("Format").classes("text-sm font-medium opacity-80")
            help_ui.help_icon("spotify_format")
        selected_fmt: dict[str, SpotifyFormat] = {"value": SpotifyFormat.MP3}
        tiles: dict[SpotifyFormat, ui.column] = {}

        with ui.grid(columns=3).classes("w-full gap-2"):
            for fmt, icon in _SPOTIFY_FORMAT_TILES:
                def make_handler(f: SpotifyFormat) -> Callable[[], None]:
                    def handler() -> None:
                        select_format(f)

                    return handler

                tiles[fmt] = components.format_tile(
                    icon, fmt.label, fmt == selected_fmt["value"], make_handler(fmt)
                )

        def select_format(fmt: SpotifyFormat) -> None:
            for f, tile in tiles.items():
                if f == fmt:
                    tile.classes(add="ytdl-tile-active")
                else:
                    tile.classes(remove="ytdl-tile-active")
            selected_fmt["value"] = fmt

        with ui.row().classes("w-full items-end gap-3 no-wrap"):
            bitrate_select = (
                ui.select(SPOTIFY_BITRATES, value="320", label="Débit")
                .props("outlined")
                .classes("w-40")
            )
            help_ui.help_icon("spotify_bitrate")

        cover_cb = ui.checkbox("Pochette d'album", value=True)

        # --- Action ----------------------------------------------------------
        add_btn = ui.button("Ajouter à la file", icon="add").props("unelevated color=primary").classes(
            "w-full"
        )

        # --- Comportements ---------------------------------------------------
        # L'analyse d'une grosse playlist peut prendre très longtemps (voir le
        # message ci-dessus) : le bouton bascule en « Annuler » pendant qu'elle
        # tourne, plutôt que de forcer à quitter l'app pour l'interrompre.
        active_probe: dict[str, object] = {"token": None}

        async def analyze() -> None:
            token = active_probe.get("token")
            if token is not None:
                token.cancel()  # type: ignore[attr-defined]
                return

            url = (url_input.value or "").strip()
            if not url:
                ui.notify("Entrez d'abord une URL Spotify.", type="warning")
                return

            token = CancelToken()
            active_probe["token"] = token
            # Pas la prop Quasar `loading` : elle remplace silencieusement
            # TOUS les gestionnaires de clic du bouton par des no-op tant
            # qu'elle est active (vérifié dans le JS de Quasar) — impossible
            # de recliquer pour annuler avec elle. Le spinner + le changement
            # de texte/couleur suffisent à indiquer l'état, sans bloquer le clic.
            analyzing_spinner.set_visibility(True)
            analyze_btn.props(add="icon=close color=negative")
            analyze_btn.set_text("Annuler l'analyse")
            url_input.props(add="disable")
            try:
                info = await ng_run.io_bound(spotify_downloader.probe, url, token)
                preview["info"] = info
                preview_card.refresh()
                ui.notify("Analyse réussie.", type="positive")
            except ProbeCancelled:
                ui.notify("Analyse annulée.", type="info")
            except Exception as exc:
                ui.notify(f"Échec de l'analyse : {exc}", type="negative", multi_line=True)
            finally:
                active_probe["token"] = None
                analyzing_spinner.set_visibility(False)
                analyze_btn.props(add="icon=search", remove="color")
                analyze_btn.set_text("Analyser")
                url_input.props(remove="disable")

        def add_to_queue() -> None:
            url = (url_input.value or "").strip()
            if not url:
                ui.notify("Entrez une URL Spotify à télécharger.", type="warning")
                return
            info = preview.get("info")
            if info is None and spotify_url_is_multi_track(url):
                # Sans analyse préalable, on ne connaît ni le nombre de pistes
                # ni leurs titres — et les redemander ici recoderait ~2s/piste
                # d'attente (voir SpotifyDownloader.download). Mieux vaut le
                # demander explicitement, comme pour une playlist YouTube non
                # analysée.
                ui.notify(
                    "Cette URL est une playlist/un album Spotify. Cliquez d'abord sur "
                    "« Analyser » (l'ajout direct redemanderait la liste des pistes, "
                    "ce qui peut prendre plusieurs minutes).",
                    type="warning",
                    multi_line=True,
                    timeout=8000,
                )
                return
            is_playlist = bool(getattr(info, "is_playlist", False))
            options = SpotifyDownloadOptions(
                fmt=selected_fmt["value"],
                bitrate=bitrate_select.value,
                output_dir=config.download_dir,
                embed_cover=cover_cb.value,
                is_playlist=is_playlist,
                playlist_tracks=list(info.entries) if is_playlist and info else [],
                archive_path=config.archive_path_spotify() if config.skip_archived else None,
            )
            title = getattr(info, "title", "") if info else ""
            queue.add(url, options, title=title)
            ui.notify("Ajouté à la file — suivez sa progression ci-contre.", type="positive")

        analyze_btn.on_click(analyze)
        add_btn.on_click(add_to_queue)


def _build_queue_card(queue: DownloadQueue) -> None:
    with ui.card().classes("ytdl-glass w-full p-5 gap-3"):
        with ui.row().classes("w-full items-center justify-between"):
            components.section_title("Téléchargements")
            ui.button(
                "Nettoyer les terminés", icon="cleaning_services", on_click=lambda: queue.clear_finished()
            ).props("flat dense")

        empty_state = ui.column().classes("w-full items-center py-10 opacity-60")
        with empty_state:
            ui.icon("inbox").classes("text-5xl")
            ui.label("Aucun téléchargement pour l'instant.")

        container = ui.column().classes("w-full gap-3 max-h-[65vh] overflow-y-auto pr-1")
        handles: dict[str, components.JobCardHandle] = {}

        def reconcile() -> None:
            jobs = queue.jobs
            current_ids = {j.id for j in jobs}

            for stale_id in list(handles):
                if stale_id not in current_ids:
                    handles.pop(stale_id).root.delete()

            for job in jobs:
                if job.id not in handles:
                    with container:
                        handles[job.id] = components.create_job_card(
                            job,
                            on_cancel=lambda jid: queue.cancel(jid),
                            on_pause=lambda jid: queue.pause(jid),
                            on_resume=lambda jid: queue.resume(jid),
                            on_restart=lambda jid: queue.restart(jid),
                            on_open=lambda j: _open_folder(j.filepath or j.options.output_dir),
                            on_play=_play_file,
                        )
                else:
                    components.update_job_card(handles[job.id], job, on_play=_play_file)

            empty_state.set_visibility(not jobs)

        reconcile()
        # Mise à jour en place (pas de reconstruction du DOM) : pas de clignotement.
        ui.timer(0.5, reconcile)


# --------------------------------------------------------------------------- #
# Réglages
# --------------------------------------------------------------------------- #
def _build_settings_section(config: AppConfig, queue: DownloadQueue) -> None:
    with ui.column().classes("w-full gap-4") as section:
        section.props("id=settings data-nav-section=settings")
        components.section_header(
            "Réglages", "Dossier, nommage, concurrence et protection anti-throttling. Appliqués sans redémarrage."
        )

        # Pas de `columns=` : ce raccourci pose un style CSS "inline" (voir
        # ui.grid) dont la spécificité écrase toujours la classe Tailwind
        # responsive `sm:grid-cols-2` ci-dessous — elle ne s'appliquait donc
        # jamais, d'où un empilement en une seule colonne (et une page bien
        # plus haute que nécessaire) même sur une fenêtre large. Cartes aussi
        # resserrées (p-4/gap-3) et sans légende dupliquant l'infobulle « ? »
        # de chaque champ.
        with ui.grid().classes("w-full gap-3 grid-cols-1 sm:grid-cols-2"):
            with ui.card().classes("ytdl-glass p-4 gap-3"):
                components.section_title("Emplacement")
                dir_input = (
                    ui.input("Dossier de téléchargement", value=config.download_dir)
                    .props("outlined")
                    .classes("w-full")
                )
                with ui.row().classes("items-center gap-1 w-full"):
                    tpl_input = (
                        ui.input("Gabarit de nom de fichier", value=config.filename_template)
                        .props("outlined")
                        .classes("flex-grow")
                    )
                    help_ui.help_icon("template")

            with ui.card().classes("ytdl-glass p-4 gap-3"):
                components.section_title("Comportement")
                with ui.row().classes("items-center gap-1"):
                    concurrent = ui.number(
                        "Téléchargements simultanés", value=config.max_concurrent, min=1, max=8, format="%d"
                    ).props("outlined").classes("w-full")
                    help_ui.help_icon("concurrent")
                with ui.row().classes("items-center gap-1"):
                    clean_cb = ui.checkbox("Nettoyer les titres", value=config.clean_titles)
                    help_ui.help_icon("clean_titles")
                with ui.row().classes("items-center gap-1"):
                    archive_cb = ui.checkbox("Ne pas re-télécharger les pistes déjà obtenues", value=config.skip_archived)
                    help_ui.help_icon("skip_archived")
                ui.button(
                    "Réinitialiser les archives de ce dossier",
                    icon="restart_alt",
                    on_click=lambda: reset_archive(),
                ).props("flat dense color=warning").classes("self-start -mt-1")

            with ui.card().classes("ytdl-glass p-4 gap-3"):
                components.section_title("Anti-throttling")
                ui.label(
                    "Un usage intensif peut être limité/bloqué temporairement par le site source."
                ).classes("text-xs opacity-60")
                with ui.row().classes("items-center gap-1"):
                    sleep_input = ui.number(
                        "Délai entre téléchargements (s)",
                        value=config.sleep_interval,
                        min=0,
                        step=0.5,
                        format="%.1f",
                    ).props("outlined").classes("w-full")
                    help_ui.help_icon("sleep_interval")
                with ui.row().classes("items-center gap-1"):
                    rate_input = ui.number(
                        "Débit maximal (Ko/s, 0 = illimité)",
                        value=config.rate_limit_kbps,
                        min=0,
                        format="%d",
                    ).props("outlined").classes("w-full")
                    help_ui.help_icon("rate_limit")

            with ui.card().classes("ytdl-glass p-4 gap-3"):
                components.section_title("Authentification")
                ui.label(
                    "Requis pour les playlists privées et le contenu réservé aux abonnés."
                ).classes("text-xs opacity-60")
                with ui.row().classes("items-center gap-1"):
                    cookies_select = ui.select(
                        {"": "Aucun (désactivé)", **{b: b.capitalize() for b in COOKIE_BROWSERS}},
                        value=config.cookies_browser,
                        label="Cookies navigateur",
                    ).props("outlined").classes("w-full")
                    help_ui.help_icon("cookies_browser")

        def save() -> None:
            config.download_dir = (dir_input.value or config.download_dir).strip()
            config.filename_template = (tpl_input.value or config.filename_template).strip()
            config.clean_titles = bool(clean_cb.value)
            config.skip_archived = bool(archive_cb.value)
            config.sleep_interval = max(0.0, float(sleep_input.value or 0))
            config.rate_limit_kbps = max(0, int(rate_input.value or 0))
            config.cookies_browser = cookies_select.value or ""

            new_concurrent = max(1, int(concurrent.value or config.max_concurrent))
            if new_concurrent != config.max_concurrent:
                config.max_concurrent = new_concurrent
                queue.set_max_concurrent(new_concurrent)

            config.save()
            ui.notify("Réglages enregistrés et appliqués immédiatement.", type="positive")

        def reset_archive() -> None:
            try:
                Path(config.archive_path()).unlink(missing_ok=True)
                Path(config.archive_path_spotify()).unlink(missing_ok=True)
                ui.notify("Archives réinitialisées : tout sera re-téléchargeable.", type="positive")
            except OSError as exc:
                ui.notify(f"Impossible de réinitialiser les archives : {exc}", type="negative")

        ui.button("Enregistrer", icon="save", on_click=save).props("unelevated")


# --------------------------------------------------------------------------- #
# Aide
# --------------------------------------------------------------------------- #
def _build_help_section() -> None:
    with ui.column().classes("w-full gap-4") as section:
        section.props("id=help data-nav-section=help")
        components.section_header("Aide", "Tout comprendre en quelques lignes.")
        help_ui.build_help_panel()


# --------------------------------------------------------------------------- #
# Installation
# --------------------------------------------------------------------------- #
def _build_install_section() -> None:
    with ui.column().classes("w-full gap-4") as section:
        section.props("id=install data-nav-section=install")
        components.section_header("Installation", "Déployer ytdl ailleurs : Docker, AppImage, binaire ou sources.")
        install_ui.build_install_panel()


def config_default_quality(fmt: MediaFormat) -> str:
    """Qualité par défaut sensée selon le type de format."""
    if fmt.is_audio:
        return "192"
    return "1080"


# --------------------------------------------------------------------------- #
# Lancement
# --------------------------------------------------------------------------- #
def run(native: bool = False, port: int | None = None, show: bool = True) -> None:
    """Démarre l'application NiceGUI.

    Args:
        native: Ouvre une fenêtre native (pywebview) au lieu du navigateur.
        port: Port du serveur web (défaut : celui de la config).
        show: Ouvre automatiquement le navigateur (mode web).
    """
    config = AppConfig.load()
    downloader = Downloader()
    spotify_downloader = SpotifyDownloader()
    queue = DownloadQueue(
        downloader=downloader,
        spotify_downloader=spotify_downloader,
        max_concurrent=config.max_concurrent,
    )

    ng_app.on_shutdown(queue.shutdown)

    @ui.page("/")
    def index() -> None:  # noqa: WPS430 (closure NiceGUI attendue)
        build_page(config, downloader, spotify_downloader, queue, native=native)

    resolved_port = port or config.port
    if native and port is None:
        # En binaire packagé, le port fixe habituel peut déjà être occupé
        # (une autre instance, un autre service local...). En mode natif sans
        # port explicite, on en cherche un de libre — recommandation NiceGUI
        # pour les apps empaquetées avec `nicegui-pack`.
        from nicegui import native as ng_native

        resolved_port = ng_native.find_open_port()

    run_kwargs: dict[str, object] = dict(
        title="ytdl — Téléchargeur vidéo & audio",
        favicon="🎬",
        native=native,
        port=resolved_port,
        show=show and not native,
        reload=False,
        dark=config.dark_mode,
    )
    if native:
        # Taille de départ ; _autofit_native_window_once l'ajuste une seule
        # fois au lancement d'après la section « Aide » (la plus dense), puis
        # elle reste fixe pour toute la session — aucune section ne change
        # plus jamais la taille de la fenêtre après ce réglage initial.
        # Redimensionnable + taille minimale : l'utilisateur garde la main.
        run_kwargs["window_size"] = (1100, 820)
        ng_app.native.window_args["resizable"] = True
        ng_app.native.window_args["min_size"] = (860, 480)

    ui.run(**run_kwargs)

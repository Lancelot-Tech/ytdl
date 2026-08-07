"""Composants d'interface réutilisables.

Les cartes de la file d'attente sont mises à jour **en place** (texte, valeur de
la barre de progression, couleurs) plutôt que détruites/recréées à chaque tick :
c'est ce qui évite le clignotement / sursaut visuel lors du rafraîchissement
périodique (voir :func:`update_job_card`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from nicegui import ui

from ..models import DownloadJob, JobStatus, PlaylistEntry

# Couleur Quasar, icône Material et libellé associés à chaque état.
_STATUS_STYLE: dict[JobStatus, tuple[str, str, str]] = {
    JobStatus.PENDING: ("grey", "schedule", "En attente"),
    JobStatus.PROBING: ("info", "search", "Analyse"),
    JobStatus.DOWNLOADING: ("primary", "download", "Téléchargement"),
    JobStatus.PROCESSING: ("secondary", "settings", "Traitement"),
    JobStatus.PAUSING: ("warning", "hourglass_top", "Mise en pause…"),
    JobStatus.PAUSED: ("warning", "pause_circle", "En pause"),
    JobStatus.CANCELLING: ("warning", "hourglass_top", "Annulation…"),
    JobStatus.DONE: ("positive", "check_circle", "Terminé"),
    JobStatus.ERROR: ("negative", "error", "Erreur"),
    JobStatus.CANCELLED: ("warning", "cancel", "Annulé"),
}

# Couleur et icône associées à chaque état d'une piste de playlist.
_TRACK_STYLE: dict[JobStatus, tuple[str, str]] = {
    JobStatus.PENDING: ("grey", "radio_button_unchecked"),
    JobStatus.DOWNLOADING: ("primary", "download"),
    JobStatus.PROCESSING: ("secondary", "autorenew"),
    JobStatus.DONE: ("positive", "check_circle"),
    JobStatus.ERROR: ("negative", "error"),
}
# États pour lesquels la piste est active : la barre de progression fine
# (indéterminée) est affichée sous la ligne plutôt qu'une icône animée.
_TRACK_ACTIVE = (JobStatus.DOWNLOADING, JobStatus.PROCESSING)


@dataclass
class PlaylistRowHandle:
    """Références vers les éléments d'une ligne de piste, pour mise à jour en place."""

    root: ui.column
    icon: ui.icon
    label: ui.label
    stage_label: ui.label
    progress: ui.linear_progress
    play_button: ui.button


@dataclass
class JobCardHandle:
    """Références vers les éléments d'une carte de job, pour mise à jour en place."""

    root: ui.card
    title_label: ui.label
    subtitle_label: ui.label
    badge: ui.badge
    badge_icon: ui.icon
    badge_label: ui.label
    progress: ui.linear_progress
    percent_label: ui.label
    meta_label: ui.label
    play_button: ui.button
    open_button: ui.button
    pause_button: ui.button
    resume_button: ui.button
    restart_button: ui.button
    cancel_button: ui.button
    playlist_section: ui.column
    playlist_summary: ui.label
    playlist_container: ui.column
    playlist_rows: dict[int, PlaylistRowHandle] = field(default_factory=dict)


def create_job_card(
    job: DownloadJob,
    on_cancel: Callable[[str], None],
    on_pause: Callable[[str], None],
    on_resume: Callable[[str], None],
    on_restart: Callable[[str], None],
    on_open: Callable[[DownloadJob], None],
    on_play: Callable[[str], None],
) -> JobCardHandle:
    """Construit la carte d'un job (structure fixe, quel que soit l'état).

    La structure ne change jamais entre les états : seuls le texte, les
    couleurs et la visibilité des boutons sont mis à jour ensuite par
    :func:`update_job_card`, ce qui garde une hauteur de carte stable. Pour
    une playlist, une liste de pistes est en plus tenue à jour en direct
    (:attr:`JobCardHandle.playlist_rows`) au lieu d'une simple barre globale.
    """
    with ui.card().classes("ytdl-glass w-full p-4 ytdl-fade-in") as root:
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            with ui.column().classes("gap-0 min-w-0 flex-grow"):
                title_label = ui.label(job.title or job.url).classes("font-semibold truncate w-full")
                subtitle_label = ui.label(job.options.fmt.label).classes("text-xs opacity-60")
            with ui.badge(color="grey").classes("px-2 py-1") as badge:
                badge_icon = ui.icon("schedule").classes("text-sm mr-1")
                badge_label = ui.label("")

        progress = ui.linear_progress(value=0.0, show_value=False).props("rounded stripe").classes("w-full")
        with ui.row().classes("w-full justify-between text-xs opacity-70"):
            percent_label = ui.label("0%").classes("ytdl-mono")
            meta_label = ui.label("").classes("ytdl-mono")

        with ui.column().classes("w-full gap-1") as playlist_section:
            playlist_summary = ui.label("").classes("ytdl-mono text-xs font-medium opacity-70")
            playlist_container = ui.column().classes("w-full gap-0.5 max-h-40 overflow-y-auto")

        with ui.row().classes("w-full justify-end gap-2"):
            play_button = ui.button(
                "Lire", icon="play_arrow", on_click=lambda: on_play(job.filepath)
            ).props("flat dense")
            open_button = ui.button("Ouvrir le dossier", icon="folder_open", on_click=lambda: on_open(job)).props(
                "flat dense"
            )
            pause_button = ui.button(
                "Pause", icon="pause", on_click=lambda: on_pause(job.id)
            ).props("flat dense")
            resume_button = ui.button(
                "Reprendre", icon="play_circle", color="primary", on_click=lambda: on_resume(job.id)
            ).props("flat dense")
            restart_button = ui.button(
                "Relancer", icon="restart_alt", color="primary", on_click=lambda: on_restart(job.id)
            ).props("flat dense")
            cancel_button = ui.button(
                "Annuler", icon="close", color="negative", on_click=lambda: on_cancel(job.id)
            ).props("flat dense")

    handle = JobCardHandle(
        root=root,
        title_label=title_label,
        subtitle_label=subtitle_label,
        badge=badge,
        badge_icon=badge_icon,
        badge_label=badge_label,
        progress=progress,
        percent_label=percent_label,
        meta_label=meta_label,
        play_button=play_button,
        open_button=open_button,
        pause_button=pause_button,
        resume_button=resume_button,
        restart_button=restart_button,
        cancel_button=cancel_button,
        playlist_section=playlist_section,
        playlist_summary=playlist_summary,
        playlist_container=playlist_container,
    )
    update_job_card(handle, job, on_play=on_play)
    return handle


def update_job_card(handle: JobCardHandle, job: DownloadJob, on_play: Callable[[str], None]) -> None:
    """Met à jour une carte existante avec l'état courant du job (sans reconstruire le DOM)."""
    color, icon, text = _STATUS_STYLE.get(job.status, ("grey", "help", job.status.value))

    handle.title_label.set_text(job.title or job.url)
    handle.subtitle_label.set_text(job.options.fmt.label)
    handle.badge_icon.props(f"name={icon}")
    handle.badge_label.set_text(text)
    handle.badge.props(f"color={color}")

    handle.progress.set_value(job.progress / 100.0)
    handle.progress.props(f"color={color}")
    if job.status == JobStatus.PROCESSING and not job.options.is_playlist:
        handle.progress.props("indeterminate")
    else:
        handle.progress.props(remove="indeterminate")

    is_playlist = job.options.is_playlist
    if is_playlist and job.playlist_total:
        handle.percent_label.set_text(f"{job.playlist_completed} / {job.playlist_total} pistes")
    else:
        handle.percent_label.set_text(f"{job.progress:.0f}%")

    if job.status == JobStatus.ERROR and job.error:
        meta_text = job.error
    elif job.status == JobStatus.DONE:
        meta_text = "Terminé"
    elif job.status == JobStatus.CANCELLED:
        meta_text = "Annulé"
    elif job.status == JobStatus.PAUSED:
        meta_text = "En pause — cliquez sur « Reprendre » pour continuer"
    elif job.status in (JobStatus.PAUSING, JobStatus.CANCELLING):
        meta_text = "Arrêt en cours…"
    elif job.status == JobStatus.PROBING:
        meta_text = "Analyse de la playlist…" if job.options.is_playlist else "Analyse…"
    elif job.speed or job.eta:
        meta_text = " · ".join(x for x in (job.speed, f"ETA {job.eta}" if job.eta else "") if x)
    else:
        meta_text = ""
    handle.meta_label.set_text(meta_text)
    handle.meta_label.classes(
        add="text-negative" if job.status == JobStatus.ERROR else None,
        remove=None if job.status == JobStatus.ERROR else "text-negative",
    )

    handle.play_button.set_visibility(
        job.status == JobStatus.DONE and bool(job.filepath) and not is_playlist
    )
    handle.open_button.set_visibility(job.status == JobStatus.DONE and bool(job.filepath))

    # Pause : uniquement pendant un vrai travail actif (pas déjà en train de
    # s'arrêter). Reprendre : seulement en pause confirmée. Relancer :
    # seulement après un arrêt en erreur ou une annulation.
    handle.pause_button.set_visibility(
        job.status in (JobStatus.PROBING, JobStatus.DOWNLOADING, JobStatus.PROCESSING)
    )
    handle.resume_button.set_visibility(job.status == JobStatus.PAUSED)
    handle.restart_button.set_visibility(job.status in (JobStatus.ERROR, JobStatus.CANCELLED))

    handle.cancel_button.set_visibility(not job.status.is_terminal)
    # Désactivé (pas caché) pendant l'arrêt : retour visuel immédiat au clic,
    # sans donner l'impression qu'il faut recliquer pour que ça marche.
    if job.status == JobStatus.CANCELLING:
        handle.cancel_button.props("disable")
    else:
        handle.cancel_button.props(remove="disable")

    handle.playlist_section.set_visibility(is_playlist)
    if is_playlist:
        _update_playlist_rows(handle, job, on_play)


def _update_playlist_rows(handle: JobCardHandle, job: DownloadJob, on_play: Callable[[str], None]) -> None:
    """Crée/actualise en place les lignes de pistes d'une carte de playlist."""
    if job.playlist_total:
        handle.playlist_summary.set_text(f"{job.playlist_completed} / {job.playlist_total} pistes téléchargées")
    else:
        handle.playlist_summary.set_text("Préparation de la playlist…")

    for entry in job.playlist_entries:
        row = handle.playlist_rows.get(entry.index)
        if row is None:
            with handle.playlist_container:
                row = _create_playlist_row(entry, on_play)
            handle.playlist_rows[entry.index] = row
        _update_playlist_row(row, entry)


def _create_playlist_row(entry: PlaylistEntry, on_play: Callable[[str], None]) -> "PlaylistRowHandle":
    with ui.column().classes("w-full gap-0.5") as row:
        with ui.row().classes("w-full items-center gap-2 no-wrap"):
            track_icon = ui.icon("radio_button_unchecked").classes("text-sm")
            track_label = ui.label(entry.title).classes("text-xs truncate flex-grow min-w-0")
            track_stage = ui.label("").classes("text-[0.65rem] opacity-60 shrink-0")
            track_play = ui.button(icon="play_arrow", on_click=lambda: on_play(entry.filepath)).props(
                "flat dense round size=sm"
            )
        # Barre fine, propre à la piste : indéterminée pendant le
        # téléchargement/traitement, masquée une fois la piste au repos ou
        # terminée (l'icône suffit alors) — remplace l'icône tournante d'avant,
        # peu lisible.
        track_progress = ui.linear_progress(value=0.0, show_value=False).props("size=3px rounded").classes("w-full")
    return PlaylistRowHandle(
        root=row,
        icon=track_icon,
        label=track_label,
        stage_label=track_stage,
        progress=track_progress,
        play_button=track_play,
    )


def _update_playlist_row(row: "PlaylistRowHandle", entry: PlaylistEntry) -> None:
    color, icon = _TRACK_STYLE.get(entry.status, ("grey", "radio_button_unchecked"))
    row.icon.props(f"name={icon}").classes(replace=f"text-sm text-{color}")
    row.label.set_text(entry.title)
    row.stage_label.set_text(entry.stage)
    row.stage_label.set_visibility(bool(entry.stage))
    row.play_button.set_visibility(entry.status == JobStatus.DONE and bool(entry.filepath))

    active = entry.status in _TRACK_ACTIVE
    row.progress.set_visibility(active)
    row.progress.props(f"color={color}")
    if active:
        row.progress.props("indeterminate")
    else:
        row.progress.props(remove="indeterminate")


# --------------------------------------------------------------------------- #
# En-tête de section (façon "/ Label")
# --------------------------------------------------------------------------- #
def section_title(text: str) -> None:
    """Affiche un en-tête de section stylé (« / Label »), à l'intérieur d'une carte."""
    ui.label(text).classes("ytdl-section-title")


def section_header(title: str, subtitle: str = "") -> None:
    """En-tête de section pleine largeur (« / Titre » + sous-titre optionnel).

    Utilisé en haut de chaque section ancrée de la page (workspace, réglages, aide).
    """
    with ui.column().classes("gap-1 mb-2"):
        ui.label(title).classes("ytdl-heading ytdl-section-title text-lg")
        if subtitle:
            ui.label(subtitle).classes("text-sm opacity-60 max-w-md")


# --------------------------------------------------------------------------- #
# Carte de résumé + popup détaillé (façon carte recto-verso)
# --------------------------------------------------------------------------- #
def popup_card(title: str, icon: str, teaser: str, render_body: Callable[[], None]) -> None:
    """Une carte de résumé ; son clic ouvre le détail dans un popup animé.

    Utilisé par les sections « Aide » et « Installation » : une grille de
    cartes plutôt qu'un accordéon, chaque carte ouvrant son détail complet
    dans un popup qui se retourne à l'ouverture (façon carte recto-verso).

    Args:
        title: Titre affiché sur la carte et dans le popup.
        icon: Nom d'icône Material.
        teaser: Résumé d'une ligne, affiché sur la carte.
        render_body: Callable construisant le contenu détaillé du popup
            (peut appeler ``ui.markdown``, ``ui.code``, etc.).
    """
    dialog = _build_popup_dialog(title, icon, render_body)

    with ui.card().classes("ytdl-glass ytdl-help-card w-full p-5 gap-2 cursor-pointer").on(
        "click", dialog.open
    ):
        ui.icon(icon).classes("text-3xl text-primary")
        ui.label(title).classes("ytdl-heading font-semibold")
        ui.label(teaser).classes("text-xs opacity-60")


def nav_card(icon: str, label: str, on_click: Callable[[], None]) -> None:
    """Carte de raccourci compacte, cliquable (icône + libellé, sans texte
    descriptif — les 5 tiennent ainsi sur une seule ligne).

    Même habillage visuel que :func:`popup_card`, mais bascule une section de
    l'accueil natif au clic plutôt que d'ouvrir un popup — voir
    ``ytdl.ui.app._build_native_home_extras``. Un clic Python plutôt qu'un
    vrai lien : ça évite de recharger la page (et donc de couper le lecteur
    audio s'il joue).
    """
    with ui.card().classes(
        "ytdl-glass ytdl-help-card w-full h-full p-3 gap-1 items-center cursor-pointer"
    ).on("click", on_click):
        ui.icon(icon).classes("text-2xl text-primary")
        ui.label(label).classes("ytdl-heading font-semibold text-sm")


def _build_popup_dialog(title: str, icon: str, render_body: Callable[[], None]) -> ui.dialog:
    """Construit (une seule fois) le popup détaillé associé à une carte."""
    with ui.dialog() as dialog, ui.card().classes("ytdl-glass ytdl-flip-card p-6 gap-3 max-w-lg"):
        with ui.row().classes("items-center gap-2"):
            ui.icon(icon).classes("text-2xl text-primary")
            ui.label(title).classes("text-lg font-bold ytdl-heading")
        render_body()
        ui.button("Fermer", icon="close", on_click=dialog.close).props("flat").classes("self-end")
    return dialog


# --------------------------------------------------------------------------- #
# Nav flottante
# --------------------------------------------------------------------------- #
def nav_link(icon: str, label: str, target_id: str, section_key: str) -> None:
    """Un lien de la nav flottante, en mode web (ancre vers une section de la
    même page à défilement).

    Args:
        icon: Nom d'icône Material.
        label: Libellé affiché sous l'icône.
        target_id: ``id`` HTML de la section visée (sans ``#``).
        section_key: Clé utilisée par le scroll-spy JS pour la surbrillance
            (repère la section visible dont l'``id`` de conteneur porte
            ``data-nav-section={section_key}``).
    """
    with ui.element("a").props(f"href=#{target_id}").classes("no-underline ytdl-nav-item") as link:
        link.props(f"data-section={section_key}")
        ui.icon(icon)
        ui.label(label)


def nav_button(icon: str, label: str, on_click: Callable[[], None]) -> ui.column:
    """Un item de la nav flottante cliquable, en mode natif (bascule de
    section en Python — jamais une vraie navigation, pour ne jamais couper
    l'audio du lecteur en cours de lecture).

    Returns:
        L'élément racine, pour pouvoir basculer sa classe ``active`` depuis
        l'appelant (qui sait quelle section est actuellement affichée).
    """
    with ui.column().classes("ytdl-nav-item").on("click", on_click) as item:
        ui.icon(icon)
        ui.label(label)
    return item


# --------------------------------------------------------------------------- #
# Pastille de statut (ex. disponibilité de ffmpeg)
# --------------------------------------------------------------------------- #
def status_pill(text: str, icon: str, color: str) -> None:
    """Petite pastille arrondie affichant un statut (couleur + icône + texte)."""
    with ui.row().classes(
        f"items-center gap-1.5 px-3 py-1 rounded-full text-xs ytdl-glass text-{color}"
    ):
        ui.icon(icon).classes("text-sm")
        ui.label(text)


# --------------------------------------------------------------------------- #
# Tuile de format sélectionnable (grille)
# --------------------------------------------------------------------------- #
def format_tile(icon: str, label: str, active: bool, on_click: Callable[[], None]) -> ui.column:
    """Une tuile cliquable de sélection de format, pour une grille de choix.

    Returns:
        L'élément racine (pour pouvoir basculer sa classe ``ytdl-tile-active``).
    """
    classes = "ytdl-tile p-3 gap-1 items-center" + (" ytdl-tile-active" if active else "")
    with ui.column().classes(classes).on("click", on_click) as tile:
        ui.icon(icon).classes("text-2xl")
        ui.label(label).classes("text-xs font-medium")
    return tile

"""Contenu de l'aide interactive : textes des tooltips et onglet « Aide ».

Centraliser les explications ici permet de les réutiliser (info-bulles sur chaque
option + page d'aide) et de les maintenir en un seul endroit.
"""

from __future__ import annotations

from functools import partial

from nicegui import ui

from . import components

# Info-bulles courtes, affichées via une icône « ? » à côté de chaque réglage.
TOOLTIPS: dict[str, str] = {
    "url": "Collez l'URL d'une vidéo ou d'une playlist, puis cliquez sur « Analyser ».",
    "format": (
        "MP4 : vidéo universelle. WebM : souvent meilleure qualité à taille égale. "
        "MP3 : audio compatible partout. M4A : audio de meilleure qualité à débit égal. "
        "« Meilleur » laisse yt-dlp choisir le flux optimal."
    ),
    "quality": (
        "Pour la vidéo : hauteur maximale (1080 = Full HD, 2160 = 4K). "
        "Pour l'audio : débit en kbps (320 = quasi sans perte). "
        "« best » prend toujours le maximum disponible."
    ),
    "subtitles": "Télécharge et intègre les sous-titres (y compris auto-générés) dans le fichier.",
    "metadata": "Écrit le titre, l'auteur et la date dans les métadonnées du fichier.",
    "thumbnail": "Intègre la miniature comme pochette (idéal pour l'audio dans un lecteur).",
    "playlist_items": "Sélection d'éléments, ex. « 1-5,8,10 ». Vide = toute la playlist.",
    "template": (
        "Gabarit de nom de fichier yt-dlp. Variables utiles : %(title)s, %(uploader)s, "
        "%(id)s, %(ext)s, %(playlist_index)s."
    ),
    "concurrent": "Nombre de téléchargements traités en même temps.",
    "clean_titles": (
        "Retire automatiquement du titre les mentions comme « (Official Video) », "
        "« (Clip Officiel) », « (Lyric Video) »… avant d'enregistrer le fichier et "
        "ses métadonnées."
    ),
    "sleep_interval": (
        "Pause avant chaque téléchargement et chaque requête (utile surtout pour les "
        "playlists). Réduit le risque de throttling/blocage temporaire par le site "
        "source. 0 = désactivé."
    ),
    "rate_limit": (
        "Limite la vitesse de téléchargement pour paraître moins agressif vis-à-vis du "
        "site source. 0 = pas de limite."
    ),
    "cookies_browser": (
        "yt-dlp réutilise les cookies de session de ce navigateur pour s'authentifier : "
        "nécessaire pour les playlists privées (Liked videos, Watch Later) ou le contenu "
        "réservé aux abonnés. Le navigateur doit être installé et connecté."
    ),
    "skip_archived": (
        "Tient un registre (dans le dossier de téléchargement) des identifiants vidéo déjà "
        "obtenus. Relancer une playlist interrompue saute directement ce qui est déjà "
        "téléchargé, même si les fichiers ont été renommés/nettoyés entre-temps."
    ),
    "spotify_format": (
        "MP3 : audio compatible partout. FLAC : sans perte (fichiers plus lourds). "
        "OGG/Opus : bonne qualité à taille réduite. M4A : bonne qualité à débit égal. "
        "WAV : brut, non compressé."
    ),
    "spotify_bitrate": (
        "Débit audio en kbps (320 = quasi sans perte). « auto » garde le débit de la "
        "source trouvée, sans ré-encodage forcé."
    ),
}

# Sections de la page d'aide : titre, icône, teaser (visible sur la carte),
# corps complet en markdown (affiché dans le popup au clic).
HELP_SECTIONS: list[tuple[str, str, str, str]] = [
    (
        "Prise en main",
        "rocket_launch",
        "Les 3 étapes pour lancer un premier téléchargement.",
        """
1. Collez une URL dans la section **Télécharger** et cliquez sur **Analyser**.
2. Vérifiez l'aperçu (titre, durée, miniature), choisissez le **format** et la **qualité**.
3. Cliquez sur **Ajouter à la file** : le téléchargement démarre juste à côté,
   dans la colonne **Téléchargements**.
""",
    ),
    (
        "Formats & qualité",
        "movie",
        "MP4, WebM, MP3, M4A… quelle différence, et laquelle choisir.",
        """
- **MP4 / WebM** : vidéo. Au-delà de 720p, YouTube sépare vidéo et audio ;
  ffmpeg les fusionne automatiquement.
- **MP3 / M4A** : extraction audio (nécessite ffmpeg).
- **Meilleur audio / vidéo** : yt-dlp choisit le flux optimal, sans ré-encodage.
""",
    ),
    (
        "Playlists",
        "playlist_play",
        "Téléchargez tout ou une sélection, suivi piste par piste.",
        """
Collez l'URL d'une playlist : l'aperçu indique le nombre d'éléments. Activez
**Traiter comme une playlist** et, au besoin, restreignez avec un champ comme
`1-5,8`. Une entrée en échec ne bloque pas les suivantes.

La carte de la file d'attente affiche chaque piste individuellement (☐ en
attente, ⬇ en cours, ✓ terminée) avec un compteur « x / y pistes », mis à
jour en direct au fil du téléchargement.
""",
    ),
    (
        "Playlists privées",
        "lock",
        "« Liked videos », « Watch Later »… nécessitent une connexion.",
        """
Les playlists **« Liked videos » (LL)**, **« Watch Later » (WL)** ou toute
playlist privée n'existent qu'associées à votre compte connecté. Sans
authentification, yt-dlp ne peut pas les lire et bascule silencieusement en
téléchargement de la seule vidéo — l'app affiche alors un avertissement à
l'analyse.

Pour y accéder : dans **Réglages → Authentification**, choisissez votre
navigateur (Chrome, Firefox, Safari…) dans **Cookies navigateur**. Il doit
être installé sur cette machine et vous y être connecté à YouTube.
""",
    ),
    (
        "Lecture",
        "play_circle",
        "Écoutez ou regardez un fichier dès qu'il est prêt, en un clic.",
        """
Une fois un fichier terminé, un bouton **Lire** l'ouvre avec l'application
par défaut de votre système (lecteur audio/vidéo habituel). Pour une
playlist, chaque piste a son propre bouton de lecture dès qu'elle est prête.
""",
    ),
    (
        "ffmpeg",
        "build",
        "Le composant requis pour l'audio et la vidéo HD.",
        """
`ffmpeg` est requis pour l'audio, la vidéo HD et l'intégration des métadonnées.
S'il manque, un bandeau apparaît en haut de l'application avec la commande
d'installation adaptée à votre système.
""",
    ),
    (
        "Runtime JavaScript (Node.js)",
        "javascript",
        "Requis par yt-dlp pour déchiffrer les flux YouTube.",
        """
YouTube pose un défi JavaScript pour déchiffrer les liens de flux vidéo/audio ;
yt-dlp a besoin d'un runtime JS (**Node.js 22+**, Deno ou Bun) pour le résoudre.

Sans lui, la plupart des formats disparaissent et les téléchargements
échouent avec « *Requested format is not available* », même avec des cookies
valides. Un bandeau apparaît en haut de l'application si aucun runtime
suffisant n'est détecté.
""",
    ),
    (
        "Éviter un blocage IP",
        "shield",
        "Un usage intensif peut se faire limiter par le site source.",
        """
En téléchargeant beaucoup en peu de temps (gros playlists, usage répété), le
site source peut temporairement limiter ou bloquer votre IP (erreurs 429,
CAPTCHA) — rarement définitif puisqu'aucun compte n'est utilisé.

Dans **Réglages → Anti-throttling** :
- **Délai entre téléchargements** : espace les requêtes, surtout utile sur
  les playlists.
- **Débit maximal** : rend le trafic moins agressif.
- Évitez aussi un nombre de **téléchargements simultanés** trop élevé.
""",
    ),
    (
        "Spotify",
        "library_music",
        "Nécessite un outil externe (spotdl) installé séparément.",
        """
Le téléchargement Spotify s'appuie sur **spotdl**, un outil externe — pas
inclus dans ytdl, à installer séparément (`pipx install spotdl`) : ses
propres dépendances entrent en conflit avec celles de l'application si on
les mélange dans le même environnement. Une pastille en haut de l'application
indique s'il est détecté.

spotdl retrouve chaque titre Spotify sur YouTube/YouTube Music et en
télécharge l'audio, avec pochette et métadonnées automatiquement intégrées.

Contrairement à YouTube, il n'y a pas de case « playlist » à cocher (une URL
de playlist/album télécharge toujours tout) ni de sélection d'éléments —
spotdl ne le permet pas.
""",
    ),
    (
        "Fichiers & nommage",
        "folder",
        "Où et sous quel nom vos téléchargements sont enregistrés.",
        """
Le dossier de destination et le **gabarit de nom** se règlent dans la section
**Réglages**. Exemple de gabarit : `%(uploader)s - %(title)s.%(ext)s`.

Activez **Nettoyer les titres** pour retirer automatiquement les mentions comme
`(Official Video)` ou `(Clip Officiel)` des noms de fichiers et métadonnées.
""",
    ),
]


def help_icon(key: str) -> None:
    """Ajoute une petite icône « ? » portant l'info-bulle ``TOOLTIPS[key]``."""
    text = TOOLTIPS.get(key, "")
    ui.icon("help_outline").classes("text-primary cursor-help text-sm").tooltip(text)


def build_help_panel() -> None:
    """Construit le contenu de la section « Aide » : une grille de cartes.

    Chaque carte résume un sujet ; cliquer dessus ouvre le détail dans un
    popup qui se retourne à l'ouverture (façon carte recto-verso), plutôt
    qu'un accordéon qui se déplie sur place.
    """
    with ui.column().classes("w-full gap-4 ytdl-fade-in"):
        with ui.grid(columns=2).classes("w-full gap-4"):
            for title, icon, teaser, body in HELP_SECTIONS:
                components.popup_card(title, icon, teaser, partial(ui.markdown, body))

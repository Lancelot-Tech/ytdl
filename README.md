# 🎬 ytdl — Téléchargeur vidéo & audio

Application moderne pour télécharger des vidéos et de l'audio (YouTube et des
centaines d'autres sites), avec choix du format/qualité, playlists, sous-titres,
métadonnées et **file d'attente à progression temps réel**.

Interface **NiceGUI** (jolie, dynamique), moteur **[yt-dlp](https://github.com/yt-dlp/yt-dlp)**.
Lançable **dans le navigateur** ou en **fenêtre native**. Idéal pour les DJ ! 🎧

> Réécriture complète de l'ancienne version PyQt5 + `pytube` (devenu non-fiable).

---

## ✨ Fonctionnalités

- **Formats** : MP4, WebM, MP3, M4A, ou « meilleur audio/vidéo » automatique.
- **Qualité** : jusqu'à la 4K pour la vidéo, jusqu'à 320 kbps pour l'audio.
- **Playlists** : téléchargez tout, ou une sélection (`1-5,8`), avec le détail de
  chaque piste (☐/⬇/✓) mis à jour en direct dans la file d'attente.
- **Sous-titres & métadonnées** : intégration des sous-titres, titre/auteur, miniature.
- **File d'attente** : plusieurs téléchargements en parallèle, barres de progression,
  vitesse et ETA en direct.
- **Lecture en un clic** : bouton **Lire** sur chaque fichier terminé (et chaque
  piste de playlist), ouvre avec le lecteur par défaut du système.
- **Aide interactive** : info-bulles sur chaque option + section d'aide (cartes + popup détaillé).
- **Titres propres** : retire automatiquement « (Official Video) », « (Clip Officiel) »… (réglage désactivable).
- **Anti-throttling** : délai entre téléchargements et limite de débit réglables, pour
  réduire le risque de blocage temporaire par le site source sur un usage intensif.
- **Réglages appliqués sans redémarrage**, y compris le nombre de téléchargements simultanés.
- **Thème clair/sombre** avec réglages persistants.
- **Page unique à ancres** : une nav flottante relie les sections (Accueil, Télécharger,
  File d'attente, Réglages, Aide, Installation) sans rechargement, façon portfolio.
- **Déployable partout** : web, fenêtre native, Docker, AppImage (Linux) ou exécutable
  Windows/macOS/Linux — voir [Déploiement](#-déploiement).

---

## 📦 Prérequis

> Avec **Docker**, aucun prérequis : ffmpeg et Node.js sont déjà inclus dans
> l'image. Voir [Déploiement](#-déploiement).

- **Python 3.9+**
- **ffmpeg** — requis pour l'audio (MP3/M4A), la vidéo HD (fusion des flux) et
  l'intégration des métadonnées. L'app affiche un bandeau si ffmpeg est absent.
- **Node.js 22+** (ou Deno/Bun) — requis par yt-dlp pour résoudre le défi
  JavaScript posé par YouTube sur les flux vidéo/audio. Sans lui, la plupart
  des téléchargements YouTube échouent avec « Requested format is not
  available », même avec des cookies valides. L'app affiche aussi un bandeau
  si aucun runtime JS suffisant n'est détecté.

| Système  | Installation de ffmpeg | Installation de Node.js |
|----------|------------------------|--------------------------|
| macOS    | `brew install ffmpeg`  | `brew install node`     |
| Linux    | `sudo apt install ffmpeg` | `sudo apt install nodejs` (>= 22 ; sinon [nodejs.org](https://nodejs.org/)) |
| Windows  | `winget install ffmpeg` | `winget install OpenJS.NodeJS.LTS` |

---

## 🚀 Installation

```bash
# 1. Créer et activer un environnement virtuel
python3 -m venv .venv
. .venv/bin/activate          # Windows : .\.venv\Scripts\activate

# 2. Installer les dépendances
pip install -r requirements.txt
```

> Windows : si l'activation échoue, lancez PowerShell en administrateur puis
> `Set-ExecutionPolicy RemoteSigned`.

---

## 🖥️ Utilisation

```bash
python -m ytdl              # ouvre l'appli dans le navigateur
python -m ytdl --native     # ouvre une fenêtre native
python -m ytdl --port 9000  # choisir le port
python main.py              # équivalent (compatibilité ascendante)
```

La page défile en une seule fois ; la nav flottante en haut saute directement à
chaque section (**Accueil**, **Télécharger**, **File d'attente**, **Réglages**, **Aide**).

1. Collez une URL et cliquez sur **Analyser** (aperçu : titre, durée, miniature).
2. Choisissez le **format** (grille de tuiles) et la **qualité**, cochez sous-titres/métadonnées si besoin.
3. Cliquez sur **Ajouter à la file** : la progression s'affiche en temps réel juste à
   côté, dans la colonne **File d'attente** de la même section.

Le dossier de destination et le gabarit de nom se règlent dans la section **Réglages**
(par défaut : `~/Downloads`, `%(uploader)s - %(title)s.%(ext)s`).

---

## 🧱 Architecture

Le code sépare nettement le **cœur** (sans UI, testable) de l'**interface** :

```
ytdl/
├── models.py        # types + traduction des options vers yt-dlp (cœur testé)
├── downloader.py    # enveloppe yt-dlp (analyse + téléchargement)
├── queue.py         # file d'attente multi-threads (concurrence modifiable à chaud)
├── config.py        # réglages persistants (surchargeables par variables d'env)
├── ffmpeg_check.py  # détection de ffmpeg
├── jsruntime_check.py  # détection d'un runtime JS (Node/Deno/Bun, requis par yt-dlp)
├── library.py       # scan d'un dossier local pour le lecteur intégré (mode natif)
└── ui/              # interface NiceGUI (app, thème, composants, aide, installation, lecteur)
tests/               # tests unitaires (yt-dlp mocké, sans réseau)
packaging/           # scripts de build : binaire natif (nicegui-pack) et AppImage
Dockerfile, docker-compose.yml, .dockerignore
```

---

## 🧪 Développement & tests

```bash
. .venv/bin/activate
pytest                 # suite complète (aucun accès réseau requis)
pytest -m network      # tests d'intégration réels (désactivés par défaut)
```

Les tests couvrent la traduction des options (`DownloadOptions.to_ydl_opts`), le
`Downloader` (yt-dlp mocké) et les transitions d'état de la file.

---

## 🚢 Déploiement

L'application est déployable de plusieurs façons (aussi listées dans la section
**Installation** de l'app elle-même). Réglages via variables d'environnement,
utiles pour Docker : `YTDL_DOWNLOAD_DIR`, `YTDL_CONFIG_DIR`, `YTDL_PORT`.

### Docker

```bash
docker build -t ytdl .
docker run -d --name ytdl -p 8080:8080 \
  -v ~/Downloads:/downloads \
  -v ytdl-config:/config \
  ytdl
```

Ou avec `docker compose up -d` (voir `docker-compose.yml`, gère les volumes
pour les téléchargements et la persistance des réglages). ffmpeg et Node.js
sont déjà inclus dans l'image.

### AppImage (Linux)

```bash
./packaging/build-appimage.sh
chmod +x dist/ytdl-*.AppImage
./dist/ytdl-*.AppImage
```

Télécharge `appimagetool` si besoin et construit l'AppImage depuis les sources.

### Exécutable natif (Windows / macOS / Linux)

```bash
python packaging/build_binary.py
```

S'appuie sur `nicegui-pack` (PyInstaller préconfiguré pour NiceGUI). Résultat
dans `dist/ytdl/` (dossier à distribuer/zipper), `dist/ytdl.app` sur macOS. Le
binaire s'ouvre directement en fenêtre native, sans terminal. Ce script doit
être exécuté séparément sur chaque OS cible (pas de cross-compilation).

### Depuis les sources

Voir [Installation](#-installation) et [Utilisation](#️-utilisation) plus haut.

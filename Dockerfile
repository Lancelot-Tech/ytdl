# Image légère pour faire tourner ytdl en mode web (pas de mode natif en
# conteneur : pas d'affichage). ffmpeg est inclus, indispensable pour l'audio
# et la vidéo HD.

# Binaire Node seul, copié depuis l'image officielle (évite un dépôt apt tiers
# ou npm) : yt-dlp en a besoin (>= 22) pour résoudre le défi JavaScript posé
# par YouTube sur les flux vidéo/audio — sans lui, la plupart des formats
# échouent avec « Requested format is not available ».
FROM node:22-slim AS node

FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node /usr/local/bin/node /usr/local/bin/node

WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY ytdl ./ytdl
COPY main.py ./
COPY assets ./assets

# Dossier de téléchargement et de configuration, à monter en volume pour
# conserver les fichiers/réglages entre redémarrages du conteneur.
ENV YTDL_DOWNLOAD_DIR=/downloads \
    YTDL_CONFIG_DIR=/config \
    YTDL_PORT=8080
RUN mkdir -p /downloads /config
VOLUME ["/downloads", "/config"]

EXPOSE 8080

CMD ["python", "-m", "ytdl", "--no-show"]

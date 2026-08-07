"""Thème et styles de l'application.

Plusieurs palettes de couleurs au choix (voir :data:`THEMES`), sélectionnables
en direct via le bouton palette (bas de l'écran) sans recharger la page — un
premier choix de palette imposé (« cuivre ») n'ayant pas plu, mieux vaut
laisser la main plutôt que d'en imposer un autre. Le reste de l'habillage
(nav flottante en pilule, pluie de notes de musique en fond, police mono
dédiée aux lectures de données façon afficheur d'appareil) est commun à
toutes les palettes. Tout le CSS/JS spécifique est regroupé ici pour garder
les composants lisibles ; tout part de variables CSS (``--ytdl-accent`` etc.)
posées une fois ci-dessous, jamais de couleur recopiée en dur ailleurs dans
l'app — c'est ce qui permet à une palette de s'appliquer partout d'un coup.
"""

from __future__ import annotations

from dataclasses import dataclass

from nicegui import ui


@dataclass(frozen=True)
class ThemeColors:
    """Les couleurs d'une palette pour un mode (clair ou sombre) donné."""

    bg: str
    accent: str
    secondary: str
    text: str
    subtext: str
    rain: str


@dataclass(frozen=True)
class ThemeDef:
    """Une palette complète : ses deux variantes clair/sombre + son libellé."""

    key: str
    label: str
    dark: ThemeColors
    light: ThemeColors


# --------------------------------------------------------------------------- #
# Palettes au choix. Chacune a été vérifiée au ratio de contraste WCAG
# (accent/secondaire/texte/sous-texte contre leur fond) : tout est ≥ 4.5:1.
# "violet" est la palette d'origine de l'app (glassmorphism), reprise comme
# choix par défaut ; les autres sont des directions alternatives, dont
# "cuivre" (matériel hi-fi) qui était l'ancien réglage imposé par défaut.
# --------------------------------------------------------------------------- #
THEMES: dict[str, ThemeDef] = {
    "violet": ThemeDef(
        key="violet",
        label="Violet",
        dark=ThemeColors(
            bg="#0f0d29", accent="#a78bfa", secondary="#38bdf8",
            text="#ffffff", subtext="#b2bed1", rain="#7d7b9c",
        ),
        light=ThemeColors(
            bg="#f5f3ff", accent="#7c3aed", secondary="#0369a1",
            text="#1e1b4b", subtext="#4b5563", rain="#97a7dc",
        ),
    ),
    "copper": ThemeDef(
        key="copper",
        label="Cuivre",
        dark=ThemeColors(
            bg="#161512", accent="#c17f3e", secondary="#4fb8ae",
            text="#f5f1e8", subtext="#a89b87", rain="#5f5548",
        ),
        light=ThemeColors(
            bg="#f7f3ea", accent="#8f5820", secondary="#146b62",
            text="#2a2419", subtext="#6b5f4d", rain="#c4b8a3",
        ),
    ),
    "ocean": ThemeDef(
        key="ocean",
        label="Océan",
        dark=ThemeColors(
            bg="#0b1622", accent="#38bdf8", secondary="#2dd4bf",
            text="#eef6fb", subtext="#9fb4c4", rain="#345166",
        ),
        light=ThemeColors(
            bg="#f0f7fb", accent="#0369a1", secondary="#0f766e",
            text="#0c2233", subtext="#4b6478", rain="#b8d3e6",
        ),
    ),
    "forest": ThemeDef(
        key="forest",
        label="Forêt",
        dark=ThemeColors(
            bg="#0f1912", accent="#4ade80", secondary="#22d3ee",
            text="#eef7ee", subtext="#9db8a0", rain="#34503a",
        ),
        light=ThemeColors(
            bg="#f2f7ee", accent="#15803d", secondary="#0e7490",
            text="#14231a", subtext="#4d5f4f", rain="#a9c7ae",
        ),
    ),
    "sunset": ThemeDef(
        key="sunset",
        label="Couchant",
        dark=ThemeColors(
            bg="#1a0f14", accent="#fb7185", secondary="#fbbf24",
            text="#fdf1f2", subtext="#b98a92", rain="#4a2530",
        ),
        light=ThemeColors(
            bg="#fdf2ee", accent="#be123c", secondary="#b45309",
            text="#2a1418", subtext="#7a5158", rain="#e8c3c9",
        ),
    ),
    "slate": ThemeDef(
        key="slate",
        label="Ardoise",
        dark=ThemeColors(
            bg="#16181d", accent="#60a5fa", secondary="#a78bfa",
            text="#f1f5f9", subtext="#94a3b8", rain="#475569",
        ),
        light=ThemeColors(
            bg="#f8fafc", accent="#2563eb", secondary="#7c3aed",
            text="#0f172a", subtext="#64748b", rain="#cbd5e1",
        ),
    ),
}

DEFAULT_THEME_KEY = "violet"


def colors_for(theme_key: str, dark_mode: bool) -> ThemeColors:
    """Couleurs de la palette ``theme_key`` (repli sur la palette par défaut
    si la clé est inconnue — ex. un ancien fichier de config)."""
    theme_def = THEMES.get(theme_key, THEMES[DEFAULT_THEME_KEY])
    return theme_def.dark if dark_mode else theme_def.light


def _hex_rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


# Couleurs de statut : communes à toutes les palettes (badges, toasts,
# graphe des résultats) — rester reconnaissable quel que soit le thème
# esthétique choisi importe plus ici que s'accorder avec chaque accent.
POSITIVE = "#10b981"
NEGATIVE = "#f87171"
WARNING = "#f59e0b"

_FONTS_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Space+Mono:wght@400;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
"""

def _theme_css_block(colors: ThemeColors, selector: str) -> str:
    """Bloc de variables CSS pour une palette + un mode (clair/sombre).

    Le fond du "verre dépoli" et sa bordure sont dérivés de l'accent de la
    palette (teinté quand sombre, neutre en clair pour rester lisible sur un
    fond parfois très clair) plutôt que fixés en dur — une nouvelle palette
    n'a donc rien d'autre à fournir que ses 6 couleurs de base.
    """
    r, g, b = _hex_rgb(colors.accent)
    is_dark = selector.endswith(".body--dark")
    if is_dark:
        glass_bg = f"rgba({r}, {g}, {b}, 0.07)"
        glass_border = f"rgba({r}, {g}, {b}, 0.18)"
    else:
        glass_bg = "rgba(255, 255, 255, 0.6)"
        glass_border = f"rgba({r}, {g}, {b}, 0.14)"
    return f"""{selector} {{
  --ytdl-bg: {colors.bg};
  --ytdl-accent: {colors.accent};
  --ytdl-secondary: {colors.secondary};
  --ytdl-text: {colors.text};
  --ytdl-subtext: {colors.subtext};
  --ytdl-rain: {colors.rain};
  --ytdl-glass-bg: {glass_bg};
  --ytdl-glass-border: {glass_border};
}}"""


def _all_themes_css() -> str:
    """CSS des variables de couleur pour toutes les palettes.

    Chaque palette est scopée par une classe sur ``<body>``
    (``.ytdl-theme-{clé}``), posée par :func:`apply` puis échangée en direct
    par le bouton palette (voir ``ytdl.ui.app._set_theme``) — pas de
    rechargement de page nécessaire pour changer de palette, seule la classe
    change et toutes les variables CSS qui en découlent suivent aussitôt.
    Le repli ``:root``/``.body--dark`` (palette par défaut, sans classe)
    couvre le bref instant avant que le script client n'ait posé la classe.
    """
    default = THEMES[DEFAULT_THEME_KEY]
    blocks = [
        _theme_css_block(default.light, ":root"),
        _theme_css_block(default.dark, ".body--dark"),
    ]
    for theme_def in THEMES.values():
        blocks.append(_theme_css_block(theme_def.light, f".ytdl-theme-{theme_def.key}"))
        blocks.append(_theme_css_block(theme_def.dark, f".ytdl-theme-{theme_def.key}.body--dark"))
    return "\n".join(blocks)


_CUSTOM_CSS_TEMPLATE = """
<style>
__THEME_TOKENS__

html { scroll-behavior: smooth; scroll-padding-top: 6.5rem; }
.q-field, .q-btn { font-family: 'Inter', sans-serif; }
.ytdl-heading { font-family: 'Space Grotesk', sans-serif; }

/* Lecture de données façon afficheur d'appareil : débit, ETA, %, temps de
   lecture, volume, compteurs "X/Y pistes". Chiffres tabulaires (largeur fixe,
   pas de gigue quand un chiffre change) + espacement léger pour l'effet
   "écran". Réservée aux valeurs qui changent en direct — pas un style de
   titre. */
.ytdl-mono {
  font-family: 'Space Mono', monospace;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
}

/* Le dégradé vit sur <body> (toujours le calque le plus en arrière) pour que
   la pluie de caractères, en z-index négatif juste au-dessus, reste visible
   sur toute la hauteur de la page plutôt que d'être recouverte par le fond
   opaque d'un conteneur de contenu. */
body {
  font-family: 'Inter', sans-serif;
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--ytdl-bg), black 16%) 0%,
    var(--ytdl-bg) 50%,
    color-mix(in srgb, var(--ytdl-bg), white 16%) 100%
  );
  background-attachment: fixed;
  min-height: 100vh;
}

.ytdl-bg {
  color: var(--ytdl-text);
  min-height: 100vh;
  position: relative;
}

.ytdl-glass {
  background: var(--ytdl-glass-bg) !important;
  backdrop-filter: blur(14px);
  border: 1px solid var(--ytdl-glass-border);
  border-radius: 1rem !important;
  box-shadow: 0 8px 32px rgba(22, 21, 18, 0.12);
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}
.ytdl-glass:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 40px rgba(22, 21, 18, 0.18);
}

.ytdl-fade-in { animation: ytdlFade 0.3s ease both; }
.ytdl-reveal { opacity: 0; transform: translateY(18px); animation: ytdlReveal 0.7s cubic-bezier(0.2,0.8,0.2,1) forwards; }
@keyframes ytdlFade {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes ytdlReveal {
  to { opacity: 1; transform: translateY(0); }
}

/* En-têtes de section façon "/ Label" */
.ytdl-section-title {
  font-family: 'Space Grotesk', sans-serif;
  color: var(--ytdl-accent);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-size: 0.8rem;
  font-weight: 700;
}
.ytdl-section-title::before { content: "/ "; opacity: 0.7; }

/* Tuiles de format sélectionnables (grille) */
.ytdl-tile {
  border-radius: 0.9rem;
  border: 1.5px solid var(--ytdl-glass-border);
  background: var(--ytdl-glass-bg);
  backdrop-filter: blur(10px);
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: center;
}
.ytdl-tile:hover {
  border-color: var(--ytdl-accent);
  transform: translateY(-1px);
}
.ytdl-tile-active {
  border-color: var(--ytdl-accent);
  background: color-mix(in srgb, var(--ytdl-accent) 16%, transparent);
  box-shadow: 0 0 0 1px var(--ytdl-accent), 0 8px 24px color-mix(in srgb, var(--ytdl-accent) 25%, transparent);
}

/* Cartes du centre d'aide */
.ytdl-help-card:hover {
  border-color: var(--ytdl-accent);
  transform: translateY(-3px);
}

/* Popup d'aide : bascule à l'ouverture, façon carte recto-verso */
.ytdl-flip-card {
  animation: ytdlFlipIn 0.5s cubic-bezier(0.2, 0.8, 0.2, 1) both;
  transform-style: preserve-3d;
  backface-visibility: hidden;
}
@keyframes ytdlFlipIn {
  from { transform: perspective(1200px) rotateY(-100deg); opacity: 0; }
  to   { transform: perspective(1200px) rotateY(0deg); opacity: 1; }
}

/* Nav flottante en pilule, reliant des ancres de la page */
.ytdl-nav {
  position: fixed;
  top: 1.25rem;
  left: 50%;
  transform: translateX(-50%);
  z-index: 40;
  display: flex;
  align-items: center;
  gap: 1.6rem;
  padding: 0.55rem 1.75rem;
  border-radius: 9999px;
  border: 1.2px solid var(--ytdl-glass-border);
  background: var(--ytdl-glass-bg);
  backdrop-filter: blur(14px);
  box-shadow: 0 8px 24px rgba(22, 21, 18, 0.15);
}
/* .ytdl-nav-item : sélecteur de classe plutôt que le tag "a", pour que les
   mêmes styles s'appliquent aussi bien à un vrai lien (mode web, ancre dans
   la page) qu'à un bouton cliquable (mode natif, bascule de section en
   JS — pas de vraie navigation, pour ne jamais couper le lecteur audio). */
.ytdl-nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.1rem;
  color: var(--ytdl-accent);
  font-size: 0.7rem;
  text-decoration: none;
  opacity: 0.75;
  cursor: pointer;
  transition: opacity 0.2s ease, transform 0.2s ease, color 0.2s ease, text-shadow 0.2s ease;
}
.ytdl-nav-item .q-icon { font-size: 1.2rem; }
.ytdl-nav-item:hover { opacity: 1; transform: translateY(-1px); }
.ytdl-nav-item.active {
  color: var(--ytdl-text);
  opacity: 1;
  font-weight: 700;
  text-shadow: 0 0 12px color-mix(in srgb, var(--ytdl-accent) 60%, transparent);
}
/* Bouton jour/nuit + bouton palette, groupés côte à côte en haut à droite
   (voir ``ytdl.ui.app._build_theme_controls``) — un seul point fixe plutôt
   que deux, pour ne pas ajouter de marge/espace réservé ailleurs sur la page. */
.ytdl-theme-controls {
  position: fixed !important;
  top: 1rem;
  right: 1rem;
  z-index: 41;
  display: flex;
  align-items: center;
  gap: 0.3rem;
}

/* Mini-lecteur flottant (mode natif) : même traitement que le bouton
   jour/nuit — un petit élément à part, pas fondu dans la pilule de nav
   principale — mais côté opposé, en haut à gauche. */
.ytdl-player-mini {
  position: fixed;
  top: 1rem;
  left: 1rem;
  z-index: 41;
  display: flex;
  align-items: center;
  gap: 0.1rem;
  padding: 0.35rem 0.6rem;
  border-radius: 1.1rem;
  border: 1.2px solid var(--ytdl-glass-border);
  background: var(--ytdl-glass-bg);
  backdrop-filter: blur(14px);
  box-shadow: 0 8px 24px rgba(22, 21, 18, 0.15);
}

/* Bandeau défilant du titre en cours, sous les boutons du mini-lecteur —
   donne à la pastille à peu près la même hauteur que la pilule de nav
   (icône + libellé) au lieu de paraître écrasée à côté. */
.ytdl-marquee {
  width: 8.5rem;
  overflow: hidden;
  white-space: nowrap;
  mask-image: linear-gradient(90deg, transparent, black 8%, black 92%, transparent);
}
.ytdl-marquee-text {
  display: inline-block;
  padding-left: 100%;
  color: var(--ytdl-accent);
  font-size: 0.65rem;
  font-weight: 600;
  animation: ytdlMarquee 9s linear infinite;
}
@keyframes ytdlMarquee {
  0%   { transform: translateX(0); }
  100% { transform: translateX(-100%); }
}

@media (max-width: 700px) {
  .ytdl-nav { top: auto; bottom: 0.75rem; width: 92%; justify-content: space-between; padding: 0.5rem 1rem; }
}

/* Mode natif (fenêtre pywebview) uniquement : page statique, aucun
   défilement de la page elle-même (la fenêtre est dimensionnée une fois au
   démarrage sur la section la plus haute, voir _autofit_native_window). Un
   conteneur enfant avec son propre `overflow-y: auto` défile quand même
   normalement malgré ce blocage global — c'est le cas de la liste de pistes
   du Lecteur (voir ytdl/ui/player.py), seule à pouvoir dépasser une hauteur
   raisonnable. */
html.ytdl-native, body.ytdl-native {
  overflow: hidden !important;
  scrollbar-width: none;
}
html.ytdl-native::-webkit-scrollbar, body.ytdl-native::-webkit-scrollbar {
  display: none;
}

/* Fond animé : pluie de notes de musique sur toute la page.
   Position fixe (couvre tout le viewport en permanence, à n'importe quelle
   position de défilement) et z-index négatif : elle reste sous le contenu
   normal (z-index auto/0) sans jamais être recouverte par le fond de <body>,
   qui peint en tout premier. Pas de masque de dégradé : l'effet doit rester
   visible sur toute la hauteur de l'écran, pas seulement en haut. */
#ytdl-rain-container {
  position: fixed;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  overflow: hidden;
  opacity: 0.9;
}
.ytdl-falling-letter {
  position: absolute;
  top: -5vh;
  font-family: 'Space Grotesk', monospace;
  font-weight: 300;
  user-select: none;
  pointer-events: none;
  line-height: 1;
  animation: ytdlFall linear forwards;
}
@keyframes ytdlFall {
  0%   { transform: translateY(-5vh); opacity: 0; }
  10%  { opacity: 0.85; }
  90%  { opacity: 0.4; }
  100% { transform: translateY(105vh); opacity: 0; }
}

/* Bouton "retour en haut" */
#ytdl-to-top {
  position: fixed;
  bottom: 1.75rem;
  right: 1.75rem;
  z-index: 40;
  width: 3.1rem;
  height: 3.1rem;
  border-radius: 9999px;
  background: var(--ytdl-glass-bg);
  border: 1px solid var(--ytdl-glass-border);
  backdrop-filter: blur(10px);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  transform: translateY(16px);
  transition: opacity 0.35s ease, transform 0.35s ease;
  box-shadow: 0 8px 24px rgba(22, 21, 18, 0.2);
}
#ytdl-to-top.visible { opacity: 1; transform: translateY(0); }

/* Logo qui flotte légèrement dans le hero */
.ytdl-float {
  animation: ytdlFloat 6s ease-in-out infinite;
}
@keyframes ytdlFloat {
  0%, 100% { transform: translateY(0); }
  50%      { transform: translateY(-6px); }
}

/* Lecteur intégré (mode natif) : rangée de contrôle fixe en bas de la page
   du lecteur — trois cartes détachées (lecture en cours, contrôles, volume),
   chacune avec son propre verre dépoli (classe ytdl-glass), pas une seule
   barre continue. */
.ytdl-player-bar {
  position: fixed;
  bottom: 0.75rem;
  left: 1rem;
  right: 1rem;
  z-index: 40;
  display: flex;
  gap: 0.75rem;
}
.ytdl-track-row {
  transition: background-color 0.15s ease;
}
.ytdl-track-row:hover {
  background-color: var(--ytdl-glass-bg);
}
.ytdl-track-row-active {
  background-color: color-mix(in srgb, var(--ytdl-accent) 16%, transparent);
  color: var(--ytdl-accent);
}

/* Vu-mètre du débit de téléchargement : signe distinctif de l'accueil, à la
   place d'un graphe en ligne générique. Une rangée de segments verticaux
   façon appareil de mesure audio ; le nombre allumé (de gauche à droite)
   reflète le débit courant relatif au maximum observé (calculé côté Python,
   voir _build_speed_meter dans app.py), chaque segment teinté du cuivre (bas
   débit, à gauche) au sarcelle (haut débit, à droite) plutôt qu'une seule
   couleur unie. `align-items: stretch` (pas `flex-end`) : les segments sont
   des <div> vides sans hauteur de contenu propre, ils doivent donc être
   étirés sur toute la hauteur du conteneur pour être visibles du tout. */
.ytdl-vu-meter {
  display: flex;
  align-items: stretch;
  gap: 0.3rem;
  height: 100%;
  min-height: 4.5rem;
}
.ytdl-vu-segment {
  flex: 1 1 0;
  border-radius: 0.25rem;
  background: color-mix(in srgb, var(--ytdl-text) 8%, transparent);
  transition: background 0.4s ease, opacity 0.4s ease;
}
.ytdl-vu-segment.lit {
  background: var(--ytdl-vu-color, var(--ytdl-accent));
  box-shadow: 0 0 10px color-mix(in srgb, var(--ytdl-vu-color, var(--ytdl-accent)) 55%, transparent);
}

/* Respecte la préférence système "mouvement réduit" : coupe la pluie de fond
   (générée en JS, voir _BODY_SCRIPT) et les animations décoratives en boucle
   (logo flottant, transition des segments du vu-mètre). Les animations
   d'apparition ponctuelles (fade/reveal/flip) restent, car elles ne bouclent
   pas et durent moins d'une seconde. */
@media (prefers-reduced-motion: reduce) {
  #ytdl-rain-container { display: none; }
  .ytdl-float { animation: none; }
  .ytdl-marquee-text { animation: none; }
  .ytdl-vu-segment { transition: none; }
}
</style>
"""

_CUSTOM_CSS = _CUSTOM_CSS_TEMPLATE.replace("__THEME_TOKENS__", _all_themes_css())

# Pluie de caractères (DOM, pas de canvas) + scroll-spy de la nav + bouton retour
# en haut. Un seul script, injecté une fois par page.
_BODY_SCRIPT = """
<script>
(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  ready(function () {
    // --- Pluie de notes de musique en fond ----------------------------------
    let rain = document.getElementById('ytdl-rain-container');
    if (!rain) {
      rain = document.createElement('div');
      rain.id = 'ytdl-rain-container';
      document.body.prepend(rain);
    }
    // Array.from (pas juste une chaîne indexée) : la clé de sol est en
    // dehors du plan Unicode de base (paire de substitution sur 2 unités
    // UTF-16) — indexer directement la chaîne risquerait de piocher une
    // moitié de caractère et d'afficher un glyphe cassé.
    const chars = Array.from('\\u266a\\u266b\\u2669\\u266c\\u{1D11E}');

    function rainColor() {
      // Sur <body>, pas <html> : les variables de palette (--ytdl-rain
      // compris) sont posées via des classes sur <body> (.ytdl-theme-*,
      // .body--dark), qui n'existent pas sur son parent <html> — les lire
      // depuis documentElement aurait toujours renvoyé la valeur par défaut
      // de :root, jamais celle de la palette/du mode choisis.
      return getComputedStyle(document.body).getPropertyValue('--ytdl-rain').trim() || '#7d7b9c';
    }

    function spawnLetter() {
      const span = document.createElement('span');
      span.className = 'ytdl-falling-letter';
      const ch = chars[Math.floor(Math.random() * chars.length)];
      span.textContent = ch;
      const isClef = ch === '\\u{1D11E}';
      const left = Math.random() * 100;
      const duration = 5 + Math.random() * 8;
      // La clé de sol est nettement plus grande que les notes : à la même
      // taille que le reste, son tracé plus fin/complexe la rendait
      // méconnaissable (juste une tache floue).
      const size = isClef ? 24 + Math.random() * 16 : 10 + Math.random() * 10;
      const color = rainColor();
      span.style.left = left + 'vw';
      span.style.fontSize = size + 'px';
      span.style.color = color;
      span.style.textShadow = '0 0 6px ' + color;
      span.style.animationDuration = duration + 's';
      rain.appendChild(span);
      setTimeout(function () { span.remove(); }, duration * 1000);
    }

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (window.innerWidth > 700 && !reducedMotion && !window.__ytdlRainStarted) {
      window.__ytdlRainStarted = true;
      setInterval(spawnLetter, 180);
    }

    // --- Nav : surbrillance de la section visible ---------------------------
    const navLinks = document.querySelectorAll('.ytdl-nav a[data-section]');
    const sections = document.querySelectorAll('[data-nav-section]');
    if (sections.length && navLinks.length) {
      const observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            const key = entry.target.getAttribute('data-nav-section');
            navLinks.forEach(function (a) {
              a.classList.toggle('active', a.getAttribute('data-section') === key);
            });
          }
        });
      }, { threshold: 0.4 });
      sections.forEach(function (s) { observer.observe(s); });
    }

    // --- Bouton retour en haut ----------------------------------------------
    let toTop = document.getElementById('ytdl-to-top');
    if (!toTop) {
      toTop = document.createElement('button');
      toTop.id = 'ytdl-to-top';
      toTop.setAttribute('aria-label', 'Retour en haut');
      toTop.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>';
      toTop.style.color = 'var(--ytdl-accent)';
      document.body.appendChild(toTop);
      toTop.addEventListener('click', function () {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
      window.addEventListener('scroll', function () {
        toTop.classList.toggle('visible', window.scrollY > 400);
      }, { passive: true });
    }
  });
})();
</script>
"""


def apply(dark_mode: bool, theme_key: str = DEFAULT_THEME_KEY, native: bool = False) -> None:
    """Applique la palette, les polices, la nav/fond animés et le mode sombre.

    À appeler une fois par page, avant de construire le contenu.

    Args:
        dark_mode: Thème sombre activé.
        theme_key: Clé de la palette choisie (voir :data:`THEMES`). Posée sur
            ``<body>`` comme classe ``ytdl-theme-{theme_key}`` : le bouton
            palette (voir ``ytdl.ui.app``) échange ensuite cette classe en
            direct pour changer de palette sans recharger la page.
        native: Fenêtre pywebview plutôt que navigateur — masque la piste de
            scrollbar (voir la règle CSS ``.ytdl-native`` ci-dessus).
    """
    colors = colors_for(theme_key, dark_mode)
    ui.colors(
        primary=colors.accent,
        secondary=colors.secondary,
        accent=colors.accent,
        positive=POSITIVE,
        negative=NEGATIVE,
        warning=WARNING,
    )
    ui.add_head_html(_FONTS_CSS + _CUSTOM_CSS)
    ui.query("body").classes(f"ytdl-theme-{theme_key}")
    if native:
        ui.query("html").classes("ytdl-native")
        ui.query("body").classes("ytdl-native")
    ui.add_body_html(_BODY_SCRIPT)
    ui.dark_mode(dark_mode)

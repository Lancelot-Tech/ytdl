"""Tests du cœur : traduction des options vers yt-dlp et modèles associés."""

from __future__ import annotations

from ytdl.models import (
    DownloadOptions,
    JobStatus,
    MediaFormat,
    MediaInfo,
    SpotifyDownloadOptions,
    SpotifyFormat,
    clean_title,
    spotify_url_is_multi_track,
    url_has_playlist_param,
)


# --------------------------------------------------------------------------- #
# MediaFormat
# --------------------------------------------------------------------------- #
def test_audio_formats_flagged():
    assert MediaFormat.MP3.is_audio
    assert MediaFormat.M4A.is_audio
    assert MediaFormat.BEST_AUDIO.is_audio
    assert not MediaFormat.MP4.is_audio
    assert not MediaFormat.WEBM.is_audio
    assert not MediaFormat.BEST_VIDEO.is_audio


# --------------------------------------------------------------------------- #
# Sélecteur de format
# --------------------------------------------------------------------------- #
def test_mp4_1080_selector_limits_height_and_container():
    opts = DownloadOptions(fmt=MediaFormat.MP4, quality="1080")
    sel = opts.format_selector()
    assert "height<=1080" in sel
    assert "ext=mp4" in sel


def test_mp4_best_quality_has_no_height_filter():
    opts = DownloadOptions(fmt=MediaFormat.MP4, quality="best")
    assert "height<=" not in opts.format_selector()


def test_audio_selector_is_bestaudio():
    opts = DownloadOptions(fmt=MediaFormat.MP3, quality="192")
    assert opts.format_selector() == "bestaudio/best"


# --------------------------------------------------------------------------- #
# Post-traitements
# --------------------------------------------------------------------------- #
def test_mp3_adds_extract_audio_postprocessor():
    opts = DownloadOptions(fmt=MediaFormat.MP3, quality="192", embed_metadata=False)
    pps = opts.to_ydl_opts()["postprocessors"]
    keys = [p["key"] for p in pps]
    assert "FFmpegExtractAudio" in keys
    extract = next(p for p in pps if p["key"] == "FFmpegExtractAudio")
    assert extract["preferredcodec"] == "mp3"
    assert extract["preferredquality"] == "192"


def test_best_audio_does_not_reencode():
    opts = DownloadOptions(fmt=MediaFormat.BEST_AUDIO, embed_metadata=False)
    keys = [p["key"] for p in opts.to_ydl_opts()["postprocessors"]]
    assert "FFmpegExtractAudio" not in keys


def test_metadata_and_thumbnail_and_subs_postprocessors():
    opts = DownloadOptions(
        fmt=MediaFormat.MP4,
        embed_metadata=True,
        embed_thumbnail=True,
        subtitles=True,
    )
    ydl = opts.to_ydl_opts()
    keys = [p["key"] for p in ydl["postprocessors"]]
    assert "FFmpegMetadata" in keys
    assert "EmbedThumbnail" in keys
    assert "FFmpegEmbedSubtitle" in keys
    embed_thumb = next(p for p in ydl["postprocessors"] if p["key"] == "EmbedThumbnail")
    assert embed_thumb["already_have_thumbnail"] is True
    assert ydl["writethumbnail"] is True
    assert ydl["writesubtitles"] is True
    assert ydl["subtitleslangs"] == opts.sub_langs


def test_embed_thumbnail_writes_to_dedicated_subfolder():
    opts = DownloadOptions(
        output_dir="/tmp/out",
        filename_template="%(uploader)s - %(title)s.%(ext)s",
        embed_thumbnail=True,
    )
    outtmpl = opts.to_ydl_opts()["outtmpl"]
    assert outtmpl["default"] == "/tmp/out/%(uploader)s - %(title)s.%(ext)s"
    assert outtmpl["thumbnail"] == "/tmp/out/Miniatures/%(uploader)s - %(title)s.%(ext)s"


# --------------------------------------------------------------------------- #
# Options globales
# --------------------------------------------------------------------------- #
def test_single_video_sets_noplaylist():
    opts = DownloadOptions(fmt=MediaFormat.MP4, is_playlist=False)
    assert opts.to_ydl_opts()["noplaylist"] is True


def test_playlist_items_only_when_playlist():
    opts = DownloadOptions(fmt=MediaFormat.MP4, is_playlist=True, playlist_items="1-3")
    ydl = opts.to_ydl_opts()
    assert ydl["noplaylist"] is False
    assert ydl["playlist_items"] == "1-3"

    single = DownloadOptions(fmt=MediaFormat.MP4, is_playlist=False, playlist_items="1-3")
    assert "playlist_items" not in single.to_ydl_opts()


def test_outtmpl_joins_dir_and_template():
    opts = DownloadOptions(output_dir="/tmp/out", filename_template="%(title)s.%(ext)s")
    assert opts.to_ydl_opts()["outtmpl"] == "/tmp/out/%(title)s.%(ext)s"


def test_archive_path_wired_when_set():
    opts = DownloadOptions(archive_path="/tmp/out/.ytdl_archive.txt")
    assert opts.to_ydl_opts()["download_archive"] == "/tmp/out/.ytdl_archive.txt"


def test_archive_path_absent_by_default():
    assert "download_archive" not in DownloadOptions().to_ydl_opts()


def test_merge_format_only_for_video_containers():
    assert DownloadOptions(fmt=MediaFormat.MP4).to_ydl_opts()["merge_output_format"] == "mp4"
    assert "merge_output_format" not in DownloadOptions(fmt=MediaFormat.MP3).to_ydl_opts()


def test_progress_hook_wired_when_provided():
    opts = DownloadOptions()
    hook = lambda d: None  # noqa: E731
    assert opts.to_ydl_opts(progress_hook=hook)["progress_hooks"] == [hook]


# --------------------------------------------------------------------------- #
# Protection anti-throttling (délai entre requêtes, limite de débit)
# --------------------------------------------------------------------------- #
def test_sleep_interval_disabled_by_default():
    ydl = DownloadOptions().to_ydl_opts()
    assert "sleep_interval" not in ydl
    assert "sleep_interval_requests" not in ydl


def test_sleep_interval_applies_to_downloads_and_requests():
    ydl = DownloadOptions(sleep_interval=3.5).to_ydl_opts()
    assert ydl["sleep_interval"] == 3.5
    assert ydl["max_sleep_interval"] == 3.5
    assert ydl["sleep_interval_requests"] == 3.5


def test_rate_limit_disabled_by_default():
    assert "ratelimit" not in DownloadOptions().to_ydl_opts()


def test_rate_limit_converted_to_bytes_per_second():
    ydl = DownloadOptions(rate_limit_kbps=500).to_ydl_opts()
    assert ydl["ratelimit"] == 500 * 1024


# --------------------------------------------------------------------------- #
# Cookies (playlists privées : Liked videos, Watch Later...)
# --------------------------------------------------------------------------- #
def test_cookies_browser_disabled_by_default():
    assert "cookiesfrombrowser" not in DownloadOptions().to_ydl_opts()


def test_cookies_browser_sets_yt_dlp_tuple():
    ydl = DownloadOptions(cookies_browser="firefox").to_ydl_opts()
    assert ydl["cookiesfrombrowser"] == ("firefox",)


def test_url_has_playlist_param_detects_list_query():
    assert url_has_playlist_param("https://www.youtube.com/watch?v=x&list=LL&pp=abc")
    assert url_has_playlist_param("https://www.youtube.com/playlist?list=PL123")
    assert not url_has_playlist_param("https://www.youtube.com/watch?v=x")
    assert not url_has_playlist_param("https://example.com/no-list-here")


# --------------------------------------------------------------------------- #
# MediaInfo
# --------------------------------------------------------------------------- #
def test_media_info_from_single_video():
    info = MediaInfo.from_ydl_info(
        {"title": "T", "uploader": "U", "duration": 3661, "thumbnail": "http://x"}
    )
    assert not info.is_playlist
    assert info.duration_str == "1:01:01"
    assert info.uploader == "U"


def test_media_info_from_playlist(playlist_info):
    info = MediaInfo.from_ydl_info(playlist_info)
    assert info.is_playlist
    assert info.entries == ["Piste 1", "Piste 2", "Piste 3"]


def test_duration_str_minutes_seconds():
    assert MediaInfo(title="x", duration=65).duration_str == "1:05"
    assert MediaInfo(title="x", duration=None).duration_str == ""


# --------------------------------------------------------------------------- #
# Nettoyage des titres
# --------------------------------------------------------------------------- #
def test_clean_title_removes_official_video():
    assert clean_title("Daft Punk - One More Time (Official Video)") == "Daft Punk - One More Time"


def test_clean_title_removes_clip_officiel_case_insensitive():
    assert clean_title("Stromae - Alors on danse (CLIP OFFICIEL)") == "Stromae - Alors on danse"


def test_clean_title_removes_bracketed_official_music_video():
    assert clean_title("Artist - Song [Official Music Video]") == "Artist - Song"


def test_clean_title_collapses_whitespace_and_trailing_dash():
    assert clean_title("Song Title  (Official Audio)   -   ") == "Song Title"


def test_clean_title_leaves_normal_titles_untouched():
    assert clean_title("Ma superbe chanson (live)") == "Ma superbe chanson (live)"


def test_clean_title_option_adds_metadata_parser_postprocessor():
    opts = DownloadOptions(fmt=MediaFormat.MP4, clean_title=True, embed_metadata=False)
    pps = opts.to_ydl_opts()["postprocessors"]
    assert pps[0]["key"] == "MetadataParser"
    assert pps[0]["when"] == "pre_process"


def test_clean_title_disabled_by_default():
    opts = DownloadOptions(fmt=MediaFormat.MP4, embed_metadata=False)
    keys = [p["key"] for p in opts.to_ydl_opts()["postprocessors"]]
    assert "MetadataParser" not in keys


# --------------------------------------------------------------------------- #
# Spotify (spotdl)
# --------------------------------------------------------------------------- #
def test_spotify_format_labels_are_audio_only():
    assert SpotifyFormat.MP3.label == "MP3 (audio)"
    assert SpotifyFormat.FLAC.label == "FLAC (sans perte)"


def test_spotify_output_template_uses_spotdl_placeholders():
    opts = SpotifyDownloadOptions(output_dir="/tmp/out")
    assert opts.output_template() == "/tmp/out/{artists} - {title}.{output-ext}"


def test_media_info_from_spotdl_songs_single_track():
    songs = [{"name": "Alors on danse", "artist": "Stromae", "cover_url": "http://img", "duration": 200}]
    info = MediaInfo.from_spotdl_songs(songs, "http://open.spotify.com/track/x")
    assert info.title == "Alors on danse"
    assert info.uploader == "Stromae"
    assert info.duration == 200
    assert not info.is_playlist
    assert info.entries == []


def test_media_info_from_spotdl_songs_playlist():
    songs = [
        {"name": "A", "artist": "X", "list_name": "Ma Playlist"},
        {"name": "B", "artist": "Y", "list_name": "Ma Playlist"},
    ]
    info = MediaInfo.from_spotdl_songs(songs, "http://open.spotify.com/playlist/x")
    assert info.is_playlist
    assert info.title == "Ma Playlist"
    assert info.entries == ["X - A", "Y - B"]


def test_spotify_url_is_multi_track_detects_playlist_album_artist():
    assert spotify_url_is_multi_track("https://open.spotify.com/playlist/37i9dQZF1DWWF3yivn1m3D")
    assert spotify_url_is_multi_track("https://open.spotify.com/album/xyz")
    assert spotify_url_is_multi_track("https://open.spotify.com/artist/xyz")
    assert spotify_url_is_multi_track("https://open.spotify.com/intl-fr/playlist/xyz")


def test_spotify_url_is_multi_track_false_for_single_track():
    assert not spotify_url_is_multi_track("https://open.spotify.com/track/65DbTqJKhbwqYbZ1Okr0rc")


def test_media_info_from_spotdl_songs_single_song_playlist_still_detected():
    # Une playlist ne contenant qu'un seul titre se distingue d'un titre isolé
    # uniquement via le champ ``list_name`` (une seule entrée dans les deux cas).
    songs = [{"name": "A", "artist": "X", "list_name": "Ma Playlist"}]
    info = MediaInfo.from_spotdl_songs(songs, "http://x")
    assert info.is_playlist


# --------------------------------------------------------------------------- #
# JobStatus
# --------------------------------------------------------------------------- #
def test_terminal_statuses():
    assert JobStatus.DONE.is_terminal
    assert JobStatus.ERROR.is_terminal
    assert JobStatus.CANCELLED.is_terminal
    assert not JobStatus.DOWNLOADING.is_terminal
    assert not JobStatus.PENDING.is_terminal

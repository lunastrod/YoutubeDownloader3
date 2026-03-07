import os
import re
import mutagen.mp3
import mutagen.id3

OS_ILLEGAL_CHARS = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
NON_PRINTABLE_CHARS = ''.join(chr(i) for i in range(32))
BAD_SUBSTRINGS = [
    "(Official Video)", "(Official Audio)", "(Official Version)",
    "(Video)", "(Official Lyric Video)", "(Official Music Video)",
    "(Official Visualizer)", "(Soundtrack Version)", "Official_Video",
    "(4K Remaster)", "(Remastered)", "(HD)",
    "[Official Video]", "[Official Audio]", "[Official Version]",
    "[Video]", "[Official Lyric Video]", "[Official Music Video]",
    "[Official Visualizer]", "[4K Remaster]", "[Remastered]", "[HD]",
    "VEVO",
]
REPLACE_CHARS = {
    "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-",
}
SPECIAL_CASES = {
    "\u2605\u2605\u2605\u2605\u2605": "5 Stars",
}


def _clean_text(text: str, remove_artist: str = "") -> str:
    for old, new in REPLACE_CHARS.items():
        text = text.replace(old, new)

    for bad in BAD_SUBSTRINGS:
        text = text.replace(bad, "")

    if remove_artist:
        artist_pattern = re.escape(remove_artist)
        text = re.sub(rf'[\W_]*{artist_pattern}[\W_]*', ' ', text, flags=re.IGNORECASE)

    for special, replacement in SPECIAL_CASES.items():
        text = text.replace(special, replacement)

    all_illegal = OS_ILLEGAL_CHARS + list(NON_PRINTABLE_CHARS)
    for char in all_illegal:
        text = text.replace(char, "")

    text = re.sub(r'\(\s*\)', '', text)
    text = re.sub(r'\[\s*\]', '', text)

    text = " ".join(text.split()).strip(' -_')
    return text


def get_downloaded_urls(directory: str) -> list[str]:
    """Lee los mp3s de un directorio y devuelve las URLs guardadas en sus metadatos."""
    urls = []
    for file in os.listdir(directory):
        if not file.endswith(".mp3"):
            continue
        path = os.path.join(directory, file)
        try:
            audio = mutagen.mp3.MP3(path, ID3=mutagen.id3.ID3)
            if audio.tags and "WOAF" in audio.tags:
                urls.append(audio.tags["WOAF"].url)
        except Exception:
            pass
    return urls


def filter_new_urls(urls: list[str], directory: str) -> list[str]:
    """Devuelve solo las URLs que no están ya descargadas en el directorio."""
    downloaded = set(get_downloaded_urls(directory))
    new_urls = []
    for url in urls:
        if url not in downloaded:
            new_urls.append(url)
    return new_urls


def embed_metadata(mp3_path: str, metadata: dict, thumbnail_path: str | None) -> None:
    """Incrusta título, álbum, artista, URL y thumbnail en el mp3."""
    audio = mutagen.mp3.MP3(mp3_path, ID3=mutagen.id3.ID3)
    if audio.tags is None:
        audio.add_tags()

    audio.tags.add(mutagen.id3.TIT2(encoding=3, text=metadata.get("title", "")))
    audio.tags.add(mutagen.id3.TALB(encoding=3, text=metadata.get("album", "")))
    audio.tags.add(mutagen.id3.TPE1(encoding=3, text=metadata.get("artist", "")))
    audio.tags.add(mutagen.id3.WOAF(url=metadata.get("url", "")))

    if thumbnail_path and os.path.exists(thumbnail_path):
        with open(thumbnail_path, "rb") as f:
            thumbnail_data = f.read()
        audio.tags.add(mutagen.id3.APIC(
            encoding=3,
            mime="image/png",
            type=3,
            desc="Cover",
            data=thumbnail_data,
        ))

    audio.save()


def embed_all(output_dir: str, thumbnails_dir: str, metadata_list: list[dict]) -> None:
    """Incrusta metadatos y thumbnails en todos los mp3s descargados."""
    for metadata in metadata_list:
        url = metadata.get("url", "")
        video_id = url.split("v=")[-1]
        mp3_path = os.path.join(output_dir, f"{video_id}.mp3")
        if not os.path.exists(mp3_path):
            continue

        thumbnail_path = None
        for ext in ["png", "jpg", "jpeg", "webp"]:
            candidate = os.path.join(thumbnails_dir, f"{video_id}.{ext}")
            if os.path.exists(candidate):
                thumbnail_path = candidate
                break

        embed_metadata(mp3_path, metadata, thumbnail_path)


def rename_files(output_dir: str, metadata_list: list[dict]) -> None:
    """Renombra los mp3s al formato 'artista - titulo.mp3'."""
    for metadata in metadata_list:
        url = metadata.get("url", "")
        video_id = url.split("v=")[-1]
        mp3_path = os.path.join(output_dir, f"{video_id}.mp3")
        if not os.path.exists(mp3_path):
            continue

        artist = _clean_text(metadata.get("artist", "Unknown Artist"))
        title = _clean_text(metadata.get("title", ""), remove_artist=artist)

        if not title:
            title = "Unknown Track"

        new_name = f"{artist} - {title}.mp3"
        new_path = os.path.join(output_dir, new_name)

        if os.path.exists(new_path):
            print(f"Warning: file already exists, skipping rename: {new_name}")
            continue

        os.replace(mp3_path, new_path)
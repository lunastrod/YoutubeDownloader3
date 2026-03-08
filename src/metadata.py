import os
import re
import sys
from io import StringIO
from concurrent.futures import ThreadPoolExecutor
import mutagen.mp3
import mutagen.id3
import syncedlyrics
import logger as log

OS_ILLEGAL_CHARS = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
NON_PRINTABLE_CHARS = ''.join(chr(i) for i in range(32))
BAD_SUBSTRINGS = [
    "(Official Video)", "(Official Audio)", "(Official Version)",
    "(Video)", "(Official Lyric Video)", "(Official Music Video)",
    "(Official Visualizer)", "(Official Visualiser)", "(Soundtrack Version)", 
    "Official_Video", "Official Video", "Official Audio",
    "(4K Remaster)", "(Remastered)", "(HD)", "(Visualizer)", "(Visualiser)",
    "[Official Video]", "[Official Audio]", "[Official Version]",
    "[Video]", "[Official Lyric Video]", "[Official Music Video]",
    "[Official Visualizer]", "[Official Visualiser]", "[4K Remaster]", 
    "[Remastered]", "[HD]", "VEVO",
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
    if not text:
        return ""
            
    for special, replacement in SPECIAL_CASES.items():
        text = text.replace(special, replacement)
        
    for old, new in REPLACE_CHARS.items():
        text = text.replace(old, new)

    for bad in BAD_SUBSTRINGS:
        pattern = re.escape(bad)
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    if remove_artist:
        artist_pattern = re.escape(remove_artist)
        text = re.sub(rf'[\W_]*{artist_pattern}[\W_]*', ' ', text, flags=re.IGNORECASE)

    all_illegal = OS_ILLEGAL_CHARS + list(NON_PRINTABLE_CHARS)
    for char in all_illegal:
        text = text.replace(char, "")

    text = re.sub(r'\(\s*\)', '', text)
    text = re.sub(r'\[\s*\]', '', text)

    cleaned = " ".join(text.split()).strip(' -_')
    return cleaned

def extract_video_id(url: str) -> str:
    match = re.search(r"v=([^&]+)", url)
    return match.group(1) if match else url

def get_downloaded_ids(directory: str) -> set[str]:
    ids = set()
    for file in os.listdir(directory):
        if not file.endswith(".mp3"):
            continue
        path = os.path.join(directory, file)
        try:
            audio = mutagen.mp3.MP3(path, ID3=mutagen.id3.ID3)
            if audio.tags and "WOAF" in audio.tags:
                ids.add(extract_video_id(audio.tags["WOAF"].url))
        except Exception:
            pass
    return ids

def get_deleted_songs(playlist_urls: list[str], directory: str) -> list[tuple[str, str]]:
    playlist_ids = set(extract_video_id(url) for url in playlist_urls)
    deleted = []
    for file in os.listdir(directory):
        if not file.endswith(".mp3"):
            continue
        path = os.path.join(directory, file)
        try:
            audio = mutagen.mp3.MP3(path, ID3=mutagen.id3.ID3)
            if audio.tags and "WOAF" in audio.tags:
                url = audio.tags["WOAF"].url
                if extract_video_id(url) not in playlist_ids:
                    deleted.append((path, url))
        except Exception:
            pass
    return deleted

def filter_new_urls(urls: list[str], directory: str) -> list[str]:
    downloaded_ids = get_downloaded_ids(directory)
    return [url for url in urls if extract_video_id(url) not in downloaded_ids]

def find_playlist_duplicates(urls: list[str]) -> list[str]:
    seen = set()
    duplicates = []
    for url in urls:
        vid = extract_video_id(url)
        if vid in seen and url not in duplicates:
            duplicates.append(url)
        seen.add(vid)
    return duplicates

def embed_metadata(mp3_path: str, metadata: dict, thumbnail_path: str | None) -> None:
    try:
        audio = mutagen.mp3.MP3(mp3_path, ID3=mutagen.id3.ID3)
        if audio.tags is None:
            audio.add_tags()

        # Limpiamos los textos ANTES de guardarlos en los metadatos
        artist = _clean_text(metadata.get("artist", "Unknown Artist"))
        title = _clean_text(metadata.get("title", ""), remove_artist=artist)
        
        # Fallback si el título queda vacío tras limpiar (caso del punto ".")
        if not title:
            title = metadata.get("title") if metadata.get("title") else "Track"
            log.logger.log_verbose(f"Title became empty after cleaning, using fallback: {title} for {artist},{title}")

        audio.tags.add(mutagen.id3.TIT2(encoding=3, text=title))
        audio.tags.add(mutagen.id3.TALB(encoding=3, text=metadata.get("album", "")))
        audio.tags.add(mutagen.id3.TPE1(encoding=3, text=artist))
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
    except Exception as e:
        log.logger.log(f"Error embedding metadata in {mp3_path}: {e}")

def embed_all(output_dir: str, thumbnails_dir: str, metadata_list: list[dict]) -> None:
    for metadata in metadata_list:
        url = metadata.get("url", "")
        video_id = extract_video_id(url)
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
    for metadata in metadata_list:
        url = metadata.get("url", "")
        video_id = extract_video_id(url)
        mp3_path = os.path.join(output_dir, f"{video_id}.mp3")
        if not os.path.exists(mp3_path):
            continue

        artist = _clean_text(metadata.get("artist", "Unknown Artist"))
        title = _clean_text(metadata.get("title", ""), remove_artist=artist)

        # Si tras limpiar no queda nada, usamos el ID para evitar conflictos
        if not title or title.strip() == "":
            title = f"Track_{video_id}"

        new_name = f"{artist} - {title}".strip() + ".mp3"
        new_path = os.path.join(output_dir, new_name)

        if os.path.exists(new_path):
            log.logger.log(f"Warning: file already exists, skipping rename: {new_name}")
            continue

        try:
            os.replace(mp3_path, new_path)
        except Exception as e:
            log.logger.log(f"Error renaming {mp3_path} to {new_name}: {e}")

def _search_lyrics(query: str) -> str | None:
    temp_stdout = StringIO()
    temp_stderr = StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = temp_stdout, temp_stderr
        return syncedlyrics.search(query)
    except Exception:
        error_output = temp_stderr.getvalue().strip()
        if error_output:
            log.logger.log_verbose(f"Lyrics Provider Error: {error_output}")
        return None
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr

def _lyrics_worker(mp3_path: str, metadata_item: dict) -> None:
    artist = _clean_text(metadata_item.get("artist", "Unknown Artist"))
    title = _clean_text(metadata_item.get("title", ""), remove_artist=artist)

    log.logger.log_verbose(f"Searching lyrics: {artist} - {title}")
    lyrics = _search_lyrics(f"{artist} {title}") or _search_lyrics(title)

    if not lyrics:
        return

    try:
        audio = mutagen.mp3.MP3(mp3_path, ID3=mutagen.id3.ID3)
        if audio.tags is None:
            audio.add_tags()
        audio.tags["USLT::eng"] = mutagen.id3.USLT(encoding=3, lang="eng", desc="Lyrics", text=lyrics)
        audio.tags.save(mp3_path)
    except Exception as e:
        log.logger.log(f"Warning: could not embed lyrics for {mp3_path}: {e}")

def embed_lyrics(output_dir: str, metadata_list: list[dict]) -> None:
    log.logger.log(f"Fetching lyrics for {len(metadata_list)} songs...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        for entry in metadata_list:
            video_id = extract_video_id(entry.get("url", ""))
            
            # Buscamos el archivo por su nombre final (ya renombrado)
            artist = _clean_text(entry.get("artist", "Unknown Artist"))
            title = _clean_text(entry.get("title", ""), remove_artist=artist)
            if not title: title = f"Track_{video_id}"
            
            final_name = f"{artist} - {title}.mp3"
            mp3_path = os.path.join(output_dir, final_name)
            
            if os.path.exists(mp3_path):
                executor.submit(_lyrics_worker, mp3_path, entry)
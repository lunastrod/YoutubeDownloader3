import os
import sys
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
import metadata
import logger as log
from process import ProcessRunner


def get_bin_dir() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "bin")


BROWSERS = ["firefox", "chrome", "edge", "brave", "opera", "chromium", "vivaldi"]
WORKERS = 10
THUMBNAIL_WORKERS = 4
META_TEMPLATE = "%(title)s\x1f%(album)s\x1f%(artist)s\x1f%(uploader)s\x1f%(webpage_url)s"


def _thumbnail_url(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"


def _parse_metadata(line: str) -> dict | None:
    parts = line.split("\x1f")
    if len(parts) < 5:
        return None
    title, album, artist, uploader, url = parts
    return {
        "title": title,
        "album": album if album != "NA" else title,
        "artist": artist if artist != "NA" else uploader,
        "url": url,
    }


class Downloader:
    def __init__(self):
        self.bin_dir = get_bin_dir()
        self.runner = ProcessRunner()
        self.browser: str | None = None

    def update_ytdlp(self) -> None:
        ytdlp = os.path.join(self.bin_dir, "yt-dlp.exe")
        log.logger.log_verbose("Updating yt-dlp...")
        _, code = self.runner.run([ytdlp, "-U"])
        if code == 0:
            log.logger.log_verbose("yt-dlp updated successfully.")
        else:
            log.logger.warning(f"yt-dlp update failed with code {code}.")

    # Try each browser in order and set self.browser to the first that works
    def detect_browser(self) -> None:
        ytdlp = os.path.join(self.bin_dir, "yt-dlp.exe")
        node = os.path.join(self.bin_dir, "node.exe")
        test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        for browser in BROWSERS:
            log.logger.log_verbose(f"Testing browser for cookies: {browser}")
            _, code = self.runner.run([ytdlp, "--cookies-from-browser", browser, "--js-runtimes", f"node:{node}", "--simulate", test_url])
            if code == 0:
                self.browser = browser
                return
        self.browser = None

    # Fetch all video URLs from a playlist without downloading
    def get_playlist_urls(self, url: str) -> list[str]:
        ytdlp = os.path.join(self.bin_dir, "yt-dlp.exe")
        stdout, _ = self.runner.run([ytdlp, "--flat-playlist", "--print", "%(url)s", url])
        urls = []
        for line in stdout.splitlines():
            if line:
                urls.append(line)
        return urls

    # Build the base yt-dlp command with ffmpeg and optional browser cookies
    def _base_cmd(self) -> list[str]:
        ytdlp = os.path.join(self.bin_dir, "yt-dlp.exe")
        node = os.path.join(self.bin_dir, "node.exe")
        cmd = [ytdlp, "--ffmpeg-location", self.bin_dir, "--js-runtimes", f"node:{node}", "--encoding", "utf-8"]
        if self.browser:
            cmd += ["--cookies-from-browser", self.browser]
        return cmd

    # Download a single thumbnail, with fallback to lower quality
    def _fetch_thumbnail(self, url: str, thumbnails_dir: str, completed: list[int], total: int, lock: threading.Lock, on_progress: Callable[[int, int], None]) -> None:
        video_id = metadata.extract_video_id(url)
        dest = os.path.join(thumbnails_dir, f"{video_id}.jpg")
        try:
            r = requests.get(_thumbnail_url(video_id), timeout=10)
            if r.status_code == 200:
                with open(dest, "wb") as f:
                    f.write(r.content)
            else:
                log.logger.warning(f"Thumbnail not found for {video_id}, trying fallback URL")
                fallback = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                r = requests.get(fallback, timeout=10)
                if r.status_code == 200:
                    with open(dest, "wb") as f:
                        f.write(r.content)
        except Exception as e:
            log.logger.warning(f"Warning: thumbnail failed for {video_id}: {e}")
        with lock:
            completed[0] += 1
            on_progress(completed[0], total)
        log.logger.log_verbose(f"Thumbnail: {video_id}")

    # Download thumbnails in parallel using requests
    def download_thumbnails(self, urls: list[str], thumbnails_dir: str, on_progress: Callable[[int, int], None]) -> None:
        os.makedirs(thumbnails_dir, exist_ok=True)
        total = len(urls)
        completed = [0]
        lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=THUMBNAIL_WORKERS) as executor:
            futures = []
            for url in urls:
                futures.append(executor.submit(self._fetch_thumbnail, url, thumbnails_dir, completed, total, lock, on_progress))
            for f in as_completed(futures):
                f.result()

    # Parse metadata lines, log download message and update progress
    def _handle_audio_line(self, line: str, metadata_list: list, metadata_lock: threading.Lock, total: int, count: list[int]) -> None:
        if "\x1f" in line:
            meta = _parse_metadata(line)
            if meta:
                with metadata_lock:
                    metadata_list.append(meta)
                    count[0] += 1
                log.logger.log(f"Downloading: {meta['artist']} - {meta['title']}")
                log.logger.set_progress(count[0] / total)

    # Download and parse metadata+audio for one chunk of URLs
    def _run_chunk(self, chunk: list[str], output_dir: str, metadata_list: list, metadata_lock: threading.Lock, codes: list[int], codes_lock: threading.Lock, total: int, count: list[int]) -> None:
        output_template = os.path.join(output_dir, "%(id)s.%(ext)s")
        cmd = self._base_cmd() + [
            "--format", "bestaudio",
            "--extract-audio",
            "--audio-format", "mp3",
            "--restrict-filenames",
            "--output", output_template,
            "--print", META_TEMPLATE,
            "--no-simulate",
            "--no-quiet",
            "--newline",
        ] + chunk

        _, code = self.runner.run(cmd, lambda line: self._handle_audio_line(line, metadata_list, metadata_lock, total, count))
        with codes_lock:
            log.logger.log_verbose(f"yt-dlp process exited with code {code} for chunk starting with {chunk[0]}")
            if code not in (0, -15) or (code == -15 and codes[0] == 0):
                log.logger.warning(f"yt-dlp exited with code {code} for chunk starting with {chunk[0]}")
                codes[0] = code

    # Launch WORKERS parallel yt-dlp processes to download audio
    def download_audio(self, urls: list[str], output_dir: str) -> tuple[int, list[dict]]:
        total = len(urls)
        chunk_size = max(1, total // WORKERS)
        chunks = []
        for i in range(0, total, chunk_size):
            chunks.append(urls[i:i + chunk_size])

        codes = [0]
        codes_lock = threading.Lock()
        metadata_list = []
        metadata_lock = threading.Lock()
        count = [0]

        threads = []
        for chunk in chunks:
            t = threading.Thread(target=self._run_chunk, args=(chunk, output_dir, metadata_list, metadata_lock, codes, codes_lock, total, count))
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        return codes[0], metadata_list

    # Terminate all active subprocesses
    def cancel(self):
        self.runner.cancel()
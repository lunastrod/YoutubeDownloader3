import subprocess
import os
import sys
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable


def get_bin_dir() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "bin")


BROWSERS = ["firefox", "chrome", "edge", "brave", "opera", "chromium", "vivaldi"]
AUDIO_COMPLETE = "[ExtractAudio] Destination:"
SHOW_LINE_PREFIXES = (
    "[ExtractAudio]",
    "ERROR",
    "WARNING",
)
WORKERS = 6
THUMBNAIL_WORKERS = 10


def should_show(line: str) -> bool:
    for prefix in SHOW_LINE_PREFIXES:
        if line.startswith(prefix):
            return True
    return False


def _thumbnail_url(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"


def _extract_video_id(url: str) -> str:
    import re
    match = re.search(r"v=([^&]+)", url)
    return match.group(1) if match else url


class Downloader:
    def __init__(self):
        self.bin_dir = get_bin_dir()
        self.processes: list[subprocess.Popen] = []
        self.processes_lock = threading.Lock()
        self.browser: str | None = None

    def _detect_browser(self) -> str | None:
        """Detecta el primer navegador disponible con cookies de YouTube."""
        ytdlp = os.path.join(self.bin_dir, "yt-dlp.exe")
        node = os.path.join(self.bin_dir, "node.exe")
        test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        for browser in BROWSERS:
            result = subprocess.run(
                [ytdlp, "--cookies-from-browser", browser, "--js-runtimes", f"node:{node}", "--simulate", test_url],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print(f"Using cookies from {browser}")
                return browser
        print("Warning: no browser cookies found, downloads may be rate limited")
        return None

    def _run(self, cmd: list[str]) -> str:
        """Ejecuta un comando y devuelve stdout."""
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        with self.processes_lock:
            self.processes.append(proc)
        stdout, _ = proc.communicate()
        with self.processes_lock:
            self.processes.remove(proc)
        return stdout

    def _stream(self, cmd: list[str], on_line: Callable[[str], None]) -> int:
        """Ejecuta un comando en streaming llamando a on_line por cada línea. Devuelve el return code."""
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        with self.processes_lock:
            self.processes.append(proc)
        for line in proc.stdout:
            on_line(line.rstrip())
        proc.wait()
        code = proc.returncode
        with self.processes_lock:
            if proc in self.processes:
                self.processes.remove(proc)
        return code

    def get_playlist_urls(self, url: str) -> list[str]:
        """Devuelve las URLs de los vídeos de una playlist sin descargar nada."""
        ytdlp = os.path.join(self.bin_dir, "yt-dlp.exe")
        stdout = self._run([ytdlp, "--flat-playlist", "--print", "%(url)s", url])
        return [line for line in stdout.splitlines() if line]

    def _base_cmd(self) -> list[str]:
        ytdlp = os.path.join(self.bin_dir, "yt-dlp.exe")
        node = os.path.join(self.bin_dir, "node.exe")
        cmd = [ytdlp, "--ffmpeg-location", self.bin_dir, "--js-runtimes", f"node:{node}"]
        if self.browser:
            cmd += ["--cookies-from-browser", self.browser]
        return cmd

    def download_thumbnails(self, urls: list[str], thumbnails_dir: str, on_progress: Callable[[int, int], None]) -> None:
        """Descarga thumbnails en paralelo con requests. Llama a on_progress(completadas, total)."""
        os.makedirs(thumbnails_dir, exist_ok=True)
        total = len(urls)
        completed = [0]
        lock = threading.Lock()

        def fetch(url: str):
            video_id = _extract_video_id(url)
            dest = os.path.join(thumbnails_dir, f"{video_id}.jpg")
            try:
                r = requests.get(_thumbnail_url(video_id), timeout=10)
                if r.status_code == 200:
                    with open(dest, "wb") as f:
                        f.write(r.content)
                else:
                    # fallback a calidad menor
                    fallback = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                    r = requests.get(fallback, timeout=10)
                    if r.status_code == 200:
                        with open(dest, "wb") as f:
                            f.write(r.content)
            except Exception as e:
                print(f"Warning: thumbnail failed for {video_id}: {e}")
            with lock:
                completed[0] += 1
                on_progress(completed[0], total)

        with ThreadPoolExecutor(max_workers=THUMBNAIL_WORKERS) as executor:
            futures = [executor.submit(fetch, url) for url in urls]
            for f in as_completed(futures):
                f.result()

    def download_audio(self, urls: list[str], output_dir: str, on_line: Callable[[str], None]) -> tuple[int, list[dict]]:
        """Lanza WORKERS subprocesos de yt-dlp en paralelo. Devuelve (peor return code, metadata_list)."""
        output_template = os.path.join(output_dir, "%(id)s.%(ext)s")
        meta_template = "%(title)s%(album)s%(artist)s%(uploader)s%(webpage_url)s"
        chunks = [urls[i::WORKERS] for i in range(WORKERS) if urls[i::WORKERS]]
        codes = [0]
        codes_lock = threading.Lock()
        metadata_list = []
        metadata_lock = threading.Lock()

        def parse_metadata(line: str) -> dict | None:
            parts = line.split("")
            if len(parts) < 5:
                return None
            title, album, artist, uploader, url = parts
            return {
                "title": title,
                "album": album if album != "NA" else title,
                "artist": artist if artist != "NA" else uploader,
                "url": url,
            }

        def run_chunk(chunk: list[str]) -> None:
            cmd = self._base_cmd() + [
                "--format", "bestaudio",
                "--extract-audio",
                "--audio-format", "mp3",
                "--restrict-filenames",
                "--output", output_template,
                "--print", meta_template,
                "--no-simulate",
                "--newline",
            ] + chunk

            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            with self.processes_lock:
                self.processes.append(proc)

            for line in proc.stdout:
                line = line.rstrip()
                if "" in line:
                    meta = parse_metadata(line)
                    if meta:
                        with metadata_lock:
                            metadata_list.append(meta)
                elif should_show(line):
                    on_line(line)

            proc.wait()
            code = proc.returncode
            with self.processes_lock:
                if proc in self.processes:
                    self.processes.remove(proc)
            with codes_lock:
                if code not in (0, -15) or (code == -15 and codes[0] == 0):
                    codes[0] = code

        threads = [threading.Thread(target=run_chunk, args=(chunk,)) for chunk in chunks]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        return codes[0], metadata_list

    def cancel(self):
        with self.processes_lock:
            for proc in self.processes:
                proc.kill()
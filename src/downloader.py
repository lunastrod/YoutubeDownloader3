import subprocess
import os
import sys
from collections.abc import Callable


def get_bin_dir() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "bin")


class Downloader:
    def __init__(self):
        self.bin_dir = get_bin_dir()
        self.process: subprocess.Popen | None = None

    def get_playlist_urls(self, url: str) -> list[str]:
        """Devuelve las URLs de los vídeos de una playlist sin descargar nada."""
        ytdlp = os.path.join(self.bin_dir, "yt-dlp.exe")
        result = subprocess.run(
            [ytdlp, "--flat-playlist", "--print", "%(url)s", url],
            capture_output=True,
            text=True,
        )
        urls = []
        for line in result.stdout.splitlines():
            if line:
                urls.append(line)
        return urls


    def get_metadata(self, urls: list[str]) -> list[dict]:
        """Devuelve una lista de diccionarios con title, album, artist y url para cada URL."""
        ytdlp = os.path.join(self.bin_dir, "yt-dlp.exe")
        template = "%(title)s%(album)s%(artist)s%(uploader)s%(webpage_url)s"
        result = subprocess.run(
            [ytdlp, "--print", template] + urls,
            capture_output=True,
            text=True,
        )
        metadata_list = []
        for line in result.stdout.splitlines():
            if not line:
                continue
            parts = line.split("")
            if len(parts) < 5:
                print(f"Warning: unexpected metadata format: {line}")
                continue
            title, album, artist, uploader, url = parts
            metadata_list.append({
                "title": title,
                "album": album if album != "NA" else title,
                "artist": artist if artist != "NA" else uploader,
                "url": url,
            })
        return metadata_list

    def _base_cmd(self) -> list[str]:
        ytdlp = os.path.join(self.bin_dir, "yt-dlp.exe")
        node = os.path.join(self.bin_dir, "node.exe")
        return [ytdlp, "--ffmpeg-location", self.bin_dir, "--js-runtimes", f"node:{node}"]

    def download_thumbnails(self, urls: list[str], thumbnails_dir: str) -> None:
        """Descarga las thumbnails de una lista de URLs en thumbnails_dir usando el ID como nombre."""
        os.makedirs(thumbnails_dir, exist_ok=True)
        output_template = os.path.join(thumbnails_dir, "%(id)s.%(ext)s")
        cmd = self._base_cmd() + [
            "--skip-download",
            "--write-thumbnail",
            "--output", output_template,
        ]
        cmd += urls
        subprocess.run(cmd, capture_output=True)

    def download_audio(self, urls: list[str], output_dir: str, on_line: Callable[[str], None]) -> int:
        """Descarga audio en mp3 usando el ID como nombre de archivo. Devuelve el return code."""
        output_template = os.path.join(output_dir, "%(id)s.%(ext)s")
        cmd = self._base_cmd() + [
            "--format", "bestaudio/best",
            "--extract-audio",
            "--audio-format", "mp3",
            "--restrict-filenames",
            "--output", output_template,
            "--newline",
        ]
        cmd += urls

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in self.process.stdout:
            on_line(line.rstrip())
        self.process.wait()
        code = self.process.returncode
        self.process = None
        return code

    def cancel(self):
        if self.process:
            self.process.terminate()
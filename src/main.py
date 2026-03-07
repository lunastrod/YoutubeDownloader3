import customtkinter as ctk
import threading
import os
import shutil
from tkinter import filedialog
from downloader import Downloader, AUDIO_COMPLETE
from metadata import filter_new_urls, embed_all, rename_files, embed_lyrics, get_deleted_songs, find_playlist_duplicates
from thumbnail import process_thumbnails

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")



class DeletedSongsDialog(ctk.CTkToplevel):
    def __init__(self, parent, deleted: list[tuple[str, str]]):
        super().__init__(parent)
        self.title("Canciones eliminadas de la playlist")
        self.geometry("500x400")
        self.resizable(False, False)
        self.grab_set()
        self.deleted = deleted
        self.vars = []
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Estas canciones ya no están en la playlist. ¿Cuáles quieres borrar?").grid(
            row=0, column=0, padx=20, pady=(20, 8), sticky="w"
        )

        scroll = ctk.CTkScrollableFrame(self)
        scroll.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        for i, (path, _) in enumerate(self.deleted):
            var = ctk.BooleanVar(value=False)
            self.vars.append(var)
            ctk.CTkCheckBox(scroll, text=os.path.basename(path), variable=var).grid(
                row=i, column=0, padx=10, pady=4, sticky="w"
            )

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=20, pady=(0, 20))

        ctk.CTkButton(btn_frame, text="Borrar seleccionadas", fg_color="red", hover_color="darkred", command=self._confirm).grid(row=0, column=0, padx=(0, 10))
        ctk.CTkButton(btn_frame, text="Cancelar", fg_color="gray30", hover_color="gray20", command=self.destroy).grid(row=0, column=1)

    def _confirm(self):
        for i, (path, _) in enumerate(self.deleted):
            if self.vars[i].get():
                os.remove(path)
        self.destroy()


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Playlist Downloader")
        self.geometry("700x560")
        self.resizable(False, False)
        self.output_dir = os.path.expanduser("~/Downloads/Music")
        self.downloader = Downloader()
        self.lyrics_var = ctk.BooleanVar(value=True)
        self._build_ui()
        threading.Thread(target=self._detect_browser, daemon=True).start()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(self, text="Playlist URL").grid(row=0, column=0, padx=20, pady=(20, 4), sticky="w")

        self.url_entry = ctk.CTkEntry(self, placeholder_text="https://www.youtube.com/playlist?list=...")
        self.url_entry.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="ew")

        folder_frame = ctk.CTkFrame(self, fg_color="transparent")
        folder_frame.grid(row=2, column=0, padx=20, pady=(0, 12), sticky="ew")
        folder_frame.grid_columnconfigure(0, weight=1)

        self.folder_label = ctk.CTkLabel(folder_frame, text=self.output_dir, anchor="w", text_color="gray")
        self.folder_label.grid(row=0, column=0, sticky="ew")

        ctk.CTkButton(folder_frame, text="Carpeta de destino", width=160, command=self._pick_folder).grid(row=0, column=1, padx=(10, 0))

        self.log_box = ctk.CTkTextbox(self, state="disabled", wrap="word")
        self.log_box.grid(row=3, column=0, padx=20, pady=(0, 8), sticky="nsew")

        self.status_label = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self.status_label.grid(row=4, column=0, padx=20, pady=(0, 4), sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=5, column=0, padx=20, pady=(0, 12), sticky="ew")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=6, column=0, padx=20, pady=(0, 20))

        self.download_btn = ctk.CTkButton(btn_frame, text="Descargar playlist", command=self._start_download)
        self.download_btn.grid(row=0, column=0, padx=(0, 10))

        self.cancel_btn = ctk.CTkButton(btn_frame, text="Cancelar", fg_color="gray30", hover_color="gray20", command=self.downloader.cancel, state="disabled")
        self.cancel_btn.grid(row=0, column=1, padx=(0, 20))

        ctk.CTkCheckBox(btn_frame, text="Incrustar letras", variable=self.lyrics_var).grid(row=0, column=2)

    def _detect_browser(self):
        self.after(0, self._set_status, "Detectando navegador...")
        self.downloader.browser = self.downloader._detect_browser()
        if self.downloader.browser:
            self.after(0, self._set_status, f"Usando cookies de {self.downloader.browser}")
        else:
            self.after(0, self._set_status, "Sin cookies de navegador, pueden aparecer limitaciones")

    def _pick_folder(self):
        folder = filedialog.askdirectory(initialdir=self.output_dir)
        if folder:
            self.output_dir = folder
            self.folder_label.configure(text=folder)

    def _log(self, msg: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        bottom = self.log_box.yview()[1]
        if bottom >= 0.99:
            self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_status(self, text: str):
        self.status_label.configure(text=text)

    def _set_progress(self, value: float):
        self.progress_bar.set(value)

    def _start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            self._log("Introduce una URL.")
            return
        self.download_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress_bar.set(0)
        threading.Thread(target=self._run_download, args=(url,), daemon=True).start()

    def _run_download(self, url: str):
        thumbnails_dir = os.path.join(self.output_dir, "thumbnails")
        try:
            self.after(0, self._set_status, "Obteniendo URLs de la playlist...")
            all_urls = self.downloader.get_playlist_urls(url)
            self.after(0, self._log, f"Canciones en la playlist: {len(all_urls)}")

            duplicates = find_playlist_duplicates(all_urls)
            for dup in duplicates:
                self.after(0, self._log, f"Duplicada en playlist: {dup}")

            new_urls = filter_new_urls(all_urls, self.output_dir)
            self.after(0, self._log, f"Canciones nuevas: {len(new_urls)}")

            if not new_urls:
                self.after(0, self._set_status, "No hay canciones nuevas que descargar.")
                return

            total = len(new_urls)
            audio_count = [0]
            audio_result = [0, []]

            def on_audio_line(line: str):
                if line.startswith(AUDIO_COMPLETE):
                    audio_count[0] += 1
                    self.after(0, self._set_progress, audio_count[0] / total)
                self.after(0, self._log, line)

            def run_audio():
                code, metadata = self.downloader.download_audio(new_urls, self.output_dir, on_audio_line)
                audio_result[0] = code
                audio_result[1] = metadata

            def run_thumbnails():
                self.downloader.download_thumbnails(new_urls, thumbnails_dir, lambda d, t: None)
                process_thumbnails(thumbnails_dir)

            self.after(0, self._set_status, "Descargando audio y thumbnails...")
            self.after(0, self._set_progress, 0)

            audio_thread = threading.Thread(target=run_audio)
            thumb_thread = threading.Thread(target=run_thumbnails)
            audio_thread.start()
            thumb_thread.start()
            audio_thread.join()
            thumb_thread.join()

            code = audio_result[0]
            metadata_list = audio_result[1]

            if code == -15:
                self.after(0, self._set_status, "Descarga cancelada.")
            else:
                if code != 0:
                    self.after(0, self._log, f"yt-dlp finalizo con codigo {code}, continuando post-procesado...")
                self.after(0, self._set_status, "Incrustando metadatos...")
                embed_all(self.output_dir, thumbnails_dir, metadata_list)
                if self.lyrics_var.get():
                    self.after(0, self._set_status, "Buscando letras...")
                    for metadata in metadata_list:
                        url = metadata.get("url", "")
                        video_id = url.split("v=")[-1]
                        mp3_path = os.path.join(self.output_dir, f"{video_id}.mp3")
                        embed_lyrics(mp3_path, metadata)
                self.after(0, self._set_status, "Renombrando archivos...")
                rename_files(self.output_dir, metadata_list)
                self.after(0, self._set_status, "Descarga completada.")
                self.after(0, self._set_progress, 1)
                deleted = get_deleted_songs(all_urls, self.output_dir)
                if deleted:
                    self.after(0, lambda d=deleted: DeletedSongsDialog(self, d))

        except FileNotFoundError:
            self.after(0, self._log, f"No se encontro yt-dlp.exe en: {self.downloader.bin_dir}")
        except Exception as e:
            self.after(0, self._log, f"Error: {e}")
        finally:
            if os.path.exists(thumbnails_dir):
                shutil.rmtree(thumbnails_dir)
            self.after(0, lambda: self.download_btn.configure(state="normal"))
            self.after(0, lambda: self.cancel_btn.configure(state="disabled"))


if __name__ == "__main__":
    App().mainloop()
import customtkinter as ctk
import threading
import os
import shutil
from tkinter import filedialog
from downloader import Downloader
from metadata import filter_new_urls, embed_all, rename_files
from thumbnail import process_thumbnails

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Playlist Downloader")
        self.geometry("700x500")
        self.resizable(False, False)
        self.output_dir = os.path.expanduser("~/Downloads")
        self.downloader = Downloader()
        self._build_ui()

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
        self.log_box.grid(row=3, column=0, padx=20, pady=(0, 12), sticky="nsew")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=4, column=0, padx=20, pady=(0, 20))

        self.download_btn = ctk.CTkButton(btn_frame, text="Descargar playlist", command=self._start_download)
        self.download_btn.grid(row=0, column=0, padx=(0, 10))

        self.cancel_btn = ctk.CTkButton(btn_frame, text="Cancelar", fg_color="gray30", hover_color="gray20", command=self.downloader.cancel, state="disabled")
        self.cancel_btn.grid(row=0, column=1)

    def _pick_folder(self):
        folder = filedialog.askdirectory(initialdir=self.output_dir)
        if folder:
            self.output_dir = folder
            self.folder_label.configure(text=folder)

    def _log(self, msg: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            self._log("Introduce una URL.")
            return
        self.download_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        threading.Thread(target=self._run_download, args=(url,), daemon=True).start()

    def _run_download(self, url: str):
        thumbnails_dir = os.path.join(self.output_dir, "thumbnails")
        try:
            self.after(0, self._log, "Obteniendo URLs de la playlist...")
            all_urls = self.downloader.get_playlist_urls(url)
            self.after(0, self._log, f"Canciones en la playlist: {len(all_urls)}")

            new_urls = filter_new_urls(all_urls, self.output_dir)
            self.after(0, self._log, f"Canciones nuevas: {len(new_urls)}")

            if not new_urls:
                self.after(0, self._log, "No hay canciones nuevas que descargar.")
                return

            self.after(0, self._log, "Obteniendo metadatos...")
            metadata_list = self.downloader.get_metadata(new_urls)

            self.after(0, self._log, "Descargando thumbnails...")
            self.downloader.download_thumbnails(new_urls, thumbnails_dir)

            self.after(0, self._log, "Procesando thumbnails...")
            process_thumbnails(thumbnails_dir)

            self.after(0, self._log, "Descargando audio...")
            code = self.downloader.download_audio(new_urls, self.output_dir, lambda line: self.after(0, self._log, line))

            if code == 0:
                self.after(0, self._log, "Incrustando metadatos...")
                embed_all(self.output_dir, thumbnails_dir, metadata_list)
                self.after(0, self._log, "Renombrando archivos...")
                rename_files(self.output_dir, metadata_list)
                self.after(0, self._log, "Descarga completada.")
            elif code == -15:
                self.after(0, self._log, "Descarga cancelada.")
            else:
                self.after(0, self._log, f"Error: codigo de salida {code}")

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
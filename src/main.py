import customtkinter as ctk
import threading
import os
import shutil
import tkinter
import downloader as dl
import metadata
import thumbnail
import logger as log
import config as cfg


class DeletedSongsDialog(ctk.CTkToplevel):
    def __init__(self, parent, deleted: list[tuple[str, str]]):
        super().__init__(parent)
        self.title("Deleted songs")
        self.geometry("500x400")
        self.resizable(True, True)
        self.grab_set()
        self.deleted = deleted
        self.vars = []
        self._build_ui()

    # Build and layout dialog widgets
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="These songs are no longer in the playlist. Which ones do you want to delete?").grid(
            row=0, column=0, padx=20, pady=(20, 8), sticky="w"
        )

        scroll = ctk.CTkScrollableFrame(self)
        scroll.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        for i, (path, _) in enumerate(self.deleted):
            var = tkinter.BooleanVar(value=False)
            self.vars.append(var)
            ctk.CTkCheckBox(scroll, text=os.path.basename(path), variable=var).grid(
                row=i, column=0, padx=10, pady=4, sticky="w"
            )

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=20, pady=(0, 20))

        ctk.CTkButton(btn_frame, text="Delete selected", fg_color="red", hover_color="darkred", command=self._confirm).grid(row=0, column=0, padx=(0, 10))
        ctk.CTkButton(btn_frame, text="Cancel", fg_color="gray30", hover_color="gray20", command=self.destroy).grid(row=0, column=1)

    # Delete checked songs and close dialog
    def _confirm(self):
        for i, (path, _) in enumerate(self.deleted):
            if self.vars[i].get():
                log.logger.log(f"Deleted: {os.path.basename(path)}")
                os.remove(path)
        self.destroy()


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("YouTube Downloader 3.1 - by Lunastrod")
        self.geometry("700x560")
        self.resizable(True, True)
        conf = cfg.load()
        self.output_dir = conf["output_dir"]
        self.downloader = dl.Downloader()
        self.downloader.browser = conf["browser"]
        self.lyrics_var = tkinter.BooleanVar(value=conf["embed_lyrics"])
        self.verbose_var = tkinter.BooleanVar(value=conf["verbose"])
        self._build_ui()
        log.logger.set_callback(self._log)
        log.logger.verbose = conf["verbose"]
        log.logger.set_progress_callback(lambda v: self.after(0, self._set_progress, v))
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._browser_thread = threading.Thread(target=self._detect_browser, daemon=True)
        self._browser_thread.start()

    # Build and layout all UI widgets
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

        ctk.CTkButton(folder_frame, text="Output folder", width=160, command=self._pick_folder).grid(row=0, column=1, padx=(10, 0))

        self.log_box = ctk.CTkTextbox(self, state="disabled", wrap="word")
        self.log_box.grid(row=3, column=0, padx=20, pady=(0, 8), sticky="nsew")

        self.status_label = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self.status_label.grid(row=4, column=0, padx=20, pady=(0, 4), sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=5, column=0, padx=20, pady=(0, 12), sticky="ew")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=6, column=0, padx=20, pady=(0, 20))

        self.download_btn = ctk.CTkButton(btn_frame, text="Download playlist", command=self._start_download)
        self.download_btn.grid(row=0, column=0, padx=(0, 10))

        self.cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", fg_color="gray30", hover_color="gray20", command=self.downloader.cancel, state="disabled")
        self.cancel_btn.grid(row=0, column=1, padx=(0, 20))

        ctk.CTkCheckBox(btn_frame, text="Embed lyrics", variable=self.lyrics_var).grid(row=0, column=2)
        ctk.CTkCheckBox(btn_frame, text="Verbose log", variable=self.verbose_var, command=self._toggle_verbose).grid(row=0, column=3, padx=(20, 0))

    # Sync verbose checkbox with logger
    def _toggle_verbose(self):
        log.logger.verbose = self.verbose_var.get()

    # Save config and close the window
    def _on_close(self):
        cfg.save({
            "output_dir": self.output_dir,
            "embed_lyrics": self.lyrics_var.get(),
            "verbose": self.verbose_var.get(),
            "browser": self.downloader.browser,
        })
        self.destroy()

    # Run browser detection in background and update status label
    def _detect_browser(self):
        self.after(0, self._set_status, "Updating yt-dlp...")
        self.downloader.update_ytdlp()
        self.after(0, self._set_status, "Detecting browser...")
        self.downloader.detect_browser()
        if self.downloader.browser:
            self.after(0, self._set_status, f"Using cookies from {self.downloader.browser}")
            log.logger.log(f"Detected browser for cookies: {self.downloader.browser}")
        else:
            self.after(0, self._set_status, "No browser cookies found, downloads may be rate limited")
            log.logger.warning("No browser cookies found, downloads may be rate limited")

    # Open folder picker dialog and update output directory
    def _pick_folder(self):
        folder = tkinter.filedialog.askdirectory(initialdir=self.output_dir)
        if folder:
            self.output_dir = folder
            self.folder_label.configure(text=folder)

    # Download and process thumbnails for all URLs
    def _run_thumbnails(self, urls: list[str], thumbnails_dir: str):
        self.downloader.download_thumbnails(urls, thumbnails_dir, lambda d, t: None)
        thumbnail.process_thumbnails(thumbnails_dir)

    # Download audio for all URLs and store result in audio_result
    def _run_audio(self, urls: list[str], audio_result: dict):
        code, meta = self.downloader.download_audio(urls, self.output_dir)
        audio_result["code"] = code
        audio_result["metadata"] = meta

    # Append a line to the log box, auto-scrolling only if already at bottom
    def _log(self, msg: str, color: str | None = None):
        self.after(0, self._write_line, msg, color)

    def _write_line(self, msg: str, color: str | None = None):
        self.log_box.configure(state="normal")
        if color:
            tag = f"color_{color}"
            self.log_box.tag_config(tag, foreground=color)
            self.log_box.insert("end", msg + "\n", tag)
        else:
            self.log_box.insert("end", msg + "\n")
        at_bottom = self.log_box.yview()[1] >= 0.99
        if at_bottom:
            self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # Update the status label text
    def _set_status(self, text: str):
        self.status_label.configure(text=text)

    # Update the progress bar value (0.0 to 1.0)
    def _set_progress(self, value: float):
        self.progress_bar.set(value)

    # Validate URL and start the download thread
    def _start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            log.logger.warning("Please enter a URL.")
            return
        self.download_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress_bar.set(0)
        threading.Thread(target=self._run_download, args=(url,), daemon=True).start()

    # Main download flow: fetch URLs, download audio and thumbnails, embed metadata
    def _run_download(self, playlist_url: str):
        thumbnails_dir = os.path.join(self.output_dir, "thumbnails")
        try:
            # Ensure browser detection is done before starting downloads
            self._browser_thread.join()

            # 1: Fetch playlist URLs
            self.after(0, self._set_status, "Fetching playlist URLs...")
            all_urls = self.downloader.get_playlist_urls(playlist_url)
            log.logger.log(f"Songs in playlist: {len(all_urls)}")

            # 2: Check for duplicates within the playlist itself
            duplicates = metadata.find_playlist_duplicates(all_urls)
            for dup in duplicates:
                log.logger.warning(f"Duplicate in playlist: {dup}")

            # 3: Filter out already downloaded songs
            new_urls = metadata.filter_new_urls(all_urls, self.output_dir)
            log.logger.log(f"New songs: {len(new_urls)}")

            if not new_urls:
                self.after(0, self._set_status, "No new songs to download.")
                log.logger.log("No new songs to download.")
                return

            # 4: Download audio and thumbnails in parallel threads
            audio_result = {"code": 0, "metadata": []}
            self.after(0, self._set_status, "Downloading audio and thumbnails...")
            self.after(0, self._set_progress, 0)

            audio_thread = threading.Thread(target=self._run_audio, args=(new_urls, audio_result))
            thumb_thread = threading.Thread(target=self._run_thumbnails, args=(new_urls, thumbnails_dir))
            audio_thread.start()
            thumb_thread.start()
            audio_thread.join()
            thumb_thread.join()

            code = audio_result["code"]
            metadata_list = audio_result["metadata"]

            if code == -15:
                self.after(0, self._set_status, "Download cancelled.")
                log.logger.warning("Download cancelled.")
            else:
                if code != 0:
                    log.logger.error(f"yt-dlp exited with code {code}, continuing post-processing...")
                # 5: Embed metadata and thumbnails
                self.after(0, self._set_status, "Embedding metadata...")
                log.logger.log("Embedding metadata and processing thumbnails...")
                metadata.embed_all(self.output_dir, thumbnails_dir, metadata_list)
                # 6: Fetch and embed lyrics
                if self.lyrics_var.get():
                    log.logger.log("Fetching and embedding lyrics...")
                    self.after(0, self._set_status, "Fetching lyrics...")
                    metadata.embed_lyrics(self.output_dir, metadata_list)
                # 7: Rename files based on metadata
                self.after(0, self._set_status, "Renaming files...")
                log.logger.log("Renaming files based on metadata...")
                metadata.rename_files(self.output_dir, metadata_list)
                self.after(0, self._set_status, "Done.")
                self.after(0, self._set_progress, 1)
                # 8: Check for deleted songs and show dialog
                deleted = metadata.get_deleted_songs(all_urls, self.output_dir)
                log.logger.log(f"Deleted songs detected: {len(deleted)}")
                if deleted:
                    self.after(0, lambda d=deleted: DeletedSongsDialog(self, d))
                log.logger.log(f"Done. {len(metadata_list)} songs downloaded.")

        except FileNotFoundError:
            log.logger.error(f"yt-dlp.exe not found in: {self.downloader.bin_dir}")
        except Exception as e:
            log.logger.error(f"Error: {e}")
        finally:
            if os.path.exists(thumbnails_dir):
                shutil.rmtree(thumbnails_dir)
            self.after(0, lambda: self.download_btn.configure(state="normal"))
            self.after(0, lambda: self.cancel_btn.configure(state="disabled"))


if __name__ == "__main__":
    App().mainloop()
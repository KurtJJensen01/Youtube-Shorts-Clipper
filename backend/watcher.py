from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


def _is_stable_file(path: Path, stable_seconds: int) -> bool:
    # Consider file stable if size hasn't changed for stable_seconds
    last_size = -1
    stable_for = 0
    while stable_for < stable_seconds:
        if not path.exists():
            return False
        size = path.stat().st_size
        if size == last_size and size > 0:
            stable_for += 1
        else:
            stable_for = 0
            last_size = size
        time.sleep(1)
    return True


class _Handler(FileSystemEventHandler):
    def __init__(
        self,
        exts: set[str],
        stable_seconds: int,
        on_ready: Callable[[Path], None],
    ):
        self.exts = exts
        self.stable_seconds = stable_seconds
        self.on_ready = on_ready

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() not in self.exts:
            return

        # Wait for download to finish
        if _is_stable_file(path, self.stable_seconds):
            self.on_ready(path)


def watch_folder(
    folder: Path,
    exts: set[str],
    stable_seconds: int,
    on_ready: Callable[[Path], None],
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    observer = Observer()
    handler = _Handler(exts, stable_seconds, on_ready)
    observer.schedule(handler, str(folder), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(0.5)
    finally:
        observer.stop()
        observer.join()

"""JSON persistence for the overlay's status text."""
import json
import os
import pathlib

DEFAULT_TEXT = "What are you working on?"


def get_storage_path() -> pathlib.Path:
    appdata = os.environ["APPDATA"]
    directory = pathlib.Path(appdata) / "FocusOverlay"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "status.json"


def load_text() -> str:
    path = get_storage_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("text", DEFAULT_TEXT)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return DEFAULT_TEXT


def save_text(text: str) -> None:
    path = get_storage_path()
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"text": text}, f)
    os.replace(tmp_path, path)

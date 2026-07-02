"""System tray icon: Show/Hide, Edit, Quit menu, backed by a runtime-drawn icon."""
import queue

import pystray
from PIL import Image, ImageDraw


def create_icon_image(size: int = 64) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = size // 8
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=(30, 144, 255, 255),
    )
    mid = size // 2
    draw.line([(margin, mid), (size - margin, mid)], fill=(255, 255, 255, 255), width=size // 12)
    return image


def build_tray_icon(event_queue: "queue.Queue") -> pystray.Icon:
    menu = pystray.Menu(
        pystray.MenuItem("Show/Hide", lambda icon, item: event_queue.put(("TOGGLE_VISIBILITY", None))),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Add Task", lambda icon, item: event_queue.put(("ADD_TASK", None))),
        pystray.MenuItem("Rename Active Task", lambda icon, item: event_queue.put(("START_EDIT", None))),
        pystray.MenuItem("Cycle Task", lambda icon, item: event_queue.put(("CYCLE_TASK", None))),
        pystray.MenuItem("Mark Done", lambda icon, item: event_queue.put(("MARK_DONE", None))),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Statistics", lambda icon, item: event_queue.put(("OPEN_STATS", None))),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", lambda icon, item: event_queue.put(("QUIT", None))),
    )
    return pystray.Icon("focus_overlay", icon=create_icon_image(), title="Focus Overlay", menu=menu)


def run_tray(icon: pystray.Icon) -> None:
    icon.run()

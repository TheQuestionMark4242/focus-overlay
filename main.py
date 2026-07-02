"""Focus Overlay: a transparent, click-through status strip pinned above the
taskbar showing the active tracked task. Ctrl+Alt+F toggles visibility,
Ctrl+Alt+T adds a task, Ctrl+Alt+E renames the active task, Ctrl+Alt+C
cycles the active task, Ctrl+Alt+D marks the active task done.
"""
import ctypes
import queue
import threading
import tkinter as tk

import win32api
import win32con
import win32gui
import win32process
import pywintypes

import stats
import tasks_db
import tray
from hotkeys import HotkeyListener

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

OVERLAY_HEIGHT = 55
OVERLAY_ALPHA = 0.6
FONT = ("Segoe UI", 14)
PLACEHOLDER_TEXT = "No active task"


def set_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def get_work_area_bottom() -> int:
    """Bottom y-coordinate of the desktop work area, i.e. the top edge of a
    bottom-docked taskbar. SPI_GETWORKAREA excludes the taskbar automatically,
    regardless of taskbar auto-hide/height settings.
    """
    SPI_GETWORKAREA = 0x0030
    rect = _Rect()
    ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
    return rect.bottom


def set_click_through(hwnd: int, enabled: bool) -> None:
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if enabled:
        style |= (WS_EX_LAYERED | WS_EX_TRANSPARENT)
    else:
        style = (style | WS_EX_LAYERED) & ~WS_EX_TRANSPARENT
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


def force_foreground(hwnd: int) -> None:
    """Windows blocks background processes from stealing keyboard focus
    (SetForegroundWindow restriction), so overrideredirect windows never
    receive real focus via Tk's focus_force() alone. Stacks three
    workarounds real launcher tools (AutoHotkey, PowerToys Run) rely on,
    since any single one can be denied depending on what currently owns
    the foreground: borrowing the foreground thread's input state via
    AttachThreadInput, refreshing "last input" with a harmless simulated
    Alt keypress, and SwitchToThisWindow — an undocumented but widely used
    user32 call that activates a window without going through the same
    lock SetForegroundWindow enforces. Never let this raise: worst case
    the edit box just doesn't get real keyboard focus.
    """
    fg_hwnd = win32gui.GetForegroundWindow()
    if fg_hwnd == hwnd:
        return
    current_thread = win32api.GetCurrentThreadId()
    fg_thread = 0
    attached = False
    try:
        if fg_hwnd:
            fg_thread = win32process.GetWindowThreadProcessId(fg_hwnd)[0]
        if fg_thread and fg_thread != current_thread:
            win32process.AttachThreadInput(fg_thread, current_thread, True)
            attached = True
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        try:
            ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
        except Exception:
            pass
        win32gui.SetForegroundWindow(hwnd)
    except pywintypes.error:
        pass
    finally:
        if attached:
            win32process.AttachThreadInput(fg_thread, current_thread, False)


class OverlayApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", OVERLAY_ALPHA)
        self.root.configure(bg="black")

        screen_w = self.root.winfo_screenwidth()
        y = get_work_area_bottom() - OVERLAY_HEIGHT
        self.root.geometry(f"{screen_w}x{OVERLAY_HEIGHT}+0+{y}")

        # Resume whatever task was active if the app was killed uncleanly
        # last run (an open time entry survives a crash on purpose — see
        # do_quit for why we never auto-close it).
        self.active_task_id = tasks_db.get_open_time_entry_task_id()
        self.current_text = self._task_display_text(self.active_task_id)

        self.label = tk.Label(self.root, text=self.current_text, fg="white", bg="black", font=FONT)
        self.label.pack(expand=True, fill="both")
        self.entry = None
        self._pending_commit = None
        self.stats_window = None

        self.root.update_idletasks()
        # winfo_id() returns Tk's inner TkChild window; window styles and
        # SetForegroundWindow only work on the real TkTopLevel ancestor.
        GA_ROOT = 2
        self.hwnd = ctypes.windll.user32.GetAncestor(self.root.winfo_id(), GA_ROOT)
        set_click_through(self.hwnd, True)

        self.event_queue: "queue.Queue" = queue.Queue()
        self.hotkey_listener = HotkeyListener(self.event_queue)
        self.tray_icon = tray.build_tray_icon(self.event_queue)

    def start(self) -> None:
        self.hotkey_listener.start()
        threading.Thread(target=tray.run_tray, args=(self.tray_icon,), daemon=True).start()
        self.root.after(50, self.poll_queue)
        self.root.mainloop()

    def poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.event_queue.get_nowait()
                if kind == "TOGGLE_VISIBILITY":
                    self.toggle_visibility()
                elif kind == "START_EDIT":
                    self.start_rename_task()
                elif kind == "ADD_TASK":
                    self.start_add_task()
                elif kind == "CYCLE_TASK":
                    self.cycle_task()
                elif kind == "MARK_DONE":
                    self.mark_active_done()
                elif kind == "OPEN_STATS":
                    self.open_stats_window()
                elif kind == "QUIT":
                    self.do_quit()
                    return
                elif kind == "HOTKEY_REGISTER_FAILED":
                    print(f"Warning: failed to register hotkey {payload} (already in use by another app?)", flush=True)
        except queue.Empty:
            pass
        self.root.after(50, self.poll_queue)

    def toggle_visibility(self) -> None:
        if self.entry is not None:
            self._on_inline_cancel()
            return
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.attributes("-topmost", True)
        else:
            self.root.withdraw()

    # -- task display / activation -----------------------------------

    def _task_display_text(self, task_id) -> str:
        if task_id is None:
            return PLACEHOLDER_TEXT
        task = tasks_db.get_task(task_id)
        return task["title"] if task is not None else PLACEHOLDER_TEXT

    def activate_task(self, task_id) -> None:
        if self.active_task_id is not None:
            tasks_db.close_open_time_entry(self.active_task_id)
        if task_id is not None:
            tasks_db.open_time_entry(task_id)
        self.active_task_id = task_id
        self.current_text = self._task_display_text(task_id)
        self.label.config(text=self.current_text)

    def _next_open_task_id(self, after_task_id):
        open_tasks = tasks_db.list_open_tasks()
        if not open_tasks:
            return None
        ids = [t["id"] for t in open_tasks]
        if after_task_id in ids:
            idx = (ids.index(after_task_id) + 1) % len(ids)
            return ids[idx]
        return ids[0]

    def cycle_task(self) -> None:
        if self.entry is not None:
            return
        self.activate_task(self._next_open_task_id(self.active_task_id))

    def mark_active_done(self) -> None:
        if self.entry is not None or self.active_task_id is None:
            return
        completing_id = self.active_task_id
        tasks_db.close_open_time_entry(completing_id)
        tasks_db.complete_task(completing_id)
        self.active_task_id = None
        # Must run after complete_task: list_open_tasks() needs to already
        # exclude completing_id, otherwise when it's the only open task the
        # round-robin wraps back to itself and reopens a closed task.
        next_id = self._next_open_task_id(completing_id)
        self.activate_task(next_id)

    # -- inline edit (shared by add-task and rename-task) -------------

    def _start_inline_edit(self, initial_text: str, on_commit_text) -> None:
        if self.entry is not None:
            return
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.attributes("-topmost", True)

        set_click_through(self.hwnd, False)
        self.label.pack_forget()

        self.entry = tk.Entry(self.root, font=FONT)
        self.entry.insert(0, initial_text)
        self.entry.pack(expand=True, fill="both")
        self.entry.select_range(0, "end")

        force_foreground(self.hwnd)
        self.root.lift()
        self.root.focus_force()
        self.entry.focus_force()

        self._pending_commit = on_commit_text
        self.entry.bind("<Return>", self._on_inline_commit)
        self.entry.bind("<Escape>", self._on_inline_cancel)

    def _on_inline_commit(self, _event=None) -> None:
        text = self.entry.get().strip()
        callback = self._pending_commit
        self._exit_inline_edit()
        if text:
            callback(text)

    def _on_inline_cancel(self, _event=None) -> None:
        self._exit_inline_edit()

    def _exit_inline_edit(self) -> None:
        self.entry.destroy()
        self.entry = None
        self._pending_commit = None
        self.label.config(text=self.current_text)
        self.label.pack(expand=True, fill="both")
        set_click_through(self.hwnd, True)

    def start_add_task(self) -> None:
        self._start_inline_edit("", self._commit_add_task)

    def _commit_add_task(self, title: str) -> None:
        new_id = tasks_db.create_task(title)
        self.activate_task(new_id)

    def start_rename_task(self) -> None:
        if self.active_task_id is None:
            self.start_add_task()
            return
        current_title = tasks_db.get_task(self.active_task_id)["title"]
        self._start_inline_edit(current_title, self._commit_rename_task)

    def _commit_rename_task(self, title: str) -> None:
        tasks_db.rename_task(self.active_task_id, title)
        self.current_text = title
        self.label.config(text=title)

    # -- statistics window ---------------------------------------------

    def open_stats_window(self) -> None:
        if self.stats_window is not None and self.stats_window.top.winfo_exists():
            self.stats_window.top.lift()
            self.stats_window.top.focus_force()
            return
        self.stats_window = stats.StatsWindow(self.root)

    def do_quit(self) -> None:
        # Intentionally does NOT close the active task's open time entry:
        # only an explicit task switch or Ctrl+Alt+D should stop the clock,
        # so a restart resumes the same task instead of losing tracked time.
        self.hotkey_listener.stop()
        self.tray_icon.stop()
        self.root.destroy()


def main() -> None:
    set_dpi_awareness()
    app = OverlayApp()
    app.start()


if __name__ == "__main__":
    main()

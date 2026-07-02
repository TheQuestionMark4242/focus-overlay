"""Focus Overlay: a transparent, click-through status strip pinned above the
taskbar. Ctrl+Alt+F toggles visibility, Ctrl+Alt+E edits the status text.
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

import storage
import tray
from hotkeys import HotkeyListener

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

OVERLAY_HEIGHT = 55
OVERLAY_ALPHA = 0.6
FONT = ("Segoe UI", 14)


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
        self.current_text = storage.load_text()

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", OVERLAY_ALPHA)
        self.root.configure(bg="black")

        screen_w = self.root.winfo_screenwidth()
        y = get_work_area_bottom() - OVERLAY_HEIGHT
        self.root.geometry(f"{screen_w}x{OVERLAY_HEIGHT}+0+{y}")

        self.label = tk.Label(self.root, text=self.current_text, fg="white", bg="black", font=FONT)
        self.label.pack(expand=True, fill="both")
        self.entry = None

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
                    self.enter_edit_mode()
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
            self.on_cancel()
            return
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.attributes("-topmost", True)
        else:
            self.root.withdraw()

    def enter_edit_mode(self) -> None:
        if self.entry is not None:
            return
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.attributes("-topmost", True)

        set_click_through(self.hwnd, False)
        self.label.pack_forget()

        self.entry = tk.Entry(self.root, font=FONT)
        self.entry.insert(0, self.current_text)
        self.entry.pack(expand=True, fill="both")
        self.entry.select_range(0, "end")

        force_foreground(self.hwnd)
        self.root.lift()
        self.root.focus_force()
        self.entry.focus_force()
        self.entry.bind("<Return>", self.on_commit)
        self.entry.bind("<Escape>", self.on_cancel)

    def on_commit(self, _event=None) -> None:
        text = self.entry.get()
        storage.save_text(text)
        self.exit_edit_mode(text)

    def on_cancel(self, _event=None) -> None:
        self.exit_edit_mode(self.current_text)

    def exit_edit_mode(self, final_text: str) -> None:
        self.current_text = final_text
        self.entry.destroy()
        self.entry = None
        self.label.config(text=final_text)
        self.label.pack(expand=True, fill="both")
        set_click_through(self.hwnd, True)

    def do_quit(self) -> None:
        self.hotkey_listener.stop()
        self.tray_icon.stop()
        self.root.destroy()


def main() -> None:
    set_dpi_awareness()
    app = OverlayApp()
    app.start()


if __name__ == "__main__":
    main()

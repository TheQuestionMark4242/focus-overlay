"""Global hotkey listener using the native Win32 RegisterHotKey API.

Runs on its own thread with a real Win32 message loop, since RegisterHotKey
delivers WM_HOTKEY as a thread message that only a GetMessage loop on the
registering thread will receive.
"""
import queue
import threading
import time

import win32api
import win32con
import win32gui
import pywintypes

HOTKEY_ID_TOGGLE = 1
HOTKEY_ID_EDIT = 2
MOD_NOREPEAT = 0x4000


class HotkeyListener:
    def __init__(self, event_queue: "queue.Queue"):
        self.event_queue = event_queue
        self.thread_id = None
        self._thread = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self.thread_id is not None:
            win32api.PostThreadMessage(self.thread_id, win32con.WM_QUIT, 0, 0)

    def _run(self) -> None:
        self.thread_id = win32api.GetCurrentThreadId()

        registered = []
        # Retry registration for a few seconds: if a previous instance of
        # this app is still shutting down, it owns the hotkeys until its
        # thread dies, and a one-shot attempt would lose them permanently.
        for hotkey_id, vk, name in (
            (HOTKEY_ID_TOGGLE, ord("F"), "Ctrl+Alt+F"),
            (HOTKEY_ID_EDIT, ord("E"), "Ctrl+Alt+E"),
        ):
            for attempt in range(10):
                try:
                    win32gui.RegisterHotKey(
                        None, hotkey_id,
                        win32con.MOD_CONTROL | win32con.MOD_ALT | MOD_NOREPEAT, vk,
                    )
                    registered.append(hotkey_id)
                    break
                except pywintypes.error:
                    time.sleep(0.5)
            else:
                self.event_queue.put(("HOTKEY_REGISTER_FAILED", name))

        try:
            while True:
                result = win32gui.GetMessage(None, 0, 0)
                if result[0] == 0:
                    break
                hwnd, message, wparam, lparam, time_, pt = result[1]
                if message == win32con.WM_HOTKEY:
                    if wparam == HOTKEY_ID_TOGGLE:
                        self.event_queue.put(("TOGGLE_VISIBILITY", None))
                    elif wparam == HOTKEY_ID_EDIT:
                        self.event_queue.put(("START_EDIT", None))
                win32gui.TranslateMessage(result[1])
                win32gui.DispatchMessage(result[1])
        finally:
            for hotkey_id in registered:
                try:
                    win32gui.UnregisterHotKey(None, hotkey_id)
                except pywintypes.error:
                    pass

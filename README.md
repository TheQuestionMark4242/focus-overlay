# Focus Overlay

A thin, semi-transparent status strip pinned just above the taskbar showing
what you're currently working on.

## Hotkeys (global, work from any app)

- `Ctrl+Alt+F` — toggle the overlay's visibility
- `Ctrl+Alt+E` — edit the status text inline (Enter to save, Escape to cancel)

## Run

```
py -3.13 -m pip install -r requirements.txt
py -3.13 main.py
```

## Build a standalone .exe

```
powershell -File build.ps1
```

Produces `dist\FocusOverlay.exe` — a single-file executable, no Python
installation required to run it. Double-click it to launch, or place it in
your Startup folder to launch automatically at sign-in.

## Quit

There's no title bar or close button by design. Right-click the tray icon
(look in the system tray, possibly under the "^" overflow arrow) and choose
**Quit**. The tray menu also has Show/Hide and Edit, mirroring the hotkeys.

## Data

The status text is saved to `%APPDATA%\FocusOverlay\status.json` and
persists across restarts.

## Known limitations

- Spans the primary monitor's width only; doesn't span multiple monitors.
- Hotkeys are fixed (Ctrl+Alt+F / Ctrl+Alt+E), not user-configurable.
- If a hotkey doesn't respond, another running app may have already claimed
  that combination — check the console output for a warning.

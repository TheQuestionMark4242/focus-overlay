# Focus Overlay

A thin, semi-transparent status strip pinned just above the taskbar showing
the task you're currently tracking, with time tracking and charts.

## Hotkeys (global, work from any app)

- `Ctrl+Alt+F` — toggle the overlay's visibility
- `Ctrl+Alt+T` — add a new task and make it active ("Add task:" prompt)
- `Ctrl+Alt+E` — rename the active task ("Rename task:" prompt; starts a new task if none is active)
- `Ctrl+Alt+C` — cycle to the next open task (blind round-robin)
- `Ctrl+Alt+L` — open a list of open tasks; arrow keys to navigate, Enter to switch, Escape to cancel
- `Ctrl+Alt+D` — mark the active task done (auto-advances to the next open task)

Editing accepts Enter to save, Escape to cancel.

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
**Quit**. The tray menu also mirrors every hotkey, plus a **Statistics**
item that opens a window with a Pie Chart tab (time spent per task) and a
Timeline tab (when each task was worked on), filterable by Today / This
Week / All Time. The window sizes itself to the charts.

## Data

Tasks and tracked time are stored in a SQLite database at
`%APPDATA%\FocusOverlay\tasks.db`. At most one task is "active" (being
timed) at once; switching, cycling, or marking a task done always closes
out the previous task's timer before starting the next. Quitting the app
does **not** stop the active task's timer — only an explicit switch or
Ctrl+Alt+D does — so relaunching resumes tracking the same task.

## Known limitations

- Spans the primary monitor's width only; doesn't span multiple monitors.
- Hotkeys are fixed, not user-configurable.
- If a hotkey doesn't respond, another running app may have already claimed
  that combination — check the console output for a warning.
- The picker list (Ctrl+Alt+L) caps its visible rows at 10; with more open
  tasks than that you'll need to scroll or use blind cycling instead.

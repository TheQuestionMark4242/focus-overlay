"""Statistics window: pie chart of time-per-task and a timeline of work
sessions, each in its own tab so the window can size itself to whichever
chart is showing.
"""
import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib import dates as mdates

import tasks_db

RANGE_LABELS = ("Today", "This Week", "All Time")
PIE_FIGSIZE = (6, 6)
TIMELINE_FIGSIZE = (8, 5)
TIMELINE_COLORS = ("red", "blue", "green", "gold", "darkorange", "purple", "cyan", "magenta")


class StatsWindow:
    def __init__(self, master: tk.Tk):
        self.top = tk.Toplevel(master)
        self.top.title("Focus Overlay - Statistics")
        self.top.protocol("WM_DELETE_WINDOW", self._on_close)

        self.range_mode = "today"

        controls = tk.Frame(self.top)
        controls.pack(side="top", fill="x", padx=8, pady=8)

        for label, mode in zip(RANGE_LABELS, ("today", "week", "all")):
            tk.Button(controls, text=label, command=lambda m=mode: self.set_range(m)).pack(side="left", padx=4)
        tk.Button(controls, text="Refresh", command=self.refresh).pack(side="left", padx=16)

        notebook = ttk.Notebook(self.top)
        notebook.pack(side="top", fill="both", expand=True)

        pie_tab = tk.Frame(notebook)
        timeline_tab = tk.Frame(notebook)
        notebook.add(pie_tab, text="Pie Chart")
        notebook.add(timeline_tab, text="Timeline")

        self.pie_figure = Figure(figsize=PIE_FIGSIZE)
        self.pie_ax = self.pie_figure.add_subplot(1, 1, 1)
        self.pie_canvas = FigureCanvasTkAgg(self.pie_figure, master=pie_tab)
        self.pie_canvas.get_tk_widget().pack(fill="both", expand=True)

        self.timeline_figure = Figure(figsize=TIMELINE_FIGSIZE)
        self.timeline_ax = self.timeline_figure.add_subplot(1, 1, 1)
        self.timeline_canvas = FigureCanvasTkAgg(self.timeline_figure, master=timeline_tab)
        self.timeline_canvas.get_tk_widget().pack(fill="both", expand=True)

        # No fixed geometry: the Toplevel sizes itself to the packed
        # canvases' requested size (figsize * dpi), i.e. to the graphs.
        self.refresh()

    def set_range(self, mode: str) -> None:
        self.range_mode = mode
        self.refresh()

    def _range_bounds(self):
        if self.range_mode == "today":
            start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            return start.isoformat(timespec="seconds"), None
        if self.range_mode == "week":
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            start = today - timedelta(days=today.weekday())
            return start.isoformat(timespec="seconds"), None
        return None, None

    def refresh(self) -> None:
        range_start, range_end = self._range_bounds()
        totals = tasks_db.get_time_per_task(range_start, range_end)
        entries = tasks_db.get_time_entries_for_chart(range_start, range_end)

        self.pie_ax.clear()
        self._draw_pie(self.pie_ax, totals)
        self.pie_canvas.draw()

        self.timeline_ax.clear()
        self._draw_timeline(self.timeline_ax, entries)
        self.timeline_canvas.draw()

    def _draw_pie(self, ax, rows) -> None:
        if not rows:
            ax.text(0.5, 0.5, "No tracked time", ha="center", va="center")
            ax.set_axis_off()
            return
        ax.pie(
            [r["total_seconds"] for r in rows],
            labels=[r["title"] for r in rows],
            autopct="%1.0f%%",
        )
        ax.set_title("Time per task")

    def _draw_timeline(self, ax, rows) -> None:
        if not rows:
            ax.text(0.5, 0.5, "No tracked time", ha="center", va="center")
            ax.set_axis_off()
            return

        titles = []
        for row in rows:
            if row["title"] not in titles:
                titles.append(row["title"])
        y_by_title = {title: i for i, title in enumerate(titles)}

        now = datetime.now()
        for row in rows:
            y = y_by_title[row["title"]]
            color = TIMELINE_COLORS[y % len(TIMELINE_COLORS)]
            start = datetime.fromisoformat(row["start_time"])
            end = datetime.fromisoformat(row["end_time"]) if row["end_time"] else now
            x_start = mdates.date2num(start)
            x_end = mdates.date2num(end)
            ax.hlines(y, x_start, x_end, colors=color, lw=4)
            ax.vlines(x_start, y - 0.15, y + 0.15, colors=color, lw=2)
            ax.vlines(x_end, y - 0.15, y + 0.15, colors=color, lw=2)

        ax.set_yticks(range(len(titles)))
        ax.set_yticklabels(titles)
        ax.set_ylim(-1, len(titles))
        ax.xaxis_date()
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
        self.timeline_figure.autofmt_xdate()
        ax.set_xlabel("Time")
        ax.set_title("Timeline")

    def _on_close(self) -> None:
        self.top.destroy()

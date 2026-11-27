"""In-window oversight for current activity and recent cycle results."""
import sqlite3
from tkinter import StringVar
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from .activity_panel import ActivityPanel
from .cycle_journal import describe_outcome
from .event_store import read_projection
from .engagement import brief_text
from .engagement_files import INBOX, OUTPUTS


STATUS = {"produced": "Completed", "existing": "Already complete", "held": "Needs attention"}


class EngagementReports:
    def __init__(self, parent, open_folder, history):
        self.history = history
        self.latest = None
        self.latest_error = None
        self.pinned = None
        self.labels = ["Latest cycle"]
        self.keys = [None]
        self.choice = StringVar(parent, value=self.labels[0])
        self.pickers = []
        self.tabs = ttk.Notebook(parent)
        self.tabs.pack(fill="both", expand=True)
        self.summary = ttk.Frame(self.tabs)
        files = ttk.Frame(self.tabs, padding=(5, 3))
        self.files = files
        self.live_page = ttk.Frame(self.tabs, padding=(4, 0))
        for page, name in ((self.live_page, "Activity"), (self.summary, "Cycle briefs"), (files, "Work files")):
            self.tabs.add(page, text=name)
        self.tabs.enable_traversal()
        self.activity = ActivityPanel(self.live_page)
        for page in (self.summary, files):
            bar = ttk.Frame(page)
            bar.pack(fill="x", pady=(0, 3))
            ttk.Label(bar, text="Cycle").pack(side="left", padx=(2, 6))
            picker = ttk.Combobox(bar, state="readonly", textvariable=self.choice, values=self.labels)
            picker.pack(side="left", fill="x", expand=True)
            picker.bind("<<ComboboxSelected>>", self.select_cycle)
            self.pickers.append(picker)
        self.actions = ttk.Frame(self.summary)
        self.actions.pack(fill="x")
        self.text = ScrolledText(self.summary, wrap="word", width=1, height=4, padx=10, pady=8)
        self.text.pack(fill="both", expand=True)
        actions = ttk.Frame(files)
        actions.pack(fill="x")
        for name, label in ((INBOX, "Open inbox"), (OUTPUTS, "Open completed files")):
            ttk.Button(actions, text=label, command=lambda n=name: open_folder(n)).pack(side="left", padx=2)
        self.detail = ttk.Label(files, anchor="w", justify="left", wraplength=440)
        self.detail.pack(fill="x", pady=4)
        files.bind("<Configure>", lambda event: self.detail.configure(wraplength=max(180, event.width - 18)), add="+")
        table = ttk.Frame(files)
        table.pack(fill="both", expand=True)
        self.listing = ttk.Treeview(table, columns=("status",), selectmode="browse", height=3)
        self.listing.heading("#0", text="Input file")
        self.listing.column("#0", width=170, minwidth=80)
        self.listing.heading("status", text="Result")
        self.listing.column("status", width=125, minwidth=96, stretch=False)
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.listing.yview)
        scrollbar.pack(side="right", fill="y")
        self.listing.configure(yscrollcommand=scrollbar.set)
        self.listing.pack(fill="both", expand=True)
        self.listing.bind("<<TreeviewSelect>>", self.selected)
        self.items = {}

    def selected(self, _event=None):
        selected = self.listing.selection()
        item = self.items.get(selected[0]) if selected else None
        if item:
            detail = item["reason"] if item["status"] == "held" else "Output: " + item["output"]
            self.detail.configure(text=item["name"] + " · " + item["operation"] + "\n" + detail)

    def update_cycles(self, latest, *, error=None):
        self.latest_error = error
        first_label = "Latest cycle"
        try:
            earlier = self.history.earlier(latest)
        except (sqlite3.Error, ValueError, OverflowError):
            earlier = []
            first_label += " (history unavailable)"
        self.latest = latest
        self.keys = [None] + [row[0] for row in earlier]
        labels = [first_label]
        occurrences = {}
        for _, stamp, status in earlier:
            label = stamp[:19].replace("T", " ") + " UTC · " + status if stamp else status
            count = occurrences.get(label, 0) + 1
            occurrences[label] = count
            labels.append(label if count == 1 else f"{label} ({count})")
        self.labels = labels
        for picker in self.pickers:
            picker.configure(values=labels)
        if self.pinned and self.pinned in self.keys:
            index = self.keys.index(self.pinned)
            self.choice.set(labels[index])
            if not earlier[index - 1][1]:
                self.display(None, error="This cycle report could not be read. Choose another cycle.")
            return  # Leave valid historical report scroll position and file selection alone.
        self.show_latest()

    def show_latest(self):
        self.choice.set(self.labels[0])
        self.select_cycle()

    def select_cycle(self, _event=None):
        self.pinned = self.keys[self.labels.index(self.choice.get())]
        try:
            if self.pinned:
                self.display(self.history.read(self.pinned))
            else:
                self.display(self.latest, error=self.latest_error)
        except (ValueError, TypeError, KeyError, AttributeError, IndexError, OSError, sqlite3.Error, RecursionError):
            self.display(None, error="This cycle report could not be read. Choose another cycle.")

    def journal_status(self, brief):
        return describe_outcome(brief, lambda: read_projection(self.history.db)["history"])

    def display(self, brief, *, error=None):
        summary = error or "Choose Engage on Home to prepare your first brief."
        hint = error or "Completed files and anything needing attention will appear here after a cycle."
        rows = []
        if brief is not None:
            if not isinstance(brief, dict):
                raise ValueError("Invalid saved brief.")
            summary = self.journal_status(brief) + "\n\nReport contents (not independently attested)\n" + brief_text(brief)
            jobs = brief["jobs"]
            if jobs.get("issue"):
                hint = jobs["issue"]
            elif jobs["full"]:
                hint = "Move completed inputs out of Scout Inbox to reduce it to 128 entries."
            elif "items" not in jobs:
                hint = "This earlier brief contains totals. The next cycle will list individual files."
            else:
                hint = "No CSV or JSON inputs were found in this cycle. Use Open inbox to add work."
                rows = sorted(jobs["items"], key=lambda row: row["status"] != "held")
                for item in rows:
                    fields = ("name", "operation", "reason" if item["status"] == "held" else "output")
                    if item["status"] not in STATUS or any(not isinstance(item[k], str) for k in fields):
                        raise ValueError("Invalid saved file result.")
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", summary)
        self.text.configure(state="disabled")
        self.listing.delete(*self.listing.get_children())
        self.items = {self.listing.insert("", "end", text=row["name"], values=(STATUS[row["status"]],)): row for row in rows}
        self.detail.configure(text=hint)
        if self.items:
            first = next(iter(self.items))
            self.listing.selection_set(first)
            self.listing.focus(first)
            self.selected()

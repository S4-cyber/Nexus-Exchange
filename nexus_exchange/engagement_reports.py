"""In-window oversight for the latest autonomous search and local production cycle."""
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from .activity_panel import ActivityPanel
from .engagement import brief_text
from .engagement_files import INBOX, OUTPUTS


STATUS = {"produced": "Completed", "existing": "Already complete", "held": "Needs attention"}


class EngagementReports:
    def __init__(self, parent, open_folder):
        self.tabs = ttk.Notebook(parent)
        self.tabs.pack(fill="both", expand=True)
        self.summary = ttk.Frame(self.tabs)
        files = ttk.Frame(self.tabs, padding=(5, 3))
        self.files = files
        self.live_page = ttk.Frame(self.tabs, padding=(4, 0))
        for page, name in ((self.live_page, "Activity"), (self.summary, "Latest cycle"), (files, "Work files")):
            self.tabs.add(page, text=name)
        self.tabs.enable_traversal()
        self.activity = ActivityPanel(self.live_page)
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

    def display(self, brief, *, error=None):
        summary = error or "Choose Engage on Home to prepare your first brief."
        hint = error or "Completed files and anything needing attention will appear here after a cycle."
        rows = []
        if brief is not None:
            if not isinstance(brief, dict):
                raise ValueError("Invalid saved brief.")
            summary = brief_text(brief)
            jobs = brief["jobs"]
            if jobs.get("issue"):
                hint = jobs["issue"]
            elif jobs["full"]:
                hint = "Move completed inputs out of Scout Inbox to reduce it to 128 entries."
            elif "items" not in jobs:
                hint = "This earlier brief contains totals. The next cycle will list individual files."
            else:
                hint = "No CSV or JSON inputs were found in the last cycle. Use Open inbox to add work."
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

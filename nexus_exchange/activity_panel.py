"""Searchable scrolling task and findings view, with inline detail."""
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from .activity_feed import STATES


class ActivityPanel:
    def __init__(self, parent):
        filters = ttk.Frame(parent)
        filters.pack(fill="x", pady=(2, 4))
        self.query = tk.StringVar()
        self.state = tk.StringVar(value="All statuses")
        ttk.Label(filters, text="Search activity").pack(side="left")
        entry = ttk.Entry(filters, textvariable=self.query, width=12)
        entry.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Combobox(filters, textvariable=self.state, values=("All statuses", *STATES),
                     state="readonly", width=15).pack(side="left")
        table = ttk.Frame(parent)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("status","time"), selectmode="browse", height=4)
        self.tree.heading("#0", text="Task or finding")
        self.tree.heading("status", text="Status")
        self.tree.heading("time", text="Updated (UTC)")
        self.tree.column("#0", width=190, minwidth=85)
        self.tree.column("status", width=107, minwidth=75, stretch=False)
        self.tree.column("time", width=130, minwidth=95, stretch=False)
        bar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        bar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(fill="both", expand=True)
        self.detail = ScrolledText(parent, wrap="word", height=3, width=1, padx=4, pady=2, state="disabled")
        self.detail.pack(fill="x", pady=(3, 0))
        self.visible = {}
        self.rows = []
        self.last_detail = None
        self.tree.bind("<<TreeviewSelect>>", self.selected)
        self.query.trace_add("write", self.filter)
        self.state.trace_add("write", self.filter)

    def selected(self, _event=None):
        selection = self.tree.selection()
        row = self.visible.get(selection[0]) if selection else None
        if row:
            value = row[2] + " · " + row[1] + ("\n" + row[3] if row[3] else "")
        elif self.visible:
            value = f"{len(self.visible)} matching items. Select a row for details."
        elif self.rows:
            value = "No matching activity. Change your search or status filter."
        else:
            value = "Choose Engage on Home to see live work and findings."
        if self.last_detail != value:
            self.detail.configure(state="normal")
            self.detail.delete("1.0", "end")
            self.detail.insert("1.0", value)
            self.detail.configure(state="disabled")
            self.last_detail = value

    def display(self, rows):
        self.rows = rows
        self.render(keep_position=True)

    def filter(self, *_):
        self.render(keep_position=False)

    def render(self, *, keep_position):
        query = self.query.get().strip().casefold()
        state = self.state.get()
        old_view = self.tree.yview()
        top_row = None
        if keep_position and old_view and old_view[0] > 0 and self.tree.winfo_ismapped():
            for y in range(0, min(60, self.tree.winfo_height()), 3):
                top_row = self.tree.identify_row(y)
                if top_row:
                    break
        matches = {r[0]: r for r in self.rows if (state == "All statuses" or r[1] == state)
                   and (not query or any(query in t.casefold() for t in r[1:]))}
        # Update in place so typing, selections and scrolled history survive live updates.
        for key in self.visible.keys() - matches.keys():
            self.tree.delete(key)
        for key, row in matches.items():
            if self.visible.get(key) == row:
                continue
            values = (row[1], row[4][:16].replace("T", " "))
            if key in self.visible:
                self.tree.item(key, text=row[2], values=values)
            else:
                self.tree.insert("", "end", iid=key, text=row[2], values=values)
        if list(matches) != list(self.visible):
            self.tree.set_children("", *matches.keys())
        self.visible = matches
        if top_row in matches:
            self.tree.yview_moveto(self.tree.index(top_row) / len(matches))
        elif not keep_position or not old_view or old_view[0] == 0:
            self.tree.yview_moveto(0)
        self.selected()

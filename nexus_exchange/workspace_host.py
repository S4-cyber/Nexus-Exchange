"""One shared desktop Tools tab with local Back navigation."""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk

from .cockpit import WorkspaceViewport, fit_geometry, install_cockpit


def install_identity(root):
    assets = Path(__file__).resolve().parent.parent / "resources" / "desktop"
    logo = tk.PhotoImage(master=root, file=str(assets / "exchange.png"))
    root.iconphoto(True, logo)
    if sys.platform == "win32":
        root.iconbitmap(default=str(assets / "exchange.ico"))
    return logo


class ToolPane(ttk.Frame):
    def __init__(self, host, previous, origin, title):
        super().__init__(host.body)
        self.host = host
        self.previous = previous
        self.origin = origin
        self.title = title.split("|")[-1].strip()
        self.return_focus = host.tabs.focus_get()
        self.viewport = WorkspaceViewport(self)

    def destroy(self):
        super().destroy()
        self.host.removed(self)


class WorkspaceHost:
    def __init__(self, notebook):
        self.tabs = notebook
        self.page = ttk.Frame(notebook, padding=(5, 3))
        bar = ttk.Frame(self.page)
        bar.pack(fill="x", pady=(0, 3))
        self.back = ttk.Button(bar, text="Back", command=self.go_back)
        self.back.pack(side="left")
        self.title = ttk.Label(bar)
        self.title.pack(side="left", padx=8)
        self.body = ttk.Frame(self.page)
        self.body.pack(fill="both", expand=True)
        self.stack = []
        self.launchers = {}
        self.tabs.winfo_toplevel()._nexus_tools = self
        self.tabs.winfo_toplevel().bind("<FocusIn>", self.reveal, add="+")

    def reveal(self, event):
        if self.stack and self.tabs.select() == str(self.page):
            self.stack[-1].viewport.reveal(event.widget)

    def button(self, parent, label, build):
        button = ttk.Button(parent, text=label)
        button.configure(command=lambda: self.launch(button, build))
        return button

    def launch(self, button, build):
        existing = self.launchers.get(button)
        if existing is None or not existing.winfo_exists():
            pane = build()
            if pane is not None:
                self.launchers[button] = pane
                pane.return_focus = button
            return pane
        # A reopened top-level tool keeps its current form and any nested review.
        chain = [existing]
        for pane in self.stack:
            if pane.previous in chain:
                chain.append(pane)
        self.show(chain[-1])
        return existing

    def open(self, parent, title):
        origin = self.tabs.select()
        previous = self.stack[-1] if self.stack and origin == str(self.page) else None
        # Explicit parent windows retain their own return path.
        ancestor = parent
        while ancestor is not None:
            if ancestor in self.stack:
                previous = ancestor
                break
            ancestor = getattr(ancestor, "master", None)
        pane = ToolPane(self, previous, previous.origin if previous is not None else origin, title)
        self.show(pane)
        return pane, pane.viewport.content

    def show(self, pane, *, activate=True):
        if self.stack:
            self.stack[-1].pack_forget()
        if pane in self.stack:
            self.stack.remove(pane)
        self.stack.append(pane)
        if str(self.page) not in self.tabs.tabs():
            self.tabs.add(self.page, text="Tools")
        pane.pack(fill="both", expand=True)
        self.title.configure(text=pane.title)
        self.back.configure(text="Back" if pane.previous else "Back to " + self.tabs.tab(pane.origin, "text"))
        if activate:
            self.tabs.select(self.page)
            self.back.focus_set()

    def go_back(self):
        if self.stack:
            self.stack[-1].destroy()

    def removed(self, pane):
        if pane not in self.stack:
            return
        active = self.stack[-1] is pane
        previous = pane.previous
        self.stack.remove(pane)
        for child in self.stack:
            if child.previous is pane:
                child.previous = previous
        for key, cached in list(self.launchers.items()):
            if cached is pane:
                del self.launchers[key]
        if not active or not self.back.winfo_exists() or not self.tabs.winfo_exists():
            return
        was_visible = self.tabs.select() == str(self.page)
        restore = previous if previous in self.stack else None
        if self.stack:
            self.show(restore or self.stack[-1], activate=False)
        else:
            self.tabs.forget(self.page)
        if not was_visible:
            return
        destination = str(self.page) if restore is not None else pane.origin
        if destination not in self.tabs.tabs():
            return
        self.tabs.select(destination)
        def restore_focus():
            if self.tabs.select() != destination:
                return
            widget = pane.return_focus
            parent_view = str(restore) if restore is not None else destination
            if widget is not None and widget.winfo_exists() and str(widget).startswith(parent_view + "."):
                widget.focus_set()
            elif restore is not None:
                self.back.focus_set()
            else:
                self.tabs.focus_set()
        self.tabs.after_idle(restore_focus)


def open_workspace(parent, title, width, height, minimum=None):
    root = parent.winfo_toplevel()
    host = getattr(root, "_nexus_tools", None)
    if host is not None:
        return host.open(parent, title)
    window = tk.Toplevel(parent)
    window.title(title)
    window.geometry(fit_geometry(window, width, height))
    if minimum is not None:
        window.minsize(*minimum)
    return window, install_cockpit(window).content

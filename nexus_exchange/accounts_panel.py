"""Optional account onboarding on the desktop. Provider secrets never enter a report."""
from datetime import datetime, timezone
import os
import re
from time import time
from tkinter import ttk, simpledialog, messagebox
from . import account_providers as api
from .account_vault import AccountVault
from .consent_callback import listener, receive

LABELS = {"bank": "Bank balance", "docusign": "DocuSign", "sam": "SAM.gov"}


def install(parent, directory, submit, blocked, open_browser):
    vault = AccountVault(directory)
    statuses = {}
    def status(kind):
        try:
            record = vault.load(kind)
            if record is None:
                return "Optional · disconnected"
            if kind == "docusign":
                return "Consent verified" if record["expires"] > time() else "Consent expired · reconnect"
            if kind == "bank":
                if record.get("available") is not None and 0 <= time() - record["as_of"] <= 86400:
                    return "Balance available for planning"
                return "Linked · planning needs one fresh USD available balance"
            return "Key saved · used during searches"
        except (OSError, ValueError, KeyError, TypeError):
            return "Protected record unavailable · reconnect"

    def refresh():
        for kind, label in statuses.items():
            label.configure(text=status(kind))

    def forget(kind):
        if blocked():
            feedback.configure(text="Wait for the current task to finish, or use Emergency halt.")
        elif messagebox.askyesno("Forget " + LABELS[kind], "Remove this connection from this device? You can also revoke access at the provider.", parent=parent):
            try:
                vault.forget(kind)
                feedback.configure(text="Connection removed from this device.")
            except OSError:
                feedback.configure(text="Windows could not remove the saved connection.")
            refresh()

    def ask(label, prompt, **kwargs):
        return simpledialog.askstring(label, prompt, parent=parent, **kwargs)

    def connect(kind):
        if blocked():
            feedback.configure(text="An operation is in progress. Try again when it finishes.")
            return
        if os.name != "nt":
            feedback.configure(text="Protected account setup is available in the Windows application.")
            return
        label = LABELS[kind]
        server = None
        if kind == "bank":
            value = ask(label, "Paste your SimpleFIN Bridge setup token for read-only balances. Share one USD operating account to use a planning ceiling. Provider fees may apply.", show="•")
            if not value:
                return
            def work(stopped):
                record = api.claim_bank(value.strip())
                if stopped():
                    raise PermissionError
                vault.save(kind, record)  # A one-time claim survives a later balance failure.
                from .engagement import read_bank
                read_bank(vault, stopped, datetime.now(timezone.utc))
                return "Bank linked. You can manage or revoke provider access at SimpleFIN."
        elif kind == "sam":
            key = ask(label, "Enter your SAM.gov public API key. Scout uses it for read-only opportunity searches.", show="•")
            if not key:
                return
            key = key.strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{8,256}", key):
                feedback.configure(text="Enter a valid SAM.gov API key.")
                return
            def work(stopped):
                if stopped():
                    raise PermissionError
                vault.save(kind, {"key": key})
                return "SAM.gov key saved for Scout."
        else:
            try:
                existing = vault.load(kind) or {}
            except (OSError, ValueError):
                existing = {}
            client = os.environ.get("NEXUS_DOCUSIGN_CLIENT_ID") or existing.get("client")
            if not client:
                client = ask(label, "Enter the production public integration key registered for Nexus Exchange. Your administrator can supply it. Consent verifies account identity.")
            if not client:
                return
            try:
                url, state, verifier = api.consent(client.strip())
                server = listener(state)
            except (ValueError, OSError):
                feedback.configure(text="Check the integration key and availability of local callback port 54381.")
                return
            def work(stopped):
                with server:
                    code = receive(server, stopped)
                if stopped():
                    raise PermissionError
                record = api.authorize_document(client.strip(), verifier, code)
                if stopped():
                    raise PermissionError
                vault.save(kind, record)
                return "DocuSign confirmed your account. Document sending and signing require separate capabilities."
        def done(message):
            refresh()
            feedback.configure(text=message)
        if submit(work, done):
            feedback.configure(text="Waiting for DocuSign consent in your browser…" if server else "Updating protected account…")
            if server:
                try:
                    opened = open_browser(url)
                except Exception:
                    opened = False
                if not opened:
                    server.denied = True
        elif server:
            server.server_close()

    ttk.Label(parent, text="Accounts", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    ttk.Label(parent, text="Optional connections. Windows protects access on this device.",
              wraplength=480).pack(anchor="w", pady=(2, 3))
    feedback = ttk.Label(parent, wraplength=460, justify="left")
    feedback.pack(anchor="w")
    for kind, label in LABELS.items():
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(5, 1))
        ttk.Label(row, text=label, font=("Segoe UI", 10, "bold")).pack(side="left")
        actions = ttk.Frame(row)
        actions.pack(side="right")
        ttk.Button(actions, text="Connect", command=lambda k=kind: connect(k)).pack(side="left")
        ttk.Button(actions, text="Forget", command=lambda k=kind: forget(k)).pack(side="left", padx=3)
        if kind == "bank":
            ttk.Button(actions, text="Get bank token", command=lambda: open_browser(api.BANK_SIGNUP)).pack(side="left", padx=3)
        statuses[kind] = ttk.Label(parent, wraplength=460)
        statuses[kind].pack(anchor="w")
    refresh()
    return refresh

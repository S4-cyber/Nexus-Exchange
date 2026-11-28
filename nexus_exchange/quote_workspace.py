"""Native, transient review of owner-declared synthetic quotations."""
from copy import deepcopy
from datetime import datetime
import re
import sqlite3

from .operator_drafts import _hash, _json, _stamp, _stored_stamp
from .quote_history import (historical_receipt, publish_receipt, inspect_receipt,
                            MAX_RECEIPT_BYTES, MAX_INDEX_RECEIPTS)
from .quote_comparison import MAX_QUOTES, MAX_CENTS, _FLAGS, compare_quotes
from .correspondence_workspace import CorrespondenceWorkspace

TERM_FIELDS = (
    ("lines", "Extended line totals (USD cents, comma-separated)"),
    ("tax", "Tax (cents)"), ("shipping", "Shipping (cents)"),
    ("fees", "Other fees (cents)"), ("delivery", "Delivery days"),
    ("payment", "Payment days"), ("valid", "Valid until (ISO time with offset)"),
)


def parse_terms(raw, count):
    if type(raw) is not dict or set(raw) != {k for k, _ in TERM_FIELDS}:
        raise ValueError("exact quotation terms required")
    if any(type(v) is not str or not 1 <= len(v) <= 256 for v in raw.values()):
        raise ValueError("bounded quotation fields required")

    def number(value, maximum):
        if re.fullmatch(r"[0-9]{1,14}", value.strip()) is None:
            raise ValueError("explicit nonnegative integer required")
        result = int(value)
        if result > maximum:
            raise ValueError("quotation field out of bounds")
        return result

    lines = [number(v, MAX_CENTS) for v in raw["lines"].split(",")]
    if len(lines) != count:
        raise ValueError("one extended total per RFQ line required")
    result = dict(currency="USD", line_totals_cents=lines,
                  tax_cents=number(raw["tax"], MAX_CENTS),
                  shipping_cents=number(raw["shipping"], MAX_CENTS),
                  fees_cents=number(raw["fees"], MAX_CENTS),
                  delivery_days=number(raw["delivery"], 3650),
                  payment_days=number(raw["payment"], 3650),
                  valid_until=_stamp(datetime.fromisoformat(raw["valid"])))
    total = sum(lines) + sum(result[k] for k in ("tax_cents", "shipping_cents", "fees_cents"))
    if not 1 <= total <= MAX_CENTS:
        raise ValueError("bounded positive total required")
    return result


class QuoteReview:
    """Stage declarations; only explicit historical file export may persist a review."""
    def __init__(self, workspace):
        self.workspace = workspace
        self._staged = []
        self._last_result = None

    def clear(self):
        self._staged.clear()
        self._last_result = None

    def _scoped_correspondence(self, draft_id, fields):
        self.workspace._permit()
        _hash(draft_id)
        draft = self.workspace.history(draft_id)["draft"]
        request = draft["request"]
        if "supplier_profile_sha256" not in request:
            raise ValueError("scoped draft required")
        correspondence = CorrespondenceWorkspace(self.workspace, draft, fields)
        # Rebuild the exact draft through the trusted runtime, rather than
        # waiting until comparison to discover a superseded declaration.
        current = self.workspace._draft(self.workspace._call(
            "prepare", supplier=correspondence.supplier,
            region=request["region"], items=request["items"]))
        if current != draft:
            raise ValueError("draft scope changed; refresh the selected draft")
        self.workspace._permit()
        return draft, correspondence

    def recipient_options(self, draft_id, fields):
        """Bounded historical IDs for the exact current draft; no verification."""
        _, correspondence = self._scoped_correspondence(draft_id, fields)
        result = correspondence.history()
        self.workspace._permit()
        return dict(draft_id=draft_id,
                    recipient_ids=tuple(r["candidate"]["recipient_id"] for r in result["rows"]),
                    truncated=result["truncated"])

    def stage(self, draft_id, recipient_id, fields, raw):
        self.workspace._permit()
        _hash(recipient_id)
        if len(self._staged) >= MAX_QUOTES:
            raise ValueError("quotation review capacity reached")
        draft, correspondence = self._scoped_correspondence(draft_id, fields)
        terms = parse_terms(raw, len(draft["request"]["items"]))
        records = correspondence.history()["rows"]
        matches = [r for r in records if r["candidate"]["recipient_id"] == recipient_id]
        if len(matches) != 1:
            raise ValueError("inspect a saved recipient within the selected draft")
        record = matches[0]
        thread = correspondence.thread(record)
        if thread is None or not thread["events"] or thread["events"][-1]["kind"] != "SIMULATED_REPLY":
            raise ValueError("latest simulated reply required")
        declaration = dict(terms, expected_head=thread["head_sha256"],
                           evidence_reference=thread["events"][-1]["evidence_reference"])
        if any(s["draft"]["request"]["supplier"] == draft["request"]["supplier"]
               or s["declaration"]["evidence_reference"] == declaration["evidence_reference"]
               for _, s in self._staged):
            raise ValueError("duplicate supplier or evidence; clear and restage")
        entry = dict(draft_id=draft_id, recipient_id=recipient_id,
                     supplier=correspondence.supplier, declaration=declaration)
        snapshot = dict(draft=draft, recipient=record["candidate"], thread=thread,
                        declaration=declaration)
        self.workspace._permit()
        self._staged.append(deepcopy((entry, snapshot)))
        self._last_result = None

    def summary(self):
        self.workspace._permit()
        return "\n\n".join(
            s["draft"]["request"]["supplier"]["identifier"] + "\nDraft: " + e["draft_id"]
            + "\nRecipient: " + e["recipient_id"] + "\nReply: " + e["declaration"]["expected_head"]
            + "\nReply evidence: " + e["declaration"]["evidence_reference"]
            + "\nExtended line totals (cents): " + str(e["declaration"]["line_totals_cents"])
            + "\nTax/shipping/fees (cents): " + "/".join(str(e["declaration"][k]) for k in
                ("tax_cents", "shipping_cents", "fees_cents"))
            + "\nDelivery/payment days: " + str(e["declaration"]["delivery_days"]) + "/"
            + str(e["declaration"]["payment_days"]) + "\nValid until: " + e["declaration"]["valid_until"]
            for e, s in self._staged)

    def compare(self, *, confirmed=None):
        self._last_result = None
        result = self._compare(confirmed=confirmed)
        self._last_result = deepcopy(result)
        return result

    def _compare(self, *, confirmed=None):
        self.workspace._permit()
        if confirmed is not True:
            raise PermissionError("explicit local comparison confirmation required")
        if len(self._staged) < 2:
            raise ValueError("at least two staged quotations required")
        entries = [deepcopy(e) for e, _ in self._staged]
        result = self.workspace.action("quote_compare", self.workspace.plan_id,
                                       entries=entries, confirmed=True)
        self.workspace._permit()
        if (type(result) is not dict or result.get("plan_id") != self.workspace.plan_id
                or any(result.get(k) is not False for k in _FLAGS)):
            raise ValueError("quotation review authority mismatch")
        now = datetime.fromisoformat(_stored_stamp(result.get("compared_at")))
        expected = compare_quotes([s for _, s in self._staged], now=now, halted=False)
        if _json(result) != _json(expected):
            raise ValueError("comparison differs from staged evidence; clear and restage")
        self.workspace._permit()
        return expected

    def inspect_history_files(self, paths):
        """Read explicit bounded local receipts for this saved plan only.

        Historical metadata is never used to stage terms or revalidate a supplier.
        Different RFQ scopes stay distinct. Invalidate the export pin so a
        historical display cannot be mistaken for a currently reviewed result.
        """
        from .deliverable_files import _read_local_file
        from .digital_deliverable import JSON_SOURCE

        self._last_result = None
        self.workspace._permit()
        if type(paths) not in (list, tuple) or not 1 <= len(paths) <= MAX_INDEX_RECEIPTS:
            raise ValueError("select one to sixty-four local review files")
        plan = _hash(self.workspace.plan_id)
        matches = {}
        for path in paths:
            self.workspace._permit()
            raw = _read_local_file(path, JSON_SOURCE, MAX_RECEIPT_BYTES,
                                   False, self.workspace.blocked_check)
            self.workspace._permit()
            item = inspect_receipt(raw)
            if item["plan_id"] != plan:
                raise ValueError("historical receipt outside selected saved plan")
            matches[item["receipt_sha256"]] = item
        self.workspace._permit()
        if self.workspace.plan_id != plan:
            raise ValueError("selected plan changed")
        return sorted(matches.values(),
                      key=lambda row: (row["rechecked_at"], row["receipt_sha256"]),
                      reverse=True)

    def history_pin(self):
        self.workspace._permit()
        if self._last_result is None:
            raise ValueError("compare staged quotations first")
        return self._last_result["comparison_sha256"]

    def export_history(self, path, *, expected_comparison, confirmed=None):
        """Export the previously reviewed result only after fresh scope checks."""
        self.workspace._permit()
        if confirmed is not True:
            raise PermissionError("explicit local history export required")
        if self.history_pin() != _hash(expected_comparison):
            raise ValueError("review changed; compare again")
        reviewed = deepcopy(self._last_result)
        try:
            current = self._compare(confirmed=True)
            receipt = historical_receipt(reviewed, current)
            if self.history_pin() != expected_comparison:
                raise ValueError("review changed; compare again")
            return publish_receipt(path, receipt, permit=self.workspace._permit)
        except BaseException:
            self._last_result = None
            raise


def mount_quote_review(parent, workspace, selected_draft, supplier_fields):
    """Inline tab; result and staged data cleared by the parent halt monitor."""
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    from tkinter.scrolledtext import ScrolledText

    review = QuoteReview(workspace)
    ttk.Label(parent, text="Synthetic local comparison only. Select a saved draft in History, "
              "reenter its supplier declaration above, and load saved recipients. "
              "Choose a local recipient; the latest simulated reply is loaded locally. Terms are unverified.",
              wraplength=950).pack(anchor="w", padx=5, pady=3)
    form = ttk.Frame(parent)
    form.pack(fill="x", padx=5)
    fields = {k: tk.StringVar(master=parent) for k, _ in (("recipient", "Saved recipient ID"), *TERM_FIELDS)}
    ttk.Label(form, text="Saved recipient ID").grid(row=0, column=0, sticky="w", pady=1)
    picker = ttk.Combobox(form, textvariable=fields["recipient"], width=68,
                          state="readonly", values=())
    picker.grid(row=0, column=1, sticky="ew", padx=4)
    loaded = None
    for i, (key, label) in enumerate(TERM_FIELDS, start=1):
        ttk.Label(form, text=label).grid(row=i, column=0, sticky="w", pady=1)
        ttk.Entry(form, textvariable=fields[key], width=68).grid(row=i, column=1, sticky="ew", padx=4)
    form.columnconfigure(1, weight=1)
    status = ttk.Label(parent, text="Stage at least two declarations; nothing is sent. History export is optional.", wraplength=950)
    status.pack(fill="x", padx=5)
    output = ScrolledText(parent, height=8, wrap="word", state="disabled")
    output.pack(fill="both", expand=True, padx=5, pady=3)

    def write(text):
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("end", text)
        output.configure(state="disabled")

    def reset_picker():
        nonlocal loaded
        loaded = None
        fields["recipient"].set("")
        picker.configure(values=())

    def clear():
        review.clear()
        reset_picker()
        for key, _ in TERM_FIELDS:
            fields[key].set("")
        write("")
        status.configure(text="Staged quotations cleared. Select and stage again.")

    def error(exc):
        write("")
        status.configure(text="Review unavailable; check scope and declarations. (" + type(exc).__name__ + ")")
        if workspace.blocked_check() is not False:
            clear()

    def load_recipients():
        nonlocal loaded
        reset_picker()
        try:
            draft_id = selected_draft()
            declared = supplier_fields()
            result = review.recipient_options(draft_id, declared)
            if selected_draft() != draft_id or supplier_fields() != declared:
                raise ValueError("selected draft or declaration changed")
            ids = result["recipient_ids"]
            loaded = (draft_id, deepcopy(declared), ids)
            picker.configure(values=ids)
            if len(ids) == 1:
                fields["recipient"].set(ids[0])
            write(review.summary())
            status.configure(text=f"{len(ids)} local recipient declarations"
                             + (" (truncated)" if result["truncated"] else "")
                             + ". Select an ID and enter declared terms.")
        except (ValueError, PermissionError, OSError, sqlite3.Error, RuntimeError) as exc:
            reset_picker()
            error(exc)

    def stage():
        try:
            draft_id, declared = selected_draft(), supplier_fields()
            recipient_id = fields["recipient"].get()
            if (loaded is None or loaded[:2] != (draft_id, declared)
                    or recipient_id not in loaded[2]):
                raise ValueError("load recipients for the current draft and declaration")
            review.stage(draft_id, recipient_id, declared,
                         {k: fields[k].get() for k, _ in TERM_FIELDS})
            write(review.summary())
            status.configure(text="Staged locally. Select another saved draft or compare.")
        except (ValueError, PermissionError, OSError, sqlite3.Error, RuntimeError) as exc:
            error(exc)

    def compare():
        try:
            summary = review.summary()
            if not summary:
                raise ValueError("stage declarations first")
            write(summary)
            if not messagebox.askyesno("Local synthetic comparison",
                    "Compare the staged declarations? This does not select a supplier or authorize any action.",
                    parent=parent):
                return
            if review.summary() != summary:
                raise ValueError("staged declarations changed")
            result = review.compare(confirmed=True)
            lines = ["SIMULATION ONLY — DECLARED TERMS NOT VERIFIED", result["status"],
                     "Comparison: " + result["comparison_sha256"]]
            for row in result["rows"]:
                lines.append(row["supplier"]["identifier"] + " | USD cents: " + str(row["total_cents"])
                             + " | delivery/payment days: " + str(row["delivery_days"]) + "/"
                             + str(row["payment_days"]))
            if result["equal_declared_timing"]:
                lines.append("Lowest declared total (USD cents): "
                             + str(result["lowest_declared_total_cents"]))
                lines.append("Number tied at lowest declared cost: "
                             + str(len(result["lowest_declared_cost_ids"])))
            else:
                lines.append("Cost ranking withheld: different declared delivery or payment timing.")
            lines.append("No supplier selected. No external authority.")
            write("\n".join(lines) + "\n\n" + summary)
            status.configure(text="Read-only comparison; optionally export a historical review file.")
        except (ValueError, PermissionError, OSError, sqlite3.Error, RuntimeError) as exc:
            error(exc)

    def export_history():
        try:
            pin = review.history_pin()
            path = filedialog.asksaveasfilename(parent=parent, defaultextension=".json",
                filetypes=[("Historical quotation review", "*.json")],
                title="Save a new local historical review file")
            if not path:
                return
            if not messagebox.askyesno("Historical review only",
                    "Save this reviewed comparison after rechecking current evidence? "
                    "The file is historical, not a current decision or authority.", parent=parent):
                return
            digest = review.export_history(path, expected_comparison=pin, confirmed=True)
            status.configure(text="Historical review file saved. SHA-256: " + digest)
        except (ValueError, PermissionError, OSError, sqlite3.Error, RuntimeError) as exc:
            error(exc)

    def inspect_history():
        try:
            workspace._permit()
            paths = filedialog.askopenfilenames(parent=parent,
                filetypes=[("Historical quotation review", "*.json")],
                title="Inspect selected local historical review files")
            if not paths:
                return
            rows = review.inspect_history_files(paths)
            lines = ["HISTORICAL ONLY — NOT REVALIDATED OR AUTHENTICATED",
                     "Different RFQ scopes are not comparable. No external authority."]
            for row in rows:
                total = row["lowest_declared_total_cents"]
                lines.extend(["", "Receipt: " + row["receipt_sha256"],
                              "RFQ scope: " + row["scope_sha256"],
                              "Compared: " + row["compared_at"],
                              "Rechecked: " + row["rechecked_at"],
                              "Declared quotations: " + str(row["quote_count"]),
                              "Lowest declared USD cents: " +
                              (str(total) if total is not None else "Ranking withheld")])
            workspace._permit()
            write("\n".join(lines))
            status.configure(text=f"{len(rows)} distinct historical reviews; no current decision.")
        except (ValueError, PermissionError, OSError, sqlite3.Error, RuntimeError) as exc:
            error(exc)

    buttons = ttk.Frame(parent)
    buttons.pack(fill="x", padx=5)
    for label, callback in (("Load saved recipients", load_recipients),
                            ("Stage selected draft", stage), ("Compare staged", compare),
                            ("Save review file", export_history),
                            ("Clear review", clear)):
        ttk.Button(buttons, text=label, command=callback).pack(side="left", padx=3)
    ttk.Button(parent, text="Inspect historical review files",
               command=inspect_history).pack(anchor="w", padx=5, pady=2)
    return clear

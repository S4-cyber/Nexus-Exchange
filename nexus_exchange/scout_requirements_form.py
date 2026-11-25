"""Explicit, read-only native Scout requirements review; no action authority."""
import re


_FIELDS = (
    "capability_id", "input_format", "input_bytes", "max_cell_chars",
    "preserve_all_fields", "requires_deduplication", "requires_inference", "requires_formulas",
    "input_sha256", "columns", "key_column", "expected_rows",
    "right_input_bytes", "right_input_sha256", "right_expected_rows",
)
_FLAGS = _FIELDS[4:8]
_SPEC = _FIELDS[8:12]
_RIGHT = _FIELDS[12:]


def declaration_from_fields(fields):
    """Translate explicit form text only; the existing backend validates actual fit."""
    if type(fields) is not dict or set(fields) != set(_FIELDS):
        raise ValueError("Complete form fields required.")
    if any(type(v) is not str or len(v) > 2048 for v in fields.values()):
        raise ValueError("Form fields must be bounded text.")
    values = {k: v.strip() for k, v in fields.items()}
    if not values["capability_id"] or not values["input_format"]:
        raise ValueError("Select a service and input format.")

    def number(key):
        value = values[key]
        if not value:
            return None
        if not re.fullmatch(r"[0-9]{1,10}", value) or int(value) > 10**9:
            raise ValueError("Use whole numbers up to one billion, or leave unknown sizes blank.")
        return int(value)

    if any(values[k] not in ("Yes", "No") for k in _FLAGS):
        raise ValueError("Answer every requirement question explicitly.")
    reconcile = values["capability_id"] == "csv_key_reconciliation_v1"
    if not reconcile and any(values[k] for k in _RIGHT):
        raise ValueError("Clear second-input fields for single-input services.")
    spec_keys = _SPEC + (_RIGHT[1:] if reconcile else ())
    spec = None
    if any(values[k] for k in spec_keys):
        if not all(values[k] for k in spec_keys):
            raise ValueError("Complete the declared schema, or leave all schema fields blank.")
        spec = dict(input_sha256=values["input_sha256"],
                    columns=[c.strip() for c in values["columns"].split(",")],
                    key_column=values["key_column"], expected_rows=number("expected_rows"))
        if reconcile:
            spec.update(right_input_sha256=values["right_input_sha256"],
                        right_expected_rows=number("right_expected_rows"))
    result = dict(capability_id=values["capability_id"], input_format=values["input_format"],
                  input_bytes=number("input_bytes"), max_cell_chars=number("max_cell_chars"),
                  specification=spec, **{k: values[k] == "Yes" for k in _FLAGS})
    if reconcile:
        result["right_input_bytes"] = number("right_input_bytes")
    return result


def open_service_requirements_window(parent, workspace, context, title, *, smoke=False):
    """Pin one selected observation; refresh its backend review on every evaluation."""
    import sqlite3
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText
    from .cockpit import install_cockpit, fit_geometry
    from .operator_capabilities import CSV_ID, JSON_ID, PROFILE_ID, RECONCILE_ID
    from .service_handoff import review_scope

    workspace.resolve(context)
    context = dict(context)
    window = tk.Toplevel(parent)
    content = install_cockpit(window).content
    window.title("Nexus Exchange | Scout service requirements")
    window.geometry(fit_geometry(window, 1060, 740))
    ttk.Label(content, text="SCOUT — Local service requirements", font=("Segoe UI", 18)).pack(pady=6)
    ttk.Label(content, text=title, wraplength=900).pack(padx=12)
    ttk.Label(content, text="Declare known requirements only. Leave unknown sizes blank. Complete all schema fields or leave them blank. Review never grants execution or external authority.", wraplength=900).pack(padx=12, pady=5)
    panel = ttk.Frame(content)
    panel.pack(fill="x", padx=12, pady=5)
    panel.columnconfigure(1, weight=1)
    panel.columnconfigure(3, weight=1)
    services = {"CSV standardization": CSV_ID, "JSON to CSV": JSON_ID,
                "CSV quality report": PROFILE_ID, "Two-file reconciliation": RECONCILE_ID}
    labels = ("Service", "Input format", "Input bytes", "Maximum cell characters",
              "Preserve all fields?", "Deduplication required?", "Inference required?", "Formulas required?",
              "Input SHA-256", "Columns (comma-separated)", "Unique key column", "Expected rows",
              "Second input bytes", "Second input SHA-256", "Second input rows")
    variables = {}
    for i, (key, label) in enumerate(zip(_FIELDS, labels)):
        row, col = divmod(i, 2)
        col *= 2
        ttk.Label(panel, text=label).grid(row=row, column=col, sticky="w", padx=3, pady=3)
        var = variables[key] = tk.StringVar(master=window, value="")
        choices = (tuple(services) if key == "capability_id" else
                   ("UTF8_CSV", "UTF8_JSON_RECORDS", "OTHER") if key == "input_format" else
                   ("Yes", "No") if key in _FLAGS else None)
        if choices is not None:
            widget = ttk.Combobox(panel, textvariable=var, values=choices, state="readonly", width=22)
        else:
            widget = ttk.Entry(panel, textvariable=var, width=24)
        widget.grid(row=row, column=col+1, sticky="ew", padx=3, pady=3)
    ttk.Label(content, text="Second-input fields are only for reconciliation. Fingerprints are declarations, not verified files.", wraplength=900).pack(padx=12)
    output = ScrolledText(content, height=11, wrap="word", state="disabled")
    output.pack(fill="both", expand=True, padx=12, pady=6)

    def write(text):
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("end", text)
        output.configure(state="disabled")

    def evaluate():
        write("")
        try:
            fields = {k: v.get() for k, v in variables.items()}
            fields["capability_id"] = services.get(fields["capability_id"], "")
            declaration = declaration_from_fields(fields)
        except ValueError as exc:
            write(str(exc))
            return None
        try:
            review = workspace.review_requirements(context, declaration)
        except (ValueError, PermissionError, OSError, sqlite3.Error):
            write("Review unavailable. Check the selected observation, current profile and halt state; reopen from a refreshed Matrix if needed.")
            return None
        assessment = review["requirements_assessment"]
        write("DECLARED STRUCTURE ONLY — NO EXECUTION OR AUTHORITY\n"
              + "State: " + review["state"] + "\n"
              + "Source hold: " + (review["source_hold"] or "None reported") + "\n"
              + "Source blockers: " + (", ".join(review["source_blockers"]) or "None reported") + "\n"
              + "Requirement reasons: " + (", ".join(assessment["reasons"]) or "None reported") + "\n"
              + "Evaluated UTC: " + review["evaluated_at"] + "\n"
              + "Review fingerprint: " + review["review_sha256"] + "\n"
              + "Local sample scope pin: " + review_scope(review) + "\n"
              + "Source bytes, permission, actual buyer requirements and commercial facts remain unverified.")
        return review

    for var in variables.values():
        var.trace_add("write", lambda *_: write("Fields changed. Review again."))
    ttk.Button(content, text="Review declared requirements", command=evaluate).pack(pady=4)
    timer = None

    def guard():
        nonlocal timer
        if workspace.halt_check() is not False:
            window.destroy()
            return
        timer = window.after(350, guard)

    def destroyed(event):
        if event.widget is window and timer is not None:
            try:
                window.after_cancel(timer)
            except tk.TclError:
                pass

    window.bind("<Destroy>", destroyed, add="+")
    guard()
    if smoke:
        variables["capability_id"].set("CSV standardization")
        variables["input_format"].set("UTF8_CSV")
        for key in _FLAGS:
            variables[key].set("Yes" if key == "preserve_all_fields" else "No")
        review = evaluate()
        if (review is None or review["state"] != "SOURCE_HELD" or review["external_authority"]
                or "NO EXECUTION OR AUTHORITY" not in output.get("1.0", "end")):
            raise RuntimeError("Scout requirements GUI lost source hold or boundary")
        variables["input_bytes"].set("200")
        if "Fields changed" not in output.get("1.0", "end"):
            raise RuntimeError("Scout requirements GUI retained stale review")
    return window

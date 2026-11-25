"""Explicit native Scout requirements review and local-only sample preview."""
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


def open_service_requirements_window(parent, workspace, context, title, *, plan_id=None,
                                     sample_action=None, blocked_check=None, smoke=False,
                                     smoke_sample=None):
    """Pin one selected observation; refresh its backend review on every evaluation."""
    import sqlite3
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from tkinter.scrolledtext import ScrolledText
    from .cockpit import install_cockpit, fit_geometry
    from .operator_capabilities import CSV_ID, JSON_ID, PROFILE_ID, RECONCILE_ID
    from .service_handoff import review_scope
    from .csv_workspace import preview_text
    from .digital_deliverable import _source_contract_format
    from .service_handoff import checked_review_route

    workspace.resolve(context)
    context = dict(context)
    window = tk.Toplevel(parent)
    content = install_cockpit(window).content
    window.title("Nexus Exchange | Scout service requirements")
    window.geometry(fit_geometry(window, 1060, 740))
    ttk.Label(content, text="SCOUT — Local service requirements", font=("Segoe UI", 18)).pack(pady=6)
    ttk.Label(content, text=title, wraplength=900).pack(padx=12)
    ttk.Label(content, text="Selected saved plan: " + (plan_id or "None — save a plan and refresh Matrix"), wraplength=900).pack(padx=12)
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

    reviewed = None

    def invalidate(message):
        nonlocal reviewed
        reviewed = None
        sample_button.configure(state="disabled")
        write(message)

    def available():
        return (plan_id is not None and callable(sample_action) and callable(blocked_check)
                and blocked_check() is False and workspace.halt_check() is False)

    def evaluate():
        nonlocal reviewed
        invalidate("")
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
        if available() and review["state"] == "DECLARED_STRUCTURE_FITS":
            # Keep the exact declaration and the stable fresh-review pin;
            # do not treat the earlier snapshot as current authority.
            reviewed = (declaration, review_scope(review), review)
            sample_button.configure(state="normal")
        return review

    def produce_sample(selected, source_path, right_path, confirmed):
        if selected is None or selected is not reviewed or not available() or confirmed is not True:
            invalidate("Review changed or local preview not confirmed. Review again.")
            return None
        declaration, pin, review = selected
        invalidate("Checking exact reviewed local inputs...")
        try:
            source, operation = checked_review_route(review, pin, context)
            result = sample_action("scoped_preview", plan_id, context=context, requirements=declaration,
                expected_scope=pin, source_path=source_path, right_source_path=right_path, confirmed=True)
            if not available() or type(result) is not dict or set(result) != {
                    "review_scope_sha256", "sample", "external_authority"}:
                raise ValueError("Invalid scoped preview result.")
            sample = result["sample"]
            if (result["external_authority"] is not False or result["review_scope_sha256"] != pin
                    or sample["contract"]["plan_id"] != plan_id
                    or sample["contract"]["context"] != context
                    or sample["contract"]["format"] != _source_contract_format(source,operation)
                    or sample["contract"]["specification"] != review["requirements_assessment"]["declared_input"]["specification"]):
                raise ValueError("Scoped preview mismatch.")
            text = preview_text(sample).replace(" (full artifact on explicit export)", " (preview only; export unavailable here)")
            write("EXACT SCOUT SCOPE — TRANSIENT LOCAL SAMPLE\nScope: " + pin + "\n" + text
                  + "\nNo export, registration, customer acceptance or revenue. Review again to produce another sample.")
            return result
        except (ValueError, PermissionError, OSError, sqlite3.Error, RuntimeError, KeyError, TypeError):
            invalidate("Local sample unavailable or changed. Check requirements, selected files, saved plan and halt state; review again.")
            return None

    def choose_sample():
        selected = reviewed
        if selected is None or not available():
            invalidate("Local preview unavailable. Review again.")
            return
        declaration, _, _ = selected
        is_json = declaration["input_format"] == "UTF8_JSON_RECORDS"
        source_path = filedialog.askopenfilename(parent=window,
            filetypes=[("JSON","*.json")] if is_json else [("CSV","*.csv")])
        if not source_path:
            return
        right_path = None
        if declaration["capability_id"] == RECONCILE_ID:
            right_path = filedialog.askopenfilename(parent=window,title="Select right CSV",filetypes=[("CSV","*.csv")])
            if not right_path:
                return
        if selected is not reviewed or not available():
            invalidate("Review changed while selecting files. Review again.")
            return
        confirmed = messagebox.askyesno("Produce scoped local work sample",
            "Confirm you are authorized to process these selected local files. Match exact reviewed sizes, fingerprints and schema; preview only, no export or external action?",
            parent=window)
        if confirmed:
            produce_sample(selected, source_path, right_path, confirmed)

    bar = ttk.Frame(content)
    bar.pack(pady=4)
    ttk.Button(bar, text="Review declared requirements", command=evaluate).pack(side="left",padx=4)
    sample_button = ttk.Button(bar,text="Preview exact local sample",command=choose_sample,state="disabled")
    sample_button.pack(side="left",padx=4)
    for var in variables.values():
        var.trace_add("write", lambda *_: invalidate("Fields changed. Review again."))
    timer = None

    def guard():
        nonlocal timer
        if workspace.halt_check() is not False:
            window.destroy()
            return
        if callable(blocked_check) and blocked_check() is not False:
            invalidate("Operator busy or halted. Review again when ready.")
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
                or str(sample_button.cget("state")) != "disabled"
                or "NO EXECUTION OR AUTHORITY" not in output.get("1.0", "end")):
            raise RuntimeError("Scout requirements GUI lost source hold or boundary")
        variables["input_bytes"].set("200")
        if "Fields changed" not in output.get("1.0", "end"):
            raise RuntimeError("Scout requirements GUI retained stale review")
    if smoke_sample is not None:
        path,size,digest,expected=smoke_sample
        for key,value in dict(capability_id="CSV standardization",input_format="UTF8_CSV",
                input_bytes=str(size),max_cell_chars="30",preserve_all_fields="Yes",
                requires_deduplication="No",requires_inference="No",requires_formulas="No",
                input_sha256=digest,columns="id,name",key_column="id",expected_rows="2").items():
            variables[key].set(value)
        review=evaluate()
        if (review is None or reviewed is None or str(sample_button.cget("state"))!="normal"):
            raise RuntimeError("Scoped sample GUI did not enable current compatible review")
        result=produce_sample(reviewed,path,None,True)
        if (result is None or result["sample"]["artifact"]!=expected
                or "EXACT SCOUT SCOPE" not in output.get("1.0","end")
                or str(sample_button.cget("state"))!="disabled"):
            raise RuntimeError("Scoped sample GUI did not produce and consume exact preview")
        variables["expected_rows"].set("1")
        if "Fields changed" not in output.get("1.0","end"):
            raise RuntimeError("Scoped sample GUI retained stale preview")
    return window

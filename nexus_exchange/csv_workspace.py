"""Native saved-plan CSV work sample preview and explicit new-file export."""
from copy import deepcopy
import csv
import io
import re
import sqlite3

from .checklist_store import _hash
from .digital_deliverable import _spec, _source_contract_format, CSV_SOURCE, JSON_SOURCE, JSON_FORMAT, PROFILE_FORMAT, RECONCILE_FORMAT
from .deliverable_files import preview_pins
from .obligation_workspace import validate_record, open_obligation_window
from .operator_workflow import preview_progress, export_progress, historical_progress, template_text, progress_text


def parse_fields(columns,key,rows):
    if (type(columns) is not str or len(columns)>700 or type(key) is not str
            or type(rows) is not str or not re.fullmatch(r"[0-9]{1,4}",rows)):
        raise ValueError("invalid bounded CSV requirements")
    spec=_spec(dict(input_sha256="0"*64,columns=[c.strip() for c in columns.split(",")],
                    key_column=key.strip(),expected_rows=int(rows)))
    return {k:spec[k] for k in ("columns","key_column","expected_rows")}


class CsvWorkspace:
    def __init__(self,plan_id,*,action,blocked_check,source_format=CSV_SOURCE,operation="PRESERVE"):
        self.plan_id=_hash(plan_id)
        self.source_format=source_format
        self.operation=operation
        self.contract_format=_source_contract_format(source_format,operation)
        if not callable(action) or not callable(blocked_check):
            raise ValueError("trusted desktop callbacks required")
        self.action=action
        self.blocked_check=blocked_check
        self.clear()

    def clear(self):
        self._pins=None
        self._inputs=None
        self._reviewed=None
        self._progress=None

    def _permit(self):
        if self.blocked_check() is not False:
            self.clear()
            raise PermissionError("CSV workspace halted or busy")

    def preview(self,source_path,columns,key,rows,*,right_source_path=None,right_rows=None):
        self.clear()
        self._permit()
        inputs=dict(source_path=source_path,**parse_fields(columns,key,rows))
        if self.operation=="RECONCILE":
            second=parse_fields(columns,key,right_rows)
            inputs.update(right_source_path=right_source_path,right_expected_rows=second["expected_rows"])
        elif right_source_path is not None or right_rows is not None:
            raise ValueError("unexpected second input")
        if self.source_format!=CSV_SOURCE:
            inputs["source_format"]=self.source_format
        if self.operation!="PRESERVE":
            inputs["operation"]=self.operation
        result=self.action("preview",self.plan_id,confirmed=True,**inputs)
        self._permit()
        pins=preview_pins(result)
        if (result["contract"]["plan_id"]!=self.plan_id or
                result["contract"]["format"]!=self.contract_format):
            raise ValueError("CSV preview outside selected plan")
        progress=preview_progress(result,halted=False)
        self._permit()
        self._pins=pins
        self._inputs=inputs
        self._reviewed=deepcopy(result)
        self._progress=progress
        return result

    @property
    def ready(self):
        return self._pins is not None

    @property
    def progress(self):
        self._permit()
        return deepcopy(self._progress)

    def export(self,destination,*,confirmed=None):
        self._permit()
        if confirmed is not True or not self.ready:
            raise PermissionError("explicit export of a current preview required")
        pins,inputs=self._pins,self._inputs
        reviewed=self._reviewed
        # Consume preview even if export fails; a second export requires review.
        self.clear()
        result=self.action("export",self.plan_id,confirmed=True,
                           destination_path=destination,**inputs,**pins)
        self._permit()
        if (type(result) is not dict or result.get("exported") is not True
                or result.get("external_authority") is not False
                or result.get("buyer_accepted") is not False
                or any(result.get(k)!=v for k,v in pins.items())):
            raise ValueError("CSV export result mismatch")
        progress=export_progress(reviewed,result,halted=False)
        self._permit()
        self._progress=progress
        return result

    def register(self,artifact_path,*,confirmed=None):
        self._permit()
        if confirmed is not True or not self.ready:
            raise PermissionError("explicit registration of a current preview required")
        pins,inputs=self._pins,self._inputs
        self.clear()
        result=self.action("register",self.plan_id,confirmed=True,
                           artifact_path=artifact_path,**inputs,**pins)
        self._permit()
        record=validate_record(result,self.plan_id)
        binding=record["binding"]
        if (binding["contract"]["contract_sha256"]!=pins["expected_contract"]
                or binding["qa_report"]["report_sha256"]!=pins["expected_report"]
                or binding["qa_report"]["artifact_sha256"]!=pins["expected_artifact"]):
            raise ValueError("registered obligation differs from reviewed preview")
        progress=historical_progress(record,self.plan_id,halted=False)
        self._permit()
        self._progress=progress
        return record


def preview_text(result):
    pins=preview_pins(result)
    report=result["report"]
    reader=csv.reader(io.StringIO(result["artifact"].decode("utf-8"),newline=""))
    reconcile=result["contract"]["format"]==RECONCILE_FORMAT
    input_rows=str(result["contract"]["specification"]["expected_rows"])
    if reconcile:
        input_rows+=" left / "+str(result["contract"]["specification"]["right_expected_rows"])+" right"
    lines=["LOCAL WORK SAMPLE — not customer acceptance or commercial authority",
           "Source: "+("flat JSON string records" if result["contract"]["format"]==JSON_FORMAT else "CSV"),
           "Service: "+("Two-file key reconciliation (key and flags only)" if reconcile else "Column quality profile (aggregate statistics)" if result["contract"]["format"]==PROFILE_FORMAT else "Field-preserving CSV output"),
           "Input rows: "+input_rows+" | output rows: "+str(report["rows"])+" | bytes: "+str(report["artifact_bytes"]),
           "Contract: "+pins["expected_contract"],"Artifact: "+pins["expected_artifact"],
           "QA: "+", ".join(report["checks"]),"",
           "Preview: header and up to 10 data rows (full artifact on explicit export)"]
    for index,row in enumerate(reader):
        if index>10:
            break
        lines.append(" | ".join(row))
    lines.extend(["",progress_text(preview_progress(result,halted=False))])
    return "\n".join(lines)


def open_csv_window(parent,*,plan_id,action,blocked_check,smoke_paths=None,smoke_evidence=None,
                    source_format=CSV_SOURCE,operation="PRESERVE"):
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
    from tkinter.scrolledtext import ScrolledText

    workspace=CsvWorkspace(plan_id,action=action,blocked_check=blocked_check,source_format=source_format,operation=operation)
    reconcile_mode=operation=="RECONCILE"
    profile_mode=operation=="COLUMN_PROFILE"
    json_source=source_format==JSON_SOURCE
    from .cockpit import install_cockpit, fit_geometry
    window=tk.Toplevel(parent)
    content=install_cockpit(window).content
    window.title("Nexus Exchange | Operator CSV reconciliation" if reconcile_mode else "Nexus Exchange | Operator CSV quality report" if profile_mode else "Nexus Exchange | Operator JSON-to-CSV" if json_source else "Nexus Exchange | Operator CSV deliverable")
    window.geometry(fit_geometry(window,1000,650))
    ttk.Label(content,text="OPERATOR — CSV reconciliation" if reconcile_mode else "OPERATOR — CSV column quality report" if profile_mode else "OPERATOR — JSON-to-CSV work sample" if json_source else "OPERATOR — Local CSV work sample",font=("Segoe UI",18)).pack(pady=8)
    ttk.Label(content,text="Saved plan: "+plan_id,wraplength=950).pack()
    ttk.Label(content,text=("Choose left and right UTF-8 CSV files with identical declared columns and unique keys. Compare exact strings; report keys, record status and changed columns, never non-key values. Combined row limit 2000. No source changes." if reconcile_mode else "Select UTF-8 CSV and declare its exact input columns, unique key and row count. Produce aggregate empty, whitespace, nonblank, distinct and length counts per column; no source cell values or data correction." if profile_mode else "Select UTF-8 JSON containing an array of flat records. Every field value must be a string; declare all columns and a unique key. No coercion, missing fields, transmission or payment." if json_source else "Select a local UTF-8 CSV; declare exact requirements. Preview checks bytes and rows, not customer acceptance. No transmission or payment."),wraplength=950).pack(pady=4)
    form=ttk.Frame(content); form.pack(fill="x",padx=12,pady=5)
    source=tk.StringVar(master=window)
    columns=tk.StringVar(master=window)
    key=tk.StringVar(master=window)
    rows=tk.StringVar(master=window)
    right_source=tk.StringVar(master=window)
    right_rows=tk.StringVar(master=window)
    fields=[("Source JSON" if json_source else "Left CSV" if reconcile_mode else "Source CSV",source),
            ("Input columns (comma separated)" if profile_mode or reconcile_mode else "Output columns (comma separated)",columns),
            ("Unique key column",key),("Expected left rows" if reconcile_mode else "Expected data rows (1–2000)",rows)]
    if reconcile_mode:
        fields.extend([("Right CSV",right_source),("Expected right rows",right_rows)])
    for i,(label,var) in enumerate(fields):
        ttk.Label(form,text=label).grid(row=i,column=0,sticky="w",pady=4)
        ttk.Entry(form,textvariable=var,width=66,state="readonly" if var in (source,right_source) else "normal").grid(row=i,column=1,sticky="ew",padx=6)
    form.columnconfigure(1,weight=1)
    status=ttk.Label(content,wraplength=950); status.pack(fill="x",padx=12,pady=4)
    output=ScrolledText(content,state="disabled",wrap="word")
    output.pack(fill="both",expand=True,padx=12,pady=6)
    bar=ttk.Frame(content); bar.pack(pady=7)
    timer=None

    def write(text):
        output.configure(state="normal")
        output.delete("1.0","end")
        output.insert("end",text)
        output.configure(state="disabled")

    def clear(message="Requirements changed. Preview explicitly."):
        workspace.clear()
        write(template_text(workspace.contract_format,halted=False))
        export_button.configure(state="disabled")
        register_button.configure(state="disabled")
        status.configure(text=message)

    def error(exc):
        clear("Operation blocked or unavailable ("+type(exc).__name__+"). Check inputs, source scope and halt. If export was attempted, inspect destination.")

    def choose():
        if blocked_check() is not False:
            clear("Halted or busy.")
            return
        path=filedialog.askopenfilename(parent=window,filetypes=[("JSON","*.json")] if json_source else [("CSV","*.csv")])
        if path and blocked_check() is False:
            source.set(path)

    def choose_right():
        if blocked_check() is not False:
            clear("Halted or busy.")
            return
        path=filedialog.askopenfilename(parent=window,filetypes=[("CSV","*.csv")])
        if path and blocked_check() is False:
            right_source.set(path)

    def preview():
        clear()
        try:
            result=workspace.preview(source.get(),columns.get(),key.get(),rows.get(),
                **(dict(right_source_path=right_source.get(),right_rows=right_rows.get()) if reconcile_mode else {}))
            write(preview_text(result))
            export_button.configure(state="normal")
            register_button.configure(state="normal")
            status.configure(text="Local QA passed. Export a new CSV or register an existing exact-match artifact; source and plan will be rechecked.")
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            if smoke_paths is not None:
                raise
            error(exc)
            return None

    def export_to(path,confirmed):
        try:
            result=workspace.export(path,confirmed=confirmed)
            progress=workspace.progress
            clear("New CSV published. No customer acceptance or revenue recorded.")
            write(progress_text(progress))
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            if smoke_paths is not None:
                raise
            error(exc)
            return None

    def export():
        if not workspace.ready or blocked_check() is not False:
            clear("Preview unavailable or halted.")
            return
        path=filedialog.asksaveasfilename(parent=window,defaultextension=".csv",
                filetypes=[("CSV","*.csv")],initialfile="nexus-work-sample.csv",confirmoverwrite=False)
        if path and messagebox.askyesno("Export new local work sample",
                "Recheck the exact preview and create this new CSV without replacing any file?",parent=window):
            export_to(path,True)

    def register_to(path,confirmed):
        try:
            record=workspace.register(path,confirmed=confirmed)
            progress=workspace.progress
            clear("Local artifact registered: "+record["obligation_id"][:12]+"... Open obligation history to review.")
            write(progress_text(progress))
            return record
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc:
            if smoke_paths is not None:
                raise
            error(exc)
            return None

    def register():
        if not workspace.ready or blocked_check() is not False:
            clear("Preview unavailable or halted.")
            return
        path=filedialog.askopenfilename(parent=window,filetypes=[("CSV","*.csv")])
        if path and messagebox.askyesno("Register matching artifact",
                "Recheck the reviewed preview and register the selected matching file fingerprint? No actual contract or buyer acceptance.",parent=window):
            register_to(path,True)

    def history():
        if blocked_check() is not False:
            clear("Halted or busy.")
            return
        return open_obligation_window(window,plan_id=plan_id,action=action,blocked_check=blocked_check)

    ttk.Button(form,text="Select file",command=choose).grid(row=0,column=2,padx=4)
    if reconcile_mode:
        ttk.Button(form,text="Select right file",command=choose_right).grid(row=4,column=2,padx=4)
    ttk.Button(bar,text="Produce and preview",command=preview).pack(side="left",padx=5)
    export_button=ttk.Button(bar,text="Export new CSV",command=export,state="disabled")
    export_button.pack(side="left",padx=5)
    register_button=ttk.Button(bar,text="Register matching CSV",command=register,state="disabled")
    register_button.pack(side="left",padx=5)
    ttk.Button(bar,text="Obligation history",command=history).pack(side="left",padx=5)
    for var in (source,columns,key,rows,right_source,right_rows):
        var.trace_add("write",lambda *_:clear())
    def check():
        nonlocal timer
        if blocked_check() is not False and workspace.ready:
            clear("Halted or busy; preview cleared.")
        timer=window.after(100,check)
    def destroyed(event):
        if event.widget is window and timer is not None:
            window.after_cancel(timer)
            workspace.clear()
    window.bind("<Destroy>",destroyed,add="+")
    check()
    write(template_text(workspace.contract_format,halted=False))
    if smoke_paths is not None:
        if reconcile_mode:
            src,other,dest=smoke_paths
            right_source.set(str(other)); right_rows.set("2")
        else:
            src,dest=smoke_paths
        source.set(str(src)); columns.set("id,name"); key.set("id"); rows.set("2")
        result=preview()
        if (result is None or "LOCAL WORK SAMPLE" not in output.get("1.0","end")
                or "WORKFLOW — " not in output.get("1.0","end")
                or "Review required" not in output.get("1.0","end")):
            raise RuntimeError("CSV native preview failed")
        if export_to(str(dest),True) is None or dest.read_bytes()!=result["artifact"]:
            raise RuntimeError("CSV native export failed")
        if (workspace.ready or str(export_button.cget("state"))!="disabled"
                or "Local export reported" not in output.get("1.0","end")):
            raise RuntimeError("CSV native preview not consumed")
        if smoke_evidence is not None:
            if preview() is None:
                raise RuntimeError("CSV registration preview failed")
            record=register_to(str(dest),True)
            if (record is None or record["buyer_accepted"] or workspace.ready
                    or "Local registration recorded" not in output.get("1.0","end")):
                raise RuntimeError("CSV native registration failed")
            history_window=open_obligation_window(window,plan_id=plan_id,action=action,
                blocked_check=blocked_check,smoke=(record["obligation_id"],smoke_evidence))
            history_window.destroy()
    return window

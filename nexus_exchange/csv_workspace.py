"""Native saved-plan CSV work sample preview and explicit new-file export."""
import csv
import io
import re
import sqlite3

from .checklist_store import _hash
from .digital_deliverable import _spec
from .deliverable_files import preview_pins
from .obligation_workspace import validate_record, open_obligation_window


def parse_fields(columns,key,rows):
    if (type(columns) is not str or len(columns)>700 or type(key) is not str
            or type(rows) is not str or not re.fullmatch(r"[0-9]{1,4}",rows)):
        raise ValueError("invalid bounded CSV requirements")
    spec=_spec(dict(input_sha256="0"*64,columns=[c.strip() for c in columns.split(",")],
                    key_column=key.strip(),expected_rows=int(rows)))
    return {k:spec[k] for k in ("columns","key_column","expected_rows")}


class CsvWorkspace:
    def __init__(self,plan_id,*,action,blocked_check):
        self.plan_id=_hash(plan_id)
        if not callable(action) or not callable(blocked_check):
            raise ValueError("trusted desktop callbacks required")
        self.action=action
        self.blocked_check=blocked_check
        self.clear()

    def clear(self):
        self._pins=None
        self._inputs=None

    def _permit(self):
        if self.blocked_check() is not False:
            self.clear()
            raise PermissionError("CSV workspace halted or busy")

    def preview(self,source_path,columns,key,rows):
        self.clear()
        self._permit()
        inputs=dict(source_path=source_path,**parse_fields(columns,key,rows))
        result=self.action("preview",self.plan_id,confirmed=True,**inputs)
        self._permit()
        pins=preview_pins(result)
        if result["contract"]["plan_id"]!=self.plan_id:
            raise ValueError("CSV preview outside selected plan")
        self._pins=pins
        self._inputs=inputs
        return result

    @property
    def ready(self):
        return self._pins is not None

    def export(self,destination,*,confirmed=None):
        self._permit()
        if confirmed is not True or not self.ready:
            raise PermissionError("explicit export of a current preview required")
        pins,inputs=self._pins,self._inputs
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
        return record


def preview_text(result):
    pins=preview_pins(result)
    report=result["report"]
    reader=csv.reader(io.StringIO(result["artifact"].decode("utf-8"),newline=""))
    lines=["LOCAL WORK SAMPLE — not customer acceptance or commercial authority",
           "Rows: "+str(report["rows"])+" | bytes: "+str(report["artifact_bytes"]),
           "Contract: "+pins["expected_contract"],"Artifact: "+pins["expected_artifact"],
           "QA: "+", ".join(report["checks"]),"",
           "Preview: header and up to 10 data rows (full artifact on explicit export)"]
    for index,row in enumerate(reader):
        if index>10:
            break
        lines.append(" | ".join(row))
    return "\n".join(lines)


def open_csv_window(parent,*,plan_id,action,blocked_check,smoke_paths=None,smoke_evidence=None):
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
    from tkinter.scrolledtext import ScrolledText

    workspace=CsvWorkspace(plan_id,action=action,blocked_check=blocked_check)
    window=tk.Toplevel(parent)
    window.title("Nexus Exchange | Operator CSV deliverable")
    window.geometry("1000x650")
    ttk.Label(window,text="OPERATOR — Local CSV work sample",font=("Segoe UI",18)).pack(pady=8)
    ttk.Label(window,text="Saved plan: "+plan_id,wraplength=950).pack()
    ttk.Label(window,text="Select a local UTF-8 CSV; declare exact requirements. Preview checks bytes and rows, not customer acceptance. No transmission or payment.",wraplength=950).pack(pady=4)
    form=ttk.Frame(window); form.pack(fill="x",padx=12,pady=5)
    source=tk.StringVar(master=window)
    columns=tk.StringVar(master=window)
    key=tk.StringVar(master=window)
    rows=tk.StringVar(master=window)
    for i,(label,var) in enumerate((("Source CSV",source),("Output columns (comma separated)",columns),
                                   ("Unique key column",key),("Expected data rows (1–2000)",rows))):
        ttk.Label(form,text=label).grid(row=i,column=0,sticky="w",pady=4)
        ttk.Entry(form,textvariable=var,width=66,state="readonly" if i==0 else "normal").grid(row=i,column=1,sticky="ew",padx=6)
    form.columnconfigure(1,weight=1)
    status=ttk.Label(window,wraplength=950); status.pack(fill="x",padx=12,pady=4)
    output=ScrolledText(window,state="disabled",wrap="word")
    output.pack(fill="both",expand=True,padx=12,pady=6)
    bar=ttk.Frame(window); bar.pack(pady=7)
    timer=None

    def write(text):
        output.configure(state="normal")
        output.delete("1.0","end")
        output.insert("end",text)
        output.configure(state="disabled")

    def clear(message="Requirements changed. Preview explicitly."):
        workspace.clear()
        write("")
        export_button.configure(state="disabled")
        register_button.configure(state="disabled")
        status.configure(text=message)

    def error(exc):
        clear("Operation blocked or unavailable ("+type(exc).__name__+"). Check inputs, source scope and halt. If export was attempted, inspect destination.")

    def choose():
        if blocked_check() is not False:
            clear("Halted or busy.")
            return
        path=filedialog.askopenfilename(parent=window,filetypes=[("CSV","*.csv")])
        if path and blocked_check() is False:
            source.set(path)

    def preview():
        clear()
        try:
            result=workspace.preview(source.get(),columns.get(),key.get(),rows.get())
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
            clear("New CSV published. No customer acceptance or revenue recorded.")
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
            clear("Local artifact registered: "+record["obligation_id"][:12]+"... Open obligation history to review.")
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
    ttk.Button(bar,text="Produce and preview",command=preview).pack(side="left",padx=5)
    export_button=ttk.Button(bar,text="Export new CSV",command=export,state="disabled")
    export_button.pack(side="left",padx=5)
    register_button=ttk.Button(bar,text="Register matching CSV",command=register,state="disabled")
    register_button.pack(side="left",padx=5)
    ttk.Button(bar,text="Obligation history",command=history).pack(side="left",padx=5)
    for var in (source,columns,key,rows):
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
    if smoke_paths is not None:
        src,dest=smoke_paths
        source.set(str(src)); columns.set("id,name"); key.set("id"); rows.set("2")
        result=preview()
        if result is None or "LOCAL WORK SAMPLE" not in output.get("1.0","end"):
            raise RuntimeError("CSV native preview failed")
        if export_to(str(dest),True) is None or dest.read_bytes()!=result["artifact"]:
            raise RuntimeError("CSV native export failed")
        if workspace.ready or str(export_button.cget("state"))!="disabled":
            raise RuntimeError("CSV native preview not consumed")
        if smoke_evidence is not None:
            if preview() is None:
                raise RuntimeError("CSV registration preview failed")
            record=register_to(str(dest),True)
            if record is None or record["buyer_accepted"] or workspace.ready:
                raise RuntimeError("CSV native registration failed")
            history_window=open_obligation_window(window,plan_id=plan_id,action=action,
                blocked_check=blocked_check,smoke=(record["obligation_id"],smoke_evidence))
            history_window.destroy()
    return window

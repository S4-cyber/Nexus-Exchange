"""Native local review of immutable scenario-assumption evidence references."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from .checklist_store import _context, _hash
from .owner_profile import ProfileStore, profile_revision
from .scenario_evidence import ScenarioEvidenceStore

LABELS={
    "compensation":"Hypothetical compensation (USD)",
    "probability_delivery_bps":"Delivery probability (basis points)",
    "probability_payment_given_delivery_bps":"Payment probability given delivery (bp)",
    "delivery_days":"Delivery duration (days)",
    "payment_days_after_delivery":"Payment delay after delivery (days)",
    "labor_hours":"Delivery labor (hours)",
    "cost:platform_fees":"Platform fees (USD)",
    "cost:software":"Software (USD)",
    "cost:materials":"Materials (USD)",
    "cost:subcontracting":"Subcontracting (USD)",
    "cost:taxes":"Taxes (USD)",
    "cost:deposits":"Deposits (USD)",
    "cost:other":"Other expenses (USD)",
    "preparation_days":"Preparation duration (days)",
    "preparation_hours":"Preparation labor (hours)",
    "delivery_start":"Hypothetical contract start (UTC)",
    "delivery_deadline":"Hypothetical delivery due (UTC)",
}
STATES={"ASSUMPTION_UNKNOWN":"Assumption unknown",
        "REFERENCE_REQUIRED":"Reference required",
        "REFERENCE_NOTED_UNVERIFIED":"Reference noted / unverified"}


class EvidenceWorkspace:
    """Fixed saved-plan identity, current declared profile and cooperative halt."""
    def __init__(self,directory,context,plan_id,*,halt_check,clock=None):
        self.directory=Path(directory)
        self.context=_context(context)
        if self.context["profile_revision"] is None:
            raise ValueError("current declared owner profile required")
        _hash(plan_id)
        self.plan_id=plan_id
        self.halt_check=halt_check
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def _permit(self):
        if self.halt_check() is not False:
            raise PermissionError("Research halted or halt state unknown.")

    def _profile(self):
        self._permit()
        with ProfileStore(self.directory/"owner-profile.sqlite3") as store:
            profile=store.load(halted=False)
        if profile is None or profile_revision(profile)!=self.context["profile_revision"]:
            raise ValueError("Owner profile changed. Refresh Scout history.")
        return profile

    @contextmanager
    def _session(self):
        profile=self._profile()
        self._permit()
        with ScenarioEvidenceStore(self.directory/"scout-leads.sqlite3") as store:
            saved=store.get(self.plan_id,halted=False)
            if saved is None or saved["context"]!=self.context:
                raise ValueError("Saved scenario outside selected context.")
            self._permit()
            yield store,profile,self.clock()
        self._permit()
        if profile_revision(self._profile())!=profile_revision(profile):
            raise ValueError("Owner profile changed. Refresh Scout history.")
        self._permit()

    def refresh(self):
        with self._session() as (store,profile,now):
            return store.coverage(self.plan_id,profile=profile,now=now,
                halted=False,halt_check=self.halt_check)

    def attach(self,field,path):
        with self._session() as (store,profile,now):
            return store.attach(self.plan_id,field,path,profile=profile,now=now,
                halted=False,halt_check=self.halt_check)

    def verify(self,field,evidence_id,path):
        with self._session() as (store,profile,now):
            return store.verify_attachment(self.plan_id,field,evidence_id,path,
                profile=profile,now=now,halted=False,halt_check=self.halt_check)


def coverage_summary(report):
    return (f'{report["referenced"]} / {report["total"]} referenced | '
            f'{report["unknown"]} unknown | '
            f'{report["independently_verified_count"]} independently verified | '
            f'UTC {report["evaluated_at"]}')


def assumption_values(field):
    return (LABELS[field["field"]],"Unknown" if field["value"] is None else str(field["value"]),
            STATES[field["state"]],str(len(field["references"])))


def reference_details(field,reference,report):
    return "\n".join([
        "UNVERIFIED EVIDENCE ASSOCIATION — NOT AUTHORITY",
        "Saved plan: "+report["plan_id"],
        "Observation: "+report["context"]["observation_sha256"],
        "Assumption: "+LABELS[field["field"]],
        "Canonical modeled value: "+str(field["value"]),
        "Evidence ID: "+reference["evidence_id"],
        "Value binding: "+reference["value_sha256"],
        "File fingerprint: "+reference["reference"],
        "Recorded UTC: "+reference["created_at"],
        "Reselect the local file to compare its bytes. A reference is not verification of content or issuer.",
    ])


def byte_result_text(result):
    return "\n".join([
        "BYTE MATCH" if result["byte_match"] is True else "BYTE MISMATCH",
        "Exact saved plan: "+result["plan_id"],
        "Assumption: "+LABELS[result["field"]],
        "Evidence ID: "+result["evidence_id"],
        "Checked UTC: "+result["evaluated_at"],
        "Expected: "+result["expected_reference"],
        "Observed: "+result["observed_reference"],
        "Byte comparison only; not factual verification, issuer authentication, or authorization.",
        "This result is ephemeral and is not saved as a current verification verdict.",
    ])


def open_evidence_window(parent,*,directory,context,plan_id,halt_check,smoke=False):
    """Local review window; never uses unsaved form inputs."""
    import tkinter as tk
    from tkinter import ttk, filedialog
    from tkinter.scrolledtext import ScrolledText

    workspace=EvidenceWorkspace(directory,context,plan_id,halt_check=halt_check)
    initial=workspace.refresh()
    from .cockpit import install_cockpit, fit_geometry
    window=tk.Toplevel(parent)
    content=install_cockpit(window).content
    window.title("Nexus Exchange | Aegis assumption evidence")
    window.geometry(fit_geometry(window,1120,820))
    window.minsize(800,650)
    ttk.Label(content,text="AEGIS — Saved scenario evidence",font=("Segoe UI",18)).pack(pady=6)
    ttk.Label(content,text="Immutable plan: "+plan_id,wraplength=1020).pack(padx=12)
    ttk.Label(content,text="Select a known assumption and local file. References are unverified; a byte match does not prove commercial facts.",
        wraplength=1020).pack(pady=5,padx=12)
    status=ttk.Label(content,wraplength=1050)
    status.pack(fill="x",padx=12,pady=4)
    panel=ttk.Frame(content)
    panel.pack(fill="both",padx=12,pady=4)
    fields=ttk.Treeview(panel,columns=("assumption","value","state","references"),
                        show="headings",selectmode="browse",height=10)
    for key,label,width in (("assumption","Assumption",310),("value","Saved value",250),
        ("state","Evidence state",235),("references","Refs",65)):
        fields.heading(key,text=label)
        fields.column(key,width=width,anchor="w")
    scroll=ttk.Scrollbar(panel,orient="vertical",command=fields.yview)
    fields.configure(yscrollcommand=scroll.set)
    fields.grid(row=0,column=0,sticky="nsew")
    scroll.grid(row=0,column=1,sticky="ns")
    panel.columnconfigure(0,weight=1)
    refs=ttk.Treeview(content,columns=("id","fingerprint","recorded"),
        show="headings",selectmode="browse",height=3)
    for key,label,width in (("id","Evidence ID",320),("fingerprint","File fingerprint",520),("recorded","Recorded UTC",240)):
        refs.heading(key,text=label)
        refs.column(key,width=width,anchor="w")
    refs.pack(fill="x",padx=12,pady=4)
    buttons=ttk.Frame(content)
    buttons.pack(before=panel, pady=4)
    details=ScrolledText(content,height=12,wrap="word",state="disabled")
    details.pack(fill="both",expand=True,padx=12,pady=6)
    report=None
    rows={}
    reference_rows={}
    timer=None
    closed=False
    shown_field=None
    shown_reference=None

    def write(text):
        details.configure(state="normal")
        details.delete("1.0","end")
        details.insert("end",text)
        details.configure(state="disabled")

    def clear(message):
        nonlocal report,shown_field,shown_reference
        report=None
        shown_field=shown_reference=None
        rows.clear()
        reference_rows.clear()
        for tree in (fields,refs):
            for item in tree.get_children():
                tree.delete(item)
        status.configure(text=message)
        write("")

    def selected_field():
        choice=fields.selection()
        if report is None or not choice or choice[0] not in rows:
            raise ValueError("Select a saved assumption.")
        return rows[choice[0]]

    def selected_reference():
        field=selected_field()
        choice=refs.selection()
        if not choice or choice[0] not in reference_rows:
            raise ValueError("Select a reference.")
        reference=reference_rows[choice[0]]
        if reference["field"]!=field["field"]:
            raise ValueError("Reference is outside selected assumption.")
        return field,reference

    def display_reference(_event=None,force=False):
        nonlocal shown_reference
        if halt_check() is not False:
            clear("Research halted. Refresh after explicit resume.")
            return
        try:
            field,reference=selected_reference()
        except ValueError:
            if shown_reference is not None or force:
                shown_reference=None
                write("")
            return
        key=reference["evidence_id"]
        if force or key!=shown_reference:
            shown_reference=key
            write(reference_details(field,reference,report))

    def display_field(_event=None,force=False):
        nonlocal shown_field,shown_reference
        if halt_check() is not False:
            clear("Research halted. Refresh after explicit resume.")
            return
        try:
            field=selected_field()
        except ValueError:
            shown_field=shown_reference=None
            reference_rows.clear()
            for item in refs.get_children():
                refs.delete(item)
            write("")
            return
        key=field["field"]
        if not force and shown_field==key:
            return
        shown_field=key
        shown_reference=None
        reference_rows.clear()
        for item in refs.get_children():
            refs.delete(item)
        for item in field["references"]:
            ident=item["evidence_id"]
            reference_rows[ident]=item
            refs.insert("","end",iid=ident,values=(ident,item["reference"],item["created_at"]))
        write("UNVERIFIED ASSUMPTION\n"+LABELS[key]+": "+
              ("Unknown" if field["value"] is None else str(field["value"]))+
              "\n"+STATES[field["state"]])

    def populate(result,field=None,reference=None):
        nonlocal report
        clear(coverage_summary(result))
        report=result
        for item in result["fields"]:
            key=item["field"]
            rows[key]=item
            fields.insert("","end",iid=key,values=assumption_values(item))
        if field is not None and fields.exists(field):
            fields.selection_set(field)
            display_field(force=True)
            if reference is not None and refs.exists(reference):
                refs.selection_set(reference)
                display_reference(force=True)

    def refresh():
        try:
            field=selected_field()["field"]
        except ValueError:
            field=None
        try:
            result=workspace.refresh()
            populate(result,field)
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error) as exc:
            clear("Evidence unavailable. Refresh owner profile/context or resume research. ("+type(exc).__name__+")")
            return None

    def attach(path=None):
        try:
            field=selected_field()
            if field["value"] is None:
                raise ValueError("Unknown assumption cannot have a value-bound reference.")
            workspace.refresh()
            if path is None:
                path=filedialog.askopenfilename(parent=window,title="Select local evidence file")
            if not path:
                return None
            key=workspace.attach(field["field"],path)
            populate(workspace.refresh(),field["field"],key)
            return key
        except (ValueError,PermissionError,OSError,sqlite3.Error) as exc:
            clear("Attachment blocked or unavailable. Refresh before retrying. ("+type(exc).__name__+")")
            return None

    def verify(path=None):
        nonlocal shown_reference
        write("")
        try:
            field,reference=selected_reference()
            workspace.refresh()
            if path is None:
                path=filedialog.askopenfilename(parent=window,title="Reselect local file to compare bytes")
            if not path:
                return None
            result=workspace.verify(field["field"],reference["evidence_id"],path)
            populate(workspace.refresh(),field["field"],reference["evidence_id"])
            shown_reference=reference["evidence_id"]
            write(byte_result_text(result))
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error) as exc:
            clear("Byte comparison blocked or unavailable. Refresh before retrying. ("+type(exc).__name__+")")
            return None

    def guard_display():
        nonlocal timer
        if closed:
            return
        if report is not None and halt_check() is not False:
            clear("Research halted. Previous evidence snapshot cleared.")
        timer=window.after(350,guard_display)

    def destroyed(event):
        nonlocal closed
        if event.widget is window:
            closed=True
            if timer is not None:
                try:
                    window.after_cancel(timer)
                except tk.TclError:
                    pass

    ttk.Button(buttons,text="Attach selected local file",command=attach).pack(side="left",padx=4)
    ttk.Button(buttons,text="Reselect file / compare bytes",command=verify).pack(side="left",padx=4)
    ttk.Button(buttons,text="Refresh coverage",command=refresh).pack(side="left",padx=4)
    fields.bind("<<TreeviewSelect>>",display_field)
    refs.bind("<<TreeviewSelect>>",display_reference)
    window.bind("<Destroy>",destroyed,add="+")
    populate(initial,"compensation")
    guard_display()
    if smoke:
        import tempfile
        with tempfile.TemporaryDirectory() as directory_name:
            path=Path(directory_name)/"synthetic-private-name.txt"
            path.write_bytes(b"synthetic financial terms")
            key=attach(path)
            if key is None or not refs.exists(key) or report["referenced"]!=1:
                raise RuntimeError("evidence GUI could not save selected assumption reference")
            refresh()
            refs.selection_set(key)
            display_reference(force=True)
            result=verify(path)
            window.update_idletasks()
            window.update()
            if result is None or result["byte_match"] is not True or "BYTE MATCH" not in details.get("1.0","end"):
                raise RuntimeError("evidence GUI could not reload and compare reference")
            path.write_bytes(b"modified financial terms")
            result=verify(path)
            window.update_idletasks()
            window.update()
            if result is None or result["byte_match"] is not False or "BYTE MISMATCH" not in details.get("1.0","end"):
                raise RuntimeError("evidence GUI did not detect modified bytes")
            if report["independently_verified_count"]!=0 or report["external_authority"]:
                raise RuntimeError("evidence GUI lost verification boundary")
            if path.name in details.get("1.0","end"):
                raise RuntimeError("evidence GUI exposed local filename")
    return window

"""Fixed-scope native local correspondence. No external delivery."""
import sqlite3
from .operator_drafts import _shape, _stored_stamp
from .operator_recipients import _scope, _for_draft, _FLAGS_EXTRA, render_correspondence
from .correspondence_thread import validate_thread
from .operator_workspace import parse_supplier


class CorrespondenceWorkspace:
    def __init__(self, workspace, draft, fields):
        self.workspace=workspace
        self.draft=workspace._draft(draft)
        self.scope=_scope(self.draft)
        self.supplier=parse_supplier(fields)

    def _call(self, operation, **inputs):
        self.workspace._permit()
        result=self.workspace.action(operation,self.workspace.plan_id,
                                     draft_id=self.scope['draft_id'],**inputs)
        self.workspace._permit()
        if operation=='thread_history' and result is None:
            return None
        if type(result) is not dict or any(result.get(k) is not False for k in _FLAGS_EXTRA):
            raise ValueError('correspondence authority mismatch')
        return result

    def contact(self,email,source,observed):
        return dict(scheme=self.supplier['scheme'],identifier=self.supplier['identifier'],
                    organization_name=self.supplier['name'],email=email,source_url=source,
                    observed_at=observed)

    def _record(self,record):
        _shape(record,{'version','candidate','recorded_at','state','historical_only',*_FLAGS_EXTRA})
        if (type(record['version']) is not int or record['version']!=1 or
                record['state']!='DECLARED_RECIPIENT_DRAFT_ONLY' or
                record['historical_only'] is not True or
                any(record[k] is not False for k in _FLAGS_EXTRA)):
            raise ValueError('invalid recipient history')
        _stored_stamp(record['recorded_at'])
        _for_draft(self.draft,record['candidate'])
        return record

    def preview(self,contact,path):
        return _for_draft(self.draft,self._call('recipient_preview',supplier=self.supplier,
                              recipient=contact,evidence_path=path))

    def save(self,contact,path,expected,*,confirmed=None):
        self.workspace._permit()
        if confirmed is not True:
            raise PermissionError('explicit local confirmation required')
        expected=_for_draft(self.draft,expected)
        result=self._record(self._call('recipient_save',supplier=self.supplier,recipient=contact,
            evidence_path=path,expected_recipient_id=expected['recipient_id'],confirmed=True))
        if result['candidate']!=expected:
            raise ValueError('saved recipient differs from preview')
        return result

    def history(self):
        result=self._call('recipient_history',limit=100)
        if (result.get('scope')!=self.scope or result.get('historical_only') is not True or
                type(result.get('rows')) is not list or len(result['rows'])>100 or
                type(result.get('truncated')) is not bool):
            raise ValueError('invalid recipient history')
        keys=[self._record(row)['candidate']['recipient_id'] for row in result['rows']]
        if len(set(keys))!=len(keys):
            raise ValueError('duplicate recipient history')
        return result

    def thread(self,record,*,create=False,confirmed=None):
        self.workspace._permit()
        candidate=self._record(record)['candidate']
        if type(create) is not bool:
            raise ValueError('invalid thread operation')
        if create:
            if confirmed is not True:
                raise PermissionError('explicit local thread confirmation required')
            result=self._call('thread_open',recipient_id=candidate['recipient_id'],
                              supplier=self.supplier,confirmed=True)
        else:
            result=self._call('thread_history',recipient_id=candidate['recipient_id'])
        if result is None and not create:
            return None
        return validate_thread(self.draft,candidate,result,halted=False)


def open_correspondence_window(parent, controller, *, smoke=False):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from tkinter.scrolledtext import ScrolledText
    from .cockpit import install_cockpit, fit_geometry
    window=tk.Toplevel(parent)
    content=install_cockpit(window).content
    window.title('Operator | Local correspondence')
    window.geometry(fit_geometry(window,900,720))
    ttk.Label(content,text='LOCAL CORRESPONDENCE — DO NOT SEND',font=('Segoe UI',16)).pack(pady=5)
    ttk.Label(content,text='Fixed RFQ: '+controller.scope['draft_id'],wraplength=850).pack()
    ttk.Label(content,text='Declared supplier: '+controller.supplier['name']+
              ' | Identity, evidence and contact permission unverified.',wraplength=850).pack(pady=3)
    form=ttk.Frame(content); form.pack(fill='x',padx=10)
    fields={key:tk.StringVar(master=window) for key in ('email','source','observed')}
    for row,(key,label) in enumerate((('email','Declared role mailbox'),('source','HTTPS contact source (not opened)'),
                                      ('observed','Observation time (ISO UTC/offset)'))):
        ttk.Label(form,text=label).grid(row=row,column=0,sticky='w')
        ttk.Entry(form,textvariable=fields[key]).grid(row=row,column=1,sticky='ew',padx=5,pady=2)
    form.columnconfigure(1,weight=1)
    path=None; prepared=None; records={}; timer=None; closed=False
    status=ttk.Label(content,text='Choose evidence and preview before saving.',wraplength=850)
    status.pack(fill='x',padx=10,pady=3)
    selected=tk.StringVar(master=window)
    picker=ttk.Combobox(content,textvariable=selected,state='readonly',values=())
    output=ScrolledText(content,height=14,wrap='word',state='disabled')
    def write(value):
        output.configure(state='normal'); output.delete('1.0','end')
        output.insert('end',value); output.configure(state='disabled')
    def invalidate(*_):
        nonlocal prepared
        prepared=None; write('')
    def clear():
        nonlocal path
        path=None; invalidate(); records.clear(); selected.set(''); picker.configure(values=())
    def args():
        return controller.contact(*(fields[key].get() for key in ('email','source','observed'))),path
    def choose():
        nonlocal path
        controller.workspace._permit()
        value=filedialog.askopenfilename(parent=window,title='Select local evidence for fingerprinting')
        controller.workspace._permit()
        if value:
            path=value; invalidate(); status.configure(text='Evidence selected; preview required.')
    def preview():
        nonlocal prepared
        contact,file=args()
        prepared=controller.preview(contact,file)
        write(render_correspondence(controller.draft,prepared,halted=False)+'\n\nEvidence: '+prepared['evidence_reference'])
        status.configure(text='Local preview only; no saved declaration or permission.')
        return prepared
    def refresh(key=None):
        invalidate()
        result=controller.history()
        records.clear(); records.update((r['candidate']['recipient_id'],r) for r in result['rows'])
        picker.configure(values=tuple(records)); selected.set(key if key in records else '')
        status.configure(text=f"{len(records)} historical declarations"+(' (truncated)' if result['truncated'] else '')+'. Select an exact fingerprint.')
        return result
    def save(auto=False):
        if prepared is None: raise ValueError('preview required')
        expected=prepared; original=args()
        if not (smoke and auto) and not messagebox.askyesno('Save unverified local declaration',
                'Save this exact local declaration? No contact permission.\n'+expected['recipient_id'],parent=window):
            return None
        if prepared!=expected or args()!=original: raise ValueError('preview changed')
        result=controller.save(original[0],original[1],expected,confirmed=True)
        refresh(expected['recipient_id'])
        return result
    def inspect(create=False,auto=False):
        key=selected.get()
        if key not in records: raise ValueError('select exact saved recipient')
        record=records[key]
        if create and not (smoke and auto) and not messagebox.askyesno('Local thread only',
                'Open local history? No message is sent.\n'+key,parent=window):
            return None
        if selected.get()!=key or records.get(key)!=record: raise ValueError('selection changed')
        thread=controller.thread(record,create=create,confirmed=True if create else None)
        lines=[render_correspondence(controller.draft,record['candidate'],halted=False),
               '', 'HISTORICAL LOCAL THREAD — NOT DELIVERY OR AUTHENTICATED REPLY']
        if thread is None:
            lines.append('No saved thread.')
        else:
            lines.extend(('Thread: '+thread['thread_id'],'Head: '+thread['head_sha256']))
            for event in thread['events']:
                lines.append(f"{event['sequence']} | {event['kind']} | {event['recorded_at']} | {event['evidence_reference']}")
        write('\n'.join(lines))
        return thread
    def guarded(callback):
        def run():
            try: return callback()
            except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError,TypeError,KeyError) as exc:
                clear(); status.configure(text='Local correspondence unavailable ('+type(exc).__name__+'). Select evidence again.')
        return run
    buttons=ttk.Frame(content); buttons.pack(pady=3)
    for label,callback in (('Choose evidence',choose),('Preview',preview),('Save declaration',save),('Refresh history',refresh)):
        ttk.Button(buttons,text=label,command=guarded(callback)).pack(side='left',padx=3)
    picker.pack(fill='x',padx=10,pady=3)
    controls=ttk.Frame(content); controls.pack(pady=3)
    ttk.Button(controls,text='Inspect history',command=guarded(inspect)).pack(side='left',padx=3)
    ttk.Button(controls,text='Open local thread',command=guarded(lambda:inspect(True))).pack(side='left',padx=3)
    output.pack(fill='both',expand=True,padx=10,pady=4)
    for var in fields.values(): var.trace_add('write',invalidate)
    picker.bind('<<ComboboxSelected>>',lambda event:invalidate())
    def monitor():
        nonlocal timer
        if closed: return
        if controller.workspace.blocked_check() is not False:
            clear(); status.configure(text='Halted or busy; prior display cleared.')
        timer=window.after(250,monitor)
    def destroyed(event):
        nonlocal closed
        if event.widget is window:
            closed=True
            if timer is not None:
                try: window.after_cancel(timer)
                except tk.TclError: pass
    window.bind('<Destroy>',destroyed,add='+')
    monitor()
    if smoke:
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from datetime import datetime, timezone
        with TemporaryDirectory() as temp:
            file=Path(temp)/'owned-contact.txt'; file.write_bytes(b'Synthetic contact declaration only')
            path=str(file)
            fields['email'].set('quotes@example.org')
            fields['source'].set('https://example.org/contact')
            fields['observed'].set(datetime.now(timezone.utc).isoformat())
            candidate=preview()
            record=save(auto=True)
            if record['candidate']!=candidate or inspect() is not None:
                raise RuntimeError('recipient GUI preview/save failed')
            thread=inspect(True,auto=True)
            if thread is None or thread['events'] or inspect()!=thread:
                raise RuntimeError('correspondence GUI thread history failed')
            if 'HISTORICAL LOCAL THREAD' not in output.get('1.0','end'):
                raise RuntimeError('correspondence GUI display failed')
    return window

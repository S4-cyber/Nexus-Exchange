"""Fixed-scope native local correspondence. No external delivery."""
import sqlite3
from .operator_drafts import _shape, _stored_stamp
from .operator_recipients import _scope, _for_draft, _FLAGS_EXTRA, render_correspondence
from .correspondence_thread import validate_thread, MAX_EVENTS, _KINDS
from .evidence import fingerprint, parse_reference
from .operator_workspace import parse_supplier
from .followup_export import write_reviewed_text


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


    def preview_event(self, record, kind, path):
        """Read only an explicitly selected local file; pin the current history."""
        self.workspace._permit()
        if type(kind) is not str or kind not in _KINDS:
            raise ValueError('unsupported local event kind')
        current=self.thread(record)
        if current is None or len(current['events'])>=MAX_EVENTS:
            raise ValueError('open thread with available capacity required')
        reference=fingerprint(path,halted=False,halt_check=self.workspace.blocked_check)
        self.workspace._permit()
        if any(e['evidence_reference']==reference for e in current['events']):
            raise ValueError('duplicate thread evidence')
        return dict(thread_id=current['thread_id'],head=current['head_sha256'],
                    kind=kind,evidence=reference)

    def save_event(self, record, path, expected, *, confirmed=None):
        """Commit an exact locally reviewed event via the runtime CAS."""
        self.workspace._permit()
        if confirmed is not True:
            raise PermissionError('explicit local event confirmation required')
        _shape(expected,{'thread_id','head','kind','evidence'})
        if type(expected['kind']) is not str or expected['kind'] not in _KINDS:
            raise ValueError('unsupported local event kind')
        parse_reference(expected['evidence'])
        candidate=self._record(record)['candidate']
        prior=self.thread(record)
        if (prior is None or prior['thread_id']!=expected['thread_id'] or
                prior['head_sha256']!=expected['head'] or len(prior['events'])>=MAX_EVENTS or
                any(e['evidence_reference']==expected['evidence'] for e in prior['events'])):
            raise ValueError('thread changed or unavailable; inspect again')
        result=validate_thread(self.draft,candidate,self._call('thread_append',
            recipient_id=candidate['recipient_id'],supplier=self.supplier,
            kind=expected['kind'],evidence_path=path,expected_head=expected['head'],
            expected_evidence=expected['evidence'],confirmed=True),halted=False)
        events=result['events']
        if (result['thread_id']!=prior['thread_id'] or len(events)!=len(prior['events'])+1 or
                events[:-1]!=prior['events'] or events[-1]['kind']!=expected['kind'] or
                events[-1]['evidence_reference']!=expected['evidence']):
            raise ValueError('saved event differs from reviewed event')
        return result


    def preview_followup(self, record):
        """Compose a historical, nonbinding local draft; never read evidence bytes."""
        self.workspace._permit()
        candidate=self._record(record)['candidate']
        current=self.thread(record)
        if current is None:
            raise ValueError('saved local thread required')
        reply=next((event for event in reversed(current['events'])
                    if event['kind']=='SIMULATED_REPLY'),None)
        if reply is None:
            raise ValueError('simulated reply evidence required')
        if any(event['kind']=='LOCAL_FOLLOWUP_DRAFT' and event['sequence']>reply['sequence']
               for event in current['events']):
            raise ValueError('a local follow-up is already recorded after this simulated reply')
        body='\n'.join((
            'LOCAL FOLLOW-UP DRAFT — DO NOT SEND',
            'Declared role mailbox (unverified): '+candidate['recipient']['email'],
            'Subject: Request for clarification (nonbinding draft)',
            '',
            'Reference: '+self.scope['draft_id'],
            'Please clarify current availability, indicative pricing, delivery timing,',
            'applicable requirements and any limitations for the referenced request.',
            'Any information would be for evaluation only. No order, acceptance,',
            'payment, agreement or authority to proceed is conveyed by this draft.',
            '',
            'Local context only: simulated reply evidence exists; its content was not read.',
            'No external message, recipient identity or permission to contact is verified.'))
        self.workspace._permit()
        return dict(draft_id=self.scope['draft_id'],recipient_id=candidate['recipient_id'],
                    thread_id=current['thread_id'],head=current['head_sha256'],
                    reply_event_sha256=reply['event_sha256'],
                    evidence_reference=reply['evidence_reference'],body=body,
                    historical_only=True,**dict.fromkeys(_FLAGS_EXTRA,False))


    def export_followup(self, record, path, expected, *, confirmed=None):
        """Export exact reviewed bytes; return a separate local event preview."""
        self.workspace._permit()
        if confirmed is not True:
            raise PermissionError('explicit local export confirmation required')
        current=self.preview_followup(record)
        if type(expected) is not dict or current!=expected:
            raise ValueError('follow-up changed; preview again')
        payload=current['body']+'\n\n'+ '\n'.join(
            key+': '+current[key] for key in ('draft_id','recipient_id','thread_id','head',
                                              'reply_event_sha256','evidence_reference'))+'\n'
        reference=write_reviewed_text(path,payload,permit=self.workspace._permit)
        event=self.preview_event(record,'LOCAL_FOLLOWUP_DRAFT',path)
        if (event['head']!=current['head'] or event['thread_id']!=current['thread_id'] or
                event['evidence']!=reference):
            raise ValueError('export not registered; history or bytes changed')
        return event


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
    path=None; prepared=None; pending_event=None; pending_followup=None; records={}; timer=None; closed=False
    status=ttk.Label(content,text='Choose evidence and preview before saving.',wraplength=850)
    status.pack(fill='x',padx=10,pady=3)
    selected=tk.StringVar(master=window)
    picker=ttk.Combobox(content,textvariable=selected,state='readonly',values=())
    output=ScrolledText(content,height=14,wrap='word',state='disabled')
    def write(value):
        output.configure(state='normal'); output.delete('1.0','end')
        output.insert('end',value); output.configure(state='disabled')
    def invalidate(*_):
        nonlocal prepared,pending_event,pending_followup
        prepared=None; pending_event=None; pending_followup=None; write('')
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
        invalidate()
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
    def followup():
        nonlocal pending_followup
        invalidate()
        key=selected.get()
        if key not in records: raise ValueError('select exact saved recipient')
        result=controller.preview_followup(records[key])
        pending_followup=(key,result)
        write(result['body']+'\n\nThread: '+result['thread_id']+'\nReviewed head: '+result['head']
              +'\nSimulated reply event: '+result['reply_event_sha256']
              +'\nEvidence: '+result['evidence_reference'])
        status.configure(text='Historical local preview only; no saved draft, message or authority.')
        return result
    def export_followup(file=None,auto=False):
        nonlocal pending_event
        if pending_followup is None:
            raise ValueError('preview local follow-up first')
        original=pending_followup
        key,expected=original
        controller.workspace._permit()
        if file is None:
            file=filedialog.asksaveasfilename(parent=window,title='Export new local text draft',
                defaultextension='.txt',filetypes=(('Text draft','*.txt'),))
        controller.workspace._permit()
        if not file: return None
        if not (smoke and auto) and not messagebox.askyesno('Export local draft only',
                'Create a new local text file containing the reviewed draft? No transmission.\n'
                +expected['head'],parent=window):
            return None
        if pending_followup!=original or selected.get()!=key or key not in records:
            raise ValueError('follow-up preview changed')
        event=controller.export_followup(records[key],file,expected,confirmed=True)
        event_kind.set('LOCAL_FOLLOWUP_DRAFT')
        invalidate()
        pending_event=(key,file,event)
        write('EXPORTED LOCAL DRAFT — NOT REGISTERED OR SENT\n'
              +'Thread: '+event['thread_id']+'\nHead: '+event['head']+'\nEvidence: '+event['evidence'])
        status.configure(text='File created. Review and record local event separately. Never send.')
        return event
    event_kind=tk.StringVar(master=window,value='SIMULATED_REPLY')
    def prepare_event(file=None):
        nonlocal pending_event
        invalidate()
        key=selected.get()
        kind=event_kind.get()
        if key not in records: raise ValueError('select exact saved recipient')
        controller.workspace._permit()
        if file is None:
            file=filedialog.askopenfilename(parent=window,title='Select local event evidence')
        controller.workspace._permit()
        if not file: return None
        if selected.get()!=key or event_kind.get()!=kind or key not in records:
            raise ValueError('event selection changed')
        expected=controller.preview_event(records[key],kind,file)
        pending_event=(key,file,expected)
        write('LOCAL EVENT PREVIEW — NOT AUTHENTICATED OR SENT\n'
              +'Recipient: '+key+'\nThread: '+expected['thread_id']+'\nHead: '+expected['head']
              +'\nKind: '+kind+'\nEvidence: '+expected['evidence'])
        status.configure(text='Review exact event and fingerprint before recording locally.')
        return expected
    def commit_event(auto=False):
        if pending_event is None: raise ValueError('preview local event first')
        original=pending_event
        key,file,expected=original
        if not (smoke and auto) and not messagebox.askyesno('Record local event only',
                'Record '+expected['kind']+' against this exact history? No delivery or authentication.\n'
                +expected['head']+'\n'+expected['evidence'],parent=window):
            return None
        if (pending_event!=original or selected.get()!=key or key not in records or
                event_kind.get()!=expected['kind']):
            raise ValueError('event preview changed')
        result=controller.save_event(records[key],file,expected,confirmed=True)
        if inspect()!=result: raise ValueError('saved thread readback changed')
        status.configure(text='Local event recorded; no message sent or reply authenticated.')
        return result
    def guarded(callback):
        def run():
            try: return callback()
            except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError,TypeError,KeyError) as exc:
                clear(); status.configure(text='Local correspondence unavailable ('+type(exc).__name__+'). Select evidence again.')
        return run
    buttons=ttk.Frame(content); buttons.pack(before=form, pady=3)
    for label,callback in (('Choose evidence',choose),('Preview',preview),('Save declaration',save),('Refresh history',refresh)):
        ttk.Button(buttons,text=label,command=guarded(callback)).pack(side='left',padx=3)
    picker.pack(before=form, fill='x',padx=10,pady=3)
    controls=ttk.Frame(content); controls.pack(before=form, pady=3)
    ttk.Button(controls,text='Inspect history',command=guarded(inspect)).pack(side='left',padx=3)
    ttk.Button(controls,text='Open local thread',command=guarded(lambda:inspect(True))).pack(side='left',padx=3)
    event_controls=ttk.Frame(content); event_controls.pack(before=form, pady=3)
    ttk.Label(event_controls,text='Local event kind').pack(side='left',padx=3)
    ttk.Combobox(event_controls,textvariable=event_kind,state='readonly',width=29,
                 values=tuple(sorted(_KINDS))).pack(side='left',padx=3)
    ttk.Button(event_controls,text='Choose and preview event',command=guarded(prepare_event)).pack(side='left',padx=3)
    ttk.Button(event_controls,text='Record local event',command=guarded(commit_event)).pack(side='left',padx=3)
    ttk.Button(controls,text='Preview local follow-up',command=guarded(followup)).pack(side='left',padx=3)
    ttk.Button(controls,text='Export local follow-up',command=guarded(export_followup)).pack(side='left',padx=3)
    event_kind.trace_add('write',invalidate)
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
            reply=Path(temp)/'owned-simulated-reply.txt'
            reply.write_bytes(b'Synthetic simulated reply; not an external message')
            expected=prepare_event(str(reply))
            updated=commit_event(auto=True)
            if (len(updated['events'])!=1 or updated['events'][0]['evidence_reference']!=expected['evidence']
                    or inspect()!=updated or 'SIMULATED_REPLY' not in output.get('1.0','end')):
                raise RuntimeError('correspondence GUI event readback failed')
            draft_preview=followup()
            if (draft_preview['head']!=updated['head_sha256']
                    or draft_preview['evidence_reference']!=expected['evidence']
                    or 'LOCAL FOLLOW-UP DRAFT' not in output.get('1.0','end')
                    or inspect()!=updated):
                raise RuntimeError('correspondence GUI follow-up preview failed')
            draft_preview=followup()
            exported=Path(temp).resolve()/'owned-followup.txt'
            export_event=export_followup(str(exported),auto=True)
            if (export_event['head']!=draft_preview['head'] or
                    export_event['evidence']!=fingerprint(exported,halted=False)):
                raise RuntimeError('correspondence GUI follow-up export failed')
            registered=commit_event(auto=True)
            if (len(registered['events'])!=2 or
                    registered['events'][-1]['kind']!='LOCAL_FOLLOWUP_DRAFT' or
                    registered['events'][-1]['evidence_reference']!=export_event['evidence']):
                raise RuntimeError('correspondence GUI follow-up registration failed')
    return window

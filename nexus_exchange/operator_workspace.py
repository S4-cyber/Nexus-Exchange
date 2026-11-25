"""Native local RFQ composer and saved-draft browser. No sending capability."""
import sqlite3
from datetime import datetime, timezone

from .operator_drafts import MAX_ITEMS, _FLAGS, _hash, _text, _validated, render_rfq

SUPPLIER_FIELDS = (
    ('scheme','Registry scheme'), ('identifier','Registry identifier'),
    ('name','Declared organization name'), ('classifications','Declared codes (scheme:code, ...)'),
    ('regions','Declared delivery regions (comma-separated)'), ('capacity','Declared USD capacity'),
    ('source_url','Declaration source URL (not opened)'), ('observed_at','Observation time (ISO UTC/offset)'),
)


def parse_supplier(fields):
    if type(fields) is not dict or set(fields) != {key for key,_ in SUPPLIER_FIELDS}:
        raise ValueError('complete supplier declaration required')
    data={key:_text(value,4096) for key,value in fields.items()}
    codes=[]
    for token in data['classifications'].split(','):
        parts=token.strip().split(':',1)
        if len(parts)!=2 or not all(part.strip() for part in parts):
            raise ValueError('use explicit scheme:code classifications')
        codes.append(dict(scheme=parts[0].strip(),code=parts[1].strip()))
    regions=[part.strip() for part in data['regions'].split(',')]
    if not all(regions) or len(regions)>32 or len(codes)>32:
        raise ValueError('bounded regions and classifications required')
    return dict(data,classifications=codes,regions=regions,roles=['supplier'],currency='USD')


def parse_items(text):
    if type(text) is not str or not 1<=len(text)<=16384:
        raise ValueError('bounded item text required')
    lines=[line for line in text.split('\n') if line.strip()]
    if not 1<=len(lines)<=MAX_ITEMS:
        raise ValueError('one to sixteen explicit line items required')
    result=[]
    for line in lines:
        if any(not char.isprintable() for char in line):
            raise ValueError('invalid line item characters')
        parts=[part.strip() for part in line.split('|')]
        if len(parts)!=5 or not all(parts):
            raise ValueError('use description | quantity | unit | scheme | code')
        desc,quantity,unit,scheme,code=parts
        result.append(dict(description=desc,quantity=quantity,unit=unit,
                           classification=dict(scheme=scheme,code=code)))
    return result


class OperatorWorkspace:
    """Fixed saved-plan identity, trusted desktop worker and runtime facade."""
    def __init__(self,plan_id,*,action,blocked_check):
        self.plan_id=_hash(plan_id)
        if not callable(action) or not callable(blocked_check):
            raise ValueError('trusted desktop facade required')
        self.action=action
        self.blocked_check=blocked_check

    def _permit(self):
        if self.blocked_check() is not False:
            raise PermissionError('Operator halted, busy or unavailable')

    def _call(self,operation,**inputs):
        self._permit()
        result=self.action(operation,self.plan_id,**inputs)
        self._permit()
        if type(result) is not dict or any(result.get(k) is not False for k in _FLAGS):
            raise ValueError('Operator authority boundary mismatch')
        return result

    def _draft(self,draft):
        draft=_validated(draft)
        if draft['request']['plan_id']!=self.plan_id:
            raise ValueError('draft outside selected saved plan')
        return draft

    def _record(self,record,key=None):
        if (type(record) is not dict or record.get('historical_only') is not True
                or any(record.get(k) is not False for k in _FLAGS)):
            raise ValueError('historical draft required')
        draft=self._draft(record['draft'])
        if (key is not None and draft['draft_id']!=key or
                record.get('supplier_scope_pinned') is not ('supplier_profile_sha256' in draft['request'])):
            raise ValueError('historical draft identity mismatch')
        return record

    def prepare(self,fields,region,text):
        self._permit()
        return self._draft(self._call('prepare',supplier=parse_supplier(fields),region=region,items=parse_items(text)))

    def save(self,fields,region,text):
        self._permit()
        return self._record(self._call('save',supplier=parse_supplier(fields),region=region,items=parse_items(text)))

    def history_list(self,limit=100):
        self._permit()
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError('invalid draft history limit')
        result=self._call('history_list',limit=limit)
        if (result.get('plan_id')!=self.plan_id or result.get('historical_only') is not True
                or type(result.get('truncated')) is not bool or type(result.get('rows')) is not list
                or len(result['rows'])>limit):
            raise ValueError('invalid plan history projection')
        for row in result['rows']:
            self._record(row)
        return result

    def history(self,key):
        return self._record(self._call('history',draft_id=_hash(key)),key)

    def acknowledge(self,key,fields,*,confirmed=None):
        self._permit()
        if confirmed is not True:
            raise PermissionError('explicit local acknowledgment required')
        return self._record(self._call('acknowledge',draft_id=_hash(key),supplier=parse_supplier(fields),confirmed=True),key)


def record_text(record):
    draft=record['draft']
    scope='Supplier declaration fingerprint: '+draft['request']['supplier_profile_sha256'] if record['supplier_scope_pinned'] else 'Legacy unpinned supplier declaration'
    return '\n'.join(['HISTORICAL ONLY — No current decision or external authority',
        'Saved draft: '+draft['draft_id'], 'State: '+record['state'], 'Created UTC: '+record['created_at'],
        'Acknowledged UTC: '+(record['acknowledged_at'] or 'Not acknowledged'), scope,'',render_rfq(draft,halted=False)])


def open_operator_window(parent,*,plan_id,action,blocked_check,smoke=False):
    import tkinter as tk
    from tkinter import ttk, messagebox
    from tkinter.scrolledtext import ScrolledText

    workspace=OperatorWorkspace(plan_id,action=action,blocked_check=blocked_check)
    from .cockpit import install_cockpit, fit_geometry
    window=tk.Toplevel(parent)
    content=install_cockpit(window).content
    window.title('Nexus Exchange | Operator quotation drafts')
    window.geometry(fit_geometry(window,1160,850))
    window.minsize(850,680)
    ttk.Label(content,text='OPERATOR — Local quotation requests',font=('Segoe UI',18)).pack(pady=5)
    ttk.Label(content,text='Saved plan: '+plan_id,wraplength=1080).pack(padx=12)
    ttk.Label(content,text='Declared supplier only. No verified recipient, sending or purchase. Reenter the same declaration to acknowledge a saved draft.',wraplength=1050).pack(pady=4)
    form=ttk.LabelFrame(content,text='Explicit supplier declaration (USD)')
    form.pack(fill='x',padx=12,pady=4)
    values={key:tk.StringVar(master=window) for key,_ in SUPPLIER_FIELDS}
    for i,(key,label) in enumerate(SUPPLIER_FIELDS):
        row,col=divmod(i,2)
        ttk.Label(form,text=label).grid(row=row,column=col*2,sticky='w',padx=3,pady=2)
        ttk.Entry(form,textvariable=values[key],width=30).grid(row=row,column=col*2+1,sticky='ew',padx=3)
    form.columnconfigure(1,weight=1)
    form.columnconfigure(3,weight=1)
    status=ttk.Label(content,text='Enter declaration and explicit line items; opening does not save anything.',wraplength=1050)
    status.pack(fill='x',padx=12,pady=4)
    tabs=ttk.Notebook(content)
    tabs.pack(fill='both',expand=True,padx=12,pady=4)
    compose=ttk.Frame(tabs); history=ttk.Frame(tabs)
    tabs.add(compose,text='Compose draft'); tabs.add(history,text='Saved draft history')
    region=tk.StringVar(master=window)
    top=ttk.Frame(compose); top.pack(fill='x',padx=5,pady=4)
    ttk.Label(top,text='Requested delivery region').pack(side='left')
    ttk.Entry(top,textvariable=region,width=15).pack(side='left',padx=4)
    ttk.Label(compose,text='One item per line: description | quantity | unit | scheme | code (maximum 16)').pack(anchor='w',padx=5)
    item_input=ScrolledText(compose,height=4,wrap='none'); item_input.pack(fill='x',padx=5,pady=4)
    current=ScrolledText(compose,wrap='word',state='disabled'); current.pack(fill='both',expand=True,padx=5,pady=4)
    tree=ttk.Treeview(history,columns=('id','state','created'),show='headings',height=5,selectmode='browse')
    for key,label,width in (('id','Draft fingerprint',480),('state','Local state',270),('created','Created UTC',240)):
        tree.heading(key,text=label); tree.column(key,width=width,anchor='w')
    tree.pack(fill='x',padx=5,pady=5)
    detail=ScrolledText(history,wrap='word',state='disabled'); detail.pack(fill='both',expand=True,padx=5,pady=4)
    records={}; displayed=None; timer=None; closed=False

    def write(widget,text):
        widget.configure(state='normal'); widget.delete('1.0','end'); widget.insert('end',text); widget.configure(state='disabled')

    def clear(message):
        nonlocal displayed
        displayed=None; records.clear()
        for key in tree.get_children(): tree.delete(key)
        write(current,''); write(detail,''); status.configure(text=message)
        ack_button.configure(state='disabled')

    def error(exc):
        clear('Operator unavailable or blocked; check declaration, source, plan and halt. ('+type(exc).__name__+')')

    def fields(): return {key:var.get() for key,var in values.items()}
    def arguments(): return fields(),region.get(),item_input.get('1.0','end-1c')

    def prepare():
        try:
            result=workspace.prepare(*arguments())
            write(current,'Draft fingerprint: '+result['draft_id']+'\n\n'+render_rfq(result,halted=False))
            status.configure(text='Unverified local preview; not saved or authorized.')
            tabs.select(compose)
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc: error(exc)

    def display(_event=None):
        nonlocal displayed
        if blocked_check() is not False:
            clear('Operator halted or busy; refresh explicitly.'); return
        selected=tree.selection()
        if not selected or selected[0] not in records:
            displayed=None; write(detail,''); ack_button.configure(state='disabled'); return
        displayed=selected[0]
        row=records[displayed]
        write(detail,record_text(row))
        ack_button.configure(state='normal' if row['supplier_scope_pinned'] and row['acknowledged_at'] is None else 'disabled')

    def populate(result,select=None):
        nonlocal displayed
        displayed=None; records.clear(); write(detail,''); ack_button.configure(state='disabled')
        for key in tree.get_children(): tree.delete(key)
        for row in result['rows']:
            key=row['draft']['draft_id']; records[key]=row
            tree.insert('','end',iid=key,values=(key,row['state'],row['created_at']))
        status.configure(text=f"{len(records)} historical drafts shown"+(' (truncated; maximum 100)' if result['truncated'] else '')+'. No current decision.')
        tabs.select(history)
        if select in records:
            tree.selection_set(select); display()

    def refresh(select=None):
        try:
            result=workspace.history_list(); populate(result,select); return result
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc: error(exc)

    def save():
        try:
            result=workspace.save(*arguments())
            key=result['draft']['draft_id']
            write(current,'Saved immutable draft: '+key+'\n\n'+render_rfq(result['draft'],halted=False))
            refresh(key)
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc: error(exc)

    def acknowledge(smoke_confirm=False):
        try:
            key=displayed
            if key is None or tree.selection()!=(key,) or records[key]['supplier_scope_pinned'] is not True:
                raise ValueError('select and inspect one saved scoped draft')
            original=fields()
            if not smoke_confirm and not messagebox.askyesno('Local acknowledgment only',
                    'Acknowledge this exact historical draft? This does not verify a recipient or authorize sending.\n'+key,parent=window):
                return None
            if displayed!=key or tree.selection()!=(key,) or original!=fields():
                raise ValueError('selection or declaration changed')
            result=workspace.acknowledge(key,original,confirmed=True)
            refresh(key)
            return result
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc: error(exc)

    def changed(*_):
        write(current,'')
        status.configure(text='Declaration or inputs edited; preview cleared. Saved drafts remain immutable.')

    def item_changed(_event=None):
        if item_input.edit_modified():
            item_input.edit_modified(False); changed()

    def monitor():
        nonlocal timer
        if closed: return
        if blocked_check() is not False:
            clear('Operator halted or busy; previous display cleared.')
        timer=window.after(250,monitor)

    def destroyed(event):
        nonlocal closed
        if event.widget is window:
            closed=True
            if timer is not None:
                try: window.after_cancel(timer)
                except tk.TclError: pass

    buttons=ttk.Frame(content); buttons.pack(pady=5)
    for label,callback in (('Preview draft',prepare),('Save immutable draft',save),('Refresh saved drafts',refresh)):
        ttk.Button(buttons,text=label,command=callback).pack(side='left',padx=4)
    ack_button=ttk.Button(buttons,text='Acknowledge selected locally',command=acknowledge,state='disabled'); ack_button.pack(side='left',padx=4)
    from .correspondence_workspace import CorrespondenceWorkspace, open_correspondence_window
    def correspondence():
        try:
            workspace._permit()
            key=displayed
            if key is None or tree.selection()!=(key,) or records[key]['supplier_scope_pinned'] is not True:
                raise ValueError('select a saved scoped draft')
            record=workspace.history(key)
            return open_correspondence_window(window,CorrespondenceWorkspace(workspace,record['draft'],fields()))
        except (ValueError,PermissionError,OSError,sqlite3.Error,RuntimeError) as exc: error(exc)
    ttk.Button(buttons,text='Local correspondence',command=correspondence).pack(side='left',padx=4)
    tree.bind('<<TreeviewSelect>>',display)
    window.bind('<Destroy>',destroyed,add='+')
    for var in (*values.values(),region): var.trace_add('write',changed)
    item_input.bind('<<Modified>>',item_changed)
    monitor()
    if smoke:
        sample=dict(scheme='REGISTRY',identifier='SYNTHETIC-1',name='Synthetic supplier',
                    classifications='NAICS:518210',regions='US-CA',capacity='1000.00',
                    source_url='https://example.org/synthetic',observed_at=datetime.now(timezone.utc).isoformat())
        for key,value in sample.items(): values[key].set(value)
        region.set('US-CA'); item_input.insert('1.0','Document indexing | 10 | hour | NAICS | 518210')
        window.update_idletasks(); window.update()
        preview=prepare(); saved=save()
        if preview is None or saved is None or saved['draft']!=preview or saved['state']!='DRAFT_ONLY':
            raise RuntimeError('Operator GUI preview/save failed')
        key=saved['draft']['draft_id']
        result=refresh(key); window.update_idletasks(); window.update()
        if result is None or key not in records or 'HISTORICAL ONLY' not in detail.get('1.0','end'):
            raise RuntimeError('Operator GUI historical listing failed')
        reviewed=acknowledge(smoke_confirm=True)
        if reviewed is None or reviewed['state']!='LOCALLY_ACKNOWLEDGED_DRAFT_ONLY' or reviewed['send_enabled']:
            raise RuntimeError('Operator GUI acknowledgment boundary failed')
        child=open_correspondence_window(window,CorrespondenceWorkspace(workspace,reviewed['draft'],fields()),smoke=True)
        child.destroy()
    return window

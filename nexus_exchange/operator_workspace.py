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


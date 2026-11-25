"""Immutable hypothetical Scout inputs in the same local SQLite archive.

The trusted caller supplies a current declared profile, clock and halt state.
A saved plan is not evidence, authority, a verified budget or an executable job.
"""
from .cash_feasibility import COSTS, FIELDS, _bounded, _money, assess
from .checklist_store import _context, _hash, context_for
from .lead_store import LeadStore, _digest, _json, _now, _permit
from .schedule_feasibility import (
    PLAN_FIELDS, _iso, _optional_timestamp, _quantity, assess_schedule,
)
from .scout import _timestamp
import json

MAX_PLANS=10000
MAX_PAYLOAD=8192
_INPUT_FIELDS={"version","context","scenario","plan"}
_RECORD_FIELDS=_INPUT_FIELDS|{"created_at"}


def _amount(value):
    amount=_money(value)
    return None if amount is None else format(amount,".2f")


def _inputs(context, scenario, plan):
    context=_context(context)
    if context["profile_revision"] is None:
        raise ValueError("scenario requires declared profile revision")
    if type(scenario) is not dict or set(scenario)!=FIELDS or scenario["currency"]!="USD":
        raise ValueError("complete USD scenario required")
    costs=scenario["costs"]
    if type(costs) is not dict or set(costs)!=set(COSTS):
        raise ValueError("all cost categories required")
    if type(plan) is not dict or set(plan)!=PLAN_FIELDS:
        raise ValueError("complete schedule plan required")
    return dict(version=1,context=context,
        scenario=dict(currency="USD",compensation=_amount(scenario["compensation"]),
            probability_delivery_bps=_bounded(scenario["probability_delivery_bps"],10000),
            probability_payment_given_delivery_bps=_bounded(scenario["probability_payment_given_delivery_bps"],10000),
            delivery_days=_bounded(scenario["delivery_days"],3650),
            payment_days_after_delivery=_bounded(scenario["payment_days_after_delivery"],3650),
            labor_hours=_bounded(scenario["labor_hours"],87600),
            costs={k:_amount(costs[k]) for k in COSTS}),
        plan=dict(preparation_days=_quantity(plan["preparation_days"],3650),
            preparation_hours=_quantity(plan["preparation_hours"],87600),
            delivery_start=_iso(_optional_timestamp(plan["delivery_start"])),
            delivery_deadline=_iso(_optional_timestamp(plan["delivery_deadline"]))))


def _scope(context):
    return _digest(_json(context))


def _decode(row):
    plan_id,scope,created_at,encoded,digest=row
    if type(encoded) is not str or len(encoded)>MAX_PAYLOAD or _digest(encoded)!=digest:
        raise ValueError("stored scenario integrity mismatch")
    data=json.loads(encoded)
    if type(data) is not dict or set(data)!=_RECORD_FIELDS or type(data["version"]) is not int or data["version"]!=1:
        raise ValueError("invalid stored scenario schema")
    inputs=_inputs(data["context"],data["scenario"],data["plan"])
    stamp=_timestamp(data["created_at"])
    if stamp<_timestamp(inputs["context"]["retrieved_at"]):
        raise ValueError("stored scenario predates observation")
    canonical=dict(inputs,created_at=_iso(stamp))
    if (_json(canonical)!=encoded or _digest(_json(inputs))!=plan_id or
            _scope(inputs["context"])!=scope or canonical["created_at"]!=created_at):
        raise ValueError("stored scenario identity mismatch")
    return dict(canonical,plan_id=plan_id,independently_verified=False,
                execution_eligible=False,external_authority=False,genesis_verified=False)


class ScenarioStore(LeadStore):
    """Additive, single-user archive table. Existing LeadStore remains compatible.

    Reassessment only uses a currently resolved latest observation; obsolete
    plans remain readable as historical inputs but cannot be reassessed against
    a different observation or profile without explicitly saving a new plan.
    """
    def __init__(self,path):
        super().__init__(path)
        try:
            self.db.execute("""CREATE TABLE IF NOT EXISTS scout_scenarios_v1(
                plan_id TEXT PRIMARY KEY, scope TEXT NOT NULL, created_at TEXT NOT NULL,
                payload TEXT NOT NULL, digest TEXT NOT NULL)""")
            self.db.execute("""CREATE INDEX IF NOT EXISTS scout_scenario_scope_v1
                ON scout_scenarios_v1(scope,created_at DESC,plan_id)""")
        except BaseException:
            self.db.close()
            raise

    def _current(self,context,profile,now,halted):
        if profile is None:
            raise ValueError("current declared profile required")
        report=self.browse(now=now,source=context["source"],lead_key=context["lead_key"],
                           limit=1,profile=profile,halted=halted)
        if not report["leads"]:
            raise ValueError("archived observation unavailable")
        lead=report["leads"][0]
        if context_for(lead)!=context:
            raise ValueError("observation or profile changed; create a new scenario")
        return lead

    def get(self,plan_id,*,halted=None):
        _permit(halted)
        _hash(plan_id)
        row=self.db.execute("""SELECT plan_id,scope,created_at,payload,digest
            FROM scout_scenarios_v1 WHERE plan_id=?""",(plan_id,)).fetchone()
        return None if row is None else _decode(row)

    def list(self,context,*,limit=100,halted=None):
        _permit(halted)
        context=_context(context)
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError("invalid scenario list limit")
        rows=self.db.execute("""SELECT plan_id,scope,created_at,payload,digest
            FROM scout_scenarios_v1 WHERE scope=? ORDER BY created_at DESC,plan_id LIMIT ?""",
            (_scope(context),limit)).fetchall()
        result=[_decode(row) for row in rows]
        if any(item["context"]!=context for item in result):
            raise ValueError("stored scenario scope mismatch")
        return result

    def save(self,context,scenario,plan,*,profile,now,halted=None):
        _permit(halted)
        now=_now(now)
        inputs=_inputs(context,scenario,plan)
        context=inputs["context"]
        plan_id=_digest(_json(inputs))
        stamp=_iso(now)
        encoded=_json(dict(inputs,created_at=stamp))
        if len(encoded)>MAX_PAYLOAD:
            raise ValueError("scenario payload exceeds limit")
        # Same connection and write transaction freeze the archive while the
        # observation identity is resolved and the immutable row is inserted.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            lead=self._current(context,profile,now,halted)
            assess_schedule(lead=lead,profile=profile,scenario=inputs["scenario"],
                            plan=inputs["plan"],now=now,halted=halted)
            prior=self.get(plan_id,halted=halted)
            if prior is not None:
                if {k:prior[k] for k in _INPUT_FIELDS}!=inputs:
                    raise ValueError("conflicting immutable scenario")
                if _timestamp(prior["created_at"])>now:
                    raise ValueError("scenario clock moved backward")
            else:
                if self.db.execute("SELECT COUNT(*) FROM scout_scenarios_v1").fetchone()[0]>=MAX_PLANS:
                    raise ValueError("scenario capacity review required")
                self.db.execute("INSERT INTO scout_scenarios_v1 VALUES (?,?,?,?,?)",
                    (plan_id,_scope(context),stamp,encoded,_digest(encoded)))
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        return plan_id

    def evaluate(self,plan_id,*,profile,now,halted=None):
        _permit(halted)
        now=_now(now)
        self.db.execute("BEGIN")
        try:
            saved=self.get(plan_id,halted=halted)
            if saved is None:
                raise ValueError("saved scenario unavailable")
            if now<_timestamp(saved["created_at"]):
                raise ValueError("evaluation predates scenario")
            lead=self._current(saved["context"],profile,now,halted)
            cash=assess(lead=lead,profile=profile,scenario=saved["scenario"],halted=halted)
            schedule=assess_schedule(lead=lead,profile=profile,scenario=saved["scenario"],
                                     plan=saved["plan"],now=now,halted=halted)
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        return dict(plan_id=plan_id,context=saved["context"],evaluated_at=_iso(now),
                    cash=cash,schedule=schedule,independently_verified=False,
                    execution_eligible=False,external_authority=False,genesis_verified=False)

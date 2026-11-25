"""Advisory search prioritization from locally consistent historical receipts.

No provider claims, probability model, revenue estimate, automatic search,
credential storage, or change to the reviewed search plan. Receipt hashes
are local consistency checks, not independent authentication.
"""
from datetime import timedelta
from fractions import Fraction

from .lead_store import _json, _digest, _now, _permit
from .scout import _timestamp
from .discovery_history import (
    FORMAT as RECEIPT_FORMAT, _validate, _scope, _filter, recent_hint, _stamp,
)
from .scout_discovery import build_plan, READY, TTL, MAX_OPTIONS

FORMAT="nexus-scout-discovery-performance-v1"
LOOKBACK=timedelta(days=7)
MIN_COMPLETE=3
MAX_HISTORY=100
_FLAGS=("external_authority","execution_eligible","automatic_search_enabled",
        "commercial_value_verified","provider_freshness_verified",
        "independently_verified")
_LABELS={
    "MEASURED_REVIEW":"Measured history",
    "EXPLORE_UNMEASURED":"Explore unmeasured filter",
    "SMALL_SAMPLE_REVIEW":"Small sample",
    "INCOMPLETE_COLLECTION_REVIEW":"Review incomplete collection",
    "RECENT_REPEAT_REVIEW":"Recent repeat; review existing results",
    "HELD":"Held by search plan",
}


def empty_history(now):
    return dict(format="nexus-scout-search-history-v1",rows=[],returned=0,total=0,
                truncated=False,evaluated_at=_now(now).isoformat(timespec="microseconds"),
                external_authority=False)


def _receipts(history,now):
    """Validate the bounded projection supplied by LeadStore.search_history.

    Archive consistency itself is established by that read, not by trusting
    arbitrary caller data as independent evidence.
    """
    if (type(history) is not dict or history.get("format")!="nexus-scout-search-history-v1"
            or history.get("external_authority") is not False
            or type(history.get("rows")) is not list or len(history["rows"])>MAX_HISTORY
            or type(history.get("returned")) is not int or history["returned"]!=len(history["rows"])
            or type(history.get("total")) is not int or not history["returned"]<=history["total"]<=2000
            or type(history.get("truncated")) is not bool
            or history["truncated"]!=(history["returned"]<history["total"])
            or _stamp(history.get("evaluated_at"))>now):
        raise ValueError("Invalid search history snapshot.")
    result=[]
    seen=set()
    for row in history["rows"]:
        if type(row) is not dict or row.get("historical_only") is not True:
            raise ValueError("Historical receipt required.")
        if any(type(row.get(key)) is not bool for key in ("future_dated","local_archive_consistent")):
            raise ValueError("Receipt consistency state missing.")
        raw={k:v for k,v in row.items() if k not in
             ("receipt_sha256","historical_only","future_dated","local_archive_consistent")}
        checked=_validate(raw)
        if (row.get("receipt_sha256")!=_digest(_json(checked))
                or row["task_id"] in seen
                or row["future_dated"]!=(_stamp(row["completed_at"])>_stamp(history["evaluated_at"]))
                or (checked["format"]!=RECEIPT_FORMAT and row["local_archive_consistent"])):
            raise ValueError("Search receipt projection mismatch.")
        seen.add(row["task_id"])
        result.append(row)
    return result


def _metrics(rows):
    complete=[row for row in rows if not row["truncated"]]
    distinct={(ref[0],ref[1]) for row in complete for ref in row["observation_refs"]}
    return dict(completed_searches=len(rows),complete_searches=len(complete),
                incomplete_searches=len(rows)-len(complete),
                total_requests=sum(row["requests"] for row in rows),
                total_returned=sum(row["returned"] for row in rows),
                newly_archived_observations=sum(row["inserted"] for row in rows),
                complete_requests=sum(row["requests"] for row in complete),
                distinct_notice_identities=len(distinct))


def _order(item):
    stats=item["metrics"]
    rate=Fraction(stats["distinct_notice_identities"],max(1,stats["complete_requests"]))
    return (item["priority"],-rate if item["reason"]=="MEASURED_REVIEW" else Fraction(0),
            item["option_id"])


def analyze(profile,plan,history,*,now,halted=None):
    """Return a deterministic, non-authorizing ranking of unchanged options."""
    _permit(halted)
    now=_now(now)
    if type(plan) is not dict or type(plan.get("options")) is not list or len(plan["options"])>MAX_OPTIONS:
        raise ValueError("Exact discovery plan required.")
    planned=_timestamp(plan.get("planned_at"))
    if planned>now or _json(build_plan(profile,plan.get("capability_id"),now=planned,halted=False))!=_json(plan):
        raise ValueError("Discovery plan or profile changed.")
    expired=now-planned>TTL
    rows=_receipts(history,now)
    excluded=dict(unverified=0,future=0,outside_lookback=0,different_profile_or_catalogue=0)
    usable=[]
    for row in rows:
        completed=_stamp(row["completed_at"])
        if completed>now:
            excluded["future"]+=1
        elif not row["local_archive_consistent"] or row["format"]!=RECEIPT_FORMAT:
            excluded["unverified"]+=1
        elif now-completed>LOOKBACK:
            excluded["outside_lookback"]+=1
        elif (row["profile_revision"]!=plan["profile_revision"]
                or row["catalog_sha256"]!=plan["catalog_sha256"]):
            excluded["different_profile_or_catalogue"]+=1
        else:
            usable.append(row)
    groups={}
    for row in usable:
        groups.setdefault(row["filter_sha256"],[]).append(row)
    options=[]
    for option in plan["options"]:
        matched=groups.get(_filter(_scope(option)),[])
        metrics=_metrics(matched)
        hint=recent_hint(option,history,now=now)
        if option["state"]!=READY:
            priority,reason=5,"HELD"
        elif hint is not None:
            priority,reason=4,"RECENT_REPEAT_REVIEW"
        elif metrics["complete_searches"]>=MIN_COMPLETE:
            priority,reason=0,"MEASURED_REVIEW"
        elif not matched:
            priority,reason=1,"EXPLORE_UNMEASURED"
        elif metrics["complete_searches"]:
            priority,reason=2,"SMALL_SAMPLE_REVIEW"
        else:
            priority,reason=3,"INCOMPLETE_COLLECTION_REVIEW"
        options.append(dict(option_id=option["option_id"],source=option["source"],
            filter_value=option["filter_value"],procurement_type=option["procurement_type"],
            reason=reason,priority=priority,metrics=metrics,recent_hint=hint,
            **dict.fromkeys(_FLAGS,False)))
    options.sort(key=_order)
    # No suggestion when only recent, held, or incomplete-only choices exist.
    suggested=next((row["option_id"] for row in options if row["priority"]<=2),None) if not expired else None
    sources=[]
    for source in sorted({row["source"] for row in plan["options"]}):
        sources.append(dict(source=source,metrics=_metrics(
            [row for row in usable if row["scope"]["source"]==source])))
    payload=dict(format=FORMAT,plan_sha256=plan["plan_sha256"],
        evaluated_at=now.isoformat(timespec="microseconds"),plan_expired=expired,
        lookback_days=7,min_complete_searches=MIN_COMPLETE,history_displayed=history["returned"],
        history_total=history["total"],history_truncated=history["truncated"],
        usable_receipts=len(usable),excluded=excluded,source_metrics=sources,
        ranked_options=options,suggested_option_id=suggested,**dict.fromkeys(_FLAGS,False))
    return dict(payload,performance_sha256=_digest(_json(payload)))


def priority_label(row):
    return _LABELS[row["reason"]]


def option_performance_text(row):
    m=row["metrics"]
    rate=("Not measured" if not m["complete_requests"] else
          str(m["distinct_notice_identities"])+"/"+str(m["complete_requests"]))
    return "\n".join([
        "Historical research priority: "+priority_label(row),
        str(m["complete_searches"])+" complete / "+str(m["incomplete_searches"])+" incomplete searches",
        "Distinct source notice identities / requests in complete sample: "+rate,
        str(m["newly_archived_observations"])+" archived observations (not necessarily new notices)",
        "Measured ordering requires at least 3 complete searches. No probability of winning or revenue is inferred.",
    ])


def performance_text(report):
    lines=["SCOUT SEARCH PERFORMANCE — historical local evidence only",
           "Evaluated UTC: "+report["evaluated_at"],
           "Scope: latest "+str(report["history_displayed"])+" of "+str(report["history_total"])+
           " receipts; up to 7 days, same profile and catalogue.",
           "Locally consistent receipts used: "+str(report["usable_receipts"]),
           "Excluded: "+", ".join(key+"="+str(n) for key,n in sorted(report["excluded"].items())),
           "Incomplete collections remain visible but are excluded from measured yield.",
           "Failed and non-planner searches are absent; this is not a success-rate or income model.",
           "", "SOURCE SUMMARY"]
    for source in report["source_metrics"]:
        m=source["metrics"]
        lines.append(source["source"]+" | "+str(m["completed_searches"])+" searches | "+
            str(m["total_requests"])+" requests | "+str(m["incomplete_searches"])+" incomplete | "+
            str(m["distinct_notice_identities"])+" distinct notice identities in complete sample")
    lines.extend(["","REVIEW ORDER"])
    for index,row in enumerate(report["ranked_options"],1):
        lines.append(str(index)+". "+row["source"]+" / "+(row["filter_value"] or "broad releases")+
            (" / "+row["procurement_type"] if row["procurement_type"] else "")+
            " — "+priority_label(row)+
            (" [suggested for review]" if row["option_id"]==report["suggested_option_id"] else ""))
    lines.extend(["","Refresh to update the snapshot. Nothing is automatically searched, skipped, bid or purchased."])
    return "\n".join(lines)

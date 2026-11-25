"""Bounded SAM.gov v2 response parsing and search planning, strictly offline.

No transport, credential, live source authentication or commercial authority.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
import re

from .governor import Action, decide
from .scout import Opportunity, normalize, _text, _timestamp
from .council_screen import screen

ENDPOINT = "https://api.sam.gov/opportunities/v2/search"
MAX_BYTES = 2_000_000
MAX_PAGES = 10
MAX_LIMIT = 100
MAX_ATTEMPTS = 3
TYPES = frozenset(("Solicitation", "Combined Synopsis/Solicitation"))


def _guard(halted):
    if not decide(Action.RESEARCH_LOCAL, halted=halted).allowed:
        raise PermissionError("HALTED_OR_UNKNOWN")


@dataclass(frozen=True, slots=True)
class Search:
    start: date
    end: date
    title: str
    limit: int = 50
    pages: int = 3

    def params(self, offset):
        if (type(self.start) is not date or type(self.end) is not date
                or not 0 <= (self.end - self.start).days <= 30):
            raise ValueError("search window must be at most 31 calendar days")
        if type(self.limit) is not int or not 1 <= self.limit <= MAX_LIMIT:
            raise ValueError("invalid page limit")
        if type(self.pages) is not int or not 1 <= self.pages <= MAX_PAGES:
            raise ValueError("invalid page budget")
        if type(offset) is not int or not 0 <= offset < self.pages:
            raise ValueError("page budget exhausted")
        title = _text(self.title, 128)
        return {"postedFrom": self.start.strftime("%m/%d/%Y"),
                "postedTo": self.end.strftime("%m/%d/%Y"), "title": title,
                "limit": self.limit, "offset": offset}


@dataclass(frozen=True, slots=True)
class Notice:
    opportunity: Opportunity
    notice_type: str
    active: str | None
    issuer: str | None
    solicitation: str | None
    naics: str | None
    set_aside: str | None
    page_digest: str
    reasons: tuple[str, ...]

    @property
    def reviewable(self):
        # Missing price, eligibility, or authenticated source evidence prevents qualification.
        return not self.reasons


@dataclass(frozen=True, slots=True)
class Batch:
    notices: tuple[Notice, ...]
    pages: int
    complete: bool
    total_records: int


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject(_):
    raise ValueError("non-standard JSON number")


def _decode(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("invalid page size")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_reject, parse_float=Decimal)
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError("invalid SAM response JSON") from None
    if type(value) is not dict:
        raise ValueError("invalid SAM response envelope")
    return value


def _optional(value, limit):
    return None if value is None or value == "" else _text(value, limit)


def _notice(row, retrieved_at, now, digest):
    if type(row) is not dict:
        raise ValueError("invalid SAM notice")
    ident = row.get("noticeId")
    if type(ident) is not str or not re.fullmatch(r"[0-9a-f]{32}", ident):
        raise ValueError("invalid notice identifier")
    notice_type = _text(row.get("type"), 100)
    active = _optional(row.get("active"), 12)
    issuer = _optional(row.get("fullParentPathName"), 512)
    solicitation = _optional(row.get("solicitationNumber"), 256)
    naics = _optional(row.get("naicsCode"), 6)
    if naics is not None and not re.fullmatch(r"[0-9]{2,6}", naics):
        raise ValueError("invalid NAICS")
    set_aside = _optional(row.get("typeOfSetAside"), 64)
    deadline = row.get("responseDeadLine")
    if deadline is not None and deadline != "":
        # Never infer a time zone. Retain an unknown deadline for review.
        try:
            deadline = _timestamp(deadline).isoformat()
        except ValueError:
            deadline = None
    else:
        deadline = None
    # Award amounts are not solicitation prices. Ignore all award/contact/link fields.
    opportunity = normalize(dict(source="sam.gov", external_id=ident,
        title=row.get("title"), source_url="https://sam.gov/opp/"+ident+"/view",
        retrieved_at=retrieved_at, deadline=deadline, currency=None, amount=None))
    reasons = list(screen(opportunity, now=now).reasons)
    if notice_type not in TYPES:
        reasons.append("NOT_SOLICITATION")
    if active != "Yes":
        reasons.append("NOT_EXPLICITLY_ACTIVE")
    if not issuer:
        reasons.append("MISSING_ISSUER")
    if not solicitation:
        reasons.append("MISSING_SOLICITATION")
    reasons.extend(("SOURCE_AUTHENTICATION_REQUIRED", "ELIGIBILITY_AND_COST_UNVERIFIED"))
    return Notice(opportunity, notice_type, active, issuer, solicitation, naics,
                  set_aside, digest, tuple(reasons))


def parse_pages(search, pages, *, retrieved_at, now, halted=None):
    """Validate a contiguous bounded batch. Never silently accept a partial page.

    Input bytes are local fixtures or user-supplied exports, not authenticated.
    Returned records exclude contact details, attachments, raw URL and raw payload.
    """
    _guard(halted)
    if type(search) is not Search or type(pages) not in (list, tuple):
        raise ValueError("invalid search batch")
    search.params(0)
    if not 1 <= len(pages) <= search.pages:
        raise ValueError("invalid page count")
    if type(now) is not datetime or now.utcoffset() is None:
        raise ValueError("aware current time required")
    retrieved = _timestamp(retrieved_at)
    if retrieved > now:
        raise ValueError("future retrieval")
    total = None
    seen = set()
    notices = []
    for offset, raw in enumerate(pages):
        params = search.params(offset)
        data = _decode(raw)
        count, limit, index = (data.get(k) for k in ("totalRecords","limit","offset"))
        if (type(count) is not int or not 0 <= count <= 10_000_000
                or type(limit) is not int or limit != params["limit"]
                or type(index) is not int or index != offset):
            raise ValueError("inconsistent page metadata")
        if total is not None and total != count:
            raise ValueError("search changed during pagination")
        total = count
        remaining = total-offset*limit
        if remaining < 0 or (remaining == 0 and offset != 0):
            raise ValueError("page beyond result set")
        rows = data.get("opportunitiesData")
        if type(rows) is not list or len(rows) != min(limit, remaining):
            raise ValueError("incomplete page")
        digest = sha256(raw).hexdigest()
        for row in rows:
            notice = _notice(row, retrieved_at, now, digest)
            key = notice.opportunity.external_id
            if key in seen:
                raise ValueError("duplicate notice across search")
            seen.add(key)
            notices.append(notice)
    return Batch(tuple(notices), len(pages), len(notices) == total, total)

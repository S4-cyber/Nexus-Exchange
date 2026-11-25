"""Curated Scout source registry; documented access is not execution permission.

Source documentation reviewed 2026-11-24. No live connector implied by catalog.
"""
from dataclasses import dataclass
from types import MappingProxyType
from urllib.parse import urlsplit
import json
from .governor import Action, decide

@dataclass(frozen=True,slots=True)
class TradeSource:
    id: str
    name: str
    sector: str
    kind: str
    access: str
    priority: str
    url: str
    evidence: str
    scope: str
    check: str

_RAW = json.loads(r'''[
  {
    "id": "sam",
    "name": "SAM.gov",
    "sector": "US public procurement",
    "kind": "earned",
    "access": "key_api",
    "priority": "high",
    "url": "https://sam.gov/opportunities",
    "evidence": "https://open.gsa.gov/api/get-opportunities-public-api/",
    "scope": "Tested read-only adapter; live key and consent required.",
    "check": "Verify solicitation, registration, set-aside and contract clauses."
  },
  {
    "id": "california",
    "name": "Cal eProcure",
    "sector": "US public procurement",
    "kind": "earned",
    "access": "portal",
    "priority": "high",
    "url": "https://caleprocure.ca.gov/",
    "evidence": "https://www.dgs.ca.gov/PD/Resources/Page-Content/Procurement-Division-Resources-List-Folder/Cal-eProcure-Portal-to-Access-Bid-Opportunities",
    "scope": "Official bid portal and vendor alerts; automatic access not approved.",
    "check": "Verify California vendor eligibility and specific solicitation requirements."
  },
  {
    "id": "ramp",
    "name": "Los Angeles RAMP",
    "sector": "US public procurement",
    "kind": "earned",
    "access": "portal",
    "priority": "high",
    "url": "https://www.rampla.org/s/",
    "evidence": "https://cid.lacity.gov/business-services/business-response-unit",
    "scope": "Official regional opportunity portal; registration and alerts.",
    "check": "Verify local procurement, vendor requirements and lobbying rules."
  },
  {
    "id": "subnet",
    "name": "SBA SUBNet",
    "sector": "Subcontracting",
    "kind": "earned",
    "access": "portal",
    "priority": "high",
    "url": "https://www.sba.gov/counseling/prime-and-subcontracting/",
    "evidence": "https://www.sba.gov/counseling/prime-and-subcontracting/",
    "scope": "Official subcontracting resource; permission for automated collection unverified.",
    "check": "Verify prime, actual work, subcontract permissions and terms."
  },
  {
    "id": "usaspending",
    "name": "USAspending",
    "sector": "Subcontracting",
    "kind": "intelligence",
    "access": "public_api",
    "priority": "high",
    "url": "https://www.usaspending.gov/",
    "evidence": "https://api.usaspending.gov/docs/endpoints",
    "scope": "Public awards/subawards API; intelligence only, not open solicitations.",
    "check": "Find verified prime contractor and independent evidence of a current demand."
  },
  {
    "id": "ebuy",
    "name": "GSA eBuy",
    "sector": "US public procurement",
    "kind": "earned",
    "access": "qualified_portal",
    "priority": "later",
    "url": "https://www.ebuy.gsa.gov/",
    "evidence": "https://www.ebuy.gsa.gov/",
    "scope": "Requests available to eligible contract holders/categories.",
    "check": "Verify applicable awarded schedule and SIN access."
  },
  {
    "id": "ted",
    "name": "EU TED",
    "sector": "International procurement",
    "kind": "earned",
    "access": "public_api",
    "priority": "high",
    "url": "https://ted.europa.eu/en/",
    "evidence": "https://ted.europa.eu/en/simap/developers-corner-for-reusers",
    "scope": "Anonymous documented notice search API.",
    "check": "Verify procedure stage, supplier eligibility, local law and delivery requirements."
  },
  {
    "id": "uk_tender",
    "name": "UK Find a Tender",
    "sector": "International procurement",
    "kind": "earned",
    "access": "public_api",
    "priority": "high",
    "url": "https://www.find-tender.service.gov.uk/",
    "evidence": "https://www.gov.uk/government/publications/open-contracting",
    "scope": "Official OCDS release package API.",
    "check": "Compile incremental releases correctly; verify latest stage, deadlines and eligibility."
  },
  {
    "id": "uk_contracts",
    "name": "UK Contracts Finder",
    "sector": "International procurement",
    "kind": "earned",
    "access": "public_api",
    "priority": "high",
    "url": "https://www.contractsfinder.service.gov.uk/",
    "evidence": "https://www.gov.uk/government/publications/open-contracting",
    "scope": "Official OCDS API with different schema mapping.",
    "check": "Verify schema version, deduplicate cross-portal notices and check open status."
  },
  {
    "id": "canada",
    "name": "CanadaBuys",
    "sector": "International procurement",
    "kind": "earned",
    "access": "open_dataset",
    "priority": "high",
    "url": "https://open.canada.ca/data/dataset/6abd20d4-7a1c-4b38-baa2-9525d0bb2fd2/resource/5870de7c-86fe-4d05-8d73-cd412e12fdeb",
    "evidence": "https://open.canada.ca/data/dataset/6abd20d4-7a1c-4b38-baa2-9525d0bb2fd2/resource/5870de7c-86fe-4d05-8d73-cd412e12fdeb",
    "scope": "Official open-tender CSV; validate schema and refresh time.",
    "check": "Verify originating tender and Canadian or trade-agreement eligibility."
  },
  {
    "id": "world_bank",
    "name": "World Bank procurement",
    "sector": "International procurement",
    "kind": "earned",
    "access": "public_api",
    "priority": "high",
    "url": "https://projects.worldbank.org/en/projects-operations/opportunities",
    "evidence": "https://datacatalog.worldbank.org/search/dataset/0037795/world-bank-procurement-notices",
    "scope": "Procurement dataset and API documented; CC BY 4.0 metadata.",
    "check": "Verify borrower, active notice, selection method and eligibility."
  },
  {
    "id": "ungm",
    "name": "UN Global Marketplace",
    "sector": "International procurement",
    "kind": "earned",
    "access": "qualified_portal",
    "priority": "medium",
    "url": "https://www.ungm.org/",
    "evidence": "https://developer.ungm.org/",
    "scope": "Official UN procurement; developer API access and scopes require review.",
    "check": "Verify vendor registration, opportunity requirements and actual API permission."
  },
  {
    "id": "ita",
    "name": "ITA Trade Leads",
    "sector": "International trade",
    "kind": "earned",
    "access": "key_api",
    "priority": "high",
    "url": "https://www.trade.gov/data",
    "evidence": "https://developer.trade.gov/apis",
    "scope": "Official international trade lead API documented; access/credentials and freshness to validate.",
    "check": "Verify original opportunity, eligibility, export controls and payment terms."
  },
  {
    "id": "ustda",
    "name": "USTDA Trade Leads",
    "sector": "International trade",
    "kind": "earned",
    "access": "api_review",
    "priority": "medium",
    "url": "https://ustda.gov/dataset/trade-lead-api/",
    "evidence": "https://ustda.gov/dataset/trade-lead-api/",
    "scope": "Official emerging-market lead API; endpoint and access need validation.",
    "check": "Check US-company eligibility and cross-border compliance."
  },
  {
    "id": "sap",
    "name": "SAP Business Network",
    "sector": "Private B2B",
    "kind": "earned",
    "access": "qualified_portal",
    "priority": "medium",
    "url": "https://www.sap.com/products/business-network/suppliers/overview.html",
    "evidence": "https://help.sap.com/docs/business-network-for-supply-chain/introduction-to-business-network/benefits-of-using-sap-business-network",
    "scope": "Supplier discovery and sourcing requests; account and permissions required.",
    "check": "Verify buyer relationship, fees, terms and supplier capability."
  },
  {
    "id": "upwork",
    "name": "Upwork",
    "sector": "Digital services",
    "kind": "earned",
    "access": "approved_api",
    "priority": "high",
    "url": "https://www.upwork.com/",
    "evidence": "https://support.upwork.com/hc/en-us/articles/43342677368467-Use-bots-and-other-automation-properly",
    "scope": "Automation requires approved API use case; no scraping.",
    "check": "Verify account, proposal costs, AI disclosure, platform rules and work scope."
  },
  {
    "id": "challenges",
    "name": "USA.gov challenges",
    "sector": "Prize competitions",
    "kind": "prize",
    "access": "portal",
    "priority": "medium",
    "url": "https://www.usa.gov/find-active-challenge",
    "evidence": "https://www.usa.gov/challenge-how-to-participate",
    "scope": "Current official federal challenge index; prizes are contingent, not receivables.",
    "check": "Verify sponsor rules, entry eligibility, intellectual property and prize conditions."
  },
  {
    "id": "grants",
    "name": "Grants.gov",
    "sector": "Restricted funding",
    "kind": "funding",
    "access": "public_api",
    "priority": "medium",
    "url": "https://www.grants.gov/",
    "evidence": "https://www.grants.gov/api/common/search2",
    "scope": "Public search2 API, no authentication required; grants are not earned revenue.",
    "check": "Verify eligible applicant, allowable uses, match and award conditions."
  },
  {
    "id": "ebay",
    "name": "eBay Browse",
    "sector": "Asset intelligence",
    "kind": "intelligence",
    "access": "approved_api",
    "priority": "later",
    "url": "https://developer.ebay.com/develop/api/buy/browse_api",
    "evidence": "https://developer.ebay.com/develop/api/buy/browse_api",
    "scope": "Documented listing API with application token and applicable approvals.",
    "check": "Listings are asking prices, not verified buyers or profits; no inventory acquisition."
  },
  {
    "id": "gsa_auctions",
    "name": "GSA Auctions",
    "sector": "Asset intelligence",
    "kind": "intelligence",
    "access": "portal",
    "priority": "later",
    "url": "https://www.gsa.gov/buy-through-us/government-property-for-sale-or-lease/office-of-personal-property-management/for-citizens-seeking-surplus-property/how-to-purchase-surplus-property",
    "evidence": "https://www.gsa.gov/buy-through-us/government-property-for-sale-or-lease/office-of-personal-property-management/for-citizens-seeking-surplus-property/how-to-purchase-surplus-property",
    "scope": "Official surplus asset sales; research only under no-inventory model.",
    "check": "Verify ownership, title, fees, removal, and authority; no bidding or purchase."
  },
  {
    "id": "amazon_affiliate",
    "name": "Amazon Associates",
    "sector": "Affiliate revenue",
    "kind": "earned",
    "access": "qualified_portal",
    "priority": "medium",
    "url": "https://affiliate-program.amazon.com/",
    "evidence": "https://affiliate-program.amazon.com/help/operating/agreement/",
    "scope": "Official affiliate program; admission and program rules apply.",
    "check": "Verify approved channel, disclosure, permitted promotion and actual commission terms."
  },
  {
    "id": "hackerone",
    "name": "HackerOne directory",
    "sector": "Prize competitions",
    "kind": "prize",
    "access": "restricted_research",
    "priority": "later",
    "url": "https://docs.hackerone.com/en/articles/8410373-directory",
    "evidence": "https://docs.hackerone.com/en/articles/8410373-directory",
    "scope": "Directory of security programs; no automated security testing authorized.",
    "check": "Verify exact program scope, authorization, safe harbor and reward terms before any separate activity."
  },
  {
    "id": "csl",
    "name": "ITA Consolidated Screening List",
    "sector": "Verification",
    "kind": "compliance",
    "access": "key_api",
    "priority": "high",
    "url": "https://www.trade.gov/data",
    "evidence": "https://developer.trade.gov/apis",
    "scope": "Official export screening API; potential matches require official-list confirmation.",
    "check": "No automatic compliance clearance; check authoritative sanctions/export lists."
  }
]''')
SOURCES = tuple(TradeSource(**row) for row in _RAW)
_BY_ID = MappingProxyType({source.id:source for source in SOURCES})
KINDS = ("earned","intelligence","funding","prize","compliance")
ACCESS = ("public_api","key_api","open_dataset","portal","qualified_portal","api_review","approved_api","restricted_research")

def get_source(source_id):
    if type(source_id) is not str or source_id not in _BY_ID:
        raise ValueError("unknown curated source")
    return _BY_ID[source_id]

def official_url(source_id, *, evidence=False, halted=None):
    if halted is not False:
        raise PermissionError("HALTED_OR_UNKNOWN")
    if type(evidence) is not bool:
        raise ValueError("invalid link selector")
    source=get_source(source_id)
    return source.evidence if evidence else source.url

def catalog(*, kind=None, sector=None, query="", halted=None):
    decision=decide(Action.RESEARCH_LOCAL,halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    if kind is not None and kind not in KINDS:
        raise ValueError("unknown source kind")
    if sector is not None and (type(sector) is not str or sector not in {s.sector for s in SOURCES}):
        raise ValueError("unknown sector")
    if type(query) is not str or len(query)>120 or any(ord(c)<32 for c in query):
        raise ValueError("invalid catalog search")
    needle=query.casefold()
    return tuple(sorted((s for s in SOURCES if (kind is None or s.kind==kind)
        and (sector is None or s.sector==sector)
        and needle in " ".join((s.name,s.sector,s.scope,s.check)).casefold()),
        key=lambda s:({"high":0,"medium":1,"later":2}[s.priority],s.name.casefold())))

def source_tasks(source_id, *, halted=None):
    if halted is not False:
        raise PermissionError("HALTED_OR_UNKNOWN")
    source=get_source(source_id)
    return ("Confirm current source access terms and approved API or manual scope.",
        source.check,"Verify current opportunity and all pre-payment cash costs.",
        "Confirm applicable licensing, owner authority and payment/delivery terms.")

def readiness(source_id, *, halted=None):
    if halted is not False:
        raise PermissionError("HALTED_OR_UNKNOWN")
    source=get_source(source_id)
    return {"source_id":source.id,"research_only":True,
        "adapter_status":"SAM adapter tested with mocks; live pilot pending" if source.id=="sam" else "catalog only",
        "income_kind":source.kind,"cash_exposure":None,"zero_capital_verified":False,
        "external_authority":False,"execution_eligible":False}

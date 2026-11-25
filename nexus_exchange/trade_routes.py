"""Conservative route taxonomy. Classification is never legal clearance."""
from dataclasses import dataclass
from types import MappingProxyType
from .governor import Action, decide

@dataclass(frozen=True,slots=True)
class Route:
    key: str
    description: str
    revenue_model: str
    capital: str
    gate: str
    requirement: str

ROUTES=(
    Route("digital_service","Direct digital services","Fixed deliverable fee","zero_candidate","contract_review","Verify client, actual skill, data rights, scope and acceptance."),
    Route("subcontract","Perform subcontracted services","Subcontract payment","zero_candidate","contract_review","Verify prime, flow-down clauses, permission, and actual performance."),
    Route("public_procurement","Direct government contracting","Contract payment","conditional","public_contract_review","Verify registration, certifications, procurement terms and performance."),
    Route("private_sourcing","B2B sourcing and supplier discovery","Written service fee","zero_candidate","contract_review","Check sector, agency duties, disclosure, fee and client consent."),
    Route("affiliate","Affiliate and reseller introductions","Program-authorized commission","conditional","program_review","Verify approved marketing channel, attribution, disclosure and platform terms."),
    Route("digital_licensing","Own software, media or IP licensing","License fee or royalty","conditional","rights_review","Verify IP ownership, permitted transfer, privacy and license terms."),
    Route("tech_transfer","Technology transfer research","Potential licensed commercialization","conditional","rights_review","Verify patent owner, licensing terms, fees and commercialization rights."),
    Route("export","Cross-border sourcing and services","Permitted service or sales fee","conditional","trade_compliance","Verify sanctions, export controls, jurisdiction, customs and payment terms."),
    Route("prize","Competitions and authorized bounties","Contingent prize","conditional","program_review","No guaranteed reward; verify rules and exact authorization; no automated testing."),
    Route("grant","Eligible restricted funding","Restricted award, not earned income","conditional","funding_review","Verify eligibility, allowable uses, match and reporting."),
    Route("asset_intel","Asset and surplus-market intelligence","Research or independently agreed service fee","research_only","no_inventory","No buying, warehousing or bidding; check ownership and sector rules."),
    Route("real_estate","Real estate and business opportunity brokerage","Regulated fee or commission","restricted","licensed_only","California BPC 10131 and applicable licensing/exemptions; legal review."),
    Route("freight","Freight brokerage","Regulated brokerage fee","restricted","licensed_only","FMCSA authority, financial security and other requirements."),
    Route("customs","Customs brokerage","Regulated brokerage fee","restricted","licensed_only","CBP licensing and scope of authority."),
    Route("securities","Securities and investment introductions","Regulated transaction compensation","restricted","licensed_only","SEC and applicable state registration/exemption; no solicitation or execution."),
    Route("credit","Commercial loan or mortgage brokerage","Regulated brokerage fee","restricted","licensed_only","Applicable DFPI/NMLS and mortgage licensing or exemption."),
    Route("insurance","Insurance distribution","Regulated commission","restricted","licensed_only","Applicable producer license, appointments and authority."),
)
_BY_KEY=MappingProxyType({r.key:r for r in ROUTES})

def route_assessment(key,*,halted=None):
    decision=decide(Action.EVALUATE,halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    if type(key) is not str or key not in _BY_KEY:
        raise ValueError("unknown commercial route")
    route=_BY_KEY[key]
    return {"route":route,"research_only":True,"external_authority":False,
        "execution_eligible":False,"license_or_legal_review_required":route.gate in
        ("licensed_only","trade_compliance","public_contract_review"),
        "zero_capital_verified":False,"cash_exposure":None,
        "earned_revenue_candidate":route.key not in ("prize","grant","asset_intel") and route.gate!="licensed_only"}

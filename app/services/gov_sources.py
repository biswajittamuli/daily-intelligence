"""Catalogue of official government, PSU and examination recruitment sources (v5, source-first).

Every entry was requested once through the app's polite fetcher on ``VERIFIED_ON`` (robots.txt respected, no
challenge bypassed). ``access`` records what that showed:

    direct       the listing page answered with readable HTML/XML containing notice links — polled incrementally
    render       the page is a JavaScript shell; it is read with the local headless browser during Discover runs
    provider     the server sends an incomplete TLS chain, so a verified direct connection is impossible; the page
                 is read through the search provider's fetch tool during Discover runs
    search       the site answers this app with a bot challenge. The challenge is never bypassed: only
                 search-engine results (title, link, excerpt) are used, during Discover runs
    unavailable  robots.txt disallows the path, or the site refuses/has no reachable careers page; never fetched

Sources are polled, never assumed to work: a source only counts as successful when it produced records.
Aggregators and news feeds are *signals*: they point at an opportunity, and are never stored as its
organization or as the canonical application record.

Add a source by appending a ``GovSource``; do not add a URL that has not been requested and seen to work.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit

VERIFIED_ON = "2026-11-16"


@dataclass(frozen=True)
class GovSource:
    id: str
    name: str
    org: str  # organization recorded on notices from this source ("" for aggregators / news)
    category: str  # exam | state_psc | science | psu | finance | news | aggregator
    url: str
    kind: str = "listing"  # listing | listing+pdf | calendar | rss
    parser: str = "links"  # links | table | json | rss
    cadence_hours: int = 12
    official: bool = True
    enabled: bool = True
    access: str = "direct"
    note: str = ""
    aliases: tuple[str, ...] = ()

    @property
    def registry_id(self) -> str:
        return f"gov:{self.id}"

    @property
    def host(self) -> str:
        return (urlsplit(self.url).hostname or "").casefold().removeprefix("www.")

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "registry_id": self.registry_id, "host": self.host, "verified_on": VERIFIED_ON}


def _s(*args: Any, **kwargs: Any) -> GovSource:
    return GovSource(*args, **kwargs)


SOURCES: list[GovSource] = [
    # ------------------------------------------------------------------ examinations (central)
    _s("ibps", "IBPS recruitment", "Institute of Banking Personnel Selection", "exam",
       "https://www.ibps.in/index.php/recruitment/", aliases=("IBPS",)),
    _s("sbi", "SBI current openings", "State Bank of India", "exam",
       "https://sbi.bank.in/web/careers/current-openings", "listing+pdf", aliases=("SBI", "State Bank")),
    _s("nta", "NTA notices", "National Testing Agency", "exam", "https://nta.ac.in/", "listing+pdf",
       aliases=("NTA", "UGC NET", "UGC-NET", "JEE", "CUET", "NEET")),
    _s("gate", "GATE 2027", "GATE 2027 (IIT Madras)", "exam", "https://gate2027.iitm.ac.in/", cadence_hours=24,
       aliases=("GATE",)),
    _s("apsc", "APSC", "Assam Public Service Commission", "state_psc", "https://apsc.nic.in/", "listing+pdf",
       aliases=("APSC", "Assam PSC")),
    _s("upsc", "UPSC", "Union Public Service Commission", "exam", "https://upsc.gov.in/examinations/active-examinations",
       access="search", note="upsc.gov.in answers this app with a bot challenge (HTTP 403)", aliases=("UPSC", "Civil Services")),
    _s("ssc", "SSC", "Staff Selection Commission", "exam", "https://ssc.gov.in/", access="render",
       note="single-page application: the notice board is rendered by JavaScript", aliases=("SSC", "CGL", "CHSL")),
    _s("rbi", "RBI opportunities", "Reserve Bank of India", "exam", "https://opportunities.rbi.org.in/Scripts/Vacancies.aspx",
       access="render", note="vacancy list is rendered by JavaScript", aliases=("RBI", "Reserve Bank")),
    _s("rrb", "RRB (Railway Recruitment Boards)", "Railway Recruitment Board", "exam", "https://www.rrbcdg.gov.in/",
       access="unavailable", note="TLS certificate does not match the host (rrbcdg.gov.in); regional board sites timed out",
       aliases=("RRB", "Railway Recruitment")),
    # ------------------------------------------------------------------ state public service commissions
    _s("uppsc", "UPPSC", "Uttar Pradesh Public Service Commission", "state_psc", "https://uppsc.up.nic.in/",
       cadence_hours=24),
    _s("bpsc", "BPSC", "Bihar Public Service Commission", "state_psc", "https://bpsc.bihar.gov.in/", "listing+pdf",
       cadence_hours=24),
    _s("tnpsc", "TNPSC", "Tamil Nadu Public Service Commission", "state_psc", "https://www.tnpsc.gov.in/", "listing+pdf",
       cadence_hours=24),
    _s("ukpsc", "UKPSC", "Uttarakhand Public Service Commission", "state_psc",
       "https://psc.uk.gov.in/candidate-corner/recruitment", "listing+pdf", cadence_hours=24),
    _s("tpsc", "TPSC", "Tripura Public Service Commission", "state_psc", "https://tpsc.tripura.gov.in/", "listing+pdf",
       cadence_hours=24),
    _s("npsc", "NPSC", "Nagaland Public Service Commission", "state_psc", "https://npsc.nagaland.gov.in/", "listing+pdf",
       cadence_hours=24),
    # ------------------------------------------------------------------ science & technology
    _s("isro", "ISRO careers", "Indian Space Research Organisation", "science", "https://www.isro.gov.in/Careers.html",
       aliases=("ISRO", "URSC", "VSSC", "ICRB")),
    _s("drdo", "DRDO vacancies", "Defence Research and Development Organisation", "science",
       "https://www.drdo.gov.in/drdo/en/offerings/vacancies", aliases=("DRDO",)),
    _s("rac", "DRDO RAC", "DRDO Recruitment & Assessment Centre", "science", "https://rac.gov.in/", "listing+pdf",
       aliases=("RAC",)),
    _s("barc", "BARC recruitment", "Bhabha Atomic Research Centre", "science", "https://www.barc.gov.in/careers/recruitment.html",
       "listing+pdf", aliases=("BARC",)),
    _s("csir", "CSIR recruitment", "Council of Scientific & Industrial Research", "science",
       "https://www.csir.res.in/en/career-opportunities/recruitment", "listing+pdf", aliases=("CSIR",)),
    _s("icmr", "ICMR employment", "Indian Council of Medical Research", "science",
       "https://www.icmr.gov.in/employment-opportunities", "listing+pdf", cadence_hours=24, aliases=("ICMR",)),
    _s("cdac", "C-DAC current jobs", "Centre for Development of Advanced Computing", "science",
       "https://www.cdac.in/index.aspx?id=current_jobs", "listing+pdf", aliases=("C-DAC", "CDAC")),
    _s("iitg", "IIT Guwahati recruitment", "Indian Institute of Technology Guwahati", "science",
       "https://www.iitg.ac.in/iitg_reqr", "listing+pdf", cadence_hours=24, aliases=("IIT Guwahati", "IITG")),
    _s("nic", "NIC careers", "National Informatics Centre", "science", "https://www.nic.in/careers/", access="search",
       note="nic.in answers this app with a bot challenge (HTTP 403)", aliases=("NIC", "National Informatics")),
    _s("meity", "MeitY vacancies", "Ministry of Electronics and Information Technology", "science",
       "https://www.meity.gov.in/vacancies", access="search", note="meity.gov.in answers this app with a bot challenge (HTTP 403)",
       aliases=("MeitY",)),
    _s("dst", "DST recruitment", "Department of Science and Technology", "science", "https://dst.gov.in/recruitment",
       access="render", note="page content is rendered by JavaScript", aliases=("DST",)),
    _s("nielit", "NIELIT recruitments", "National Institute of Electronics & Information Technology", "science",
       "https://www.nielit.gov.in/recruitments", access="provider", note="server sends an incomplete TLS certificate chain",
       aliases=("NIELIT",)),
    _s("cdot", "C-DOT careers", "Centre for Development of Telematics", "science", "https://www.cdot.in/cdotweb/web/careers.php",
       access="render", note="openings are loaded by JavaScript", aliases=("C-DOT", "CDOT")),
    # ------------------------------------------------------------------ public sector undertakings
    _s("ongc", "ONGC recruitment notices", "Oil and Natural Gas Corporation", "psu",
       "https://ongcindia.com/web/eng/career/recruitment-notice", "listing+pdf", aliases=("ONGC",)),
    _s("hpcl", "HPCL job openings", "Hindustan Petroleum Corporation Limited", "psu",
       "https://www.hindustanpetroleum.com/job-openings", "listing+pdf", aliases=("HPCL", "Hindustan Petroleum")),
    _s("bpcl", "BPCL careers", "Bharat Petroleum Corporation Limited", "psu",
       "https://www.bharatpetroleum.in/Job-Seekers/Careers.aspx", "listing+pdf", cadence_hours=24, aliases=("BPCL", "Bharat Petroleum")),
    _s("ntpc", "NTPC jobs", "NTPC Limited", "psu", "https://ntpc.co.in/jobs-ntpc", "listing+pdf", aliases=("NTPC",)),
    _s("powergrid", "POWERGRID job opportunities", "Power Grid Corporation of India", "psu",
       "https://www.powergrid.in/en/job-opportunities", "listing+pdf", aliases=("POWERGRID", "Power Grid", "PGCIL")),
    _s("nhpc", "NHPC jobs", "NHPC Limited", "psu", "https://www.nhpcindia.com/welcome/job", "listing+pdf", aliases=("NHPC",)),
    _s("npcil", "NPCIL careers", "Nuclear Power Corporation of India", "psu",
       "https://www.npcilcareers.co.in/MainSite/default.aspx", "listing+pdf", aliases=("NPCIL",)),
    _s("bhel", "BHEL careers", "Bharat Heavy Electricals Limited", "psu", "https://careers.bhel.in/index.jsp", "listing+pdf",
       aliases=("BHEL",)),
    _s("coalindia", "Coal India jobs", "Coal India Limited", "psu", "https://www.coalindia.in/career-cil/jobs-coal-india/",
       "listing+pdf", aliases=("Coal India", "CIL")),
    _s("ircon", "IRCON", "Ircon International Limited", "psu", "https://www.ircon.org/", "listing+pdf", cadence_hours=24,
       aliases=("IRCON",)),
    _s("mdl", "Mazagon Dock careers", "Mazagon Dock Shipbuilders Limited", "psu", "https://mazagondock.in/Careers.aspx",
       "listing+pdf", cadence_hours=24, aliases=("MDL", "Mazagon Dock")),
    _s("grse", "GRSE careers", "Garden Reach Shipbuilders & Engineers", "psu", "https://grse.in/career/", "listing+pdf",
       cadence_hours=24, aliases=("GRSE",)),
    _s("irel", "IREL careers", "IREL (India) Limited", "psu", "https://www.irel.co.in/careers", "listing+pdf", cadence_hours=24,
       aliases=("IREL",)),
    _s("eil", "EIL careers", "Engineers India Limited", "psu", "https://engineersindia.com/careers", "listing+pdf",
       cadence_hours=24, aliases=("EIL", "Engineers India")),
    _s("oil", "Oil India current openings", "Oil India Limited", "psu", "https://www.oil-india.com/advertisement-list",
       "listing+pdf", aliases=("Oil India", "OIL")),
    _s("nrl", "NRL careers", "Numaligarh Refinery Limited", "psu", "https://www.nrl.co.in/Careers", "listing+pdf",
       cadence_hours=24, aliases=("NRL", "Numaligarh")),
    _s("railtel", "RailTel careers", "RailTel Corporation of India", "psu", "https://www.railtel.in/careers.html",
       "listing+pdf", cadence_hours=24, aliases=("RailTel",)),
    _s("bsnl", "BSNL jobs", "Bharat Sanchar Nigam Limited", "psu",
       "https://www.bsnl.co.in/opencms/bsnl/BSNL/about_us/hrd/jobs.html", "listing+pdf", cadence_hours=24, aliases=("BSNL",)),
    _s("bis", "BIS recruitment", "Bureau of Indian Standards", "psu",
       "https://www.bis.gov.in/recruitment-career-opportunities/?lang=en", "listing+pdf", cadence_hours=24, aliases=("BIS",)),
    _s("iocl", "IOCL latest job openings", "Indian Oil Corporation Limited", "psu", "https://iocl.com/latest-job-opening",
       access="search", note="iocl.com answers this app with a redirect challenge", aliases=("IOCL", "Indian Oil")),
    _s("gail", "GAIL careers", "GAIL (India) Limited", "psu", "https://gailonline.com/", access="search",
       note="no stable public careers URL was found on gailonline.com (previous paths return 404)", aliases=("GAIL",)),
    _s("bel", "BEL job notifications", "Bharat Electronics Limited", "psu", "https://bel-india.in/job-notifications/",
       access="provider", note="server sends an incomplete TLS certificate chain", aliases=("BEL", "Bharat Electronics")),
    _s("sail", "SAIL careers", "Steel Authority of India Limited", "psu", "https://sail.co.in/en/careers", access="provider",
       note="server sends an incomplete TLS certificate chain; sailcareers.com is disallowed by robots.txt", aliases=("SAIL",)),
    _s("rites", "RITES careers", "RITES Limited", "psu", "https://www.rites.com/Career", access="provider",
       note="server sends an incomplete TLS certificate chain", aliases=("RITES",)),
    _s("concor", "CONCOR careers", "Container Corporation of India", "psu", "https://concorindia.co.in/career",
       access="provider", note="server sends an incomplete TLS certificate chain", aliases=("CONCOR",)),
    _s("nalco", "NALCO careers", "National Aluminium Company Limited", "psu", "https://nalcoindia.com/career/",
       access="provider", note="server sends an incomplete TLS certificate chain", aliases=("NALCO",)),
    _s("hal", "HAL careers", "Hindustan Aeronautics Limited", "psu", "https://hal-india.co.in/career", access="render",
       note="page content is rendered by JavaScript", aliases=("HAL", "Hindustan Aeronautics")),
    _s("nmdc", "NMDC careers", "NMDC Limited", "psu", "https://www.nmdc.co.in/careers", access="render",
       note="page content is rendered by JavaScript", aliases=("NMDC",)),
    _s("hsl", "HSL careers", "Hindustan Shipyard Limited", "psu", "https://www.hslvizag.in/careers", access="render",
       note="page content is rendered by JavaScript", aliases=("HSL", "Hindustan Shipyard")),
    _s("neepco", "NEEPCO careers", "North Eastern Electric Power Corporation", "psu", "https://neepco.co.in/careers",
       access="render", note="page content is rendered by JavaScript", aliases=("NEEPCO",)),
    _s("dfccil", "DFCCIL careers", "Dedicated Freight Corridor Corporation of India", "psu",
       "https://dfccil.com/Home/DynemicPages?MenuId=75", access="unavailable", note="the site refuses this app (HTTP 403)",
       aliases=("DFCCIL",)),
    _s("ecil", "ECIL jobs", "Electronics Corporation of India Limited", "psu", "https://www.ecil.co.in/jobs.html",
       access="unavailable", note="robots.txt disallows the site", aliases=("ECIL",)),
    _s("aai", "AAI recruitment", "Airports Authority of India", "psu", "https://www.aai.aero/en/careers/recruitment",
       access="unavailable", note="robots.txt disallows the site", aliases=("AAI", "Airports Authority")),
    # ------------------------------------------------------------------ financial institutions
    _s("nabard", "NABARD career notices", "National Bank for Agriculture and Rural Development", "finance",
       "https://www.nabard.org/careers-notices1.aspx?cid=693&id=26", "listing+pdf", cadence_hours=24, aliases=("NABARD",)),
    _s("sidbi", "SIDBI careers", "Small Industries Development Bank of India", "finance", "https://www.sidbi.in/en/careers",
       "listing+pdf", cadence_hours=24, aliases=("SIDBI",)),
    _s("lic", "LIC careers", "Life Insurance Corporation of India", "finance", "https://licindia.in/web/guest/careers",
       "listing+pdf", cadence_hours=24, aliases=("LIC",)),
    # ------------------------------------------------------------------ notification / news sources (signals)
    _s("empnews", "Employment News", "", "news", "https://employmentnews.gov.in/NewEmp/Home.aspx", cadence_hours=24),
    _s("ncs", "National Career Service", "", "news", "https://www.ncs.gov.in/", cadence_hours=24),
    _s("et_careers", "Economic Times — government jobs feed", "", "news",
       "https://economictimes.indiatimes.com/jobs/government-jobs/rssfeeds/107115.cms", "rss", "rss", cadence_hours=12,
       official=False),
    _s("hindu_careers", "The Hindu — careers feed", "", "news", "https://www.thehindu.com/education/careers/feeder/default.rss",
       "rss", "rss", cadence_hours=24, official=False),
    _s("pib", "Press Information Bureau", "", "news", "https://pib.gov.in/allRel.aspx", access="unavailable",
       note="pib.gov.in answers this app with a bot challenge (HTTP 403); press releases are not fetched"),
    _s("dopt", "DoPT", "", "news", "https://dopt.gov.in/", access="render", cadence_hours=24,
       note="page content is rendered by JavaScript"),
    # ------------------------------------------------------------------ aggregators (discovery signals only)
    _s("freejobalert", "FreeJobAlert (aggregator)", "", "aggregator", "https://www.freejobalert.com/latest-notifications/",
       cadence_hours=12, official=False),
    _s("indgovtjobs", "IndGovtJobs (aggregator)", "", "aggregator", "https://www.indgovtjobs.in/", cadence_hours=12,
       official=False),
    _s("sarkariresult", "Sarkari Result (aggregator)", "", "aggregator", "https://www.sarkariresult.com/latestjob/",
       cadence_hours=24, official=False),
]
BY_ID = {source.id: source for source in SOURCES}
assert len(BY_ID) == len(SOURCES), "duplicate government source id"

AGGREGATOR_HOSTS = {"freejobalert.com", "indgovtjobs.in", "sarkariresult.com", "sarkariresult.freejobalert.com",
                    "sarkariexam.com", "jagranjosh.com", "adda247.com", "testbook.com", "careerpower.in",
                    "rojgarresult.com", "govtjobsalert.in", "employmentnews.co.in", "freshersnow.com", "recruitment.guru",
                    "bankersadda.com", "gktoday.in", "freshersworld.com", "naukri.com", "shiksha.com", "collegedunia.com",
                    "byjus.com", "oliveboard.in", "safalta.com", "prepp.in", "careers360.com", "sarkarinaukriblog.com",
                    "indiatoday.in", "hindustantimes.com", "timesofindia.indiatimes.com", "livemint.com",
                    "economictimes.indiatimes.com", "thehindu.com", "ndtv.com", "news18.com"}
OFFICIAL_SUFFIXES = (".gov.in", ".nic.in", ".ac.in", ".res.in", ".edu.in", ".mil.in", ".gov")
SOCIAL_HOSTS = ("facebook.com", "twitter.com", "x.com", "youtube.com", "instagram.com", "t.me", "telegram.me",
                "whatsapp.com", "linkedin.com", "play.google.com", "apps.apple.com", "google.com", "wa.me")


def host_of(url: str) -> str:
    try:
        return (urlsplit(str(url or "")).hostname or "").casefold().removeprefix("www.")
    except ValueError:
        return ""


def _under(host: str, base: str) -> bool:
    return host == base or host.endswith("." + base)


def is_aggregator(url: str) -> bool:
    host = host_of(url)
    return bool(host) and any(_under(host, base) for base in AGGREGATOR_HOSTS)


_OFFICIAL_HOSTS = {source.host for source in SOURCES if source.official}
_OFFICIAL_BASES = {"sbi.bank.in", "sbi.co.in", "bank.sbi", "ibps.in", "ongcindia.com", "hindustanpetroleum.com",
                   "bharatpetroleum.in", "ntpc.co.in", "powergrid.in", "nhpcindia.com", "npcilcareers.co.in", "bhel.in",
                   "coalindia.in", "ircon.org", "mazagondock.in", "grse.in", "irel.co.in", "engineersindia.com",
                   "oil-india.com", "nrl.co.in", "railtel.in", "railtelindia.com", "bsnl.co.in", "iocl.com",
                   "gailonline.com", "bel-india.in", "sail.co.in", "rites.com", "concorindia.co.in", "nalcoindia.com",
                   "hal-india.co.in", "nmdc.co.in", "hslvizag.in", "neepco.co.in", "dfccil.com", "ecil.co.in", "aai.aero",
                   "nabard.org", "sidbi.in", "licindia.in", "cdac.in", "cdot.in", "rbi.org.in", "nta.ac.in"}


def is_official_url(url: str) -> bool:
    """True for government domains and the catalogue's own official hosts; never for aggregators or news sites."""
    host = host_of(url)
    if not host or is_aggregator(url):
        return False
    if host.endswith(OFFICIAL_SUFFIXES) or any(host == s.lstrip(".") for s in OFFICIAL_SUFFIXES):
        return True
    return host in _OFFICIAL_HOSTS or any(_under(host, base) for base in _OFFICIAL_BASES)


def source_for_url(url: str) -> GovSource | None:
    """The official catalogue source a URL belongs to (same registrable site), if any."""
    host = host_of(url)
    if not host:
        return None
    best = None
    for source in SOURCES:
        if not source.official or not source.org:
            continue
        base = source.host
        parts = base.split(".")
        # compare on the registrable part (last 2 labels, or 3 for *.gov.in / *.co.in style suffixes)
        tail = ".".join(parts[-3:] if len(parts) >= 3 and parts[-2] in {"gov", "co", "nic", "ac", "res", "org", "bank"} else parts[-2:])
        if _under(host, base) or _under(host, tail):
            if best is None or len(source.host) > len(best.host):
                best = source
    return best


def source_for_name(text: str) -> GovSource | None:
    """The catalogue source whose organization (or alias) is named in a headline."""
    best: tuple[int, GovSource] | None = None
    for source in SOURCES:
        if not source.org:
            continue
        for alias in (source.org, *source.aliases):
            if len(alias) < 3:
                continue
            flags = 0 if alias.isupper() and len(alias) <= 5 else re.I
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", text or "", flags):
                if best is None or len(alias) > best[0]:
                    best = (len(alias), source)
    return best[1] if best else None


def catalogue(overrides: dict[str, Any] | None = None) -> list[GovSource]:
    """Catalogue with the user's enable/disable choices applied ({source id: bool})."""
    overrides = overrides or {}
    output = []
    for source in SOURCES:
        if source.id in overrides and overrides[source.id] is not None:
            output.append(GovSource(**{**asdict(source), "enabled": bool(overrides[source.id])}))
        else:
            output.append(source)
    return output


def summary() -> dict[str, Any]:
    by_access: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for source in SOURCES:
        by_access[source.access] = by_access.get(source.access, 0) + 1
        by_category[source.category] = by_category.get(source.category, 0) + 1
    return {"total": len(SOURCES), "official": sum(1 for s in SOURCES if s.official and s.org),
            "official_direct": sum(1 for s in SOURCES if s.official and s.org and s.access == "direct"),
            "official_direct_enabled": sum(1 for s in SOURCES if s.official and s.org and s.access == "direct" and s.enabled),
            "by_access": by_access, "by_category": by_category, "verified_on": VERIFIED_ON}

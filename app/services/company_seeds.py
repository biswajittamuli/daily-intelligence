"""Built-in company registry seed (v5).

Three sources, each with its provenance recorded on the row:

* ``ats_sources.DEFAULT_COMPANIES`` — ATS boards verified live on 2026-11-08/09 (public Greenhouse, Lever, Ashby,
  SmartRecruiters, Workable APIs). Tenant is known, so these are scanned immediately.
* ``ats_sources.INDIAN_CAREER_SITES`` — Indian startups/established product companies. Only the official website
  is recorded; the scanner detects the ATS from the company's own careers page and never guesses a tenant.
* ``GCC_CORPORATE`` — global capability centres, engineering/R&D centres and Indian IT services companies. Only
  the company's official careers URL is recorded; the ATS is detected on the first scan.

Nothing is scraped from a logged-in network, and a company is only added here when its official domain is known.
The weekly scan backfills ``ats``/``tenant``/``careers_url`` from what each company's own page says.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from app.services.ats_sources import DEFAULT_COMPANIES, INDIAN_BOARDS, INDIAN_CAREER_SITES

SEED_VERSION = "2026-11-16.1"

# Official domains of the verified public boards in ats_sources.DEFAULT_COMPANIES.
BOARD_DOMAINS: dict[str, str] = {
    "groww": "groww.in", "databricks": "databricks.com", "mongodb": "mongodb.com", "gitlab": "gitlab.com",
    "cloudflare": "cloudflare.com", "stripe": "stripe.com", "coinbase": "coinbase.com", "rubrik": "rubrik.com",
    "airbnb": "airbnb.com", "hackerrank": "hackerrank.com", "druva": "druva.com", "elastic": "elastic.co",
    "cred": "cred.club", "meesho": "meesho.com", "zeta": "zeta.tech", "paytm": "paytm.com",
    "spotify": "spotify.com", "sarvam": "sarvam.ai", "notion": "notion.so", "openai": "openai.com",
    "linear": "linear.app", "ramp": "ramp.com", "plaid": "plaid.com", "supabase": "supabase.com",
    "posthog": "posthog.com", "swiggy": "swiggy.com", "freshworks": "freshworks.com", "upstox": "upstox.com",
    "unacademy": "unacademy.com", "cars24": "cars24.com", "whatfix": "whatfix.com", "ixigo": "ixigo.com",
    "inmobi": "inmobi.com", "glance": "glance.com", "highradius": "highradius.com", "sigmoid": "sigmoid.ai",
    "mindtickle": "mindtickle.com", "fampay": "fampay.in", "pocketfm": "pocketfm.com", "atlan": "atlan.com",
    "tekion": "tekion.com", "apna": "apna.co",
}

# Global capability centres, engineering/R&D centres and Indian IT services. (name, official domain, careers URL)
GCC_CORPORATE: list[tuple[str, str, str]] = [
    ("Google India", "google.com", "https://www.google.com/about/careers/applications/jobs/results/"),
    ("Microsoft India", "microsoft.com", "https://jobs.careers.microsoft.com/global/en/search"),
    ("Amazon India", "amazon.com", "https://www.amazon.jobs/en/"),
    ("Adobe India", "adobe.com", "https://careers.adobe.com/us/en"),
    ("Oracle India", "oracle.com", "https://careers.oracle.com/jobs/"),
    ("SAP India", "sap.com", "https://jobs.sap.com/"),
    ("IBM India", "ibm.com", "https://www.ibm.com/careers/search"),
    ("Cisco India", "cisco.com", "https://jobs.cisco.com/"),
    ("Intel India", "intel.com", "https://www.intel.com/content/www/us/en/jobs/locations/india.html"),
    ("Qualcomm India", "qualcomm.com", "https://careers.qualcomm.com/"),
    ("NVIDIA India", "nvidia.com", "https://www.nvidia.com/en-in/about-nvidia/careers/"),
    ("Salesforce India", "salesforce.com", "https://careers.salesforce.com/en/jobs/"),
    ("ServiceNow India", "servicenow.com", "https://careers.servicenow.com/"),
    ("Dell Technologies", "dell.com", "https://jobs.dell.com/"),
    ("Hewlett Packard Enterprise", "hpe.com", "https://careers.hpe.com/"),
    ("HP Inc", "hp.com", "https://jobs.hp.com/"),
    ("PayPal India", "paypal.com", "https://careers.pypl.com/"),
    ("Intuit India", "intuit.com", "https://www.intuit.com/careers/"),
    ("Uber India", "uber.com", "https://www.uber.com/us/en/careers/list/"),
    ("Walmart Global Tech India", "walmart.com", "https://careers.walmart.com/"),
    ("Target India", "target.com", "https://corporate.target.com/careers"),
    ("Lowe's India", "lowes.com", "https://talent.lowes.com/"),
    ("Tesco Technology India", "tesco.com", "https://www.tesco-careers.com/"),
    ("Shell India", "shell.com", "https://www.shell.com/careers.html"),
    ("HSBC India", "hsbc.com", "https://www.hsbc.com/careers"),
    ("Barclays India", "barclays.com", "https://home.barclays/careers/"),
    ("JPMorgan India", "jpmorganchase.com", "https://careers.jpmorgan.com/"),
    ("Goldman Sachs India", "goldmansachs.com", "https://www.goldmansachs.com/careers"),
    ("Morgan Stanley India", "morganstanley.com", "https://www.morganstanley.com/careers"),
    ("Citi India", "citi.com", "https://jobs.citi.com/"),
    ("Wells Fargo India", "wellsfargo.com", "https://www.wellsfargojobs.com/"),
    ("Deutsche Bank India", "db.com", "https://careers.db.com/"),
    ("UBS India", "ubs.com", "https://www.ubs.com/global/en/careers.html"),
    ("American Express India", "americanexpress.com", "https://www.americanexpress.com/en-us/careers/"),
    ("Mastercard India", "mastercard.com", "https://careers.mastercard.com/"),
    ("Visa India", "visa.com", "https://usa.visa.com/careers.html"),
    ("Fidelity India", "fidelity.com", "https://jobs.fidelity.com/"),
    ("Fiserv India", "fiserv.com", "https://careers.fiserv.com/"),
    ("FIS India", "fisglobal.com", "https://careers.fisglobal.com/"),
    ("Broadridge India", "broadridge.com", "https://www.broadridge.com/careers"),
    ("State Street India", "statestreet.com", "https://careers.statestreet.com/"),
    ("BNY India", "bnymellon.com", "https://www.bnymellon.com/careers.html"),
    ("Standard Chartered India", "sc.com", "https://www.sc.com/en/careers/"),
    ("Societe Generale India", "societegenerale.com", "https://careers.societegenerale.com/"),
    ("BNP Paribas India", "bnpparibas.com", "https://group.bnpparibas/en/careers"),
    ("Nomura India", "nomura.com", "https://www.nomura.com/careers/"),
    ("Macquarie India", "macquarie.com", "https://www.macquarie.com/careers"),
    ("BlackRock India", "blackrock.com", "https://careers.blackrock.com/"),
    ("Bloomberg India", "bloomberg.com", "https://www.bloomberg.com/company/careers/"),
    ("Thomson Reuters India", "thomsonreuters.com", "https://www.thomsonreuters.com/en/careers.html"),
    ("S&P Global India", "spglobal.com", "https://www.spglobal.com/en/careers"),
    ("Moody's India", "moodys.com", "https://careers.moodys.com/"),
    ("Experian India", "experian.com", "https://www.experian.com/careers/"),
    ("TransUnion India", "transunion.com", "https://www.transunion.com/careers"),
    ("Nielsen India", "nielsen.com", "https://www.nielsen.com/careers/"),
    ("Kantar India", "kantar.com", "https://www.kantar.com/careers"),
    ("McKinsey India", "mckinsey.com", "https://www.mckinsey.com/careers"),
    ("BCG India", "bcg.com", "https://careers.bcg.com/"),
    ("Bain India", "bain.com", "https://www.bain.com/careers/"),
    ("Accenture India", "accenture.com", "https://www.accenture.com/in-en/careers"),
    ("Deloitte India", "deloitte.com", "https://www.deloitte.com/in/en/careers.html"),
    ("EY India", "ey.com", "https://www.ey.com/en_in/careers"),
    ("KPMG India", "kpmg.com", "https://kpmg.com/in/en/home/careers.html"),
    ("PwC India", "pwc.com", "https://www.pwc.in/careers.html"),
    ("Capgemini India", "capgemini.com", "https://www.capgemini.com/in-en/careers/"),
    ("Cognizant India", "cognizant.com", "https://careers.cognizant.com/global/en"),
    ("Genpact", "genpact.com", "https://www.genpact.com/careers"),
    ("WNS", "wns.com", "https://www.wns.com/careers"),
    ("EXL Service", "exlservice.com", "https://www.exlservice.com/careers"),
    ("Bosch India", "bosch.in", "https://www.bosch.in/careers/"),
    ("Siemens India", "siemens.com", "https://www.siemens.com/global/en/company/jobs.html"),
    ("ABB India", "abb.com", "https://careers.abb/"),
    ("Schneider Electric India", "se.com", "https://www.se.com/in/en/about-us/careers/"),
    ("Philips India", "philips.com", "https://www.careers.philips.com/"),
    ("GE India", "ge.com", "https://jobs.gecareers.com/"),
    ("Honeywell India", "honeywell.com", "https://careers.honeywell.com/"),
    ("Emerson India", "emerson.com", "https://careers.emerson.com/"),
    ("Rockwell Automation India", "rockwellautomation.com", "https://www.rockwellautomation.com/en-us/company/careers.html"),
    ("Cummins India", "cummins.com", "https://careers.cummins.com/"),
    ("Caterpillar India", "caterpillar.com", "https://careers.caterpillar.com/"),
    ("John Deere India", "deere.com", "https://careers.deere.com/"),
    ("Boeing India", "boeing.com", "https://jobs.boeing.com/"),
    ("Airbus India", "airbus.com", "https://www.airbus.com/en/careers"),
    ("Rolls-Royce India", "rolls-royce.com", "https://careers.rolls-royce.com/"),
    ("Mercedes-Benz R&D India", "mbrdi.co.in", "https://www.mbrdi.co.in/careers"),
    ("Continental India", "continental.com", "https://www.continental.com/en/career/"),
    ("HARMAN India", "harman.com", "https://jobs.harman.com/"),
    ("Aptiv India", "aptiv.com", "https://www.aptiv.com/en/careers"),
    ("Valeo India", "valeo.com", "https://www.valeo.com/en/careers/"),
    ("Bosch Global Software Technologies", "bosch-softwaretechnologies.com", "https://www.bosch-softwaretechnologies.com/en/career/"),
    ("Dassault Systemes India", "3ds.com", "https://www.3ds.com/careers"),
    ("Autodesk India", "autodesk.com", "https://www.autodesk.com/careers"),
    ("PTC India", "ptc.com", "https://www.ptc.com/en/careers"),
    ("Trimble India", "trimble.com", "https://careers.trimble.com/"),
    ("Ansys India", "ansys.com", "https://www.ansys.com/careers"),
    ("MathWorks India", "mathworks.com", "https://www.mathworks.com/company/jobs/opportunities.html"),
    ("Synopsys India", "synopsys.com", "https://www.synopsys.com/careers.html"),
    ("Cadence India", "cadence.com", "https://www.cadence.com/en_US/home/company/careers.html"),
    ("Texas Instruments India", "ti.com", "https://careers.ti.com/"),
    ("Analog Devices India", "analog.com", "https://www.analog.com/en/about-adi/careers.html"),
    ("Micron India", "micron.com", "https://careers.micron.com/"),
    ("Applied Materials India", "appliedmaterials.com", "https://careers.appliedmaterials.com/"),
    ("Lam Research India", "lamresearch.com", "https://careers.lamresearch.com/"),
    ("AMD India", "amd.com", "https://jobs.amd.com/"),
    ("Arm India", "arm.com", "https://careers.arm.com/"),
    ("Marvell India", "marvell.com", "https://www.marvell.com/company/careers.html"),
    ("Western Digital India", "westerndigital.com", "https://jobs.westerndigital.com/"),
    ("Seagate India", "seagate.com", "https://www.seagate.com/jobs/"),
    ("NetApp India", "netapp.com", "https://careers.netapp.com/"),
    ("Pure Storage India", "purestorage.com", "https://www.purestorage.com/company/careers.html"),
    ("Nutanix India", "nutanix.com", "https://www.nutanix.com/company/careers"),
    ("Palo Alto Networks India", "paloaltonetworks.com", "https://jobs.paloaltonetworks.com/"),
    ("Fortinet India", "fortinet.com", "https://www.fortinet.com/corporate/careers"),
    ("CrowdStrike India", "crowdstrike.com", "https://www.crowdstrike.com/careers/"),
    ("Zscaler India", "zscaler.com", "https://www.zscaler.com/careers"),
    ("Akamai India", "akamai.com", "https://www.akamai.com/careers"),
    ("F5 India", "f5.com", "https://www.f5.com/company/careers"),
    ("Juniper Networks India", "juniper.net", "https://www.juniper.net/us/en/company/careers.html"),
    ("Arista Networks India", "arista.com", "https://www.arista.com/en/careers"),
    ("Ericsson India", "ericsson.com", "https://www.ericsson.com/en/careers"),
    ("Nokia India", "nokia.com", "https://www.nokia.com/careers/"),
    ("Samsung R&D India", "samsung.com", "https://www.samsung.com/in/about-us/careers/"),
    ("Sony India", "sony.com", "https://www.sony.com/en/SonyInfo/Careers/"),
    ("Panasonic India", "panasonic.com", "https://www.panasonic.com/global/careers.html"),
    ("Hitachi India", "hitachi.com", "https://www.hitachi.com/careers/"),
    ("Fujitsu India", "fujitsu.com", "https://www.fujitsu.com/global/about/careers/"),
    ("NEC India", "nec.com", "https://www.nec.com/en/global/careers/"),
    ("Canon India", "canon.com", "https://global.canon/en/careers/"),
    ("Xerox India", "xerox.com", "https://www.xerox.com/en-us/jobs"),
    # Indian IT services and engineering services
    ("TCS", "tcs.com", "https://www.tcs.com/careers"),
    ("Infosys", "infosys.com", "https://www.infosys.com/careers/"),
    ("Wipro", "wipro.com", "https://careers.wipro.com/"),
    ("HCLTech", "hcltech.com", "https://www.hcltech.com/careers"),
    ("Tech Mahindra", "techmahindra.com", "https://careers.techmahindra.com/"),
    ("LTIMindtree", "ltimindtree.com", "https://www.ltimindtree.com/careers/"),
    ("Mphasis", "mphasis.com", "https://careers.mphasis.com/"),
    ("Coforge", "coforge.com", "https://www.coforge.com/careers"),
    ("Persistent Systems", "persistent.com", "https://www.persistent.com/careers/"),
    ("Zensar", "zensar.com", "https://www.zensar.com/careers"),
    ("Birlasoft", "birlasoft.com", "https://www.birlasoft.com/careers"),
    ("Hexaware", "hexaware.com", "https://hexaware.com/careers/"),
    ("KPIT", "kpit.com", "https://www.kpit.com/careers/"),
    ("Tata Elxsi", "tataelxsi.com", "https://www.tataelxsi.com/careers"),
    ("Cyient", "cyient.com", "https://www.cyient.com/careers"),
    ("Sonata Software", "sonata-software.com", "https://www.sonata-software.com/careers"),
    ("Newgen Software", "newgensoft.com", "https://newgensoft.com/careers/"),
    ("Intellect Design Arena", "intellectdesign.com", "https://www.intellectdesign.com/careers/"),
    ("Tanla Platforms", "tanla.com", "https://www.tanla.com/careers"),
    ("Route Mobile", "routemobile.com", "https://routemobile.com/careers/"),
    ("Affle", "affle.com", "https://affle.com/careers/"),
    ("Nazara Technologies", "nazara.com", "https://www.nazara.com/careers/"),
    # Indian product / unicorn companies not on a verified public board
    ("Zoho", "zoho.com", "https://www.zoho.com/careers/"),
    ("Icertis", "icertis.com", "https://www.icertis.com/company/careers/"),
    ("Innovaccer", "innovaccer.com", "https://innovaccer.com/careers/"),
    ("Mindtree", "mindtree.com", "https://www.ltimindtree.com/careers/"),
    ("Zetwerk", "zetwerk.com", "https://www.zetwerk.com/careers/"),
    ("Licious", "licious.in", "https://www.licious.in/careers"),
    ("Razorpay", "razorpay.com", "https://razorpay.com/jobs/"),
    ("PhonePe", "phonepe.com", "https://www.phonepe.com/careers/"),
    ("Zepto", "zepto.com", "https://www.zeptonow.com/careers"),
    ("Postman", "postman.com", "https://www.postman.com/company/careers/"),
    ("BrowserStack", "browserstack.com", "https://www.browserstack.com/careers"),
    ("Dream11", "dream11.com", "https://www.dream11.com/careers"),
    ("ShareChat", "sharechat.com", "https://sharechat.com/careers"),
    ("Physics Wallah", "pw.live", "https://www.pw.live/careers"),
    ("Nykaa", "nykaa.com", "https://www.nykaa.com/careers"),
    ("Lenskart", "lenskart.com", "https://www.lenskart.com/careers"),
    ("Rapido", "rapido.bike", "https://www.rapido.bike/careers"),
    ("Juspay", "juspay.io", "https://juspay.io/careers"),
    ("Chargebee", "chargebee.com", "https://www.chargebee.com/careers/"),
    ("CleverTap", "clevertap.com", "https://clevertap.com/careers/"),
    ("MoEngage", "moengage.com", "https://www.moengage.com/careers/"),
    ("Acko", "acko.com", "https://www.acko.com/careers/"),
    ("Urban Company", "urbancompany.com", "https://www.urbancompany.com/careers"),
    ("ClearTax", "cleartax.in", "https://cleartax.in/careers"),
    ("Ola Electric", "olaelectric.com", "https://www.olaelectric.com/careers"),
    ("Krutrim", "olakrutrim.com", "https://www.olakrutrim.com/careers"),
    ("Ather Energy", "atherenergy.com", "https://www.atherenergy.com/careers"),
    ("Udaan", "udaan.com", "https://udaan.com/careers"),
    ("Pine Labs", "pinelabs.com", "https://www.pinelabs.com/careers"),
    ("LeadSquared", "leadsquared.com", "https://www.leadsquared.com/careers/"),
    ("Sprinklr", "sprinklr.com", "https://www.sprinklr.com/careers/"),
    ("Jupiter", "jupiter.money", "https://jupiter.money/careers/"),
    ("smallcase", "smallcase.com", "https://www.smallcase.com/careers"),
    ("Setu", "setu.co", "https://setu.co/careers"),
    ("Spinny", "spinny.com", "https://www.spinny.com/careers/"),
    ("Policybazaar", "policybazaar.com", "https://www.policybazaar.com/careers/"),
    ("Hasura", "hasura.io", "https://hasura.io/careers/"),
    ("CoinDCX", "coindcx.com", "https://coindcx.com/careers/"),
    ("CoinSwitch", "coinswitch.co", "https://coinswitch.co/careers"),
    ("Jar", "myjar.app", "https://www.myjar.app/careers"),
    ("Zupee", "zupee.com", "https://www.zupee.com/careers/"),
    ("Games24x7", "games24x7.com", "https://www.games24x7.com/careers/"),
    ("Delhivery", "delhivery.com", "https://www.delhivery.com/careers"),
    ("Shiprocket", "shiprocket.in", "https://www.shiprocket.in/careers/"),
    ("MakeMyTrip", "makemytrip.com", "https://www.makemytrip.com/careers/"),
    ("OYO", "oyorooms.com", "https://www.oyorooms.com/careers/"),
    ("Khatabook", "khatabook.com", "https://khatabook.com/careers"),
    ("BharatPe", "bharatpe.com", "https://bharatpe.com/careers"),
    ("MobiKwik", "mobikwik.com", "https://www.mobikwik.com/careers"),
    ("Cashfree Payments", "cashfree.com", "https://www.cashfree.com/careers/"),
    ("Scaler", "scaler.com", "https://www.scaler.com/careers/"),
    ("HackerEarth", "hackerearth.com", "https://www.hackerearth.com/careers/"),
    ("Dailyhunt", "dailyhunt.in", "https://www.dailyhunt.in/careers"),
    ("Rebel Foods", "rebelfoods.com", "https://www.rebelfoods.com/careers"),
    ("Purplle", "purplle.com", "https://www.purplle.com/careers"),
    ("Teachmint", "teachmint.com", "https://www.teachmint.com/careers"),
    ("Classplus", "classplusapp.com", "https://classplusapp.com/careers"),
    ("Vedantu", "vedantu.com", "https://www.vedantu.com/careers"),
    ("Airmeet", "airmeet.com", "https://www.airmeet.com/careers"),
    ("Country Delight", "countrydelight.in", "https://countrydelight.in/careers"),
    ("BlackBuck", "blackbuck.com", "https://blackbuck.com/careers"),
    ("Signzy", "signzy.com", "https://www.signzy.com/careers"),
    ("HyperVerge", "hyperverge.co", "https://hyperverge.co/careers"),
    ("Locus", "locus.sh", "https://locus.sh/careers/"),
    ("Rocketlane", "rocketlane.com", "https://www.rocketlane.com/careers"),
    ("Plum", "plumhq.com", "https://www.plumhq.com/careers"),
    ("Sprinto", "sprinto.com", "https://sprinto.com/careers/"),
    ("KreditBee", "kreditbee.in", "https://www.kreditbee.in/careers"),
    ("INDmoney", "indmoney.com", "https://www.indmoney.com/careers"),
    ("Porter", "porter.in", "https://porter.in/careers"),
    ("OfBusiness", "ofbusiness.com", "https://www.ofbusiness.com/careers"),
    ("Infra.Market", "infra.market", "https://www.infra.market/careers"),
    ("Perfios", "perfios.com", "https://www.perfios.com/careers/"),
    ("M2P Fintech", "m2pfintech.com", "https://m2pfintech.com/careers/"),
    ("Kuku FM", "kukufm.com", "https://kukufm.com/careers/"),
    ("WinZO", "winzogames.com", "https://www.winzogames.com/careers"),
    ("Fractal", "fractal.ai", "https://fractal.ai/careers/"),
    ("Zerodha", "zerodha.com", "https://zerodha.com/careers/"),
    ("Blinkit", "blinkit.com", "https://blinkit.com/careers"),
    ("Zomato", "zomato.com", "https://www.zomato.com/careers"),
    ("Flipkart", "flipkart.com", "https://www.flipkartcareers.com/"),
    ("Myntra", "myntra.com", "https://careers.myntra.com/"),
    ("Swiggy", "swiggy.com", "https://careers.swiggy.com/"),
    ("Freshworks", "freshworks.com", "https://careers.freshworks.com/"),
    ("Paytm", "paytm.com", "https://paytm.com/careers/"),
    ("CRED", "cred.club", "https://careers.cred.club/"),
    ("Groww", "groww.in", "https://groww.in/careers"),
    ("Upstox", "upstox.com", "https://upstox.com/careers/"),
    ("Unacademy", "unacademy.com", "https://unacademy.com/careers"),
    ("Cars24", "cars24.com", "https://www.cars24.com/careers/"),
    ("Whatfix", "whatfix.com", "https://whatfix.com/careers/"),
    ("ixigo", "ixigo.com", "https://www.ixigo.com/careers"),
    ("InMobi", "inmobi.com", "https://www.inmobi.com/company/careers"),
    ("Glance", "glance.com", "https://www.glance.com/careers"),
    ("HighRadius", "highradius.com", "https://www.highradius.com/company/careers/"),
    ("Sigmoid", "sigmoid.ai", "https://www.sigmoid.ai/careers/"),
    ("Mindtickle", "mindtickle.com", "https://www.mindtickle.com/careers/"),
    ("FamPay", "fampay.in", "https://fampay.in/careers"),
    ("Pocket FM", "pocketfm.com", "https://www.pocketfm.com/careers"),
    ("Atlan", "atlan.com", "https://atlan.com/careers/"),
    ("Tekion", "tekion.com", "https://tekion.com/careers"),
    ("Apna", "apna.co", "https://www.apna.co/careers"),
]


def _registrable(host: str) -> str:
    parts = [part for part in str(host or "").casefold().split(".") if part]
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "net", "gov", "ac", "edu"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else (parts[0] if parts else "")


def _domain_of(url: str) -> str:
    try:
        return _registrable(urlsplit(url if "://" in url else f"https://{url}").hostname or "")
    except ValueError:
        return ""


def _board_rows() -> list[dict[str, Any]]:
    rows = []
    for company in DEFAULT_COMPANIES:
        slug = company["slug"]
        rows.append({"name": company["name"], "domain": BOARD_DOMAINS.get(slug) or f"{slug}.com",
                     "segment": "startup" if INDIAN_BOARDS.get(slug) == "startup" else "product",
                     "ats": company["ats"], "tenant": slug, "careers_url": "", "priority": 78,
                     "source": "built-in verified ATS board", "verified_at": "2026-11-16"})
    return rows


def _site_rows() -> list[dict[str, Any]]:
    return [{"name": site["name"], "domain": _domain_of(site["website"]),
             "segment": "startup" if site["classification"] == "startup" else "product",
             "ats": None, "tenant": None, "careers_url": "", "priority": 62,
             "source": "built-in Indian startup list", "verified_at": None}
            for site in INDIAN_CAREER_SITES]


def _corporate_rows() -> list[dict[str, Any]]:
    rows = []
    for name, domain, careers_url in GCC_CORPORATE:
        segment = "services" if name in {
            "TCS", "Infosys", "Wipro", "HCLTech", "Tech Mahindra", "LTIMindtree", "Mphasis", "Coforge",
            "Persistent Systems", "Zensar", "Birlasoft", "Hexaware", "KPIT", "Tata Elxsi", "Cyient",
            "Sonata Software", "Newgen Software", "Intellect Design Arena", "Tanla Platforms", "Route Mobile",
            "Affle", "Nazara Technologies", "Genpact", "WNS", "EXL Service", "Accenture India", "Deloitte India",
            "EY India", "KPMG India", "PwC India", "Capgemini India", "Cognizant India"} else (
            "gcc" if " India" in name or name in {"Shell India"} else "product")
        rows.append({"name": name, "domain": _registrable(domain), "segment": segment,
                     "ats": None, "tenant": None, "careers_url": careers_url, "priority": 55,
                     "source": "official careers page (GCC/corporate seed)", "verified_at": None})
    return rows


def companies() -> list[dict[str, Any]]:
    """The full seed, deduplicated by registrable domain (first row wins: verified ATS board > startup > corporate)."""
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for row in [*_board_rows(), *_corporate_rows(), *_site_rows()]:
        domain = _registrable(row["domain"])
        if not domain or domain in seen:
            continue
        seen.add(domain)
        row["domain"] = domain
        output.append(row)
    return output


def summary() -> dict[str, Any]:
    rows = companies()
    segments: dict[str, int] = {}
    for row in rows:
        segments[row["segment"]] = segments.get(row["segment"], 0) + 1
    return {"version": SEED_VERSION, "companies": len(rows), "segments": segments,
            "with_ats": sum(1 for row in rows if row.get("ats"))}

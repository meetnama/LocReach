"""
config.py — Shared constants for the LocReach lead discovery pipeline.
All query banks, keyword lists, blocked domains, presets, etc. live here.
Import from this module everywhere — never hardcode constants in source files.
"""

# ── Target job titles ──────────────────────────────────────────────────────────
TARGET_TITLES = [
    # ── C-suite / Owner / Founder (all relevant at any verified LSP) ──
    "ceo", "chief executive",
    "coo", "chief operating officer",
    "cto", "chief technology officer",
    "founder", "co-founder", "cofounder",
    "owner", "co-owner",
    "managing director", "managing partner",
    "executive director", "president",
    "general manager",

    # ── Head of / Director / VP ───────────────────────────────────────
    "head of localization",           "head of localisation",
    "head of translation",            "head of language",    "head of languages",
    "director of localization",       "localization director",
    "director of translation",        "translation director",
    "director of language",           "language director",
    "vp of localization",             "vp of translation",
    "vice president of localization", "vice president of translation",

    # ── Manager level ─────────────────────────────────────────────────
    "localization manager",           "localisation manager",
    "translation manager",            "language manager",
    "language services manager",
    "vendor manager",                 "vendor coordinator",
    "localization vendor manager",    "translation vendor manager",
    "project manager",                "localization project manager",
    "translation project manager",    "localization coordinator",
    "localization operations manager",
    "language operations manager",

    # ── Specialist / Engineer / Lead ──────────────────────────────────
    "localization lead",              "localisation lead",
    "localization engineer",
    "localization specialist",        "localisation specialist",
    "translation specialist",         "language specialist",
    "terminology manager",
]

# ── Blocked domains ────────────────────────────────────────────────────────────
# Rule: if a site is a DIRECTORY, AGGREGATOR, NEWS OUTLET, RESEARCH FIRM,
#       SOCIAL NETWORK, JOB BOARD, or TOOL — block it.
# Real companies (even large ones like Ubisoft) are kept IN so we can prospect them.
BLOCKED_DOMAINS = {
    # ── Freelance marketplaces ────────────────────────────────────────────────
    "proz.com", "translationdirectory.com", "translationcafe.com",
    "upwork.com", "fiverr.com", "freelancer.com", "guru.com", "peopleperhour.com",
    "toptal.com", "arc.dev", "workana.com", "truelancer.com", "99designs.com",

    # ── Job boards ────────────────────────────────────────────────────────────
    "indeed.com", "glassdoor.com", "ziprecruiter.com", "remote.com",
    "monster.com", "careerbuilder.com", "simplyhired.com", "dice.com",
    "wellfound.com", "angel.co", "angellist.com", "amazon.jobs",
    "workable.com", "lever.co", "greenhouse.io", "smartrecruiters.com",
    "jobs.com", "jobleads.com", "otta.com", "careers.com",
    "reed.co.uk", "totaljobs.com", "cv-library.co.uk", "jobsite.co.uk",
    "bamboohr.com", "recruitee.com", "teamtailor.com",

    # ── Business directories & company aggregators ────────────────────────────
    "clutch.co", "goodfirms.io", "goodfirms.co", "sortlist.com",
    "expertise.com", "themanifest.com", "designrush.com",
    "zoominfo.com", "crunchbase.com", "pitchbook.com", "owler.com",
    "dnb.com", "hoovers.com", "manta.com", "thomasnet.com",
    "companieshouse.gov.uk", "europages.com", "kompass.com",
    "yelp.com", "yelp.co.uk", "yellowpages.com", "bark.com",
    "checkatrade.com", "trustindex.io", "citlob.com", "trustpilot.com",
    "f6s.com", "startupranking.com", "startupblink.com",
    "upcity.com", "thumbtack.com", "directory.com", "hotfrog.com",
    "cylex.us", "superpages.com", "brownbook.net", "b2blistings.org",
    "gamecompanies.com", "gamecompanies.co",
    "builtin.com", "builtinnyc.com", "builtinla.com", "builtinchicago.com",
    "builtin.co.uk",

    # ── Market research & analytics ───────────────────────────────────────────
    "statista.com", "ibisworld.com", "grandviewresearch.com",
    "mordorintelligence.com", "marketsandmarkets.com", "alliedmarketresearch.com",
    "sphericalinsights.com", "globenewswire.com", "businessresearchinsights.com",
    "precedenceresearch.com", "expertmarketresearch.com", "imarcgroup.com",
    "fortunebusinessinsights.com", "coherentmarketinsights.com",
    "valuatesreports.com", "reportsanddata.com", "databridgemarketresearch.com",
    "researchandmarkets.com", "businesswire.com", "prnewswire.com", "prweb.com",
    "newzoo.com", "niko.partners", "vginsights.com", "gamasutra.com",
    "similarweb.com", "semrush.com", "ahrefs.com", "moz.com",

    # ── Social networks ───────────────────────────────────────────────────────
    "linkedin.com", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "tiktok.com", "pinterest.com", "snapchat.com",
    "youtube.com", "vimeo.com", "twitch.tv", "discord.com", "reddit.com",
    "xing.com", "viadeo.com",
    "blogger.com", "wordpress.com", "tumblr.com",

    # ── General news & media ──────────────────────────────────────────────────
    "techcrunch.com", "venturebeat.com", "wired.com", "theverge.com",
    "engadget.com", "cnet.com", "zdnet.com", "arstechnica.com",
    "forbes.com", "businessinsider.com", "inc.com", "entrepreneur.com",
    "bloomberg.com", "wsj.com", "ft.com", "economist.com", "reuters.com",
    "bbc.com", "bbc.co.uk", "cnn.com", "nytimes.com", "theguardian.com",
    "lemonde.fr", "lefigaro.fr", "spiegel.de", "faz.net", "elmundo.es",
    "medium.com", "substack.com", "quora.com",

    # ── Gaming news & trade media (not companies) ─────────────────────────────
    "gamesindustry.biz", "pocketgamer.biz", "gamedeveloper.com",
    "gamespot.com", "ign.com", "pcgamer.com", "pcgamesn.com",
    "eurogamer.net", "rockpapershotgun.com", "kotaku.com", "polygon.com",
    "gamesradar.com", "destructoid.com", "gamereactor.eu", "vg247.com",
    "develop-online.net", "mcvuk.com", "gamesintelligence.com",
    "superdataresearch.com", "gameworldobserver.com",

    # ── Review platforms ──────────────────────────────────────────────────────
    "g2.com", "capterra.com", "getapp.com", "softwareadvice.com",
    "sitejabber.com", "reviews.co.uk", "trustradius.com",

    # ── Reference & encyclopaedia ─────────────────────────────────────────────
    "wikipedia.org", "wikimedia.org", "wikia.com", "fandom.com",
    "iso.org", "britannica.com",

    # ── Tourism / local portals — not buyers ─────────────────────────────────
    "tripadvisor.com", "booking.com", "airbnb.com", "expedia.com",
    "iamsterdam.com", "visitlondon.com", "timeout.com",

    # ── Government / institutional ────────────────────────────────────────────
    # (most .gov.* domains are caught by the .gov. pattern check in is_blocked())
    "gov.uk", "gov.au", "govt.nz", "health.nyc.gov", "schools.nyc.gov",

    # ── Translation/localization trade associations & directories ─────────────
    "proz.com", "translationdirectory.com", "translationcafe.com",
    "gala-global.org", "ata-divisions.org", "atanet.org",
    "translatorswithoutborders.org", "twb.ngo",
    "slator.com", "multilingual.com", "tcworld.info", "translationjournal.net",

    # ── TMS / CAT tools (product companies — not buyers at this stage) ────────
    "deepl.com", "google.com", "microsoft.com", "apple.com",
    "canva.com", "onlinedoctranslator.com", "immersivetranslate.com",
    "translate.google.com", "translate.google.us", "translate.google.com.eg",
    "translate.google.com.jo", "cloud.google.com", "docs.google.com",
    "github.com", "gitlab.com", "wiktionary.org", "wikipedia.org",
    "babbel.com", "duolingo.com",
    "sdl.com", "smartling.com", "transifex.com", "crowdin.com",
    "lokalise.com", "phrase.com", "weglot.com", "unbabel.com",
    "systran.com", "lilt.com", "memoq.com", "trados.com",
    "xtm-intl.com", "xtm.ai", "madcap-software.com", "madcapsoftware.com",
    "wordbee.com", "memsource.com", "lingotek.com", "plunet.com",
    "xbench.net", "cafetran.com", "omegat.org", "wordfast.com",

    # ── Certification / standards bodies ─────────────────────────────────────
    "usqc.us", "bsigroup.com", "tuvsud.com", "dnv.com", "sgs.com",

    # ── Dictionary / language reference ──────────────────────────────────────
    "dictionary.cambridge.org", "cambridge.org",
    "merriam-webster.com", "collinsdictionary.com", "wordreference.com",
    "linguee.com", "reverso.net", "deepl.com",

    # ── Big portals / platforms (not companies) ───────────────────────────────
    "yahoo.com", "bing.com", "baidu.com", "ask.com",
    "onlyfans.com", "patreon.com", "ko-fi.com",
    "scribd.com", "issuu.com", "slideshare.net",
    "weworkremotely.com", "remoteok.com", "remote.co",
    "producthunt.com", "betalist.com", "alternativeto.net",
    "appsumo.com", "saasworthy.com",

    # ── Company data / aggregator sites ──────────────────────────────────────
    "superbcompanies.com", "companiesmarketcap.com", "companydata.com",
    "techbehemoths.com", "digitalagencynetwork.com", "agencyspotter.com",
    "sortlist.co.uk", "agencyanalytics.com", "semrush.com",
    "visiblevc.com", "craft.co", "rocketreach.co",

    # ── Trade associations & industry bodies ─────────────────────────────────
    "iabeurope.eu", "iab.com", "iab.net",
    "ama.org", "cim.co.uk", "termnet.org",
    "wfanet.org", "egta.com", "eaca.eu",

    # ── Financial data sites ──────────────────────────────────────────────────
    "finance.yahoo.com", "marketwatch.com", "investing.com",
    "stockanalysis.com", "macrotrends.net",
}

# ── Free / personal email domains ─────────────────────────────────────────────
FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "live.com", "icloud.com", "protonmail.com", "aol.com",
    "126.com", "163.com", "qq.com", "sina.com", "yandex.com",
    "mail.ru", "gmx.com", "gmx.de", "web.de",
}

# ── Per-industry search-result keywords ───────────────────────────────────────
# Used in Step 1 to validate that a Google result title/snippet actually belongs
# to the searched industry.  At least ONE keyword must appear in title+snippet.
# Keys match the ind_kw slugs from INDUSTRY_OPTIONS in app.py.
INDUSTRY_KEYWORDS = {
    "translation": [
        "translation", "localization", "localisation", "language", "interpreter",
        "linguist", "multilingual", "translat", "翻译", "traduct", "übersetzung",
        "subtitl", "dubbing", "lsp", "language service", "certified translat",
        "sworn translat", "transcription", "interpreting",
        # Arabic (Egypt/MENA SERPs)
        "ترجمة", "تعريب", "توطين", "مترجم", "ترجمة معتمدة", "خدمات ترجمة",
    ],
    "localization": [
        "localization", "localisation", "translation", "language", "l10n",
        "i18n", "internationalization", "globaliz", "linguistic", "multilingual",
        "translat", "lsp", "language service", "interpreting", "subtitl",
        # Arabic (Egypt/MENA SERPs)
        "ترجمة", "تعريب", "توطين", "مترجم", "ترجمة معتمدة", "خدمات ترجمة",
    ],
    "marketing": [
        "marketing", "advertising agency", "branding agency", "campaign",
        "digital agency", "digital marketing", "creative agency",
        "communications agency", "media agency", "pr agency", "content agency",
        "seo agency", "social media agency", "marketing strategy",
        "marketing firm", "marketing company", "publicis", "wpp", "ogilvy",
        "integrated marketing", "performance marketing", "growth marketing",
    ],
    "gaming": [
        "game", "gaming", "studio", "developer", "publisher", "esport",
        "interactive", "video game", "mobile game", "indie", "playstation",
        "xbox", "nintendo", "pc game",
    ],
    "medical": [
        "medical", "pharma", "pharmaceutical", "healthcare", "clinical", "biotech",
        "hospital", "health", "life science", "diagnostic", "therapeutic",
        "medtech", "bioscience",
    ],
    "legal": [
        "legal", "law", "attorney", "lawyer", "barrister", "solicitor",
        "counsel", "litigation", "firm", "legal service", "juridical",
    ],
    "e-commerce": [
        "ecommerce", "e-commerce", "online store", "retail", "shop", "marketplace",
        "shopping", "commerce", "merchant", "dropship", "fulfilment",
    ],
    "financial": [
        "financial", "finance", "banking", "investment", "insurance", "fintech",
        "wealth", "asset management", "accounting", "audit", "tax", "fund",
    ],
    "software": [
        "software", "saas", "tech", "technology", "app", "platform", "cloud",
        "developer", "digital", "data", "api", "enterprise", "it service",
    ],
    "subtitling": [
        "subtitle", "subtitling", "dubbing", "caption", "captioning", "media",
        "post-production", "broadcast", "streaming", "localiz", "translat",
        "audio description", "accessibility",
    ],
    "education": [
        "education", "learning", "training", "university", "school", "academy",
        "e-learning", "edtech", "course", "curriculum", "tutoring",
    ],
}

# ── LSP relevance keywords (homepage content check) ───────────────────────────
RELEVANCE_KEYWORDS = [
    "translation", "localization", "localisation", "language service",
    "interpretation", "interpreter", "linguist", "multilingual",
    "übersetzung", "traduction", "traduccion", "tradução",
    "vertaling", "tłumaczenie", "翻译", "tercüme", "перевод",
    "lsp", "language provider", "certified translation",
    "sworn translation", "subtitling", "dubbing", "localize", "localise", "l10n",
]

# ── TLD → Country ──────────────────────────────────────────────────────────────
TLD_COUNTRY = {
    ".co.uk": "United Kingdom", ".org.uk": "United Kingdom", ".uk": "United Kingdom",
    ".de": "Germany",   ".fr": "France",   ".es": "Spain",   ".it": "Italy",
    ".nl": "Netherlands", ".pl": "Poland", ".se": "Sweden",  ".no": "Norway",
    ".dk": "Denmark",   ".fi": "Finland",  ".pt": "Portugal", ".be": "Belgium",
    ".ch": "Switzerland", ".at": "Austria", ".ro": "Romania", ".hu": "Hungary",
    ".cz": "Czech Republic", ".sk": "Slovakia", ".hr": "Croatia", ".bg": "Bulgaria",
    ".gr": "Greece",    ".ru": "Russia",   ".ua": "Ukraine",
    ".co.in": "India",  ".in": "India",    ".jp": "Japan",   ".co.jp": "Japan",
    ".cn": "China",     ".com.au": "Australia", ".net.au": "Australia", ".au": "Australia",
    ".ca": "Canada",    ".com.br": "Brazil", ".mx": "Mexico",
    ".co.za": "South Africa", ".za": "South Africa",
    ".ae": "UAE",        ".sa": "Saudi Arabia", ".com.sa": "Saudi Arabia",
    ".tr": "Turkey",    ".com.tr": "Turkey",   ".eg": "Egypt",
    ".il": "Israel",    ".co.il": "Israel",    ".ng": "Nigeria",  ".ke": "Kenya",
    ".ar": "Argentina", ".com.ar": "Argentina", ".cl": "Chile",
    ".kr": "South Korea", ".co.kr": "South Korea",
    ".sg": "Singapore", ".com.sg": "Singapore",
    ".my": "Malaysia",  ".ph": "Philippines",  ".nz": "New Zealand", ".ie": "Ireland",
}

# ── Country → location signals (geographic qualification gate) ─────────────────
# Used by sources/geo.py to confirm a company is actually BASED in the selected
# country, not merely serving it. `code` = international dialling prefix;
# `adj` = country name / adjective / local-language forms (for HQ phrasing);
# `cities` = major cities & business districts (lowercased). ccTLDs are derived
# by inverting TLD_COUNTRY, so they are not repeated here.
COUNTRY_GEO = {
    "Argentina":      {"code": "+54",  "adj": ["argentina", "argentine", "argentinian"], "cities": ["buenos aires", "córdoba", "cordoba", "rosario"]},
    "Australia":      {"code": "+61",  "adj": ["australia", "australian"], "cities": ["sydney", "melbourne", "brisbane", "perth", "canberra"]},
    "Austria":        {"code": "+43",  "adj": ["austria", "austrian", "österreich"], "cities": ["vienna", "wien", "graz", "linz", "salzburg"]},
    "Belgium":        {"code": "+32",  "adj": ["belgium", "belgian", "belgië", "belgique"], "cities": ["brussels", "bruxelles", "antwerp", "antwerpen", "ghent", "gent"]},
    "Brazil":         {"code": "+55",  "adj": ["brazil", "brazilian", "brasil"], "cities": ["são paulo", "sao paulo", "rio de janeiro", "brasília", "brasilia"]},
    "Canada":         {"code": "+1",   "adj": ["canada", "canadian"], "cities": ["toronto", "vancouver", "montreal", "montréal", "ottawa", "calgary"]},
    "Chile":          {"code": "+56",  "adj": ["chile", "chilean"], "cities": ["santiago", "valparaíso", "valparaiso", "concepción", "concepcion"]},
    "China":          {"code": "+86",  "adj": ["china", "chinese"], "cities": ["shanghai", "beijing", "shenzhen", "guangzhou"]},
    "Colombia":       {"code": "+57",  "adj": ["colombia", "colombian"], "cities": ["bogotá", "bogota", "medellín", "medellin", "cali"]},
    "Czech Republic": {"code": "+420", "adj": ["czech", "czechia", "česká"], "cities": ["prague", "praha", "brno", "ostrava"]},
    "Denmark":        {"code": "+45",  "adj": ["denmark", "danish", "danmark"], "cities": ["copenhagen", "københavn", "kobenhavn", "aarhus", "odense"]},
    "Egypt":          {"code": "+20",  "adj": ["egypt", "egyptian"], "cities": ["cairo", "alexandria", "giza", "nasr city", "maadi", "heliopolis", "new cairo", "6th of october", "zamalek", "mansoura"]},
    "Finland":        {"code": "+358", "adj": ["finland", "finnish", "suomi"], "cities": ["helsinki", "espoo", "tampere", "vantaa"]},
    "France":         {"code": "+33",  "adj": ["france", "french", "française", "francaise"], "cities": ["paris", "lyon", "marseille", "toulouse", "lille"]},
    "Germany":        {"code": "+49",  "adj": ["germany", "german", "deutschland"], "cities": ["berlin", "munich", "münchen", "munchen", "hamburg", "frankfurt", "cologne", "köln"]},
    "Greece":         {"code": "+30",  "adj": ["greece", "greek", "ελλάδα"], "cities": ["athens", "thessaloniki", "patras", "piraeus"]},
    "Hungary":        {"code": "+36",  "adj": ["hungary", "hungarian", "magyarország"], "cities": ["budapest", "debrecen", "szeged"]},
    "India":          {"code": "+91",  "adj": ["india", "indian"], "cities": ["mumbai", "delhi", "new delhi", "bangalore", "bengaluru", "hyderabad", "chennai", "pune", "noida", "gurgaon", "gurugram"]},
    "Indonesia":      {"code": "+62",  "adj": ["indonesia", "indonesian"], "cities": ["jakarta", "surabaya", "bandung", "medan"]},
    "Ireland":        {"code": "+353", "adj": ["ireland", "irish", "éire"], "cities": ["dublin", "cork", "galway", "limerick"]},
    "Israel":         {"code": "+972", "adj": ["israel", "israeli"], "cities": ["tel aviv", "jerusalem", "haifa", "herzliya"]},
    "Italy":          {"code": "+39",  "adj": ["italy", "italian", "italia"], "cities": ["milan", "milano", "rome", "roma", "turin", "torino", "naples", "napoli"]},
    "Japan":          {"code": "+81",  "adj": ["japan", "japanese"], "cities": ["tokyo", "osaka", "yokohama", "nagoya", "kyoto"]},
    "Kenya":          {"code": "+254", "adj": ["kenya", "kenyan"], "cities": ["nairobi", "mombasa", "kisumu"]},
    "Malaysia":       {"code": "+60",  "adj": ["malaysia", "malaysian"], "cities": ["kuala lumpur", "george town", "johor bahru", "petaling jaya"]},
    "Mexico":         {"code": "+52",  "adj": ["mexico", "mexican", "méxico"], "cities": ["mexico city", "ciudad de méxico", "guadalajara", "monterrey"]},
    "Netherlands":    {"code": "+31",  "adj": ["netherlands", "dutch", "holland", "nederland"], "cities": ["amsterdam", "rotterdam", "the hague", "den haag", "utrecht", "eindhoven"]},
    "New Zealand":    {"code": "+64",  "adj": ["new zealand"], "cities": ["auckland", "wellington", "christchurch"]},
    "Nigeria":        {"code": "+234", "adj": ["nigeria", "nigerian"], "cities": ["lagos", "abuja", "kano", "ibadan"]},
    "Norway":         {"code": "+47",  "adj": ["norway", "norwegian", "norge"], "cities": ["oslo", "bergen", "trondheim", "stavanger"]},
    "Pakistan":       {"code": "+92",  "adj": ["pakistan", "pakistani"], "cities": ["karachi", "lahore", "islamabad", "rawalpindi"]},
    "Peru":           {"code": "+51",  "adj": ["peru", "peruvian", "perú"], "cities": ["lima", "arequipa", "trujillo"]},
    "Philippines":    {"code": "+63",  "adj": ["philippines", "filipino", "philippine"], "cities": ["manila", "quezon city", "cebu", "makati", "taguig"]},
    "Poland":         {"code": "+48",  "adj": ["poland", "polish", "polska"], "cities": ["warsaw", "warszawa", "kraków", "krakow", "wrocław", "wroclaw", "gdańsk", "gdansk"]},
    "Portugal":       {"code": "+351", "adj": ["portugal", "portuguese"], "cities": ["lisbon", "lisboa", "porto", "braga"]},
    "Romania":        {"code": "+40",  "adj": ["romania", "romanian", "românia"], "cities": ["bucharest", "bucurești", "bucuresti", "cluj-napoca", "cluj", "timișoara", "timisoara"]},
    "Russia":         {"code": "+7",   "adj": ["russia", "russian"], "cities": ["moscow", "saint petersburg", "st petersburg", "novosibirsk"]},
    "Saudi Arabia":   {"code": "+966", "adj": ["saudi arabia", "saudi", "ksa"], "cities": ["riyadh", "jeddah", "dammam", "mecca", "medina", "khobar"]},
    "Singapore":      {"code": "+65",  "adj": ["singapore", "singaporean"], "cities": ["singapore"]},
    "South Africa":   {"code": "+27",  "adj": ["south africa", "south african"], "cities": ["johannesburg", "cape town", "durban", "pretoria"]},
    "South Korea":    {"code": "+82",  "adj": ["south korea", "korea", "korean"], "cities": ["seoul", "busan", "incheon", "daegu"]},
    "Spain":          {"code": "+34",  "adj": ["spain", "spanish", "españa", "espana"], "cities": ["madrid", "barcelona", "valencia", "seville", "sevilla", "málaga", "malaga"]},
    "Sweden":         {"code": "+46",  "adj": ["sweden", "swedish", "sverige"], "cities": ["stockholm", "gothenburg", "göteborg", "goteborg", "malmö", "malmo"]},
    "Switzerland":    {"code": "+41",  "adj": ["switzerland", "swiss", "schweiz", "suisse"], "cities": ["zurich", "zürich", "geneva", "genève", "geneve", "basel", "bern", "lausanne"]},
    "Thailand":       {"code": "+66",  "adj": ["thailand", "thai"], "cities": ["bangkok", "chiang mai", "phuket", "nonthaburi"]},
    "Turkey":         {"code": "+90",  "adj": ["turkey", "turkish", "türkiye", "turkiye"], "cities": ["istanbul", "ankara", "izmir", "bursa", "antalya"]},
    "UAE":            {"code": "+971", "adj": ["united arab emirates", "emirati", "emirates", "uae"], "cities": ["dubai", "abu dhabi", "sharjah", "ajman"]},
    "Ukraine":        {"code": "+380", "adj": ["ukraine", "ukrainian"], "cities": ["kyiv", "kiev", "kharkiv", "odesa", "odessa", "lviv", "dnipro"]},
    "United Kingdom": {"code": "+44",  "adj": ["united kingdom", "britain", "british", "england", "scotland", "wales"], "cities": ["london", "manchester", "birmingham", "leeds", "glasgow", "edinburgh", "bristol", "liverpool"]},
    "United States":  {"code": "+1",   "adj": ["united states", "u.s.a", "america", "american"], "cities": ["new york", "los angeles", "chicago", "houston", "san francisco", "boston", "seattle", "atlanta", "miami", "washington"]},
}

# ── Search query bank ──────────────────────────────────────────────────────────
QUERY_CATEGORIES = {
    "🏙️ Cities — Europe": [
        "translation agency London",          "translation company Manchester",
        "translation agency Birmingham",       "translation company Edinburgh",
        "translation agency Dublin Ireland",   "translation company Amsterdam",
        "translation agency Rotterdam",        "translation company Berlin",
        "translation agency Munich",           "translation company Hamburg",
        "translation agency Frankfurt",        "translation company Paris",
        "translation agency Lyon",             "translation company Madrid",
        "translation agency Barcelona",        "translation company Milan",
        "translation agency Rome",             "translation company Warsaw",
        "translation agency Krakow",           "translation company Stockholm",
        "translation agency Oslo",             "translation company Copenhagen",
        "translation agency Helsinki",         "translation company Vienna",
        "translation agency Zurich",           "translation company Brussels",
        "translation agency Lisbon",           "translation company Prague",
        "translation agency Budapest",         "translation company Bucharest",
        "translation agency Athens",
    ],
    "🏙️ Cities — Americas": [
        "translation agency New York",         "translation company Los Angeles",
        "translation agency Chicago",          "translation company Houston",
        "translation agency Miami",            "translation company Washington DC",
        "translation agency Boston",           "translation company San Francisco",
        "translation agency Toronto",          "translation company Vancouver",
        "translation agency Montreal",         "translation company Buenos Aires",
        "translation agency Sao Paulo",        "translation company Mexico City",
        "translation agency Bogota",           "translation company Lima Peru",
        "translation agency Santiago Chile",
    ],
    "🏙️ Cities — Asia & Middle East": [
        "translation agency Dubai",            "translation company Abu Dhabi",
        "translation agency Riyadh",           "translation company Cairo",
        "translation agency Istanbul",         "translation company Mumbai",
        "translation agency Delhi",            "translation company Bangalore",
        "translation agency Tokyo",            "translation company Shanghai",
        "translation agency Beijing",          "translation company Seoul",
        "translation agency Singapore",        "translation company Kuala Lumpur",
        "translation agency Bangkok",          "translation company Jakarta",
        "translation agency Manila",           "translation company Tel Aviv",
    ],
    "🏙️ Cities — Africa & Oceania": [
        "translation agency Johannesburg",     "translation company Cape Town",
        "translation agency Lagos Nigeria",    "translation company Nairobi Kenya",
        "translation agency Sydney",           "translation company Melbourne",
        "translation agency Auckland New Zealand",
    ],
    "🗣️ Language Pairs": [
        "Arabic English translation agency",   "Chinese English translation company",
        "Japanese English translation agency", "Korean English translation company",
        "German English translation agency",   "French English translation company",
        "Spanish English translation agency",  "Portuguese English translation company",
        "Italian English translation agency",  "Dutch English translation company",
        "Polish English translation agency",   "Russian English translation company",
        "Turkish English translation agency",  "Hebrew English translation company",
        "Hindi English translation agency",    "Swahili translation company",
        "Vietnamese English translation agency","Indonesian English translation company",
    ],
    "🔬 Specializations": [
        "legal translation agency",            "certified legal translation company",
        "medical translation agency",          "pharmaceutical translation company",
        "technical translation agency",        "patent translation company",
        "financial translation agency",        "website localization agency",
        "software localization company",       "game localization agency",
        "eLearning localization company",      "subtitling localization company",
        "dubbing localization agency",         "transcreation agency",
        "sworn certified translation company", "desktop publishing translation agency",
    ],
    "💼 Job Titles": [
        "vendor manager LSP translation company",  "localization vendor manager agency",
        "translation project manager company",     "localization project manager agency",
        "translation outsourcing manager",         "localization director agency",
        "head of translation company",             "translation department manager company",
        "localization program manager agency",
    ],
    "🏅 Certifications": [
        "ISO 17100 certified translation agency",  "ISO 9001 translation company",
        "ATA member translation agency",           "GALA member localization company",
        "ITI member translation company",          "NAATI accredited translation company",
        "ATC member translation agency UK",
    ],
    "🌐 General": [
        "language service provider LSP",           "translation bureau professional",
        "language solutions company",              "multilingual services agency",
        "translation outsourcing company",         "boutique translation agency",
        "full-service localization agency",        "global language services company",
        "professional translation services company","content localization agency",
    ],
}

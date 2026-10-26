#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Search PubMed, bioRxiv/medRxiv, ClinicalTrials.gov, and FDA drug labels.

Uses only the Python standard library and free, keyless public APIs. Literature
goes through Europe PMC, which indexes PubMed and both preprint servers behind
one query language; bioRxiv's own API has no keyword search.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

VERSION = "0.1.0"
USER_AGENT = f"biosearch/{VERSION} (+https://github.com/kpatdev/my-skills)"

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
CTGOV = "https://clinicaltrials.gov/api/v2/studies"
OPENFDA = "https://api.fda.gov/drug/label.json"

SERVERS = {"biorxiv": "bioRxiv", "medrxiv": "medRxiv"}
PUB_TYPES = {
    "review": "review",
    "systematic-review": "systematic review",
    "meta-analysis": "meta-analysis",
    "rct": "randomized controlled trial",
    "clinical-trial": "clinical trial",
    "guideline": "guideline",
}
LIT_SORTS = {"relevance": None, "date": "P_PDATE_D desc", "cited": "CITED desc"}
# Publication types that say nothing about evidence level.
GENERIC_PUB_TYPES = {"journal article", "research-article", "article", "preprint", "review-article"}
# Europe PMC matches full text by default, which surfaces papers that mention a
# term once in passing; title/abstract scoping keeps results on-topic.
SCOPES = ("title-abs", "all")
FIELD_SYNTAX = re.compile(r"\b[A-Z_]{2,}:")

TRIAL_STATUSES = {
    "recruiting": ["RECRUITING"],
    "not-yet-recruiting": ["NOT_YET_RECRUITING"],
    "open": ["RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"],
    "active": ["ACTIVE_NOT_RECRUITING"],
    "completed": ["COMPLETED"],
    "terminated": ["TERMINATED"],
    "withdrawn": ["WITHDRAWN"],
    "suspended": ["SUSPENDED"],
}
TRIAL_PHASES = {"early1": "EARLY_PHASE1", "1": "PHASE1", "2": "PHASE2", "3": "PHASE3", "4": "PHASE4"}
TRIAL_SORTS = {"relevance": None, "updated": "LastUpdatePostDate:desc", "start": "StartDate:desc"}

# Short names for label sections; "warnings" covers both the PLR-format field
# and the older one, since a label carries one or the other.
LABEL_SECTIONS = {
    "boxed": ["boxed_warning"],
    "indications": ["indications_and_usage"],
    "dosage": ["dosage_and_administration"],
    "forms": ["dosage_forms_and_strengths"],
    "contraindications": ["contraindications"],
    "warnings": ["warnings_and_cautions", "warnings"],
    "adverse": ["adverse_reactions"],
    "interactions": ["drug_interactions"],
    "populations": ["use_in_specific_populations"],
    "pregnancy": ["pregnancy"],
    "mechanism": ["mechanism_of_action"],
    "pk": ["pharmacokinetics"],
    "studies": ["clinical_studies"],
    "overdose": ["overdosage"],
}
DEFAULT_LABEL_SECTIONS = ["boxed", "indications", "dosage", "contraindications", "warnings", "adverse", "interactions"]


class NotFound(Exception):
    pass


class SourceError(Exception):
    pass


def fetch(url: str, params: dict | None = None, *, raw: bool = False, retries: int = 3):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"
    host = urllib.parse.urlsplit(url).netloc
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
            return body if raw else json.loads(body)
        except urllib.error.HTTPError as exc:
            # openFDA answers an empty result set with 404.
            if exc.code == 404:
                raise NotFound(url) from exc
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2**attempt)
                continue
            detail = clean(exc.read().decode("utf-8", "replace"))[:300]
            raise SourceError(f"HTTP {exc.code} from {host}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < retries - 1:
                time.sleep(2**attempt)
                continue
            raise SourceError(f"{host} unreachable: {exc}") from exc
    raise SourceError(f"{host}: retries exhausted")


def clean(text) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(text))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def clip(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + f" … [+{len(text) - limit:,} chars]"


def split_csv(value: str | None) -> list[str]:
    return [part.strip().lower() for part in (value or "").split(",") if part.strip()]


# --- Literature (Europe PMC) -------------------------------------------------


def literature_query(query, *, source, scope="title-abs", server="all", since=None, until=None, pub_type=None) -> str:
    # A query that already names fields keeps the caller's own scoping.
    scoped = scope == "title-abs" and not FIELD_SYNTAX.search(query)
    parts = [f"TITLE_ABS:({query})" if scoped else f"({query})"]
    if source == "pubmed":
        parts.append("SRC:MED")
    else:
        names = SERVERS.values() if server == "all" else [SERVERS[server]]
        parts.append("SRC:PPR")
        parts.append("(" + " OR ".join(f'PUBLISHER:"{name}"' for name in names) + ")")
    if since or until:
        parts.append(f"PUB_YEAR:[{since or 1800} TO {until or 3000}]")
    if pub_type:
        parts.append(f'PUB_TYPE:"{PUB_TYPES[pub_type]}"')
    return " AND ".join(parts)


def search_literature(query, *, source, limit, sort="relevance", **filters):
    params = {
        "query": literature_query(query, source=source, **filters),
        "format": "json",
        "resultType": "core",
        "pageSize": limit,
    }
    if LIT_SORTS[sort]:
        params["sort"] = LIT_SORTS[sort]
    data = fetch(f"{EPMC}/search", params)
    results = data.get("resultList", {}).get("result", [])
    return data.get("hitCount", 0), [article_record(r) for r in results]


def article_record(r: dict) -> dict:
    preprint = r.get("source") == "PPR"
    journal = ((r.get("journalInfo") or {}).get("journal") or {}).get("title")
    publisher = (r.get("bookOrReportDetails") or {}).get("publisher")
    authors = [a.strip() for a in (r.get("authorString") or "").rstrip(".").split(",") if a.strip()]
    types = [t for t in (r.get("pubTypeList") or {}).get("pubType", [])
             if t.lower() not in GENERIC_PUB_TYPES and not t.lower().startswith("research support")]
    mesh = [m.get("descriptorName") for m in (r.get("meshHeadingList") or {}).get("meshHeading", [])]
    keywords = (r.get("keywordList") or {}).get("keyword", [])
    record = {
        "source": "preprint" if preprint else "pubmed",
        "id": r.get("id") if preprint else f"PMID:{r.get('pmid') or r.get('id')}",
        "pmcid": r.get("pmcid"),
        "doi": r.get("doi"),
        "title": clean(r.get("title")),
        "authors": authors,
        "venue": publisher if preprint else journal,
        "date": r.get("firstPublicationDate") or r.get("pubYear"),
        "cited_by": int(r.get("citedByCount") or 0),
        "types": types,
        "full_text": r.get("inEPMC") == "Y",
        "abstract": clean(r.get("abstractText")),
        "mesh": [m for m in mesh if m],
        "keywords": keywords,
    }
    if preprint:
        record["url"] = f"https://doi.org/{record['doi']}" if record["doi"] else f"https://europepmc.org/article/PPR/{r.get('id')}"
    else:
        record["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{r.get('pmid') or r.get('id')}/"
    return record


def author_line(authors: list[str], limit: int = 3) -> str:
    if len(authors) <= limit:
        return ", ".join(authors)
    return ", ".join(authors[:limit]) + f", et al. ({len(authors)} authors)"


def format_article(index: int, a: dict, abstract_chars: int) -> list[str]:
    meta = [a["id"]]
    if a.get("pmcid"):
        meta.append(a["pmcid"])
    meta += [x for x in (a.get("venue"), a.get("date")) if x]
    if a.get("cited_by"):
        meta.append(f"cited {a['cited_by']}")
    if a.get("types"):
        meta.append(", ".join(a["types"]))
    if a.get("full_text"):
        meta.append("full text available")
    lines = [f"{index}. {a['title']}", "   " + " | ".join(meta)]
    if a.get("authors"):
        lines.append("   " + author_line(a["authors"]))
    if abstract_chars and a.get("abstract"):
        lines.append("   Abstract: " + clip(a["abstract"], abstract_chars))
    return lines


def get_article(kind: str, ident: str) -> dict:
    query = {
        "pmid": f"EXT_ID:{ident} AND SRC:MED",
        "pmc": f"PMCID:{ident}",
        "ppr": f"EXT_ID:{ident} AND SRC:PPR",
        "doi": f'DOI:"{ident}"',
    }[kind]
    data = fetch(f"{EPMC}/search", {"query": query, "format": "json", "resultType": "core", "pageSize": 1})
    results = data.get("resultList", {}).get("result", [])
    if not results:
        raise NotFound(ident)
    return article_record(results[0])


def format_article_detail(a: dict) -> list[str]:
    lines = [f"# {a['title']}", ""]
    ids = [a["id"]] + [x for x in (a.get("pmcid"), a.get("doi") and f"DOI:{a['doi']}") if x]
    lines.append("IDs: " + " | ".join(ids))
    lines.append("Published: " + " | ".join(x for x in (a.get("venue"), a.get("date")) if x))
    if a["source"] == "preprint":
        lines.append("Status: preprint, not peer reviewed")
    if a.get("types"):
        lines.append("Type: " + ", ".join(a["types"]))
    lines.append(f"Cited by: {a.get('cited_by', 0)}")
    if a.get("authors"):
        lines.append("Authors: " + author_line(a["authors"], limit=10))
    if a.get("mesh"):
        lines.append("MeSH: " + "; ".join(a["mesh"][:15]))
    if a.get("keywords"):
        lines.append("Keywords: " + "; ".join(a["keywords"][:15]))
    lines.append("URL: " + a["url"])
    lines.append("Full text: " + ("available, use --full" if a.get("full_text") else "not in Europe PMC; abstract only"))
    lines += ["", "## Abstract", a.get("abstract") or "(no abstract)"]
    return lines


def fulltext_sections(xml_text: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Return (top-level section titles, [(heading, text)]) from JATS XML."""
    root = ET.fromstring(xml_text)
    body = root.find(".//body")
    if body is None:
        return [], []
    out: list[tuple[str, str]] = []

    def text_of(element) -> str:
        return clean("".join(element.itertext()))

    def walk(element, top: str, depth: int):
        for child in element:
            if child.tag == "sec":
                title_el = child.find("title")
                title = text_of(title_el) if title_el is not None else ""
                section_top = top or title
                if title:
                    out.append((section_top, "#" * min(depth + 1, 4) + " " + title))
                walk(child, section_top, depth + 1)
            elif child.tag == "p":
                out.append((top, text_of(child)))

    walk(body, "", 1)
    titles = list(dict.fromkeys(top for top, _ in out if top))
    return titles, out


def format_fulltext(xml_text: str, sections: list[str], max_chars: int) -> list[str]:
    titles, blocks = fulltext_sections(xml_text)
    if not blocks:
        return ["(full text has no body)"]
    lines = ["", "## Full text", "Sections: " + "; ".join(titles), ""]
    if sections:
        blocks = [b for b in blocks if any(s in b[0].lower() for s in sections)]
        if not blocks:
            return lines + [f"(no section matches {', '.join(sections)})"]
    lines.append(clip("\n\n".join(text for _, text in blocks), max_chars))
    return lines


# --- Trials (ClinicalTrials.gov v2) ------------------------------------------


def trial_params(query, *, condition=None, intervention=None, status=None, phase=None,
                 since=None, with_results=False, sort="relevance", limit=10) -> dict:
    params = {"pageSize": limit, "countTotal": "true"}
    if query:
        params["query.term"] = query
    if condition:
        params["query.cond"] = condition
    if intervention:
        params["query.intr"] = intervention
    statuses = [s for key in split_csv(status) for s in TRIAL_STATUSES[key]]
    if statuses:
        params["filter.overallStatus"] = ",".join(dict.fromkeys(statuses))
    advanced = []
    phases = [TRIAL_PHASES[p] for p in split_csv(phase)]
    if phases:
        advanced.append("(" + " OR ".join(f"AREA[Phase]{p}" for p in phases) + ")")
    if since:
        advanced.append(f"AREA[StartDate]RANGE[{since}-01-01,MAX]")
    if advanced:
        params["filter.advanced"] = " AND ".join(advanced)
    if with_results:
        params["aggFilters"] = "results:with"
    if TRIAL_SORTS[sort]:
        params["sort"] = TRIAL_SORTS[sort]
    return params


def search_trials(query, **options):
    data = fetch(CTGOV, trial_params(query, **options))
    return data.get("totalCount", 0), [trial_record(s) for s in data.get("studies", [])]


def trial_record(study: dict) -> dict:
    p = study.get("protocolSection", {})
    ident = p.get("identificationModule", {})
    status = p.get("statusModule", {})
    design = p.get("designModule", {})
    arms = p.get("armsInterventionsModule", {})
    nct = ident.get("nctId")
    enrollment = design.get("enrollmentInfo", {})
    return {
        "source": "trial",
        "id": nct,
        "title": clean(ident.get("briefTitle")),
        "official_title": clean(ident.get("officialTitle")),
        "status": status.get("overallStatus"),
        "why_stopped": status.get("whyStopped"),
        "phases": design.get("phases", []),
        "study_type": design.get("studyType"),
        "enrollment": enrollment.get("count"),
        "enrollment_type": enrollment.get("type"),
        "start": (status.get("startDateStruct") or {}).get("date"),
        "primary_completion": (status.get("primaryCompletionDateStruct") or {}).get("date"),
        "conditions": p.get("conditionsModule", {}).get("conditions", []),
        "interventions": [f"{i.get('type', '').title()}: {i.get('name')}" for i in arms.get("interventions", [])],
        "sponsor": p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name"),
        "has_results": bool(study.get("hasResults")),
        "summary": clean(p.get("descriptionModule", {}).get("briefSummary")),
        "url": f"https://clinicaltrials.gov/study/{nct}",
    }


def trial_meta(t: dict) -> str:
    meta = [t["status"] or "UNKNOWN STATUS"]
    if t["phases"]:
        meta.append("/".join(t["phases"]))
    if t["study_type"]:
        meta.append(t["study_type"])
    if t["enrollment"]:
        meta.append(f"n={t['enrollment']}" + (" (est.)" if t["enrollment_type"] == "ESTIMATED" else ""))
    if t["start"]:
        meta.append(f"start {t['start']}")
    if t["primary_completion"]:
        meta.append(f"primary completion {t['primary_completion']}")
    meta.append("results posted" if t["has_results"] else "no results posted")
    return " | ".join(meta)


def format_trial(index: int, t: dict, summary_chars: int) -> list[str]:
    lines = [f"{index}. {t['id']} {t['title']}", "   " + trial_meta(t)]
    detail = []
    if t["conditions"]:
        detail.append("Conditions: " + "; ".join(t["conditions"][:4]))
    if t["interventions"]:
        detail.append("Interventions: " + "; ".join(t["interventions"][:4]))
    if t["sponsor"]:
        detail.append("Sponsor: " + t["sponsor"])
    if detail:
        lines.append("   " + " | ".join(detail))
    if summary_chars and t["summary"]:
        lines.append("   Summary: " + clip(t["summary"], summary_chars))
    return lines


def primary_results(study: dict) -> list[str]:
    """Best-effort digest of posted primary outcome results."""
    measures = study.get("resultsSection", {}).get("outcomeMeasuresModule", {}).get("outcomeMeasures", [])
    lines = []
    for m in measures:
        if m.get("type") != "PRIMARY":
            continue
        groups = {g.get("id"): g.get("title") for g in m.get("groups", [])}
        unit = m.get("unitOfMeasure", "")
        lines.append(f"- {clean(m.get('title'))} ({m.get('timeFrame', '')})")
        try:
            measurements = m["classes"][0]["categories"][0]["measurements"]
        except (KeyError, IndexError):
            measurements = []
        for meas in measurements:
            spread = f" ± {meas['spread']}" if meas.get("spread") else ""
            lines.append(f"    {groups.get(meas.get('groupId'), meas.get('groupId'))}: {meas.get('value')}{spread} {unit}".rstrip())
        for analysis in m.get("analyses", [])[:2]:
            if analysis.get("pValue"):
                method = analysis.get("statisticalMethod", "")
                lines.append(f"    p={analysis['pValue']} {method}".rstrip())
    return lines


def format_trial_detail(study: dict, criteria_chars: int) -> list[str]:
    t = trial_record(study)
    p = study.get("protocolSection", {})
    lines = [f"# {t['id']} {t['title']}", ""]
    if t["official_title"] and t["official_title"] != t["title"]:
        lines.append("Official title: " + t["official_title"])
    lines.append(trial_meta(t))
    if t["why_stopped"]:
        lines.append("Why stopped: " + t["why_stopped"])
    lines.append("Sponsor: " + (t["sponsor"] or "unknown"))
    lines.append("Conditions: " + "; ".join(t["conditions"]))
    lines.append("URL: " + t["url"])
    lines += ["", "## Summary", t["summary"] or "(none)"]
    arms = p.get("armsInterventionsModule", {}).get("armGroups", [])
    if arms:
        lines += ["", "## Arms"]
        lines += [f"- {a.get('label')} ({a.get('type', '')}): {clip(clean(a.get('description')), 300)}" for a in arms]
    outcomes = p.get("outcomesModule", {})
    if outcomes.get("primaryOutcomes"):
        lines += ["", "## Primary outcomes"]
        lines += [f"- {clean(o.get('measure'))} ({o.get('timeFrame', '')})" for o in outcomes["primaryOutcomes"]]
    if outcomes.get("secondaryOutcomes"):
        lines.append(f"Secondary outcomes: {len(outcomes['secondaryOutcomes'])}")
    if t["has_results"]:
        results = primary_results(study)
        lines += ["", "## Posted primary results"] + (results or ["(posted, but not in a parseable shape; see URL)"])
    elig = p.get("eligibilityModule", {})
    if elig:
        ages = " to ".join(x for x in (elig.get("minimumAge"), elig.get("maximumAge")) if x)
        lines += ["", "## Eligibility", f"Sex: {elig.get('sex', 'ALL')} | Age: {ages or 'any'} | Healthy volunteers: {elig.get('healthyVolunteers', False)}"]
        lines.append(clip(clean(elig.get("eligibilityCriteria")), criteria_chars))
    locations = p.get("contactsLocationsModule", {}).get("locations", [])
    if locations:
        countries = sorted({loc.get("country") for loc in locations if loc.get("country")})
        lines += ["", f"Sites: {len(locations)} in {', '.join(countries)}"]
    return lines


# --- Drug labels (openFDA) ---------------------------------------------------


def label_search_expr(query: str | None = None, drug: str | None = None) -> str:
    if drug:
        name = drug.replace('"', "")
        # A space between clauses is OR in openFDA.
        return " ".join(f'openfda.{field}:"{name}"' for field in ("brand_name", "generic_name", "substance_name"))
    if re.search(r'[:"]|\b(AND|OR|NOT)\b', query):
        return query
    return " AND ".join(query.split())


def label_fields(sections: list[str]) -> list[str]:
    return [field for key in sections for field in LABEL_SECTIONS[key]]


def search_labels(query=None, *, drug=None, limit=5):
    params = {"search": label_search_expr(query, drug), "limit": min(100, limit * 5), "sort": "effective_time:desc"}
    if os.environ.get("OPENFDA_API_KEY"):
        params["api_key"] = os.environ["OPENFDA_API_KEY"]
    try:
        data = fetch(OPENFDA, params)
    except NotFound:
        return 0, []
    records = dedupe_labels([label_record(r) for r in data.get("results", [])])
    return data.get("meta", {}).get("results", {}).get("total", 0), records[:limit]


def dedupe_labels(records: list[dict]) -> list[dict]:
    """Keep the newest label per product; repackagers repeat the same text."""
    seen, out = set(), []
    for record in records:
        key = (record["name"].lower(), record["generic"].lower(), record["route"].lower())
        if key not in seen:
            seen.add(key)
            out.append(record)
    return out


def label_record(r: dict) -> dict:
    o = r.get("openfda") or {}
    product = clean(" ".join(r.get("spl_product_data_elements", [])))
    effective = r.get("effective_time", "")
    return {
        "source": "label",
        "id": f"label:{r.get('set_id')}",
        "name": ", ".join(o.get("brand_name", [])[:2]) or product.split(" ")[0] or "unknown product",
        "generic": ", ".join(o.get("generic_name", [])[:2]),
        "manufacturer": (o.get("manufacturer_name") or [""])[0],
        "route": ", ".join(o.get("route", [])),
        "product_type": (o.get("product_type") or [""])[0],
        "effective": f"{effective[:4]}-{effective[4:6]}-{effective[6:8]}" if len(effective) == 8 else effective,
        "has_openfda": bool(o),
        "sections": {f: clean(" ".join(r[f])) for fields in LABEL_SECTIONS.values() for f in fields if r.get(f)},
        "url": f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={r.get('set_id')}",
    }


def label_heading(label: dict) -> str:
    name = label["name"] + (f" ({label['generic']})" if label["generic"] and label["generic"].lower() != label["name"].lower() else "")
    meta = [x for x in (label["manufacturer"], label["route"], label["product_type"]) if x]
    meta.append(f"effective {label['effective']}")
    if not label["has_openfda"]:
        meta.append("no openFDA metadata (often unapproved or OTC monograph)")
    return f"{name} | " + " | ".join(meta)


def format_label(index: int, label: dict, snippet_chars: int) -> list[str]:
    lines = [f"{index}. {label_heading(label)}", f"   {label['id']}"]
    if "boxed_warning" in label["sections"]:
        lines.append("   BOXED WARNING: " + clip(label["sections"]["boxed_warning"], snippet_chars))
    if "indications_and_usage" in label["sections"]:
        lines.append("   Indications: " + clip(label["sections"]["indications_and_usage"], snippet_chars))
    return lines


def get_label(set_id: str) -> dict:
    try:
        data = fetch(OPENFDA, {"search": f'set_id:"{set_id}"', "limit": 1})
    except NotFound:
        raise NotFound(set_id)
    return label_record(data["results"][0])


def format_label_detail(label: dict, sections: list[str], section_chars: int) -> list[str]:
    lines = [f"# {label_heading(label)}", label["id"], "URL: " + label["url"]]
    names = {field: key for key, fields in LABEL_SECTIONS.items() for field in fields}
    present = [names[f] for f in label["sections"]]
    lines.append("Sections on this label: " + ", ".join(dict.fromkeys(present)))
    for field in label_fields(sections):
        if field in label["sections"]:
            lines += ["", f"## {field.replace('_', ' ').capitalize()}", clip(label["sections"][field], section_chars)]
    return lines


# --- Commands ----------------------------------------------------------------


def resolve_id(raw: str) -> tuple[str, str]:
    s = raw.strip()
    if re.fullmatch(r"(?i)nct\d{8}", s):
        return "trial", s.upper()
    if s.lower().startswith("label:"):
        return "label", s[6:]
    if re.fullmatch(r"(?i)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", s):
        return "label", s.lower()
    if re.fullmatch(r"(?i)pmc\d+", s):
        return "pmc", s.upper()
    if re.fullmatch(r"(?i)ppr\d+", s):
        return "ppr", s.upper()
    if m := re.fullmatch(r"(?i)(?:pmid:?\s*)?(\d+)", s):
        return "pmid", m.group(1)
    if m := re.fullmatch(r"(?i)(?:doi:\s*|https?://(?:dx\.)?doi\.org/)?(10\.\d+/\S+)", s):
        return "doi", m.group(1)
    raise ValueError(f"unrecognized id {raw!r}: expected PMID, PMCID, PPR id, DOI, NCT id, or label:<set_id>")


def emit(blocks: list[dict], as_json: bool, render) -> int:
    """Print blocks of {name, total, results} or {name, error}; exit 1 if all failed."""
    if as_json:
        print(json.dumps(blocks if len(blocks) > 1 else blocks[0], indent=2))
    else:
        for block in blocks:
            if "error" in block:
                print(f"## {block['name']}: ERROR {block['error']}\n")
                continue
            print(f"## {block['name']}: {block['total']:,} matches, showing {len(block['results'])}")
            if not block["results"]:
                print("(no matches)")
            for i, record in enumerate(block["results"], 1):
                print("\n".join(render(i, record)))
            print()
    return 1 if all("error" in b for b in blocks) else 0


def render_any(abstract_chars: int):
    def render(i, record):
        if record["source"] == "trial":
            return format_trial(i, record, abstract_chars)
        if record["source"] == "label":
            return format_label(i, record, max(abstract_chars, 300))
        return format_article(i, record, abstract_chars)
    return render


def run_jobs(jobs: dict) -> list[dict]:
    blocks = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {name: pool.submit(job) for name, job in jobs.items()}
        for name, future in futures.items():
            try:
                total, results = future.result()
                blocks.append({"name": name, "total": total, "results": results})
            except (SourceError, NotFound, ValueError) as exc:
                blocks.append({"name": name, "error": str(exc)})
    return blocks


def cmd_search(args) -> int:
    q, n = args.query, args.limit
    jobs = {
        "PubMed": lambda: search_literature(q, source="pubmed", limit=n, scope=args.scope, since=args.since),
        "Preprints (bioRxiv/medRxiv)": lambda: search_literature(q, source="preprints", limit=n, scope=args.scope, since=args.since),
        "ClinicalTrials.gov": lambda: search_trials(q, limit=n, since=args.since),
    }
    if args.drug:
        jobs["FDA drug labels"] = lambda: search_labels(drug=args.drug, limit=n)
    return emit(run_jobs(jobs), args.json, render_any(args.abstracts))


def cmd_pubmed(args) -> int:
    job = lambda: search_literature(args.query, source="pubmed", limit=args.limit, sort=args.sort,
                                    scope=args.scope, since=args.since, until=args.until, pub_type=args.type)
    return emit(run_jobs({"PubMed": job}), args.json, render_any(args.abstracts))


def cmd_preprints(args) -> int:
    job = lambda: search_literature(args.query, source="preprints", limit=args.limit, sort=args.sort,
                                    scope=args.scope, server=args.server, since=args.since, until=args.until)
    return emit(run_jobs({f"Preprints ({args.server})": job}), args.json, render_any(args.abstracts))


def cmd_trials(args) -> int:
    if not (args.query or args.condition or args.intervention):
        raise ValueError("give a query, --condition, or --intervention")
    for key in split_csv(args.status):
        if key not in TRIAL_STATUSES:
            raise ValueError(f"unknown status {key!r}; choose from {', '.join(TRIAL_STATUSES)}")
    for key in split_csv(args.phase):
        if key not in TRIAL_PHASES:
            raise ValueError(f"unknown phase {key!r}; choose from {', '.join(TRIAL_PHASES)}")
    job = lambda: search_trials(args.query, condition=args.condition, intervention=args.intervention,
                                status=args.status, phase=args.phase, since=args.since,
                                with_results=args.with_results, sort=args.sort, limit=args.limit)
    return emit(run_jobs({"ClinicalTrials.gov": job}), args.json, render_any(args.summaries))


def cmd_labels(args) -> int:
    if not (args.query or args.drug):
        raise ValueError("give a query or --drug")
    job = lambda: search_labels(args.query, drug=args.drug, limit=args.limit)
    return emit(run_jobs({"FDA drug labels": job}), args.json, render_any(args.snippet))


def parse_sections(value: str) -> list[str]:
    if value == "all":
        return list(LABEL_SECTIONS)
    keys = split_csv(value)
    unknown = [k for k in keys if k not in LABEL_SECTIONS]
    if unknown:
        raise ValueError(f"unknown label section {', '.join(unknown)}; choose from {', '.join(LABEL_SECTIONS)}, all")
    return keys


def cmd_get(args) -> int:
    kind, ident = resolve_id(args.id)
    if kind == "trial":
        study = fetch(f"{CTGOV}/{ident}")
        if args.json:
            print(json.dumps(study, indent=2))
        else:
            print("\n".join(format_trial_detail(study, args.max_chars)))
        return 0
    if kind == "label":
        label = get_label(ident)
        if args.json:
            print(json.dumps(label, indent=2))
        else:
            sections = parse_sections(args.sections or ",".join(DEFAULT_LABEL_SECTIONS))
            print("\n".join(format_label_detail(label, sections, args.max_chars)))
        return 0
    article = get_article(kind, ident)
    lines = format_article_detail(article)
    if args.full:
        target = article.get("pmcid") or (article["id"] if article["source"] == "preprint" else None)
        try:
            if not target:
                raise NotFound(ident)
            xml_text = fetch(f"{EPMC}/{target}/fullTextXML", raw=True)
            lines += format_fulltext(xml_text, split_csv(args.sections), args.max_chars * 5)
            article["full_text_xml_source"] = f"{EPMC}/{target}/fullTextXML"
        except NotFound:
            lines += ["", "## Full text", f"(no open full text in Europe PMC; read the abstract or {article['url']})"]
    if args.json:
        print(json.dumps(article, indent=2))
    else:
        print("\n".join(lines))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="biosearch",
        description="Search PubMed, bioRxiv/medRxiv, ClinicalTrials.gov, and FDA drug labels. "
        "Searches list compact records; `get <id>` returns one record in depth.",
    )
    parser.add_argument("--version", action="version", version=f"biosearch {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="emit JSON instead of text")

    def scope(p):
        p.add_argument("--scope", choices=SCOPES, default="title-abs",
                       help="literature match scope (default title-abs; all adds full text). Fielded queries keep their own scope")

    def years(p):
        p.add_argument("--since", type=int, metavar="YEAR", help="published (or started) in YEAR or later")

    s = sub.add_parser("search", parents=[common], help="fan out one query to literature, preprints, and trials")
    s.add_argument("query", help="Europe PMC syntax; plain words are ANDed")
    s.add_argument("--limit", type=int, default=5, help="results per source (default 5)")
    s.add_argument("--abstracts", type=int, nargs="?", const=600, default=0, metavar="CHARS",
                   help="include abstracts/summaries, clipped to CHARS (default 600)")
    s.add_argument("--drug", help="also search FDA labels for this drug name")
    scope(s)
    years(s)
    s.set_defaults(func=cmd_search)

    for name, helptext in (("pubmed", "search PubMed (via Europe PMC)"), ("preprints", "search bioRxiv and medRxiv preprints")):
        p = sub.add_parser(name, parents=[common], help=helptext)
        p.add_argument("query", help="Europe PMC syntax: TITLE:, ABSTRACT:, AUTH:, MESH:, \"phrase\", AND/OR/NOT")
        p.add_argument("--limit", type=int, default=10, help="max results (default 10, max 1000)")
        p.add_argument("--sort", choices=list(LIT_SORTS), default="relevance")
        p.add_argument("--abstracts", type=int, nargs="?", const=600, default=0, metavar="CHARS",
                       help="include abstracts, clipped to CHARS (default 600)")
        scope(p)
        years(p)
        p.add_argument("--until", type=int, metavar="YEAR", help="published in YEAR or earlier")
        if name == "pubmed":
            p.add_argument("--type", choices=list(PUB_TYPES), help="publication type filter")
            p.set_defaults(func=cmd_pubmed)
        else:
            p.add_argument("--server", choices=["all", *SERVERS], default="all")
            p.set_defaults(func=cmd_preprints)

    t = sub.add_parser("trials", parents=[common], help="search ClinicalTrials.gov")
    t.add_argument("query", nargs="?", help="free-text terms (Essie syntax)")
    t.add_argument("--condition", help="condition or disease")
    t.add_argument("--intervention", help="drug, device, or procedure")
    t.add_argument("--status", help=f"comma list: {', '.join(TRIAL_STATUSES)}")
    t.add_argument("--phase", help=f"comma list: {', '.join(TRIAL_PHASES)}")
    t.add_argument("--with-results", action="store_true", help="only trials with posted results")
    t.add_argument("--sort", choices=list(TRIAL_SORTS), default="relevance")
    t.add_argument("--limit", type=int, default=10, help="max results (default 10, max 1000)")
    t.add_argument("--summaries", type=int, nargs="?", const=400, default=0, metavar="CHARS",
                   help="include brief summaries, clipped to CHARS (default 400)")
    years(t)
    t.set_defaults(func=cmd_trials)

    lb = sub.add_parser("labels", parents=[common], help="search FDA drug labels (openFDA)")
    lb.add_argument("query", nargs="?", help="free text across all label sections, or openFDA field syntax")
    lb.add_argument("--drug", help="match brand, generic, or substance name")
    lb.add_argument("--limit", type=int, default=5, help="max distinct products (default 5)")
    lb.add_argument("--snippet", type=int, default=300, metavar="CHARS", help="indication/boxed-warning clip (default 300)")
    lb.set_defaults(func=cmd_labels)

    g = sub.add_parser("get", parents=[common], help="one record in depth: PMID, PMCID, PPR id, DOI, NCT id, or label:<set_id>")
    g.add_argument("id")
    g.add_argument("--full", action="store_true", help="articles: append open-access full text when Europe PMC has it")
    g.add_argument("--sections", help="articles with --full: comma list of section-title substrings (e.g. methods,results); "
                   f"labels: comma list of {', '.join(LABEL_SECTIONS)}, or all")
    g.add_argument("--max-chars", type=int, default=4000,
                   help="clip per label section or eligibility criteria (default 4000); full text gets 5x")
    g.set_defaults(func=cmd_get)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"biosearch: {exc}", file=sys.stderr)
        return 2
    except NotFound as exc:
        print(f"biosearch: not found: {exc}", file=sys.stderr)
        return 1
    except SourceError as exc:
        print(f"biosearch: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

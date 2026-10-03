"""Citation checker for FORGE.

Checks two separate things for every reference:

1. Resolution: does the identifier (DOI, arXiv ID, OpenAlex work ID or URL)
   point to a real record?
2. Quote support: when a quoted span is given, does it appear in the source
   text we can retrieve?

These are reported separately (benchmark metrics S3 and S4 in
bench/PROTOCOL.md). An identifier that resolves can still fail to support the
quote it is cited for.

Limits:
- Quote checks run against the text we can fetch: the arXiv abstract, the
  OpenAlex/Crossref abstract, or a full text file supplied by the caller.
  A quote taken from a paper body is reported as "not_in_available_text",
  not as "fabricated".
- A network error is not a failed resolution. Errors get resolved=None and
  are counted separately so they never inflate the unresolvable rate.

Usage:
    python tools/citation_check.py refs.json -o citations.json
    python tools/citation_check.py final_report.md -o citations.json

refs.json is a list of objects: {"ref": "<id or url>", "quote": "...",
"claim": "...", "fulltext_path": "..."}; only "ref" is required. For a
Markdown/text input, identifiers are extracted with regexes and have no quotes.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import quote as urlquote

SCHEMA_VERSION = "1.0"
TIMEOUT_SECONDS = 20

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>\]\)]+)", re.IGNORECASE)
ARXIV_NEW_RE = re.compile(r"\b(\d{4}\.\d{4,5})(v\d+)?\b")
ARXIV_OLD_RE = re.compile(r"\b([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?\b")
ARXIV_PREFIX_RE = re.compile(
    r"(?:arxiv:|arxiv\.org/(?:abs|pdf)/)\s*([^\s\"'<>\]\)]+?)(?:\.pdf)?(?=[\s\"'<>\]\),;]|$)",
    re.IGNORECASE,
)
OPENALEX_RE = re.compile(r"(?:openalex\.org/)?\b(W\d{4,})\b")
URL_RE = re.compile(r"https?://[^\s\"'<>\]\)]+")

ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass
class Response:
    status: int
    text: str


Fetcher = Callable[[str], Response]


@dataclass
class RefResult:
    ref: str
    kind: str  # doi | arxiv | openalex | url | unknown
    normalized_id: Optional[str]
    resolved: Optional[bool]  # None means we could not check (network error)
    resolver: Optional[str]
    title: Optional[str] = None
    quote: Optional[str] = None
    claim: Optional[str] = None
    # found | not_in_available_text | no_quote | source_text_unavailable | unchecked
    quote_status: str = "no_quote"
    checked_text: Optional[str] = None  # abstract | fulltext | None
    error: Optional[str] = None
    notes: list[str] = field(default_factory=list)


def default_fetcher(url: str) -> Response:
    import requests

    headers = {"User-Agent": "forge-citation-check/1.0"}
    contact = os.environ.get("FORGE_CONTACT_EMAIL")
    if contact:
        headers["User-Agent"] += f" (mailto:{contact})"
    r = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS, allow_redirects=True)
    return Response(status=r.status_code, text=r.text)


# ---------------------------------------------------------------- parsing


def classify(ref: str) -> tuple[str, Optional[str]]:
    """Return (kind, normalized identifier) for a reference string."""
    s = ref.strip()
    m = ARXIV_PREFIX_RE.search(s)
    if m:
        return "arxiv", _strip_arxiv_version(m.group(1))
    m = DOI_RE.search(s)
    if m:
        return "doi", _clean_doi(m.group(1))
    m = OPENALEX_RE.fullmatch(s) or (OPENALEX_RE.search(s) if "openalex.org" in s else None)
    if m:
        return "openalex", m.group(1)
    m = ARXIV_NEW_RE.fullmatch(s) or ARXIV_OLD_RE.fullmatch(s)
    if m:
        return "arxiv", m.group(1)
    if URL_RE.fullmatch(s):
        return "url", s
    return "unknown", None


def _clean_doi(doi: str) -> str:
    return doi.rstrip(".,;:").lower()


def _strip_arxiv_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id.strip().rstrip(".,;:"))


def extract_refs(text: str) -> list[str]:
    """Extract unique identifiers from free text, in order of appearance."""
    found: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []

    def add(start: int, end: int, value: str) -> None:
        if any(start < e and s < end for s, e in taken):
            return
        taken.append((start, end))
        found.append((start, value))

    for m in ARXIV_PREFIX_RE.finditer(text):
        add(m.start(), m.end(), "arXiv:" + _strip_arxiv_version(m.group(1)))
    for m in DOI_RE.finditer(text):
        add(m.start(), m.end(), _clean_doi(m.group(1)))
    for m in OPENALEX_RE.finditer(text):
        add(m.start(), m.end(), m.group(1))
    for m in URL_RE.finditer(text):
        add(m.start(), m.end(), m.group(0).rstrip(".,;:"))

    seen: set[str] = set()
    out = []
    for _, value in sorted(found):
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


# ---------------------------------------------------------------- text matching


def normalize_text(s: str) -> str:
    s = html.unescape(s)
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"<[^>]+>", " ", s)  # JATS/HTML tags in Crossref abstracts
    s = s.replace("‐", "-").replace("‑", "-").replace("–", "-").replace("—", "-")
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def quote_in_text(quote: str, text: str) -> bool:
    q = normalize_text(quote)
    return bool(q) and q in normalize_text(text)


def abstract_from_inverted_index(index: Optional[dict]) -> Optional[str]:
    if not index:
        return None
    positions = [(pos, word) for word, poss in index.items() for pos in poss]
    return " ".join(word for _, word in sorted(positions))


# ---------------------------------------------------------------- resolvers


def _resolve_doi(doi: str, fetch: Fetcher) -> tuple[Optional[bool], str, Optional[str], Optional[str], list[str]]:
    """Returns (resolved, resolver, title, abstract, notes)."""
    notes: list[str] = []
    r = fetch(f"https://api.openalex.org/works/doi:{urlquote(doi, safe='/')}")
    if r.status == 200:
        data = json.loads(r.text)
        abstract = abstract_from_inverted_index(data.get("abstract_inverted_index"))
        return True, "openalex", data.get("display_name") or data.get("title"), abstract, notes
    notes.append(f"openalex status {r.status}")
    r = fetch(f"https://api.crossref.org/works/{urlquote(doi, safe='/')}")
    if r.status == 200:
        msg = json.loads(r.text).get("message", {})
        titles = msg.get("title") or []
        return True, "crossref", titles[0] if titles else None, msg.get("abstract"), notes
    notes.append(f"crossref status {r.status}")
    if r.status == 404:
        return False, "crossref", None, None, notes
    return None, "crossref", None, None, notes


def _resolve_arxiv(arxiv_id: str, fetch: Fetcher) -> tuple[Optional[bool], str, Optional[str], Optional[str], list[str]]:
    r = fetch(f"https://export.arxiv.org/api/query?id_list={urlquote(arxiv_id, safe='/')}")
    if r.status != 200:
        return (False if r.status in (400, 404) else None), "arxiv", None, None, [f"arxiv status {r.status}"]
    root = ET.fromstring(r.text)
    for entry in root.findall(f"{ATOM}entry"):
        entry_id = (entry.findtext(f"{ATOM}id") or "").strip()
        title = " ".join((entry.findtext(f"{ATOM}title") or "").split())
        # The arXiv API returns an "Error" entry instead of a 4xx for bad IDs.
        if "/api/errors" in entry_id or title.lower() == "error":
            return False, "arxiv", None, None, ["arxiv returned an error entry"]
        if _strip_arxiv_version(entry_id.rsplit("/abs/", 1)[-1]) == arxiv_id:
            summary = " ".join((entry.findtext(f"{ATOM}summary") or "").split())
            return True, "arxiv", title, summary, []
    return False, "arxiv", None, None, ["no matching arxiv entry"]


def _resolve_openalex(work_id: str, fetch: Fetcher) -> tuple[Optional[bool], str, Optional[str], Optional[str], list[str]]:
    r = fetch(f"https://api.openalex.org/works/{work_id}")
    if r.status == 200:
        data = json.loads(r.text)
        return True, "openalex", data.get("display_name"), abstract_from_inverted_index(data.get("abstract_inverted_index")), []
    return (False if r.status == 404 else None), "openalex", None, None, [f"openalex status {r.status}"]


def _resolve_url(url: str, fetch: Fetcher) -> tuple[Optional[bool], str, Optional[str], Optional[str], list[str]]:
    r = fetch(url)
    if r.status < 400:
        return True, "http", None, None, ["page text is not used for quote checks"]
    if r.status in (404, 410):
        return False, "http", None, None, [f"http status {r.status}"]
    return None, "http", None, None, [f"http status {r.status}"]


RESOLVERS = {"doi": _resolve_doi, "arxiv": _resolve_arxiv, "openalex": _resolve_openalex, "url": _resolve_url}


def check_ref(item: dict, fetch: Fetcher = default_fetcher) -> RefResult:
    ref = str(item["ref"])
    kind, norm = classify(ref)
    result = RefResult(ref=ref, kind=kind, normalized_id=norm, resolved=None, resolver=None,
                       quote=item.get("quote") or None, claim=item.get("claim") or None)
    if kind == "unknown":
        result.resolved = False
        result.notes.append("not a recognizable DOI, arXiv ID, OpenAlex ID or URL")
        result.quote_status = "unchecked" if result.quote else "no_quote"
        return result

    abstract = None
    try:
        resolved, resolver, title, abstract, notes = RESOLVERS[kind](norm, fetch)
        result.resolved, result.resolver, result.title = resolved, resolver, title
        result.notes.extend(notes)
    except Exception as exc:  # network failures, malformed responses
        result.error = f"{type(exc).__name__}: {exc}"

    if not result.quote:
        result.quote_status = "no_quote"
        return result
    if result.resolved is not True:
        result.quote_status = "unchecked"
        return result

    fulltext_path = item.get("fulltext_path")
    if fulltext_path:
        with open(fulltext_path, encoding="utf-8", errors="replace") as f:
            source, result.checked_text = f.read(), "fulltext"
    elif abstract:
        source, result.checked_text = abstract, "abstract"
    else:
        result.quote_status = "source_text_unavailable"
        return result
    result.quote_status = "found" if quote_in_text(result.quote, source) else "not_in_available_text"
    return result


# ---------------------------------------------------------------- summary


def summarize(results: list[RefResult]) -> dict:
    total = len(results)
    errors = sum(r.resolved is None for r in results)
    unresolvable = sum(r.resolved is False for r in results)
    resolvable = sum(r.resolved is True for r in results)
    checked = total - errors
    with_quote = [r for r in results if r.resolved is True and r.quote]
    found = sum(r.quote_status == "found" for r in with_quote)
    not_found = sum(r.quote_status == "not_in_available_text" for r in with_quote)
    unavailable = sum(r.quote_status == "source_text_unavailable" for r in with_quote)
    quote_checked = found + not_found
    return {
        "references_total": total,
        "check_errors": errors,
        "references_checked": checked,
        "unresolvable": unresolvable,
        "resolvable": resolvable,
        # S3: unresolvable / references actually checked (errors excluded and reported).
        "unresolvable_rate": (unresolvable / checked) if checked else None,
        "resolvable_with_quote": len(with_quote),
        "quote_found": found,
        "quote_not_in_available_text": not_found,
        "quote_source_text_unavailable": unavailable,
        # S4: quotes not found / quotes we could check against some source text.
        "unsupported_quote_rate": (not_found / quote_checked) if quote_checked else None,
    }


def run(items: list[dict], fetch: Fetcher = default_fetcher) -> dict:
    results = [check_ref(item, fetch) for item in items]
    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": summarize(results),
        "results": [asdict(r) for r in results],
    }


def load_items(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    if path.endswith(".json"):
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("JSON input must be a list of reference objects")
        return [d if isinstance(d, dict) else {"ref": str(d)} for d in data]
    return [{"ref": ref} for ref in extract_refs(raw)]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check that references resolve and quotes appear in the source.")
    parser.add_argument("input", help="refs .json list, or a .md/.txt report to extract identifiers from")
    parser.add_argument("-o", "--output", help="write JSON report here (default: stdout)")
    args = parser.parse_args(argv)

    report = run(load_items(args.input))
    out = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out + "\n")
    else:
        print(out)
    s = report["summary"]
    print(
        f"{s['references_total']} refs: {s['resolvable']} resolved, {s['unresolvable']} unresolvable, "
        f"{s['check_errors']} errors; quotes found {s['quote_found']}/"
        f"{s['quote_found'] + s['quote_not_in_available_text']} checkable",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

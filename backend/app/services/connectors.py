from collections.abc import Iterable
from urllib.parse import quote_plus

import httpx

from app.utils import RCAABUT_CATEGORIES


def _clean(value: str | None) -> str:
    return " ".join((value or "").split())


def _score(query_terms: set[str], title: str, abstract: str = "") -> float:
    haystack = f"{title} {abstract}".lower()
    if not query_terms:
        return 0.5
    matches = sum(1 for term in query_terms if term in haystack)
    return min(0.95, 0.45 + (matches / max(len(query_terms), 1)) * 0.5)


def _query_terms(query: str) -> set[str]:
    stop = {"and", "the", "for", "with", "from", "into", "course", "topic", "week"}
    return {part.lower() for part in query.split() if len(part) > 3 and part.lower() not in stop}


def _dedupe(rows: Iterable[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for row in rows:
        key = (row.get("url") or row.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def search_openalex(query: str, limit: int = 8) -> list[dict]:
    try:
        response = httpx.get(
            "https://api.openalex.org/works",
            params={"search": query, "per-page": limit, "sort": "relevance_score:desc"},
            timeout=18,
        )
        response.raise_for_status()
    except Exception:
        return []

    terms = _query_terms(query)
    rows: list[dict] = []
    for item in response.json().get("results", []):
        title = _clean(item.get("title"))
        if not title:
            continue
        authors = [
            _clean((authorship.get("author") or {}).get("display_name"))
            for authorship in item.get("authorships", [])[:4]
            if (authorship.get("author") or {}).get("display_name")
        ]
        abstract = " ".join((item.get("abstract_inverted_index") or {}).keys())[:1000]
        work_type = item.get("type") or "journal-article"
        category = "Journal Articles" if "article" in work_type else "Books"
        rows.append(
            {
                "category": category,
                "title": title,
                "authors": authors,
                "year": item.get("publication_year"),
                "abstract": abstract,
                "url": item.get("doi") or item.get("id") or "",
                "source_system": "openalex",
                "source_record_id": item.get("id"),
                "relevance_score": _score(terms, title, abstract),
                "match_reason": "Matched through OpenAlex scholarly metadata search.",
            }
        )
    return rows


def search_crossref(query: str, limit: int = 8) -> list[dict]:
    try:
        response = httpx.get(
            "https://api.crossref.org/works",
            params={"query": query, "rows": limit, "select": "DOI,title,author,published-print,published-online,URL,type,abstract"},
            timeout=18,
        )
        response.raise_for_status()
    except Exception:
        return []

    terms = _query_terms(query)
    rows: list[dict] = []
    for item in response.json().get("message", {}).get("items", []):
        title = _clean((item.get("title") or [""])[0])
        if not title:
            continue
        authors = [
            _clean(f"{author.get('given', '')} {author.get('family', '')}")
            for author in item.get("author", [])[:4]
            if author.get("family") or author.get("given")
        ]
        year_parts = (item.get("published-print") or item.get("published-online") or {}).get("date-parts") or []
        year = year_parts[0][0] if year_parts and year_parts[0] else None
        abstract = _clean(item.get("abstract"))[:1000]
        rows.append(
            {
                "category": "Journal Articles",
                "title": title,
                "authors": authors,
                "year": year,
                "abstract": abstract,
                "url": item.get("URL") or (f"https://doi.org/{item.get('DOI')}" if item.get("DOI") else ""),
                "source_system": "crossref",
                "source_record_id": item.get("DOI"),
                "relevance_score": _score(terms, title, abstract),
                "match_reason": "Matched through Crossref DOI metadata.",
            }
        )
    return rows


def search_open_library(query: str, limit: int = 8) -> list[dict]:
    try:
        response = httpx.get(
            "https://openlibrary.org/search.json",
            params={"q": query, "limit": limit},
            timeout=18,
        )
        response.raise_for_status()
    except Exception:
        return []

    terms = _query_terms(query)
    rows: list[dict] = []
    for item in response.json().get("docs", []):
        title = _clean(item.get("title"))
        if not title:
            continue
        key = item.get("key")
        rows.append(
            {
                "category": "Books",
                "title": title,
                "authors": [_clean(author) for author in item.get("author_name", [])[:4]],
                "year": item.get("first_publish_year"),
                "abstract": _clean(", ".join(item.get("subject", [])[:8])),
                "url": f"https://openlibrary.org{key}" if key else f"https://openlibrary.org/search?q={quote_plus(query)}",
                "source_system": "open_library",
                "source_record_id": key,
                "relevance_score": _score(terms, title, " ".join(item.get("subject", [])[:8])),
                "match_reason": "Matched through Open Library book metadata.",
            }
        )
    return rows


def suggested_tools(query: str) -> list[dict]:
    lower = query.lower()
    tool_names: list[tuple[str, str]] = []
    if any(term in lower for term in ["artificial intelligence", "machine learning", "nlp", "computer vision"]):
        tool_names = [
            ("Python", "https://www.python.org/"),
            ("scikit-learn", "https://scikit-learn.org/"),
            ("TensorFlow", "https://www.tensorflow.org/"),
        ]
    elif any(term in lower for term in ["statistics", "economics", "cash flow", "micro", "macro"]):
        tool_names = [
            ("R Project", "https://www.r-project.org/"),
            ("EViews", "https://www.eviews.com/"),
            ("GNU Octave", "https://octave.org/"),
        ]
    elif any(term in lower for term in ["algebra", "calculus", "mathematics", "polynomial"]):
        tool_names = [
            ("SageMath", "https://www.sagemath.org/"),
            ("Wolfram Mathematica", "https://www.wolfram.com/mathematica/"),
            ("GeoGebra", "https://www.geogebra.org/"),
        ]
    else:
        tool_names = [
            ("Google Scholar", "https://scholar.google.com/"),
            ("Zotero", "https://www.zotero.org/"),
        ]

    return [
        {
            "category": "Software & Tools",
            "title": name,
            "authors": [],
            "year": None,
            "abstract": f"Useful software/tool for studying or researching {query}.",
            "url": url,
            "source_system": "tool_suggestion",
            "source_record_id": name.lower().replace(" ", "-"),
            "relevance_score": 0.7 - index * 0.03,
            "match_reason": "Suggested as a practical tool for the topic area.",
        }
        for index, (name, url) in enumerate(tool_names)
    ]


def discover_resource_candidates(query: str, limit: int = 5, enabled_sources: set[str] | None = None) -> list[dict]:
    enabled = enabled_sources or {"openalex", "crossref", "open_library", "tool_suggestion"}
    rows: list[dict] = []
    if "openalex" in enabled:
        rows.extend(search_openalex(query, limit=8))
    if "crossref" in enabled:
        rows.extend(search_crossref(query, limit=8))
    if "open_library" in enabled:
        rows.extend(search_open_library(query, limit=8))
    if "tool_suggestion" in enabled:
        rows.extend(suggested_tools(query))
    deduped = _dedupe(rows)
    deduped.sort(key=lambda row: float(row.get("relevance_score") or 0), reverse=True)
    return deduped[:limit]

import json
from typing import Any

import httpx

from app.core.config import settings
from app.utils import RCAABUT_CATEGORIES


GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiError(RuntimeError):
    pass


COURSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "course_code": {"type": "STRING"},
        "course_title": {"type": "STRING"},
        "college": {"type": "STRING"},
        "department": {"type": "STRING"},
        "programme": {"type": "STRING"},
        "level": {"type": "STRING"},
        "semester": {"type": "STRING"},
        "session": {"type": "STRING"},
        "lecturers": {"type": "ARRAY", "items": {"type": "STRING"}},
        "description": {"type": "STRING"},
        "topics": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "module_number": {"type": "INTEGER"},
                    "module_title": {"type": "STRING"},
                    "week_number": {"type": "INTEGER"},
                    "topic_title": {"type": "STRING"},
                    "subtopics": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "outcomes": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "is_searchable": {"type": "BOOLEAN"},
                    "extraction_confidence": {"type": "NUMBER"},
                },
                "required": ["week_number", "topic_title", "subtopics", "outcomes", "is_searchable"],
            },
        },
    },
    "required": ["course_code", "course_title", "description", "topics"],
}

RESOURCE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "resources": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "category": {"type": "STRING"},
                    "title": {"type": "STRING"},
                    "authors": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "year": {"type": "INTEGER"},
                    "abstract": {"type": "STRING"},
                    "url": {"type": "STRING"},
                    "source_system": {"type": "STRING"},
                    "relevance_score": {"type": "NUMBER"},
                    "match_reason": {"type": "STRING"},
                },
                "required": ["category", "title", "authors", "abstract", "url", "source_system", "relevance_score", "match_reason"],
            },
        }
    },
    "required": ["resources"],
}

RERANK_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "resources": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "source_record_id": {"type": "STRING"},
                    "category": {"type": "STRING"},
                    "relevance_score": {"type": "NUMBER"},
                    "match_reason": {"type": "STRING"},
                },
                "required": ["source_record_id", "category", "relevance_score", "match_reason"],
            },
        }
    },
    "required": ["resources"],
}


def gemini_available() -> bool:
    return bool(settings.gemini_api_key.strip())


def _extract_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates", [])
    if not candidates:
        raise GeminiError("Gemini returned no candidates")
    parts = (candidates[0].get("content") or {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not text.strip():
        raise GeminiError("Gemini returned an empty response")
    return text


def _generate_json(prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
    if not gemini_available():
        raise GeminiError("Gemini API key is not configured")

    url = f"{GEMINI_API_BASE}/{settings.gemini_model}:generateContent"
    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": (
                        "You are the AI engine for a Covenant University library resource repository prototype. "
                        "Return only valid JSON that matches the provided schema. Be faithful to the supplied data."
                    )
                }
            ]
        },
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    response = httpx.post(url, params={"key": settings.gemini_api_key}, json=payload, timeout=60)
    response.raise_for_status()
    return json.loads(_extract_text(response.json()))


def parse_course_compact(extracted_text: str) -> dict[str, Any]:
    prompt = f"""
Parse this Covenant University course compact into structured data.

Rules:
- Extract only course compact information that is present or strongly implied.
- Extract teachable weekly topics from the course outline.
- Mark Revision, Examination, empty weeks, grading sections, ground rules, recommended readings, and generic non-teaching rows as is_searchable=false or omit them.
- Handle formats such as "Module 1 [Week 1]", "Week One", and portal-table rows with Module/Week/Topic columns.
- Keep topic titles concise and suitable for academic resource search.
- Include subtopics/outcomes when visible.

Course compact text:
\"\"\"
{extracted_text[:28000]}
\"\"\"
""".strip()
    return _generate_json(prompt, COURSE_SCHEMA)


def generate_topic_resources(course: dict[str, Any], topic: dict[str, Any]) -> list[dict[str, Any]]:
    prompt = f"""
Generate the top 5 recommended RCAABUT-style learning resources for this course topic.

Use these exact categories when appropriate:
{json.dumps(RCAABUT_CATEGORIES)}

Requirements:
- Return exactly five resources when possible.
- Prefer credible academic books, journal articles, open resources, reports, workshops/trainings, or software/tools.
- Include Software & Tools where genuinely useful for the topic.
- Classify each result into the closest RCAABUT category.
- Provide a URL when you know a stable official or search/discovery URL. If uncertain, use an empty string rather than inventing.
- This is a prototype recommendation layer; be useful and defendable.

Course:
{json.dumps(course, ensure_ascii=True)}

Topic:
{json.dumps(topic, ensure_ascii=True)}
""".strip()
    payload = _generate_json(prompt, RESOURCE_SCHEMA)
    resources = payload.get("resources", [])[:5]
    cleaned: list[dict[str, Any]] = []
    for item in resources:
        category = item.get("category") if item.get("category") in RCAABUT_CATEGORIES else "Books"
        cleaned.append({**item, "category": category})
    return cleaned


def rerank_connector_resources(course: dict[str, Any], topic: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates:
        return []

    compact_candidates = [
        {
            "source_record_id": str(item.get("source_record_id") or item.get("url") or index),
            "category": item.get("category", "Books"),
            "title": item.get("title", ""),
            "authors": item.get("authors", [])[:4],
            "year": item.get("year"),
            "abstract": (item.get("abstract") or "")[:800],
            "source_system": item.get("source_system", ""),
        }
        for index, item in enumerate(candidates)
    ]
    prompt = f"""
Select and rerank the best 5 resource candidates for this course topic.

Use only the supplied candidates. Do not invent new titles, authors, or URLs.
You may adjust the RCAABUT category, relevance score, and match reason.

Valid categories:
{json.dumps(RCAABUT_CATEGORIES)}

Course:
{json.dumps(course, ensure_ascii=True)}

Topic:
{json.dumps(topic, ensure_ascii=True)}

Candidates:
{json.dumps(compact_candidates, ensure_ascii=True)}
""".strip()
    ranked = _generate_json(prompt, RERANK_SCHEMA).get("resources", [])
    by_id = {
        str(item.get("source_record_id") or item.get("url") or index): item
        for index, item in enumerate(candidates)
    }
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in ranked:
        key = str(row.get("source_record_id") or "")
        candidate = by_id.get(key)
        if not candidate or key in seen:
            continue
        seen.add(key)
        category = row.get("category") if row.get("category") in RCAABUT_CATEGORIES else candidate.get("category", "Books")
        output.append(
            {
                **candidate,
                "category": category,
                "relevance_score": float(row.get("relevance_score") or candidate.get("relevance_score") or 0),
                "match_reason": row.get("match_reason") or candidate.get("match_reason") or "",
            }
        )
    for candidate in candidates:
        key = str(candidate.get("source_record_id") or candidate.get("url") or candidate.get("title"))
        if key not in seen:
            output.append(candidate)
        if len(output) >= 5:
            break
    return output[:5]

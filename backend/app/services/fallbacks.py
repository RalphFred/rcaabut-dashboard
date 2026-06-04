import re
from urllib.parse import quote_plus

from app.utils import RCAABUT_CATEGORIES


WEEK_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
}


SKIP_TOPICS = {"revision", "examination", "exam", "tutorials", "recommended reading", "ground rules"}
PORTAL_STOP_PREFIXES = (
    "general overview",
    "explain ",
    "what is ",
    "the use ",
    "discussion",
    "class ",
    "having ",
    "lecture",
    "abiodun",
    "jonathan",
    "relationship",
    "comparing",
)


def _clean(value: str | None) -> str:
    cleaned = re.sub(r"\s+", " ", value or "").strip(" :-\t•")
    cleaned = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", cleaned)
    replacements = {
        "Introductionto": "Introduction to",
        "Foundationsof": "Foundations of",
        "Sequentialand": "Sequential and",
        "Programmingpractical": "Programming practical",
        "practicalapplications": "practical applications",
        "MACHINELANGUAGE": "MACHINE LANGUAGE",
        "HIGHLEVELLANGUAGE": "HIGH LEVEL LANGUAGE",
        "LANGUAGE&": "LANGUAGE &",
    }
    for bad, good in replacements.items():
        cleaned = cleaned.replace(bad, good)
    cleaned = re.sub(r"\bto(?=the\b)", "to ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bof(?=[A-Z])", "of ", cleaned)
    return cleaned


def _field(text: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}\s*:?\s*([^\n]+)", text, flags=re.IGNORECASE)
    return _clean(match.group(1)) if match else ""


def _week_number(token: str) -> int | None:
    cleaned = token.strip().lower()
    if cleaned.isdigit():
        return int(cleaned)
    return WEEK_WORDS.get(cleaned)


def _is_searchable(topic: str) -> bool:
    normalized = _clean(topic).lower()
    return bool(normalized) and not any(skip in normalized for skip in SKIP_TOPICS)


def _looks_like_portal_stop(line: str) -> bool:
    cleaned = _clean(line).lower()
    return cleaned.startswith(PORTAL_STOP_PREFIXES) or "discussion:-" in cleaned


def _parse_portal_topics(lines: list[str]) -> list[dict]:
    topics: list[dict] = []
    try:
        start = next(index for index, line in enumerate(lines) if "ModuleWeek Topic" in line)
    except StopIteration:
        return topics

    index = start + 1
    row_pattern = re.compile(r"^(?P<module>\d+)\s+(?P<week>\d+)(?:\s+(?P<title>.+))?$")
    while index < len(lines):
        line = lines[index].strip()
        match = row_pattern.match(line)
        if not match:
            index += 1
            continue

        module_number = int(match.group("module"))
        week_number = int(match.group("week"))
        title_parts: list[str] = []
        if match.group("title"):
            title_parts.append(match.group("title"))
        index += 1

        while index < len(lines) and not title_parts:
            next_line = lines[index].strip()
            if row_pattern.match(next_line):
                break
            if not next_line or _looks_like_portal_stop(next_line):
                index += 1
                continue
            title_parts.append(next_line)
            index += 1
            break

        title = _clean(" ".join(title_parts))
        if title:
            topics.append(
                {
                    "module_number": module_number,
                    "module_title": "",
                    "week_number": week_number,
                    "topic_title": title,
                    "subtopics": [],
                    "outcomes": [],
                    "is_searchable": _is_searchable(title),
                    "extraction_confidence": 0.66,
                }
            )
    return topics


def parse_course_compact_fallback(text: str) -> dict:
    title = _field(text, "Course Title")
    code = _field(text, "Course Code")
    portal = re.search(r"Course Code/Title:\s*([^/\n]+)/\s*([^:\n]+)", text, flags=re.IGNORECASE)
    if portal:
        code = _clean(portal.group(1))
        title = _clean(portal.group(2))

    topics: list[dict] = []
    module_title = ""
    module_number = None
    module_pattern = re.compile(
        r"Module\s+(?P<module>\d+)(?:\s+\[Week(?:s)?\s+(?P<bracket_week>\d+)(?:[–-]\d+)?\])?:?\s*(?P<title>[^\n]+)",
        flags=re.IGNORECASE,
    )
    week_pattern = re.compile(
        r"Week\s+(?P<week>\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen):?\s*(?P<title>[^\n]+)",
        flags=re.IGNORECASE,
    )

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    topics.extend(_parse_portal_topics(lines))
    for line in lines:
        module_match = module_pattern.search(line)
        if module_match:
            module_number = int(module_match.group("module"))
            module_title = _clean(module_match.group("title"))
            week = _week_number(module_match.group("bracket_week") or "")
            if week and _is_searchable(module_title):
                topics.append(
                    {
                        "module_number": module_number,
                        "module_title": module_title,
                        "week_number": week,
                        "topic_title": module_title,
                        "subtopics": [],
                        "outcomes": [],
                        "is_searchable": True,
                        "extraction_confidence": 0.72,
                    }
                )
            continue

        week_match = week_pattern.search(line)
        if week_match:
            topic = _clean(week_match.group("title"))
            topics.append(
                {
                    "module_number": module_number,
                    "module_title": module_title,
                    "week_number": _week_number(week_match.group("week")),
                    "topic_title": topic,
                    "subtopics": [],
                    "outcomes": [],
                    "is_searchable": _is_searchable(topic),
                    "extraction_confidence": 0.68,
                }
            )

    return {
        "course_code": code or "UNKNOWN",
        "course_title": title or "Untitled Course Compact",
        "college": _field(text, "College"),
        "department": _field(text, "Department"),
        "programme": _field(text, "Programme") or _field(text, "Programme(s)"),
        "level": "",
        "semester": _field(text, "Semester"),
        "session": _field(text, "Session"),
        "lecturers": [_field(text, "Course Lecturer(s)") or _field(text, "Course Lecturers")],
        "description": _field(text, "Overview") or _field(text, "Course Overview"),
        "topics": [topic for topic in topics if topic["topic_title"]],
    }


def generate_resources_fallback(course: dict, topic: dict) -> list[dict]:
    topic_title = topic.get("topic_title", "course topic")
    rows: list[dict] = []
    for index in range(5):
        category = RCAABUT_CATEGORIES[index]
        query = quote_plus(f"{course.get('course_title', '')} {topic_title} {category}")
        rows.append(
        {
            "category": category,
            "title": f"{topic_title} - {category} search result",
            "authors": [],
            "year": None,
            "abstract": "Fallback recommendation generated because Gemini is not configured.",
            "url": f"https://scholar.google.com/scholar?q={query}",
            "source_system": "fallback",
            "relevance_score": round(0.82 - (index * 0.05), 2),
            "match_reason": "Generated as a review placeholder from the course topic.",
        }
        )
    return rows

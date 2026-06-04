import json
from typing import Any


RCAABUT_CATEGORIES = [
    "Books",
    "Journal Articles",
    "Newspaper Articles",
    "Industry Reports",
    "Workshops & Trainings",
    "Software & Tools",
]


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, default=str)


def loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback

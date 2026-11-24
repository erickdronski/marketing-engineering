"""Check whether a revision request names an actionable, locatable change."""

import re

from .errors import MktgError

VAGUE = re.compile(
    r"\b(?:make it better|not quite right|more punchy|try again|improve it|needs work)\b", re.IGNORECASE
)
CONCRETE = re.compile(
    r"\b(?:cut|lead|add|remove|replace|move|shorten|cite|name|quote|split|"
    r"explain|clarify|show|delete|rewrite|headline|first line|opening|"
    r"call to action|subject line|paragraph|caption|hero|meta description|alt text)\b",
    re.IGNORECASE,
)


def validate(text):
    if len(re.findall(r"\b[\w'-]+\b", text)) < 5 or not CONCRETE.search(VAGUE.sub("", text)):
        raise MktgError(
            "feedback needs a specific edit", fix="Name what to change or where, in at least five words."
        )

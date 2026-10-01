"""Section-aware text used when extracting mandatory experience requirements."""
import re


# Scraped JDs often flatten headings and bullets onto a single line.
_HEADINGS = re.compile(
    r"\b(?P<preferred>preferred\s+(?:qualifications?|skills|experience)"
    r"|nice[-\s]+to[-\s]+have|bonus\s+qualifications?)\b"
    r"|\b(?P<other>(?:basic|minimum|required)\s+(?:qualifications?|requirements?|skills)"
    r"|requirements|(?:key\s+job\s+)?responsibilities|about\s+(?:the\s+)?team"
    r"|about\s+us|benefits|compensation|pay\s+range)\b"
    r"|\b(?P<colon>required|minimum|preferred)\s*:",
    re.IGNORECASE,
)


def mandatory_experience_text(text: str) -> str:
    """Mask preferred sections, preserving offsets for contextual extraction."""
    text = text or ""
    headings = list(_HEADINGS.finditer(text))
    parts = list(text)
    for index, heading in enumerate(headings):
        is_preferred = heading.group("preferred") or (
            (heading.group("colon") or "").lower() == "preferred"
        )
        if not is_preferred:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        parts[heading.start():end] = " " * (end - heading.start())
    return "".join(parts)

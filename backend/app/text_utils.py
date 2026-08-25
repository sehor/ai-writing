import re


def truncate(value: str, limit: int = 2000, *, collapse_whitespace: bool = False) -> str:
    """
    Truncates a string to the given limit.
    If collapse_whitespace is True, all whitespace sequences are collapsed to a single space.
    """
    if not value:
        return ""
    text = " ".join(value.split()) if collapse_whitespace else value.strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."


def one_line(value: str, limit: int = 120, fallback: str = "") -> str:
    """
    Converts a string to a single line and truncates it.
    """
    if not value:
        return fallback
    text = " ".join(value.split())
    if not text:
        return fallback
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def slugify(value: str, fallback: str = "page") -> str:
    """
    Creates a slug by replacing non-alphanumeric characters with hyphens.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def safe_slug(value: str, fallback: str = "scene") -> str:
    """
    Creates a simple slug, stripping out non-alphanumeric characters.
    """
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value)
    return "-".join(part for part in cleaned.split("-") if part) or fallback


def slug_with_id(label: str, record_id: str) -> str:
    """
    Combines a label and an ID into a single slug.
    """
    label_slug = slugify(label)
    id_slug = slugify(record_id)
    if label_slug == id_slug or id_slug == "page":
        return label_slug
    return f"{label_slug}-{id_slug}"

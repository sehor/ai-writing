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


def prose_excerpt(content: str, max_chars: int = 4000) -> str:
    """
    Keeps a prose sample inside the recommended 2,000-6,000 character band
    instead of copying the full manuscript text. The head and tail of the
    piece are preserved with an explicit omission marker pointing at the
    authoritative source_ref.
    """
    text = content.strip()
    if len(text) <= max_chars:
        return text
    head_len = (max_chars * 2) // 3
    tail_len = max_chars - head_len
    omitted = len(text) - max_chars
    return (
        f"{text[:head_len].rstrip()}\n\n"
        f"[... excerpt: {omitted} characters omitted; "
        f"see the source revision for the full text ...]\n\n"
        f"{text[-tail_len:].lstrip()}"
    )


def slug_with_id(label: str, record_id: str) -> str:
    """
    Combines a label and an ID into a single slug.
    """
    label_slug = slugify(label)
    id_slug = slugify(record_id)
    if label_slug == id_slug or id_slug == "page":
        return label_slug
    return f"{label_slug}-{id_slug}"

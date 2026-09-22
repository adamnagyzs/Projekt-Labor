import re
import unicodedata


def normalize_code(value: str) -> str:

    return " ".join(value.strip().upper().split())


def normalize_text(value: str) -> str:

    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", without_accents).strip().lower()


def is_meaningful_serial_number(value: str | None) -> bool:

    if value is None:
        return False

    cleaned = normalize_code(value)

    if cleaned in {"", "-", "?", "NINCS", "BÚTOR"}:
        return False

    if cleaned.startswith("IMÜ-"):
        return False

    return len(cleaned) >= 3

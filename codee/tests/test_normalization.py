from leltariv_domain.normalization import (
    is_meaningful_serial_number,
    normalize_code,
    normalize_text,
)


def test_normalize_code_keeps_leading_zeroes() -> None:
    assert normalize_code("  005071  ") == "005071"


def test_normalize_code_normalizes_spaces_and_uppercase() -> None:
    assert normalize_code("  ab   12  ") == "AB 12"


def test_normalize_text_is_case_and_accent_insensitive() -> None:
    assert normalize_text("  Tárgyalőszék  ") == "targyaloszek"


def test_meaningful_serial_number_filter() -> None:
    invalid_values = [None, "", "-", "?", "NINCS", "BÚTOR", "IMÜ-02", "12"]
    for value in invalid_values:
        assert not is_meaningful_serial_number(value)

    assert is_meaningful_serial_number("SN-12345")

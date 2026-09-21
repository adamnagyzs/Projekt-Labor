from datetime import date, datetime

import pytest
from leltariv_domain.xlsx_import import (
    as_source_text,
    clean_header,
    excel_serial_to_date,
    is_asset_row,
    zone_code_from_site,
)


def test_clean_header_removes_leading_and_trailing_spaces() -> None:
    assert clean_header("      Besz.ért. ") == "Besz.ért."
    assert clean_header(None) == ""


def test_as_source_text_preserves_leading_zeroes_for_string_values() -> None:
    assert as_source_text("005071") == "005071"


def test_as_source_text_converts_excel_integer_without_decimal_suffix() -> None:
    assert as_source_text(3001540) == "3001540"
    assert as_source_text(3001540.0) == "3001540"


def test_excel_serial_date_conversion() -> None:
    assert excel_serial_to_date(46077) == date(2026, 2, 24)
    assert excel_serial_to_date(datetime(2026, 2, 24, 14, 30)) == date(2026, 2, 24)


def test_excel_serial_date_rejects_boolean() -> None:
    with pytest.raises(ValueError):
        excel_serial_to_date(True)


def test_zone_code_comes_from_first_three_site_digits() -> None:
    assert zone_code_from_site("2610000000") == "261"
    assert zone_code_from_site(2620000000) == "262"


def test_summary_rows_are_excluded_based_on_sub_number() -> None:
    assert is_asset_row(("3001540", 0, "005071"))
    assert not is_asset_row(("3001540", None, None))
    assert not is_asset_row(("3001540", "", None))
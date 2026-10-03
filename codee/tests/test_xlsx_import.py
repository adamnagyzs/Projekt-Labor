from datetime import date, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook

from leltariv_domain.xlsx_import import (
    as_source_text,
    clean_header,
    excel_serial_to_date,
    is_asset_row,
    read_asset_rows,
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


def test_read_asset_rows_preserves_excel_row_numbers(tmp_path: Path) -> None:
    path = tmp_path / "teszt.xlsx"

    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.append(["Eszköz", "Alszám", "Eszköz megnevezése"])
    worksheet.append(["3000001", 0, "Első eszköz"])
    worksheet.append(["3000002", 1, "Második eszköz"])
    workbook.save(path)
    workbook.close()

    rows = list(read_asset_rows(path))

    assert [row_number for row_number, _ in rows] == [2, 3]
    assert rows[0][1]["Eszköz"] == "3000001"
    assert rows[1][1]["Alszám"] == 1
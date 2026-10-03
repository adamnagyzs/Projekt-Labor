from pathlib import Path

from openpyxl import Workbook


output = Path("bad-seed-demo.xlsx")

workbook = Workbook()
worksheet = workbook.active
assert worksheet is not None
worksheet.title = "Eszközök"

worksheet.append(
    [
        "Eszköz",
        "Alszám",
        "Leltárszám",
        "Eredeti eszköz",
        "Adóhivatal",
        "Aktiválás dátuma",
        "Eszköz megnevezése",
        "Besz.ért.",
        "Kum. ÉCS",
        "K.sz.ért",
        "Pénznem",
        "Telephely",
        "Gyártási szám",
        "Mennyiség",
    ]
)

worksheet.append(
    [
        "DEMO-001",
        0,
        "D001",
        None,
        None,
        None,
        "Működő teszteszköz",
        1000,
        0,
        1000,
        "HUF",
        "2610000000",
        "DEMO-SN-001",
        1,
    ]
)

worksheet.append(
    [
        None,
        0,
        "D002",
        None,
        None,
        None,
        "Hibás teszteszköz",
        1000,
        0,
        1000,
        "HUF",
        "2610000000",
        "DEMO-SN-002",
        1,
    ]
)

worksheet.append(
    [
        "DEMO-003",
        0,
        "D003",
        None,
        None,
        None,
        "Második működő teszteszköz",
        1000,
        0,
        1000,
        "HUF",
        "2610000000",
        "DEMO-SN-003",
        1,
    ]
)

workbook.save(output)
workbook.close()

print(f"Elkészült: {output}")
"""Unit tests for the export generators (FR-RPT-02/03; Volume 3, Chapter
26.2) — pure format transformation of a Report Preview DTO into bytes,
with and without the fines column.

Run: python -m unittest discover -s tests
"""

import unittest
from datetime import date
from io import BytesIO

from openpyxl import load_workbook

from app.reporting import (
    ExcelExporter,
    PdfExporter,
    ReportPreviewDto,
    ReportRowDto,
    ReportTotalsDto,
)

START, END = date(2026, 8, 1), date(2026, 8, 31)


def make_report(include_fines=True, rows=None):
    if rows is None:
        rows = (
            ReportRowDto(
                date=date(2026, 8, 4), issued=2, returned=0, overdue=1, fines=0.0
            ),
            ReportRowDto(
                date=date(2026, 8, 18), issued=1, returned=2, overdue=0, fines=12.5
            ),
        )
    return ReportPreviewDto(
        report_type="MONTHLY",
        start_date=START,
        end_date=END,
        totals=ReportTotalsDto(issued=3, returned=2, overdue=1, fines=12.5),
        rows=rows,
        include_fines=include_fines,
    )


class PdfExporterTest(unittest.TestCase):
    def test_generates_pdf_bytes(self):
        result = PdfExporter().generate(make_report())
        self.assertEqual(result.file_name, "Monthly Report.pdf")
        self.assertTrue(result.file_bytes.startswith(b"%PDF"))

    def test_empty_report_still_generates_pdf(self):
        result = PdfExporter().generate(make_report(rows=()))
        self.assertTrue(result.file_bytes.startswith(b"%PDF"))

    def test_fines_column_omitted_when_disabled(self):
        result = PdfExporter().generate(make_report(include_fines=False))
        self.assertTrue(result.file_bytes.startswith(b"%PDF"))


class ExcelExporterTest(unittest.TestCase):
    def _round_trip(self, report):
        result = ExcelExporter().generate(report)
        self.assertEqual(result.file_name, "Monthly Report.xlsx")
        self.assertTrue(result.file_bytes.startswith(b"PK"))
        return load_workbook(BytesIO(result.file_bytes)).active

    def test_sheet_contains_header_rows_and_data(self):
        sheet = self._round_trip(make_report())
        header = [cell.value for cell in sheet[4]]
        self.assertEqual(
            header[:4], ["Date", "Books Issued", "Books Returned", "Overdue Items"]
        )
        self.assertEqual(header[4], "Fines Collected")
        self.assertEqual(sheet.cell(row=5, column=2).value, 2)
        self.assertEqual(sheet.cell(row=6, column=5).value, 12.5)

    def test_fines_column_omitted_when_disabled(self):
        sheet = self._round_trip(make_report(include_fines=False))
        header = [cell.value for cell in sheet[4]]
        self.assertEqual(
            header, ["Date", "Books Issued", "Books Returned", "Overdue Items"]
        )
        self.assertIsNone(sheet.cell(row=5, column=5).value)

    def test_summary_section_present(self):
        sheet = self._round_trip(make_report())
        labels = [
            sheet.cell(row=row, column=1).value for row in range(1, sheet.max_row + 1)
        ]
        self.assertIn("Books Issued", labels)
        self.assertIn("Period: 2026-08-01 to 2026-08-31", labels)

    def test_empty_report_still_generates_workbook(self):
        sheet = self._round_trip(make_report(rows=()))
        self.assertEqual(sheet.cell(row=5, column=1).value, None)


if __name__ == "__main__":
    unittest.main()

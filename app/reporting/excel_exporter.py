"""ExcelExporter — Professional dashboard-style .xlsx report.

Renders a polished, centered, institutional Excel report matching
the redesigned PDF visual language. Data-driven and reusable across
all report types.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import (
    Alignment,
    Border,
    Font,
    PatternFill,
    Side,
)
from openpyxl.utils import get_column_letter

from app.reporting import ExportResultDto, ReportExporter, ReportPreviewDto

# ── Colour palette ──────────────────────────────────────────────────────────
NAVY = "1B2A4A"
BLUE = "2E6F9E"
LIGHT_BLUE = "EBF2FA"
TEAL = "1D9A6C"
LIGHT_TEAL = "E6F7F1"
ORANGE = "D97706"
LIGHT_ORANGE = "FEF3E2"
PURPLE = "6B5CE7"
LIGHT_PURPLE = "F0EEFF"
GRAY = "6B7280"
LIGHT_GRAY = "F3F4F6"
CARD_BG = "F8FAFC"
SECTION_BG = "F1F5F9"
WHITE = "FFFFFF"
BORDER_CLR = "D1D5DB"
TOTAL_BG = "EBF0F7"

# ── Layout ──────────────────────────────────────────────────────────────────
REPORT_START = 1  # column A
REPORT_END = 13  # column M
REPORT_WIDTH = REPORT_END - REPORT_START + 1  # 12 columns


# ── Style builders ──────────────────────────────────────────────────────────

def _fill(hex_color: str) -> PatternFill:
    return PatternFill(start_color=hex_color, end_color=hex_color, fill_type="solid")


def _font(bold=False, size=10, color="000000", name="Calibri"):
    return Font(bold=bold, size=size, color=color, name=name)


def _align(h="left", v="center", wrap=False):
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap)


def _border(left=None, right=None, top=None, bottom=None):
    sides = {}
    for side, val in [("left", left), ("right", right), ("top", top), ("bottom", bottom)]:
        sides[side] = Side(style=val["style"], color=val["color"]) if val else Side(style=None)
    return Border(**sides)


def _thin_border(color=BORDER_CLR):
    s = Side(style="thin", color=color)
    return Border(left=s, right=s, top=s, bottom=s)


def _bottom_border(color=BORDER_CLR):
    return Border(bottom=Side(style="thin", color=color))


# ── Reusable section builders ───────────────────────────────────────────────

def _section_header(ws, row, title, icon_char=""):
    """Write a light-blue section header spanning REPORT_WIDTH."""
    label = f"  {icon_char}  {title}" if icon_char else f"  {title}"
    ws.merge_cells(
        start_row=row, start_column=REPORT_START + 1,
        end_row=row, end_column=REPORT_END,
    )
    cell = ws.cell(row=row, column=REPORT_START + 1, value=label)
    cell.font = _font(bold=True, size=13, color=NAVY)
    cell.fill = _fill(SECTION_BG)
    cell.alignment = _align("left", "center")
    ws.row_dimensions[row].height = 28
    for c in range(REPORT_START, REPORT_END + 1):
        ws.cell(row=row, column=c).fill = _fill(SECTION_BG)
    return row + 1


def _card_start(ws, row):
    """Mark the start of a card (apply light fill to width)."""
    for c in range(REPORT_START, REPORT_END + 1):
        ws.cell(row=row, column=c).fill = _fill(WHITE)
    return row


def _card_border(ws, row_start, row_end):
    """Apply thin border around a card area."""
    for r in range(row_start, row_end + 1):
        for c in range(REPORT_START, REPORT_END + 1):
            cell = ws.cell(row=r, column=c)
            sides = {}
            if r == row_start:
                sides["top"] = Side(style="thin", color=BORDER_CLR)
            if r == row_end:
                sides["bottom"] = Side(style="thin", color=BORDER_CLR)
            if c == REPORT_START:
                sides["left"] = Side(style="thin", color=BORDER_CLR)
            if c == REPORT_END:
                sides["right"] = Side(style="thin", color=BORDER_CLR)
            if sides:
                cell.border = Border(**sides)


def _label_value(ws, row, col_label, col_value, label, value, label_color=NAVY, value_color="333333"):
    """Write a label/value pair."""
    lc = ws.cell(row=row, column=col_label, value=label)
    lc.font = _font(bold=True, size=9, color=label_color)
    lc.alignment = _align("left", "center")
    vc = ws.cell(row=row, column=col_value, value=value)
    vc.font = _font(size=9, color=value_color)
    vc.alignment = _align("left", "center")


def _date_range(start, end) -> str:
    return f"{start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}"


def _fmt_date(report_type, dt) -> str:
    if report_type == "WEEKLY":
        return f"{dt.strftime('%d %b %Y')} - {(dt + timedelta(days=5)).strftime('%d %b %Y')}"
    if report_type == "MONTHLY":
        return dt.strftime("%B %Y")
    if report_type == "YEARLY":
        return str(dt.year)
    return dt.strftime("%d %b %Y")


# ── Report type titles ──────────────────────────────────────────────────────
REPORT_TITLES = {
    "DAILY": "Daily Library Activity Report",
    "WEEKLY": "Weekly Library Activity Report",
    "MONTHLY": "Monthly Library Activity Report",
    "YEARLY": "Yearly Library Activity Report",
    "CUSTOM": "Library Activity Report",
}


# ── Main Exporter ───────────────────────────────────────────────────────────

class ExcelExporter(ReportExporter):
    """Renders report previews to styled .xlsx workbooks via OpenPyXL."""

    def generate(self, report: ReportPreviewDto) -> ExportResultDto:
        wb = Workbook()
        ws = wb.active
        ws.title = "Report"

        # Hide gridlines
        ws.sheet_view.showGridLines = False

        row = 1

        # ── Header ─────────────────────────────────────────────────────────
        row = self._write_header(ws, row)

        # ── Title ──────────────────────────────────────────────────────────
        row = self._write_title(ws, row, report)

        # ── Report Details ─────────────────────────────────────────────────
        row = self._write_details(ws, row, report)

        # ── Report Context ─────────────────────────────────────────────────
        row = self._write_context(ws, row, report)

        # ── Executive Summary ──────────────────────────────────────────────
        row = self._write_summary(ws, row, report)

        # ── Activity Details ───────────────────────────────────────────────
        row = self._write_activity(ws, row, report)

        # ── Report Notes ───────────────────────────────────────────────────
        row = self._write_notes(ws, row, report)

        # ── Footer ─────────────────────────────────────────────────────────
        row = self._write_footer(ws, row)

        # ── Column widths ──────────────────────────────────────────────────
        self._set_column_widths(ws)

        # ── Print settings ─────────────────────────────────────────────────
        self._configure_print(ws, row)

        # ── Freeze panes below header ──────────────────────────────────────
        ws.freeze_panes = "A5"

        buf = BytesIO()
        wb.save(buf)
        return ExportResultDto(
            file_name=f"{REPORT_TITLES.get(report.report_type, 'Library Activity Report')}.xlsx",
            file_bytes=buf.getvalue(),
        )

    # ── Section writers ─────────────────────────────────────────────────────

    def _write_header(self, ws, row):
        """Institutional branding header."""
        ws.row_dimensions[row].height = 8
        row += 1

        # Institution name
        ws.merge_cells(
            start_row=row, start_column=REPORT_START + 1,
            end_row=row, end_column=REPORT_END,
        )
        cell = ws.cell(row=row, column=REPORT_START + 1, value="Library Management System")
        cell.font = _font(bold=True, size=20, color=NAVY)
        cell.alignment = _align("left", "center")
        ws.row_dimensions[row].height = 28
        row += 1

        # Subtitle
        ws.merge_cells(
            start_row=row, start_column=REPORT_START + 1,
            end_row=row, end_column=REPORT_END,
        )
        cell = ws.cell(row=row, column=REPORT_START + 1,
                        value="Learn  •  Read  •  Grow")
        cell.font = _font(size=10, color=BLUE)
        cell.alignment = _align("left", "center")
        ws.row_dimensions[row].height = 16
        row += 1

        # Accent line
        ws.row_dimensions[row].height = 3
        for c in range(REPORT_START, REPORT_END + 1):
            ws.cell(row=row, column=c).fill = _fill(BLUE)
        row += 1

        ws.row_dimensions[row].height = 8
        return row + 1

    def _write_title(self, ws, row, report):
        """Report title with icon marker."""
        title = REPORT_TITLES.get(report.report_type, "Library Activity Report")
        ws.merge_cells(
            start_row=row, start_column=REPORT_START + 1,
            end_row=row, end_column=REPORT_END,
        )
        cell = ws.cell(row=row, column=REPORT_START + 1, value=f"📋  {title}")
        cell.font = _font(bold=True, size=18, color=NAVY)
        cell.alignment = _align("left", "center")
        ws.row_dimensions[row].height = 36
        return row + 2

    def _write_details(self, ws, row, report):
        """Report Details card."""
        row = _section_header(ws, row, "REPORT DETAILS", "📋")
        card_top = row

        report_id = self._report_id(report)
        gen_on = datetime.now().strftime("%d %b %Y, %I:%M %p")
        period = _date_range(report.start_date, report.end_date)
        rtype = f"{report.report_type.title()} Report"

        # Row 1: Reporting Period | Report Type
        _label_value(ws, row, REPORT_START + 1, REPORT_START + 2,
                     "Reporting Period", period)
        _label_value(ws, row, REPORT_START + 6, REPORT_START + 7,
                     "Report Type", rtype)
        ws.row_dimensions[row].height = 18
        row += 1

        # Row 2: Generated On | Report ID
        _label_value(ws, row, REPORT_START + 1, REPORT_START + 2,
                     "Generated On", gen_on)
        _label_value(ws, row, REPORT_START + 6, REPORT_START + 7,
                     "Report ID", report_id)
        ws.row_dimensions[row].height = 18
        row += 1

        ws.row_dimensions[row].height = 6
        row += 1

        _card_border(ws, card_top, row - 1)
        return row + 1

    def _write_context(self, ws, row, report):
        """Report Context card."""
        row = _section_header(ws, row, "REPORT CONTEXT", "📋")
        card_top = row

        fields = [
            ("System", "Library Management System"),
            ("Library / Department", "Main Library"),
            ("Academic Year", report.academic_year or "—"),
            ("Generated By", report.generated_by or "System"),
            ("Reporting Period", _date_range(report.start_date, report.end_date)),
            ("Report Type", f"{report.report_type.title()} Report"),
        ]

        for i in range(0, len(fields), 2):
            left_label, left_val = fields[i]
            if i + 1 < len(fields):
                right_label, right_val = fields[i + 1]
            else:
                right_label, right_val = "", ""

            _label_value(ws, row, REPORT_START + 1, REPORT_START + 2,
                         left_label, left_val)
            if right_label:
                _label_value(ws, row, REPORT_START + 6, REPORT_START + 7,
                             right_label, right_val)
            ws.row_dimensions[row].height = 18
            row += 1

        ws.row_dimensions[row].height = 6
        row += 1

        _card_border(ws, card_top, row - 1)
        return row + 1

    def _write_summary(self, ws, row, report):
        """Executive Summary with KPI cards — all cards on same rows."""
        row = _section_header(ws, row, "EXECUTIVE SUMMARY", "📊")
        card_top = row

        total = report.totals.issued + report.totals.returned
        kpis = [
            ("📚", "Books Issued", str(report.totals.issued),
             "During selected period", TEAL, LIGHT_TEAL),
            ("↩", "Books Returned", str(report.totals.returned),
             "During selected period", BLUE, LIGHT_BLUE),
            ("⚠", "Currently Overdue", str(report.totals.overdue),
             "At report generation", ORANGE, LIGHT_ORANGE),
            ("⇄", "Total Transactions", str(total),
             "Issued + Returned", PURPLE, LIGHT_PURPLE),
        ]

        card_w = REPORT_WIDTH // 4
        card_cols = []
        for idx, (icon, label, value, sub, accent, bg) in enumerate(kpis):
            col_start = REPORT_START + 1 + idx * card_w
            col_end = col_start + card_w - 1
            card_cols.append((col_start, col_end, icon, label, value, sub, bg))

        # Row 1: Icons
        for col_start, col_end, icon, _, _, _, bg in card_cols:
            ws.merge_cells(start_row=row, start_column=col_start,
                           end_row=row, end_column=col_end)
            ic = ws.cell(row=row, column=col_start, value=icon)
            ic.font = _font(size=18)
            ic.alignment = _align("center", "center")
            ic.fill = _fill(bg)
            for c in range(col_start, col_end + 1):
                ws.cell(row=row, column=c).fill = _fill(bg)
        ws.row_dimensions[row].height = 30
        row += 1

        # Row 2: Labels
        for col_start, col_end, _, label, _, _, bg in card_cols:
            ws.merge_cells(start_row=row, start_column=col_start,
                           end_row=row, end_column=col_end)
            lc = ws.cell(row=row, column=col_start, value=label)
            lc.font = _font(bold=True, size=9, color=NAVY)
            lc.alignment = _align("center", "center")
            lc.fill = _fill(bg)
            for c in range(col_start, col_end + 1):
                ws.cell(row=row, column=c).fill = _fill(bg)
        ws.row_dimensions[row].height = 16
        row += 1

        # Row 3: Values
        for col_start, col_end, _, _, value, _, bg in card_cols:
            ws.merge_cells(start_row=row, start_column=col_start,
                           end_row=row, end_column=col_end)
            vc = ws.cell(row=row, column=col_start, value=value)
            vc.font = _font(bold=True, size=24, color=NAVY)
            vc.alignment = _align("center", "center")
            vc.fill = _fill(bg)
            for c in range(col_start, col_end + 1):
                ws.cell(row=row, column=c).fill = _fill(bg)
        ws.row_dimensions[row].height = 36
        row += 1

        # Row 4: Subtitles
        for col_start, col_end, _, _, _, sub, bg in card_cols:
            ws.merge_cells(start_row=row, start_column=col_start,
                           end_row=row, end_column=col_end)
            sc = ws.cell(row=row, column=col_start, value=sub)
            sc.font = _font(size=8, color=GRAY)
            sc.alignment = _align("center", "center")
            sc.fill = _fill(bg)
            for c in range(col_start, col_end + 1):
                ws.cell(row=row, column=c).fill = _fill(bg)
        ws.row_dimensions[row].height = 16
        row += 1

        _card_border(ws, card_top, row - 1)
        return row + 1

    def _write_activity(self, ws, row, report):
        """Activity Details table with Excel formulas."""
        row = _section_header(ws, row, "ACTIVITY DETAILS", "📋")
        card_top = row

        # Table header
        cols = ["Date", "Books Issued", "Books Returned", "Overdue Items", "Total Activity"]
        if report.include_fines:
            cols.append("Fines Collected")

        table_start_col = REPORT_START + 1

        for ci, col_name in enumerate(cols):
            c = ws.cell(row=row, column=table_start_col + ci, value=col_name)
            c.font = _font(bold=True, size=9, color=WHITE)
            c.fill = _fill(NAVY)
            c.alignment = _align("center", "center")
        ws.row_dimensions[row].height = 22
        row += 1

        # Data rows
        data_start = row
        issued_col = get_column_letter(table_start_col + 1)   # C
        returned_col = get_column_letter(table_start_col + 2)  # D

        for ri, data_row in enumerate(report.rows):
            bg = LIGHT_GRAY if ri % 2 == 0 else WHITE

            # Date
            c = ws.cell(row=row, column=table_start_col,
                        value=_fmt_date(report.report_type, data_row.date))
            c.font = _font(size=9, color="333333")
            c.fill = _fill(bg)
            c.alignment = _align("left", "center")

            # Books Issued
            c = ws.cell(row=row, column=table_start_col + 1, value=data_row.issued)
            c.font = _font(size=9, color="333333")
            c.fill = _fill(bg)
            c.alignment = _align("center", "center")
            c.number_format = "#,##0"

            # Books Returned
            c = ws.cell(row=row, column=table_start_col + 2, value=data_row.returned)
            c.font = _font(size=9, color="333333")
            c.fill = _fill(bg)
            c.alignment = _align("center", "center")
            c.number_format = "#,##0"

            # Overdue Items
            c = ws.cell(row=row, column=table_start_col + 3, value=data_row.overdue)
            c.font = _font(size=9, color="333333")
            c.fill = _fill(bg)
            c.alignment = _align("center", "center")
            c.number_format = "#,##0"

            # Total Activity = Issued + Returned (formula)
            c = ws.cell(row=row, column=table_start_col + 4,
                        value=f"={issued_col}{row}+{returned_col}{row}")
            c.font = _font(size=9, color="333333")
            c.fill = _fill(bg)
            c.alignment = _align("center", "center")
            c.number_format = "#,##0"

            # Fines Collected
            if report.include_fines:
                c = ws.cell(row=row, column=table_start_col + 5,
                            value=round(data_row.fines, 2))
                c.font = _font(size=9, color="333333")
                c.fill = _fill(bg)
                c.alignment = _align("center", "center")
                c.number_format = "#,##0.00"

            ws.row_dimensions[row].height = 18
            row += 1

        data_end = row - 1

        # Total row with SUM formulas
        total_cols = [1, 2, 3, 4]  # indices for Issued, Returned, Overdue, Activity
        if report.include_fines:
            total_cols.append(5)

        c = ws.cell(row=row, column=table_start_col, value="Total")
        c.font = _font(bold=True, size=9, color=NAVY)
        c.fill = _fill(TOTAL_BG)
        c.border = Border(top=Side(style="thin", color=BLUE))
        c.alignment = _align("left", "center")

        for ci in total_cols:
            col_letter = get_column_letter(table_start_col + ci)
            c = ws.cell(row=row, column=table_start_col + ci,
                        value=f"=SUM({col_letter}{data_start}:{col_letter}{data_end})")
            c.font = _font(bold=True, size=9, color=NAVY)
            c.fill = _fill(TOTAL_BG)
            c.border = Border(top=Side(style="thin", color=BLUE))
            c.alignment = _align("center", "center")
            c.number_format = "#,##0.00" if ci == 5 else "#,##0"

        ws.row_dimensions[row].height = 22
        row += 1

        # Apply borders to data area
        for r in range(data_start, row):
            for ci in range(len(cols)):
                c = ws.cell(row=r, column=table_start_col + ci)
                c.border = Border(
                    bottom=Side(style="thin", color=BORDER_CLR),
                )

        ws.row_dimensions[row].height = 6
        row += 1

        _card_border(ws, card_top, row - 1)
        return row + 1

    def _write_notes(self, ws, row, report):
        """Report Notes section."""
        row = _section_header(ws, row, "REPORT NOTES", "ℹ")
        card_top = row
        row += 1

        bullets = []
        bullets.append(
            f"This report covers library transactions from "
            f"{report.start_date.strftime('%d %b %Y')} to "
            f"{report.end_date.strftime('%d %b %Y')}."
        )
        if report.totals.overdue == 0:
            bullets.append("No books are currently overdue as of the report generation time.")
        else:
            bullets.append(
                f"There are currently {report.totals.overdue} overdue item(s) requiring attention."
            )
        if report.include_fines:
            if report.totals.fines > 0:
                bullets.append(
                    f"Total fines collected during this period: ₹{report.totals.fines:.2f}."
                )
            else:
                bullets.append("No fines were recorded during this period.")
        if not report.rows or all(
            row_data.issued == 0 and row_data.returned == 0 for row_data in report.rows
        ):
            bullets.append("No circulation activity was recorded during the selected period.")
        bullets.append("All data is sourced from the Library Management System records.")

        for b in bullets:
            ws.merge_cells(
                start_row=row, start_column=REPORT_START + 1,
                end_row=row, end_column=REPORT_END,
            )
            cell = ws.cell(row=row, column=REPORT_START + 1, value=f"•  {b}")
            cell.font = _font(size=9, color="444444")
            cell.alignment = _align("left", "center", wrap=True)
            cell.fill = _fill(CARD_BG)
            for c in range(REPORT_START, REPORT_END + 1):
                ws.cell(row=row, column=c).fill = _fill(CARD_BG)
            ws.row_dimensions[row].height = 20
            row += 1

        ws.row_dimensions[row].height = 6
        row += 1

        _card_border(ws, card_top, row - 1)
        return row + 1

    def _write_footer(self, ws, row):
        """Footer branding."""
        ws.row_dimensions[row].height = 6
        row += 1
        ws.merge_cells(
            start_row=row, start_column=REPORT_START,
            end_row=row, end_column=REPORT_END,
        )
        cell = ws.cell(row=row, column=REPORT_START,
                        value="Knowledge Today  •  A Brighter Tomorrow")
        cell.font = _font(size=9, color=GRAY)
        cell.alignment = _align("center", "center")
        return row + 1

    # ── Utilities ───────────────────────────────────────────────────────────

    def _set_column_widths(self, ws):
        """Auto-fit column widths based on content length."""
        for col_idx in range(REPORT_START, REPORT_END + 1):
            col_letter = get_column_letter(col_idx)
            if col_idx == REPORT_START:
                ws.column_dimensions[col_letter].width = 8.5
                continue
            max_len = 0
            for cell in ws[col_letter]:
                if cell.value is not None:
                    val = str(cell.value)
                    font_size = cell.font.size if cell.font and cell.font.size else 10
                    multiplier = max(1.0, font_size / 10)
                    cell_len = len(val) * multiplier
                    max_len = max(max_len, cell_len)
            width = max(8, min(max_len + 3, 40))
            ws.column_dimensions[col_letter].width = width

    def _configure_print(self, ws, last_row):
        """Configure print settings for professional output."""
        ws.page_setup.orientation = "portrait"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.page_margins.left = 0.4
        ws.page_margins.right = 0.4
        ws.page_margins.top = 0.4
        ws.page_margins.bottom = 0.4
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_options.horizontalCentered = True
        ws.print_area = f"A1:M{last_row}"

    @staticmethod
    def _report_id(r: ReportPreviewDto) -> str:
        d = r.start_date
        return f"LMS-{r.report_type[:2]}-{d.year}-{d.month:02d}-{d.day:02d}-001"

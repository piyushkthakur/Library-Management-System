"""PDF Report Generator — Library Management System.

Modular, data-driven PDF renderer matching a modern institutional design
system. The visual template is fixed; only data populates it.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.reporting import ExportResultDto, ReportExporter, ReportPreviewDto

# ── Colour palette ──────────────────────────────────────────────────────────
NAVY = HexColor("#1B2A4A")
BLUE = HexColor("#2E6F9E")
LIGHT_BLUE = HexColor("#EBF2FA")
TEAL = HexColor("#1D9A6C")
LIGHT_TEAL = HexColor("#E6F7F1")
ORANGE = HexColor("#D97706")
LIGHT_ORANGE = HexColor("#FEF3E2")
PURPLE = HexColor("#6B5CE7")
LIGHT_PURPLE = HexColor("#F0EEFF")
GRAY = HexColor("#6B7280")
LIGHT_GRAY = HexColor("#F3F4F6")
CARD_BG = HexColor("#F8FAFC")
WHITE = colors.white
BORDER = HexColor("#D1D5DB")
SECTION_BG = HexColor("#F1F5F9")
ACCENT_LINE = HexColor("#2E6F9E")

# ── Page geometry ───────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
BOX_W = CONTENT_W * 0.88
PAD = (CONTENT_W - BOX_W) / 2

# ── Report type titles ──────────────────────────────────────────────────────
REPORT_TITLES = {
    "DAILY": "Daily Library Activity Report",
    "WEEKLY": "Weekly Library Activity Report",
    "MONTHLY": "Monthly Library Activity Report",
    "YEARLY": "Yearly Library Activity Report",
    "CUSTOM": "Library Activity Report",
}


# ── Icon drawing helpers ────────────────────────────────────────────────────
# Each function draws a small icon centred at (cx, cy) on a canvas.

def _icon_book(c, cx: float, cy: float, sz: float = 12):
    """Open book icon."""
    c.saveState()
    c.setFillColor(WHITE)
    c.setStrokeColor(WHITE)
    c.setLineWidth(0.8)
    # Left page
    c.roundRect(cx - sz * 0.6, cy - sz * 0.4, sz * 0.55, sz * 0.8, 1, fill=1, stroke=0)
    # Right page
    c.roundRect(cx + sz * 0.05, cy - sz * 0.4, sz * 0.55, sz * 0.8, 1, fill=1, stroke=0)
    c.restoreState()


def _icon_calendar(c, cx: float, cy: float, sz: float = 12):
    """Calendar icon."""
    c.saveState()
    c.setStrokeColor(WHITE)
    c.setFillColor(WHITE)
    c.setLineWidth(0.7)
    # Body
    c.roundRect(cx - sz * 0.4, cy - sz * 0.35, sz * 0.8, sz * 0.7, 2, fill=0, stroke=1)
    # Top bar
    c.setFillColor(WHITE)
    c.rect(cx - sz * 0.4, cy + sz * 0.15, sz * 0.8, sz * 0.12, fill=1, stroke=0)
    # Dots for days
    for dx in (-0.18, 0.0, 0.18):
        for dy in (-0.08, -0.2):
            c.circle(cx + sz * dx, cy + sz * dy, sz * 0.03, fill=1, stroke=0)
    c.restoreState()


def _icon_building(c, cx: float, cy: float, sz: float = 12):
    """Building / institution icon."""
    c.saveState()
    c.setStrokeColor(WHITE)
    c.setFillColor(WHITE)
    c.setLineWidth(0.7)
    # Main body
    c.rect(cx - sz * 0.25, cy - sz * 0.35, sz * 0.5, sz * 0.65, fill=0, stroke=1)
    # Roof triangle
    c.line(cx - sz * 0.35, cy + sz * 0.3, cx, cy + sz * 0.45)
    c.line(cx, cy + sz * 0.45, cx + sz * 0.35, cy + sz * 0.3)
    # Door
    c.rect(cx - sz * 0.08, cy - sz * 0.35, sz * 0.16, sz * 0.25, fill=1, stroke=0)
    c.restoreState()


def _icon_library(c, cx: float, cy: float, sz: float = 12):
    """Library / bookshelf icon."""
    c.saveState()
    c.setStrokeColor(WHITE)
    c.setFillColor(WHITE)
    c.setLineWidth(0.7)
    # Shelf
    c.line(cx - sz * 0.35, cy - sz * 0.1, cx + sz * 0.35, cy - sz * 0.1)
    # Books (vertical bars)
    for dx in (-0.25, -0.12, 0.0, 0.12, 0.25):
        h = sz * (0.35 + 0.05 * (hash(dx) % 3))
        c.rect(cx + sz * dx - sz * 0.04, cy - sz * 0.1, sz * 0.08, h, fill=1, stroke=0)
    c.restoreState()


def _icon_graduation(c, cx: float, cy: float, sz: float = 12):
    """Graduation cap icon."""
    c.saveState()
    c.setStrokeColor(WHITE)
    c.setFillColor(WHITE)
    c.setLineWidth(0.7)
    # Diamond top
    c.line(cx - sz * 0.35, cy + sz * 0.05, cx, cy + sz * 0.35)
    c.line(cx, cy + sz * 0.35, cx + sz * 0.35, cy + sz * 0.05)
    c.line(cx + sz * 0.35, cy + sz * 0.05, cx, cy - sz * 0.1)
    c.line(cx, cy - sz * 0.1, cx - sz * 0.35, cy + sz * 0.05)
    # Tassel
    c.line(cx + sz * 0.35, cy + sz * 0.05, cx + sz * 0.45, cy - sz * 0.15)
    c.restoreState()


def _icon_person(c, cx: float, cy: float, sz: float = 12):
    """Person / user icon."""
    c.saveState()
    c.setStrokeColor(WHITE)
    c.setFillColor(WHITE)
    c.setLineWidth(0.7)
    # Head
    c.circle(cx, cy + sz * 0.18, sz * 0.14, fill=0, stroke=1)
    # Body arc
    c.arc(cx - sz * 0.3, cy - sz * 0.35, cx + sz * 0.3, cy + sz * 0.1, 0, 180)
    c.restoreState()


def _icon_doc(c, cx: float, cy: float, sz: float = 12):
    """Document / report icon."""
    c.saveState()
    c.setStrokeColor(WHITE)
    c.setFillColor(WHITE)
    c.setLineWidth(0.7)
    # Page
    c.roundRect(cx - sz * 0.25, cy - sz * 0.35, sz * 0.5, sz * 0.7, 2, fill=0, stroke=1)
    # Lines
    for dy in (0.1, -0.02, -0.14):
        c.line(cx - sz * 0.15, cy + sz * dy, cx + sz * 0.15, cy + sz * dy)
    c.restoreState()


def _icon_chart(c, cx: float, cy: float, sz: float = 12):
    """Bar chart icon."""
    c.saveState()
    c.setFillColor(WHITE)
    bars = [(-0.2, 0.15), (-0.05, 0.3), (0.1, 0.2), (0.25, 0.35)]
    for dx, h in bars:
        c.rect(cx + sz * dx - sz * 0.04, cy - sz * 0.2, sz * 0.08, sz * h, fill=1, stroke=0)
    c.restoreState()


def _icon_info(c, cx: float, cy: float, sz: float = 12):
    """Information icon (i in circle)."""
    c.saveState()
    c.setStrokeColor(WHITE)
    c.setFillColor(WHITE)
    c.setLineWidth(0.7)
    c.circle(cx, cy, sz * 0.35, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", sz * 0.3)
    c.drawCentredString(cx, cy - sz * 0.05, "i")
    c.restoreState()


def _icon_issued(c, cx: float, cy: float, sz: float = 12):
    """Books issued — open book icon."""
    _icon_book(c, cx, cy, sz)


def _icon_returned(c, cx: float, cy: float, sz: float = 12):
    """Books returned — circular arrow icon."""
    c.saveState()
    c.setStrokeColor(WHITE)
    c.setFillColor(WHITE)
    c.setLineWidth(1.2)
    c.arc(cx - sz * 0.25, cy - sz * 0.25, cx + sz * 0.25, cy + sz * 0.25, 30, 300)
    # Arrowhead
    ax, ay = cx + sz * 0.18, cy + sz * 0.18
    c.line(ax, ay, ax - sz * 0.08, ay - sz * 0.04)
    c.line(ax, ay, ax - sz * 0.04, ay + sz * 0.08)
    c.restoreState()


def _icon_overdue(c, cx: float, cy: float, sz: float = 12):
    """Overdue — warning triangle."""
    c.saveState()
    c.setFillColor(WHITE)
    c.setStrokeColor(WHITE)
    c.setLineWidth(0.8)
    h = sz * 0.4
    w = sz * 0.7
    p = c.beginPath()
    p.moveTo(cx, cy + h * 0.6)
    p.lineTo(cx - w / 2, cy - h * 0.4)
    p.lineTo(cx + w / 2, cy - h * 0.4)
    p.close()
    c.drawPath(p, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", sz * 0.22)
    c.drawCentredString(cx, cy - sz * 0.08, "!")
    c.restoreState()


def _icon_exchange(c, cx: float, cy: float, sz: float = 12):
    """Transactions — two opposing arrows."""
    c.saveState()
    c.setStrokeColor(WHITE)
    c.setLineWidth(1.0)
    # Right arrow
    c.line(cx - sz * 0.25, cy + sz * 0.08, cx + sz * 0.2, cy + sz * 0.08)
    c.line(cx + sz * 0.15, cy + sz * 0.15, cx + sz * 0.2, cy + sz * 0.08)
    c.line(cx + sz * 0.15, cy + sz * 0.01, cx + sz * 0.2, cy + sz * 0.08)
    # Left arrow
    c.line(cx + sz * 0.25, cy - sz * 0.08, cx - sz * 0.2, cy - sz * 0.08)
    c.line(cx - sz * 0.15, cy - sz * 0.15, cx - sz * 0.2, cy - sz * 0.08)
    c.line(cx - sz * 0.15, cy - sz * 0.01, cx - sz * 0.2, cy - sz * 0.08)
    c.restoreState()


def _draw_circle_bg(c, cx: float, cy: float, r: float, fill_color):
    """Draw a filled circle background for an icon."""
    c.saveState()
    c.setFillColor(fill_color)
    c.circle(cx, cy, r, fill=1, stroke=0)
    c.restoreState()


# ── Styles ──────────────────────────────────────────────────────────────────

def _styles():
    s = getSampleStyleSheet()

    s.add(ParagraphStyle(
        "ReportTitle", fontName="Helvetica-Bold", fontSize=22,
        textColor=NAVY, leading=28, alignment=TA_LEFT,
    ))
    s.add(ParagraphStyle(
        "SectionHead", fontName="Helvetica-Bold", fontSize=13,
        textColor=NAVY, leading=16, alignment=TA_LEFT,
    ))
    s.add(ParagraphStyle(
        "MetaLabel", fontName="Helvetica-Bold", fontSize=8,
        textColor=NAVY, leading=11,
    ))
    s.add(ParagraphStyle(
        "MetaValue", fontName="Helvetica", fontSize=8.5,
        textColor=GRAY, leading=11,
    ))
    s.add(ParagraphStyle(
        "CtxLabel", fontName="Helvetica-Bold", fontSize=8,
        textColor=NAVY, leading=11,
    ))
    s.add(ParagraphStyle(
        "CtxValue", fontName="Helvetica", fontSize=8,
        textColor=GRAY, leading=11,
    ))
    s.add(ParagraphStyle(
        "KpiLabel", fontName="Helvetica-Bold", fontSize=8,
        textColor=NAVY, leading=10, alignment=TA_CENTER,
    ))
    s.add(ParagraphStyle(
        "KpiValue", fontName="Helvetica-Bold", fontSize=22,
        textColor=NAVY, leading=26, alignment=TA_CENTER,
    ))
    s.add(ParagraphStyle(
        "KpiSub", fontName="Helvetica", fontSize=7,
        textColor=GRAY, leading=9, alignment=TA_CENTER,
    ))
    s.add(ParagraphStyle(
        "TblHead", fontName="Helvetica-Bold", fontSize=8,
        textColor=WHITE, leading=10, alignment=TA_CENTER,
    ))
    s.add(ParagraphStyle(
        "TblCell", fontName="Helvetica", fontSize=8,
        textColor=NAVY, leading=10, alignment=TA_CENTER,
    ))
    s.add(ParagraphStyle(
        "TblCellBold", fontName="Helvetica-Bold", fontSize=8,
        textColor=NAVY, leading=10, alignment=TA_CENTER,
    ))
    s.add(ParagraphStyle(
        "TblCellLeft", fontName="Helvetica", fontSize=8,
        textColor=NAVY, leading=10, alignment=TA_LEFT,
    ))
    s.add(ParagraphStyle(
        "NoteBullet", fontName="Helvetica", fontSize=8,
        textColor=GRAY, leading=12, leftIndent=12, bulletIndent=0,
    ))

    return s


# ── Reusable section builder ───────────────────────────────────────────────

def _section_header(title: str, icon_fn, icon_color=BLUE) -> Table:
    """Build a section header bar: [icon_circle | title text]."""
    # We use a placeholder Paragraph for the icon space; the actual icon
    # is drawn via a custom Flowable-like approach: we embed the icon
    # drawing in a small table cell and use a canvas callback.
    # Simpler: just use a coloured dot via ZapfDingbats in a styled para.
    icon_p = Paragraph(
        "\u25cf",
        ParagraphStyle("_ih", fontName="ZapfDingbats", fontSize=12,
                       textColor=icon_color, leading=14, alignment=TA_CENTER),
    )
    title_p = Paragraph(title, ParagraphStyle(
        "_it", fontName="Helvetica-Bold", fontSize=13,
        textColor=NAVY, leading=16,
    ))
    tbl = Table([[icon_p, Spacer(1, 1), title_p]], colWidths=[20, 4, BOX_W - 24])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (0, 0), 6),
        ("RIGHTPADDING", (-1, -1), (-1, -1), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 0),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
    ]))
    # Wrap in outer table with light blue background
    outer = Table([[tbl]], colWidths=[BOX_W])
    outer.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SECTION_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("ROUNDEDCORNERS", [4, 4, 0, 0]),
    ]))
    return outer


def _section_body(content_flowable) -> Table:
    """Wrap content in a rounded-bottom container."""
    outer = Table([[content_flowable]], colWidths=[BOX_W])
    outer.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [0, 0, 4, 4]),
    ]))
    return outer


def _section_section(title: str, icon_fn, icon_color, content_flowable):
    """Return [section_header, section_body] as a list of flowables."""
    return [_section_header(title, icon_fn, icon_color), _section_body(content_flowable)]


# ── Page callbacks ──────────────────────────────────────────────────────────

def _draw_page(canvas, doc):
    """Draw header and footer on every page."""
    canvas.saveState()

    # ── Header ──
    y = PAGE_H - 14 * mm
    left = MARGIN + PAD
    right = PAGE_W - MARGIN - PAD

    # App name (generic book icon mark, no logo image)
    text_x = left + 30
    _draw_circle_bg(canvas, left + 10, y + 2, 14, BLUE)
    _icon_book(canvas, left + 10, y + 2, sz=14)

    canvas.setFont("Helvetica-Bold", 20)
    canvas.setFillColor(NAVY)
    canvas.drawString(text_x, y + 4, "Library Management System")

    # Tagline
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(text_x, y - 10, "Learn  •  Read  •  Grow")

    # Quote (right-aligned)
    canvas.setFont("Helvetica-Oblique", 8)
    canvas.setFillColor(GRAY)
    canvas.drawRightString(right, y + 4,
                           "A library is not just a place for books,")
    canvas.drawRightString(right, y - 8,
                           "it\u2019s a place for better futures.")

    # Accent line
    canvas.setStrokeColor(ACCENT_LINE)
    canvas.setLineWidth(1.5)
    canvas.line(left, y - 28, right, y - 28)

    # ── Footer ──
    fy = 10 * mm
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(left, fy + 6, right, fy + 6)

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GRAY)
    canvas.drawCentredString(PAGE_W / 2, fy - 2,
                             "Knowledge Today  \u00b7  A Brighter Tomorrow")

    canvas.setFont("Helvetica", 6.5)
    canvas.drawRightString(right, fy - 2, f"Page {doc.page}")

    canvas.restoreState()


# ── Helpers ─────────────────────────────────────────────────────────────────


def _fmt_date_range(start, end) -> str:
    return f"{start.strftime('%d %b %Y')} \u2013 {end.strftime('%d %b %Y')}"


def _fmt_date(d, report_type=None) -> str:
    if report_type == "YEARLY":
        return d.strftime("%Y")
    if report_type == "MONTHLY":
        return d.strftime("%B %Y")
    return d.strftime("%d %b %Y")


# ── Main Exporter ───────────────────────────────────────────────────────────

class PdfExporter(ReportExporter):

    def generate(self, report: ReportPreviewDto) -> ExportResultDto:
        buf = BytesIO()
        sty = _styles()

        doc = BaseDocTemplate(
            buf, pagesize=A4,
            title=REPORT_TITLES.get(report.report_type, "Library Activity Report"),
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
        )
        frame = Frame(MARGIN, 0, CONTENT_W,
                       PAGE_H - doc.topMargin - doc.bottomMargin, id="main",
                       leftPadding=PAD, rightPadding=PAD)
        doc.addPageTemplates([PageTemplate(id="body", frames=[frame],
                                           onPage=_draw_page)])

        story: list = []

        # ── Title ──────────────────────────────────────────────────────────
        story.append(Spacer(1, 2 * mm))
        story.append(self._title_block(report, sty))
        story.append(Spacer(1, 4 * mm))

        # ── Metadata card ──────────────────────────────────────────────────
        story.extend(self._metadata_section(report, sty))
        story.append(Spacer(1, 4 * mm))

        # ── Report Context ─────────────────────────────────────────────────
        story.extend(self._context_section(report, sty))
        story.append(Spacer(1, 4 * mm))

        # ── Executive Summary ──────────────────────────────────────────────
        story.extend(self._summary_section(report, sty))
        story.append(Spacer(1, 4 * mm))

        # ── Activity Details ───────────────────────────────────────────────
        story.extend(self._activity_section(report, sty))
        story.append(Spacer(1, 4 * mm))

        # ── Report Notes ───────────────────────────────────────────────────
        story.extend(self._notes_section(report, sty))

        doc.build(story)
        return ExportResultDto(
            file_name=self._file_name(report),
            file_bytes=buf.getvalue(),
        )

    # ── Title block ────────────────────────────────────────────────────────

    def _title_block(self, r: ReportPreviewDto, sty) -> Table:
        title = REPORT_TITLES.get(r.report_type, "Library Activity Report")
        # Icon in a navy rounded square
        icon_p = Paragraph(
            "\u25a0",
            ParagraphStyle("_ti", fontName="ZapfDingbats", fontSize=16,
                           textColor=BLUE, leading=18, alignment=TA_CENTER),
        )
        title_p = Paragraph(title, sty["ReportTitle"])
        tbl = Table([[icon_p, Spacer(1, 6), title_p]],
                     colWidths=[32, 6, BOX_W - 38])
        tbl.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        return tbl

    # ── Metadata section ───────────────────────────────────────────────────

    def _metadata_section(self, r: ReportPreviewDto, sty):
        header = _section_header("Report Details", _icon_doc, BLUE)

        report_id = self._report_id(r)
        gen_on = datetime.now().strftime("%d %b %Y, %I:%M %p")

        # Two-column grid of label/value pairs
        def _pair(label, value):
            return [
                Paragraph(label, sty["MetaLabel"]),
                Paragraph(value, sty["MetaValue"]),
            ]

        data = [
            [_pair("Reporting Period", _fmt_date_range(r.start_date, r.end_date)),
             _pair("Report Type", f"{r.report_type.title()} Report")],
            [_pair("Generated On", gen_on),
             _pair("Report ID", report_id)],
        ]

        half = BOX_W / 2 - 4
        tbl = Table(data, colWidths=[half, half])
        tbl.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))

        body = _section_body(tbl)
        return [header, body, Spacer(1, 0)]

    # ── Context section ────────────────────────────────────────────────────

    def _context_section(self, r: ReportPreviewDto, sty):
        header = _section_header("Report Context", _icon_doc, BLUE)

        half = BOX_W / 2 - 4

        def _cell(icon_char: str, icon_clr, label: str, value: str) -> Table:
            """Single context cell: [icon_circle | label+value]."""
            icon_p = Paragraph(
                icon_char,
                ParagraphStyle("_ci", fontName="ZapfDingbats", fontSize=11,
                               textColor=icon_clr, leading=13, alignment=TA_CENTER),
            )
            text_p = Paragraph(
                f'{label}<br/><b>{value}</b>',
                ParagraphStyle("_cv", fontName="Helvetica", fontSize=8,
                               textColor=NAVY, leading=11),
            )
            inner = Table([[icon_p, text_p]], colWidths=[22, half - 28])
            inner.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]))
            return inner

        rows = [
            [_cell("\u25a0", BLUE, "System", "Library Management System"),
             _cell("\u25a0", BLUE, "Library / Department", "Main Library")],
            [_cell("\u25a0", TEAL, "Academic Year", r.academic_year or "\u2014"),
             _cell("\u25a0", BLUE, "Generated By", r.generated_by or "System")],
            [_cell("\u25a0", BLUE, "Reporting Period",
                    _fmt_date_range(r.start_date, r.end_date)),
             _cell("\u25a0", BLUE, "Report Type", f"{r.report_type.title()} Report")],
        ]

        tbl = Table(rows, colWidths=[half, half])
        tbl.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))

        body = _section_body(tbl)
        return [header, body, Spacer(1, 0)]

    # ── Summary section ────────────────────────────────────────────────────

    def _summary_section(self, r: ReportPreviewDto, sty):
        header = _section_header("Executive Summary", _icon_chart, BLUE)

        total = r.totals.issued + r.totals.returned

        kpis = [
            ("\u25a0", TEAL, LIGHT_TEAL, "Books Issued",
             str(r.totals.issued), "During selected period"),
            ("\u25a0", BLUE, LIGHT_BLUE, "Books Returned",
             str(r.totals.returned), "During selected period"),
            ("\u25a0", ORANGE, LIGHT_ORANGE, "Currently Overdue",
             str(r.totals.overdue), "At report generation"),
            ("\u25a0", PURPLE, LIGHT_PURPLE, "Total Transactions",
             str(total), "Issued + Returned"),
        ]

        card_w = BOX_W / 4
        cards = []
        for icon_ch, icon_clr, bg_clr, label, value, sub in kpis:
            # Icon in coloured circle
            icon_circle = Table(
                [[Paragraph(icon_ch, ParagraphStyle(
                    "_kc", fontName="ZapfDingbats", fontSize=14,
                    textColor=icon_clr, leading=16, alignment=TA_CENTER,
                ))]],
                colWidths=[36],
            )
            icon_circle.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), bg_clr),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("ROUNDEDCORNERS", [18, 18, 18, 18]),
            ]))

            card_content = Table([
                [icon_circle],
                [Spacer(1, 6)],
                [Paragraph(label, sty["KpiLabel"])],
                [Spacer(1, 4)],
                [Paragraph(value, sty["KpiValue"])],
                [Spacer(1, 4)],
                [Paragraph(sub, sty["KpiSub"])],
            ], colWidths=[card_w - 8])
            card_content.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]))
            cards.append(card_content)

        kpi_row = Table([cards], colWidths=[card_w] * 4)
        kpi_row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ]))

        body = _section_body(kpi_row)
        return [header, body, Spacer(1, 0)]

    # ── Activity section ───────────────────────────────────────────────────

    def _activity_section(self, r: ReportPreviewDto, sty):
        header = _section_header("Activity Details", _icon_doc, BLUE)

        cols = ["Date", "Issued", "Returned", "Overdue", "Total Activity"]
        if r.include_fines:
            cols.append("Fines Collected")

        tbl_head = [Paragraph(c, sty["TblHead"]) for c in cols]
        data_rows = [tbl_head]

        for row in r.rows:
            activity = row.issued + row.returned
            cells = [
                Paragraph(_fmt_date(row.date, r.report_type), sty["TblCellLeft"]),
                Paragraph(str(row.issued), sty["TblCell"]),
                Paragraph(str(row.returned), sty["TblCell"]),
                Paragraph(str(row.overdue), sty["TblCell"]),
                Paragraph(str(activity), sty["TblCellBold"]),
            ]
            if r.include_fines:
                cells.append(Paragraph(f"\u20b9{row.fines:.2f}", sty["TblCell"]))
            data_rows.append(cells)

        # Total row
        total_activity = r.totals.issued + r.totals.returned
        total_cells = [
            Paragraph("Total", sty["TblCellBold"]),
            Paragraph(str(r.totals.issued), sty["TblCellBold"]),
            Paragraph(str(r.totals.returned), sty["TblCellBold"]),
            Paragraph(str(r.totals.overdue), sty["TblCellBold"]),
            Paragraph(str(total_activity), sty["TblCellBold"]),
        ]
        if r.include_fines:
            total_cells.append(Paragraph(f"\u20b9{r.totals.fines:.2f}", sty["TblCellBold"]))
        data_rows.append(total_cells)

        n = len(cols)
        w = BOX_W / n
        tbl = Table(data_rows, colWidths=[w] * n, repeatRows=1)

        cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("BACKGROUND", (0, 1), (-1, -2), WHITE),
            ("ROUNDEDCORNERS", [4, 4, 0, 0]),
        ]
        for i in range(2, len(data_rows) - 1):
            if i % 2 == 0:
                cmds.append(("BACKGROUND", (0, i), (-1, i), LIGHT_GRAY))
        cmds.append(("BACKGROUND", (0, -1), (-1, -1), LIGHT_BLUE))
        cmds.append(("LINEABOVE", (0, -1), (-1, -1), 0.8, BLUE))

        tbl.setStyle(TableStyle(cmds))

        inner = Table([[tbl]], colWidths=[BOX_W])
        inner.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))

        body = _section_body(inner)
        return [header, body, Spacer(1, 0)]

    # ── Notes section ──────────────────────────────────────────────────────

    def _notes_section(self, r: ReportPreviewDto, sty):
        header = _section_header("Report Notes", _icon_info, BLUE)

        bullets = []
        bullets.append(
            f"This report covers library transactions from "
            f"{_fmt_date(r.start_date)} to {_fmt_date(r.end_date)}."
        )
        if r.totals.overdue == 0:
            bullets.append(
                "No books are currently overdue as of the report generation time."
            )
        else:
            bullets.append(
                f"There are currently {r.totals.overdue} overdue item(s) "
                f"requiring attention."
            )
        if r.include_fines:
            if r.totals.fines > 0:
                bullets.append(
                    f"Total fines collected during this period: "
                    f"\u20b9{r.totals.fines:.2f}."
                )
            else:
                bullets.append("No fines were recorded during this period.")
        if not r.rows or all(
            row.issued == 0 and row.returned == 0 for row in r.rows
        ):
            bullets.append(
                "No circulation activity was recorded during the selected period."
            )
        bullets.append(
            "All data is sourced from the Library Management System records."
        )

        # Info icon
        info_icon = Paragraph(
            "\u25a0",
            ParagraphStyle("_ni", fontName="ZapfDingbats", fontSize=11,
                           textColor=BLUE, leading=13, alignment=TA_CENTER),
        )

        note_paras = []
        for b in bullets:
            note_paras.append(
                [Paragraph(f"\u2022&nbsp;&nbsp;{b}", sty["NoteBullet"])]
            )
        note_tbl = Table(note_paras, colWidths=[BOX_W - 40])
        note_tbl.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ]))

        content = Table([[info_icon, note_tbl]], colWidths=[24, BOX_W - 32])
        content.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))

        body = _section_body(content)
        return [header, body]

    # ── Utilities ──────────────────────────────────────────────────────────

    @staticmethod
    def _report_id(r: ReportPreviewDto) -> str:
        d = r.start_date
        return f"LMS-{r.report_type[:2]}-{d.year}-{d.month:02d}-{d.day:02d}-001"

    @staticmethod
    def _file_name(r: ReportPreviewDto) -> str:
        title = REPORT_TITLES.get(r.report_type, "Library Activity Report")
        return f"{title}.pdf"

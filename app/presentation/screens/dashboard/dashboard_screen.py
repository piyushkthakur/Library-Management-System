"""Dashboard screen: KPI cards, trend + category charts, overdue panel."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.presentation.shared_components.buttons import Button
from app.presentation.shared_components.cards import KpiCard, page_header
from app.presentation.shared_components.chart_container import ChartContainer
from app.presentation.shared_components.dialogs import DIALOG_BG
from app.presentation.shared_components.errors import notify_error
from app.presentation.shared_components.toast import ToastHost
from app.presentation.theme import (
    COLOR_ACCENT,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_SURFACE,
    COLOR_SUCCESS,
    COLOR_TEXT,
    SPACING,
    styled_text,
)

# ponytail: dashboard charts render on the shared white card surfaces.
_PIE_PALETTE = ["#1F2A44", "#2E6F9E", "#1D9A6C", "#C0362C", "#B7791F", "#6B7280"]


def _mpl_figure(width: int, height: int):
    """Lazy Agg figure (import kept local so the dashboard works even where
    Matplotlib is not installed — the fallback is then skipped)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt.subplots(figsize=(width / 100, height / 100), dpi=100)


def _mpl_save(fig) -> bytes:
    import io

    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    plt.close(fig)
    return buf.getvalue()


def _mpl_trend_png(dates, issued, returned, width: int = 520, height: int = 280) -> bytes:
    """Same line-chart look as the Plotly version, rendered in-process."""
    import matplotlib.ticker as mticker

    xs = list(range(len(dates)))
    fig, ax = _mpl_figure(width, height)
    ax.plot(xs, issued, color=COLOR_ACCENT, linewidth=2, label="Issued")
    ax.plot(xs, returned, color=COLOR_SUCCESS, linewidth=2, label="Returned")
    ax.set_xlim(0, max(len(dates) - 1, 1))
    ax.set_ylim(0, max([*issued, *returned, 1]) + 1)
    step = max(1, len(dates) // 6)
    ax.set_xticks(xs[::step])
    ax.set_xticklabels([dates[i].strftime("%d %b") for i in range(0, len(dates), step)])
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.tick_params(colors=COLOR_TEXT, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color((0.6, 0.64, 0.68, 1))
    ax.grid(True, color=(0.85, 0.87, 0.89, 1), linewidth=0.5)
    ax.legend(frameon=False, labelcolor=COLOR_TEXT, fontsize=9)
    fig.subplots_adjust(left=0.10, right=0.97, top=0.95, bottom=0.22)
    return _mpl_save(fig)


def _mpl_pie_png(
    names: list[str],
    values: list[int],
    width: int = 520,
    height: int = 280,
    text_color: str = COLOR_TEXT,
) -> bytes:
    """Same outside-label pie look as the Plotly version, in-process: one
    'name: value (pct%)' text per slice, clockwise from the top."""
    total = sum(values) or 1
    fig, ax = _mpl_figure(width, height)
    colors = [_PIE_PALETTE[i % len(_PIE_PALETTE)] for i in range(len(values))]
    texts = ax.pie(
        values,
        colors=colors,
        radius=0.45,
        labels=[f"{n}: {v} ({v / total * 100:.1f}%)" for n, v in zip(names, values)],
        startangle=90,
        counterclock=False,
        textprops={"color": text_color, "fontsize": 9},
        wedgeprops={"edgecolor": "#FFFFFF", "linewidth": 1},
        labeldistance=1.2,
    )[1]
    # ponytail: spread stacked outside labels apart in pixel space (like
    # Plotly does) and clamp inside the figure, so tiny adjacent slices
    # stay readable instead of printing over each other or off the edge.
    ax.axis("equal")
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    items = []
    for t in texts:
        bb = t.get_window_extent(renderer)
        items.append([t, bb.y0, bb.height])
    items.sort(key=lambda row: row[1])
    for i in range(1, len(items)):
        need = items[i - 1][1] + items[i - 1][2] + 4 - items[i][1]
        if need > 0:
            items[i][1] += need
    overflow = max(y + h for _, y, h in items) - (fig.bbox.height - 4)
    if overflow > 0:
        for item in items:
            item[1] -= overflow
    underflow = 4 - min(y for _, y, _ in items)
    if underflow > 0:
        for item in items:
            item[1] += underflow
    inv = ax.transData.inverted()
    for t, new_y0, _ in items:
        x_disp, base_disp = ax.transData.transform(t.get_position())
        old_y0 = t.get_window_extent(renderer).y0
        _, new_base = inv.transform((x_disp, base_disp + (new_y0 - old_y0)))
        x_old, _ = t.get_position()
        t.set_position((x_old, new_base))
    return _mpl_save(fig)








class DashboardScreen:
    def __init__(
        self,
        page: ft.Page,
        dashboard_service,
        context,
        toasts: ToastHost,
        on_open_transactions: Callable[[str], None],
    ) -> None:
        self._page = page
        self._dashboard = dashboard_service
        self._context = context
        self._toasts = toasts
        self._on_open_transactions = on_open_transactions
        self.kpi_books = KpiCard("Total Books", ft.Icons.MENU_BOOK)
        self.kpi_available = KpiCard("Available Copies", ft.Icons.INVENTORY_2)
        self.kpi_active = KpiCard("Issued Books", ft.Icons.BOOKMARK_ADDED)
        self.kpi_overdue = KpiCard("Overdue", ft.Icons.ERROR_OUTLINE)
        self.trend_chart = ChartContainer("Issued vs Returned", height=280)
        self.category_chart = ChartContainer("Books by Category", height=280)
        self._overdue_list = ft.Column(spacing=SPACING["sm"], tight=True)
        self._root: ft.Control | None = None

    def build(self) -> ft.Control:
        self.category_chart.on_click = self._open_category_chart
        for card in (self.kpi_books, self.kpi_available, self.kpi_active, self.kpi_overdue):
            card.container.col = {"xs": 12, "sm": 6, "lg": 3}
        for chart in (self.trend_chart, self.category_chart):
            chart.col = {"xs": 12, "lg": 6}
        kpi_row = ft.ResponsiveRow(
            [
                self.kpi_books.container,
                self.kpi_available.container,
                self.kpi_active.container,
                self.kpi_overdue.container,
            ],
            spacing=SPACING["md"],
        )
        charts = ft.ResponsiveRow(
            [self.trend_chart, self.category_chart],
            spacing=SPACING["md"],
            run_spacing=SPACING["md"],
        )
        overdue_panel = ft.Container(
            ft.Column(
                [
                    styled_text("Overdue Books", style="h2"),
                    self._overdue_list,
                ],
                spacing=SPACING["sm"],
            ),
            padding=ft.Padding.all(20),
            bgcolor=COLOR_SURFACE,
            border=ft.Border.all(1, COLOR_BORDER),
            border_radius=8,
        )
        content = ft.Column(
            [
                page_header("Dashboard", "A quick overview of your library"),
                kpi_row,
                charts,
                overdue_panel,
            ],
            spacing=SPACING["md"],
            scroll=ft.Scrollbar(thumb_visibility=True),
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            expand=True,
        )
        self._root = content
        return self._root

    def activate(self, params=None) -> None:
        if not self._root:
            return
        try:
            data = self._dashboard.get_dashboard()
        except Exception as exc:
            notify_error(self._toasts, exc)
            return
        try:
            self.kpi_books.set_value(str(data.total_books))
            self.kpi_available.set_value(str(data.total_available_copies))
            self.kpi_active.set_value(str(data.active_transactions))
            self.kpi_overdue.set_value(str(data.overdue_transactions))
        except Exception:
            pass
        # ponytail: Agg renders both charts in ~0.2s in-process — no task,
        # no Kaleido, tab switches stay instant.
        if data.trend:
            try:
                self.trend_chart.render_png(
                    _mpl_trend_png(
                        [p.date for p in data.trend],
                        [p.issued for p in data.trend],
                        [p.returned for p in data.trend],
                    )
                )
            except Exception:
                self.trend_chart.show_empty("Chart rendering is unavailable.")
        else:
            self.trend_chart.show_empty("No activity in the last 30 days.")
        self._category_data = [
            (c.category_name, c.book_count)
            for c in data.category_distribution
            if c.book_count > 0
        ]
        if self._category_data:
            try:
                names = [name for name, _ in self._category_data]
                values = [count for _, count in self._category_data]
                self.category_chart.render_png(_mpl_pie_png(names, values))
            except Exception:
                self.category_chart.show_empty("Chart rendering is unavailable.")
        else:
            self.category_chart.show_empty("No books catalogued yet.")
        try:
            self._overdue_list.controls = self._overdue_rows(data.overdue_items)
        except Exception:
            pass
        self._page.update()

    def _overdue_rows(self, items) -> list[ft.Control]:
        if not items:
            return [styled_text("No overdue books. Great job!", style="caption")]
        rows = []
        for item in items:
            panel = ft.Container(
                ft.Row(
                    [
                        ft.Container(
                            ft.Column(
                                [
                                    styled_text(item.book_title, style="body_emphasis"),
                                    styled_text(item.student_name, style="caption"),
                                ],
                                spacing=0,
                            ),
                            expand=True,
                        ),
                        styled_text(f"{item.days_overdue}d overdue", style="body", color=COLOR_DANGER, weight=ft.FontWeight.W_600),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                border=ft.Border(bottom=ft.BorderSide(1, "#EEF1F6")),
                on_click=lambda e, t=item: self._on_open_transactions("Overdue"),
            )
            rows.append(panel)
        return rows

    def _open_category_chart(self, e=None) -> None:
        # ponytail: dialog renders its own dark-text pie (light dialog bg),
        # in-process so it never blocks on Kaleido.
        if not self._category_data:
            return
        try:
            names = [name for name, _ in self._category_data]
            values = [count for _, count in self._category_data]
            png = _mpl_pie_png(names, values, width=800, height=450, text_color="#1D2939")
        except Exception:
            return
        dialog_img = ft.Image(src=png, fit=ft.BoxFit.CONTAIN, height=450)
        close_btn = Button("Close", on_click=self._close_dialog, variant="outline", width=100)
        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=DIALOG_BG,
            title=styled_text("Books by Category", style="h1"),
            title_padding=ft.Padding.only(left=24, top=20, right=24),
            content=ft.Container(dialog_img, alignment=ft.Alignment.CENTER, width=640, height=360),
            scrollable=True,
            content_padding=ft.Padding.only(left=24, top=8, right=24, bottom=12),
            actions=[close_btn],
            actions_padding=ft.Padding.only(left=24, right=24, bottom=18),
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._page.show_dialog(dialog)
        self._page.update()

    def _close_dialog(self, e=None) -> None:
        self._page.pop_dialog()
        self._page.update()
"""Shell chrome: sidebar, header and footer (Volume 2, Ch. 11-13, 49)."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.presentation.shared_components.buttons import Button
from app.presentation.theme import (
    COLOR_ACCENT,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_PRIMARY,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    COLOR_TEXT,
    COLOR_TEXT_SECONDARY,
    HINT_STYLE,
    NAV_INACTIVE,
    RADIUS_SM,
    SPACING,
    styled_text,
)

SIDEBAR_EXPANDED = 240
SIDEBAR_COLLAPSED = 64


class SidebarItem(ft.Container):
    def __init__(
        self,
        icon: str,
        label: str,
        key: str,
        selected: bool,
        on_click: Callable[[str], None],
        badge: str | None = None,
    ) -> None:
        self._badge_ctl = (
            ft.Container(
                content=styled_text(badge, style="caption", color=COLOR_SURFACE, weight=ft.FontWeight.W_600),
                bgcolor=COLOR_ACCENT,
                padding=ft.Padding.symmetric(horizontal=6, vertical=1),
                border_radius=RADIUS_SM,
            )
            if badge
            else None
        )
        self._label = label
        self._key = key
        self._on_click = on_click
        self._icon = icon
        self._label_ctl = styled_text(
            label, style="body", color=self._fg(selected),
            weight=ft.FontWeight.W_500 if selected else ft.FontWeight.W_400,
        )
        badge_cell = self._badge_ctl if self._badge_ctl else ft.Container()
        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(icon, size=18, color=self._fg(selected)),
                    self._label_ctl,
                    ft.Container(expand=True),
                    badge_cell,
                ],
                spacing=10,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=9),
            border_radius=RADIUS_SM,
            bgcolor=COLOR_ACCENT if selected else None,
            on_click=lambda e: self._on_click(self._key),
            ink=True,
            tooltip=label,
        )

    def _fg(self, selected: bool) -> str:
        return COLOR_SURFACE if selected else NAV_INACTIVE

    def set_selected(self, selected: bool) -> None:
        self.bgcolor = COLOR_ACCENT if selected else None
        row = self.content
        row.controls[0].color = self._fg(selected)
        self._label_ctl.color = self._fg(selected)
        self._label_ctl.weight = ft.FontWeight.W_500 if selected else ft.FontWeight.W_400

    def set_collapsed(self, collapsed: bool) -> None:
        self._label_ctl.visible = not collapsed
        self.content.controls[2].visible = not collapsed  # spacer
        self.content.controls[3].visible = not collapsed


class Sidebar(ft.Container):
    """Collapsible brand + nav rail."""

    def __init__(
        self,
        items: list[tuple[str, str, str, str | None]],
        on_navigate: Callable[[str], None],
        on_toggle: Callable[[], None] | None = None,
    ) -> None:
        self._on_navigate = on_navigate
        self._on_toggle = on_toggle
        self._items: dict[str, SidebarItem] = {}
        self._collapsed = False
        self._narrow = False
        self._wide_collapsed = False

        self._brand_icon = ft.Icon(ft.Icons.LOCAL_LIBRARY, color=COLOR_ACCENT, size=40)
        self._brand_label = styled_text("Library", style="h2", color=COLOR_SURFACE)
        self._brand_sublabel = styled_text("Management System", style="caption", color=NAV_INACTIVE)
        self._brand_row = ft.Row(
            [
                self._brand_icon,
                ft.Column(
                    [self._brand_label, self._brand_sublabel],
                    spacing=0,
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        brand = ft.Container(
            self._brand_row,
            padding=ft.Padding.symmetric(horizontal=14, vertical=18),
        )
        self._brand = brand
        nav = ft.Container(
            ft.Column(
                [self._item(icon, label, key, badge) for icon, label, key, badge in items],
                spacing=4,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            padding=ft.Padding.symmetric(horizontal=10),
            expand=True,
        )
        self._toggle_btn = ft.IconButton(
            icon=ft.Icons.CHEVRON_LEFT,
            tooltip="Collapse sidebar",
            on_click=lambda e: self.toggle(),
            icon_color=NAV_INACTIVE,
            icon_size=18,
        )
        sidebar_footer = ft.Container(
            ft.Column(
                [
                    self._toggle_btn,
                    styled_text("v1.0.0", style="caption", color=NAV_INACTIVE),
                ],
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=6, vertical=14),
        )
        super().__init__(
            content=ft.Column([brand, nav, sidebar_footer], spacing=0),
            width=SIDEBAR_EXPANDED,
            bgcolor=COLOR_PRIMARY,
            animate_size=ft.Animation(200, ft.AnimationCurve.EASE_IN_OUT),
        )

    def _item(self, icon: str, label: str, key: str, badge: str | None) -> SidebarItem:
        item = SidebarItem(icon, label, key, False, self._on_navigate, badge)
        self._items[key] = item
        return item

    def select(self, key: str) -> None:
        for k, item in self._items.items():
            item.set_selected(k == key)

    def resize(self, width: float) -> None:
        narrow = width < 1100
        if narrow != self._narrow:
            self._narrow = narrow
            self._set_collapsed(True if narrow else self._wide_collapsed)

    def toggle(self) -> None:
        self._set_collapsed(not self._collapsed)
        if not self._narrow:
            self._wide_collapsed = self._collapsed
        if self._on_toggle:
            self._on_toggle()
        elif self.page is not None:
            self.update()

    def _set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.width = SIDEBAR_COLLAPSED if self._collapsed else SIDEBAR_EXPANDED
        self._brand_row.controls[1].visible = not self._collapsed
        self._brand_label.visible = not self._collapsed
        self._brand_sublabel.visible = not self._collapsed
        self._toggle_btn.icon = ft.Icons.CHEVRON_RIGHT if self._collapsed else ft.Icons.CHEVRON_LEFT
        self._toggle_btn.tooltip = "Expand sidebar" if self._collapsed else "Collapse sidebar"
        # ponytail: collapsed content width must equal the 50px logo exactly
        # ((64 - 50) / 2 padding); any slack lets row spacing/alignment drift it.
        self._brand.padding = ft.Padding.symmetric(
            horizontal=7 if self._collapsed else 14, vertical=18
        )
        self._brand_row.spacing = 0 if self._collapsed else 12
        self._brand_row.alignment = (
            ft.MainAxisAlignment.CENTER if self._collapsed else ft.MainAxisAlignment.START
        )
        for item in self._items.values():
            item.set_collapsed(self._collapsed)


class Header(ft.Container):
    """Title, global search, notification bell, account popup."""

    def __init__(
        self,
        page: ft.Page,
        user_name: str = "",
        user_role: str = "",
        user_email: str = "",
        on_global_search: Callable[[str], None] | None = None,
        on_global_search_clear: Callable[[], None] | None = None,
        on_notifications: Callable[[], None] | None = None,
        on_profile: Callable[[], None] | None = None,
        on_logout: Callable[[], None] | None = None,
    ) -> None:
        self._page = page
        self.title = styled_text("Library Management System", style="h1")
        self._search = ft.TextField(
            hint_text="Search books, students, issued/returned books...",
            hint_style=HINT_STYLE,
            prefix_icon=ft.Icons.SEARCH,
            on_submit=lambda e: on_global_search(e.control.value) if on_global_search else None,
            on_change=lambda e: (
                on_global_search_clear()
                if on_global_search_clear and not (e.control.value or "").strip()
                else None
            ),
            width=360,
            height=40,
            text_size=13,
            color="#000000",
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT,
            content_padding=ft.Padding.symmetric(horizontal=12),
        )
        self.bell = ft.IconButton(
            icon=ft.Icons.NOTIFICATIONS_OUTLINED,
            tooltip="Notifications",
            on_click=lambda e: on_notifications() if on_notifications else None,
            icon_color=COLOR_PRIMARY,
            badge=ft.Badge(label="0", label_visible=False, bgcolor=COLOR_ACCENT),
        )
        initial = user_name[0].upper() if user_name else "?"
        role_label = "Administrator" if user_role == "ADMINISTRATOR" else "Librarian"
        avatar = ft.Container(
            content=ft.Text(initial, size=16, weight=ft.FontWeight.W_600, color=COLOR_SURFACE, text_align=ft.TextAlign.CENTER),
            width=36,
            height=36,
            border_radius=ft.BorderRadius.all(18),
            bgcolor=COLOR_PRIMARY,
            alignment=ft.Alignment.CENTER,
        )
        dropdown = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Column(
                            [
                                styled_text(user_name, style="body_emphasis"),
                                styled_text(user_email, style="caption", color=COLOR_TEXT_SECONDARY),
                                styled_text(role_label, style="caption", color=COLOR_TEXT_SECONDARY),
                            ],
                            spacing=2,
                        ),
                        padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                    ),
                    ft.Divider(height=1, color=COLOR_BORDER),
                    ft.Container(
                        content=styled_text("My Profile", style="body"),
                        padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                        on_click=lambda e: on_profile() if on_profile else None,
                    ),
                    ft.Divider(height=1, color=COLOR_BORDER),
                    ft.Container(
                        content=styled_text("Sign Out", style="body"),
                        padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                        on_click=lambda e: on_logout() if on_logout else None,
                    ),
                ],
                spacing=0,
            ),
            bgcolor=COLOR_SURFACE,
            border_radius=ft.BorderRadius.all(8),
            border=ft.Border.all(1, COLOR_BORDER),
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=8, color=ft.Colors.with_opacity(0.15, ft.Colors.BLACK), offset=ft.Offset(0, 2)),
            visible=False,
        )

        def _toggle(e=None):
            dropdown.visible = not dropdown.visible
            self._page.update()

        self.dropdown = dropdown
        avatar.on_click = _toggle
        avatar.tooltip = "Account menu"
        header_bar = ft.Container(
            content=ft.Row(
                [
                    ft.Container(self.title, expand=True),
                    self._search,
                    self.bell,
                    avatar,
                ],
                spacing=SPACING["md"],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLOR_SURFACE,
            padding=ft.Padding.symmetric(horizontal=24, vertical=12),
            border=ft.Border(bottom=ft.BorderSide(1, COLOR_BORDER)),
        )
        self._bar = header_bar
        super().__init__(
            content=header_bar,
            clip_behavior=ft.ClipBehavior.NONE,
        )

    def resize(self, width: float) -> None:
        self._search.visible = width >= 850
        self._search.width = min(360, max(200, width - 680))
        self.title.max_lines = 1
        self.title.overflow = ft.TextOverflow.ELLIPSIS

    def set_title(self, title: str) -> None:
        self.title.value = title

    def set_unread_count(self, count: int) -> None:
        self.bell.badge.label = str(count)
        self.bell.badge.label_visible = count > 0
        self.bell.tooltip = f"Notifications ({count} unread)"

class NotificationDialog:
    def __init__(self, page: ft.Page, on_refresh: Callable, on_action: Callable) -> None:
        self.error = styled_text("", style="caption", color=COLOR_DANGER)
        self.error.visible = False
        self.items = ft.Column(spacing=SPACING["sm"], scroll=ft.ScrollMode.AUTO, expand=True)
        self._on_action = on_action
        self.mark_all = Button(
            "Mark all read", on_click=lambda e: on_action("mark_all_read"), variant="outline"
        )
        self.dialog = ft.AlertDialog(
            modal=True,
            bgcolor=COLOR_SURFACE,
            title=styled_text("Notifications", style="h1"),
            content=ft.Column(
                [
                    styled_text("Latest 50 notifications. Refresh here or navigate to check for updates.", style="caption"),
                    self.error,
                    self.items,
                ],
                width=560,
                height=400,
                spacing=SPACING["sm"],
            ),
            actions=[
                Button("Refresh", on_click=lambda e: on_refresh(), variant="outline"),
                self.mark_all,
                Button("Close", on_click=lambda e: page.pop_dialog(), variant="outline"),
            ],
        )

    def set_notifications(self, notifications, unread_count: int) -> None:
        self.error.visible = False
        self.mark_all.disabled = unread_count == 0
        self.items.controls = [self._row(item) for item in notifications] or [
            styled_text("You're all caught up. No notifications.")
        ]

    def set_error(self, message: str) -> None:
        self.error.value = message
        self.error.visible = True

    def _row(self, item) -> ft.Container:
        return ft.Container(
            data=item.id,
            bgcolor=COLOR_SURFACE_ALT if item.is_read else ft.Colors.with_opacity(0.1, COLOR_ACCENT),
            border=ft.Border.all(1, COLOR_BORDER if item.is_read else COLOR_ACCENT),
            border_radius=RADIUS_SM,
            padding=SPACING["sm"],
            content=ft.Row(
                [
                    ft.Column(
                        [
                            styled_text("Read" if item.is_read else "Unread", style="caption"),
                            styled_text(item.message, style="body" if item.is_read else "body_emphasis"),
                            styled_text(item.created_at.strftime("%d %b %Y, %H:%M"), style="caption"),
                        ],
                        spacing=SPACING["xs"],
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DONE,
                        tooltip="Mark read",
                        disabled=item.is_read,
                        icon_color=COLOR_ACCENT,
                        on_click=lambda e: self._on_action("mark_read", item.id),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        tooltip="Dismiss notification",
                        icon_color=COLOR_TEXT_SECONDARY,
                        on_click=lambda e: self._on_action("dismiss", item.id),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        )

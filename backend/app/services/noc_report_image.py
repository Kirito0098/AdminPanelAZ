"""Weekly NOC report as a single PNG dashboard (Pillow)."""

from __future__ import annotations

import io
from colorsys import hls_to_rgb
from datetime import datetime
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.services.image_fonts import load_image_font, load_mono_font
from app.services.traffic_limit import human_bytes


def _hsl(h: float, s: float, l: float) -> str:
    r, g, b = hls_to_rgb(h / 360.0, l / 100.0, s / 100.0)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


class _Theme:
    WIDTH = 1080
    PAD = 28
    GAP = 12
    RADIUS = 12

    # Match frontend dark theme (index.css)
    BG = _hsl(222, 47, 7)
    CARD = _hsl(222, 47, 10)
    CARD_BORDER = _hsl(217, 33, 18)
    TEXT = _hsl(210, 20, 96)
    MUTED = _hsl(215, 16, 65)
    ACCENT = _hsl(187, 72, 45)
    ACCENT_DIM = _hsl(187, 55, 32)
    SUCCESS = _hsl(142, 71, 45)
    WARNING = _hsl(38, 92, 50)
    DANGER = _hsl(0, 62, 50)
    BAR_BG = _hsl(217, 33, 17)
    ROW_ALT = _hsl(222, 47, 8)


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return load_image_font(size, bold=bold)


def _format_resource_avg_peak(avg: float | None, peak: float | None, *, suffix: str = "%") -> str | None:
    if avg is None and peak is None:
        return None
    avg_label = "-" if avg is None else f"{avg:g}{suffix}"
    peak_label = "-" if peak is None else f"{peak:g}{suffix}"
    return f"{avg_label} / {peak_label}"


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "-"
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.strftime("%Y-%m-%d %H:%M")


def _text_w(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    if not text:
        return 0
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _text_h(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    if not text:
        return 0
    box = draw.textbbox((0, 0), text, font=font)
    return box[3] - box[1]


def _truncate(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> str:
    if _text_w(draw, text, font) <= max_w:
        return text
    ell = "..."
    trimmed = text
    while trimmed and _text_w(draw, trimmed + ell, font) > max_w:
        trimmed = trimmed[:-1]
    return (trimmed + ell) if trimmed else ell


def _rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    *,
    radius: int,
    fill: str,
    outline: str | None = None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def _parse_pct(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def _metric_bar_pct(avg: Any, peak: Any) -> float | None:
    try:
        peak_f = float(peak) if peak is not None else None
        avg_f = float(avg) if avg is not None else None
    except (TypeError, ValueError):
        return None
    if peak_f is None or peak_f <= 0:
        return avg_f
    return peak_f


class NocWeeklyImageRenderer:
    CARD_PAD = 14
    KPI_ROW_H = 94
    KPI_WIDE_H = 78

    def __init__(self, report_data: dict[str, Any]):
        self.data = report_data
        self.theme = _Theme()
        self.font_title = _load_font(24, bold=True)
        self.font_section = _load_font(15, bold=True)
        self.font_label = _load_font(11)
        self.font_value = _load_font(20, bold=True)
        self.font_value_sm = _load_font(16, bold=True)
        self.font_mono = load_mono_font(18)
        self.font_mono_sm = load_mono_font(15)
        self.font_small = _load_font(10)
        self.font_table = _load_font(11)
        self.font_table_head = _load_font(11, bold=True)
        self._layout_draw: ImageDraw.ImageDraw | None = None

    def render(self) -> bytes:
        height = self._estimate_height()
        img = Image.new("RGB", (self.theme.WIDTH, height), self.theme.BG)
        draw = ImageDraw.Draw(img)
        self._layout_draw = draw
        y = self.theme.PAD
        y = self._draw_header(draw, y)
        y = self._draw_kpi_grid(draw, y)
        y = self._draw_nodes(draw, y)
        y = self._draw_top_clients(draw, y)
        y = self._draw_footer(draw, y)
        self._layout_draw = None
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    def _content_w(self) -> int:
        return self.theme.WIDTH - 2 * self.theme.PAD

    def _estimate_height(self) -> int:
        summary = self.data.get("summary") or {}
        nodes = summary.get("nodes") or []
        top = self.data.get("top_clients") or []

        h = self.theme.PAD
        h += 76  # header
        h += 4 * (self.KPI_ROW_H + self.theme.GAP) + self.KPI_WIDE_H + self.theme.GAP
        if nodes:
            h += 28 + 32 + len(nodes) * 30 + self.theme.GAP
        h += 28 + max(1, len(top)) * 34 + self.theme.GAP
        h += 28 + 72 + self.theme.PAD
        return max(h, 760)

    def _fit_value_font(self, draw: ImageDraw.ImageDraw, value: str, max_w: int, *, mono: bool = True):
        for font in (
            self.font_mono if mono else self.font_value,
            self.font_mono_sm if mono else self.font_value_sm,
            self.font_small,
        ):
            if _text_w(draw, value, font) <= max_w:
                return font, value
        font = self.font_small
        return font, _truncate(draw, value, font, max_w)

    def _draw_header(self, draw: ImageDraw.ImageDraw, y: int) -> int:
        t = self.theme
        period = self.data.get("period") or {}
        start = _fmt_dt(period.get("start"))
        end = _fmt_dt(period.get("end"))
        header_h = 76

        _rounded_rect(
            draw,
            (t.PAD, y, t.WIDTH - t.PAD, y + header_h),
            radius=t.RADIUS,
            fill=t.CARD,
            outline=t.CARD_BORDER,
        )
        draw.text((t.PAD + 18, y + 16), "NOC Weekly Report", fill=t.ACCENT, font=self.font_title)
        period_text = f"{start}  -  {end}"
        draw.text((t.PAD + 18, y + 46), period_text, fill=t.MUTED, font=self.font_label)
        brand = "AdminPanelAZ"
        brand_w = _text_w(draw, brand, self.font_small)
        draw.text((t.WIDTH - t.PAD - brand_w - 16, y + 30), brand, fill=t.MUTED, font=self.font_small)
        return y + header_h + t.GAP

    def _draw_kpi_card(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        w: int,
        h: int,
        label: str,
        value: str,
        *,
        sub: str | None = None,
        bar_pct: float | None = None,
        bar_color: str | None = None,
        value_color: str | None = None,
        mono_value: bool = True,
    ) -> None:
        t = self.theme
        pad = self.CARD_PAD
        _rounded_rect(draw, (x, y, x + w, y + h), radius=10, fill=t.CARD, outline=t.CARD_BORDER)

        label_text = label.upper()
        draw.text((x + pad, y + pad), label_text, fill=t.MUTED, font=self.font_label)
        label_bottom = y + pad + 14

        max_val_w = w - 2 * pad
        value_font, value_text = self._fit_value_font(draw, value, max_val_w, mono=mono_value)
        value_y = label_bottom + 6
        draw.text((x + pad, value_y), value_text, fill=value_color or t.TEXT, font=value_font)
        value_bottom = value_y + _text_h(draw, value_text, value_font)

        bottom_limit = y + h - pad
        if bar_pct is not None:
            bar_h = 5
            bar_bottom = y + h - pad
            bar_top = bar_bottom - bar_h
            bottom_limit = bar_top - 8

        if sub:
            sub_text = _truncate(draw, sub, self.font_small, max_val_w)
            sub_h = _text_h(draw, sub_text, self.font_small)
            sub_y = bottom_limit - sub_h
            if sub_y >= value_bottom + 4:
                draw.text((x + pad, sub_y), sub_text, fill=t.MUTED, font=self.font_small)

        if bar_pct is not None:
            bar_h = 5
            bar_bottom = y + h - pad
            bar_top = bar_bottom - bar_h
            bar_x0 = x + pad
            bar_x1 = x + w - pad
            _rounded_rect(draw, (bar_x0, bar_top, bar_x1, bar_bottom), radius=3, fill=t.BAR_BG)
            fill_w = int((bar_x1 - bar_x0) * min(max(bar_pct, 0), 100) / 100)
            if fill_w > 0:
                _rounded_rect(
                    draw,
                    (bar_x0, bar_top, bar_x0 + fill_w, bar_bottom),
                    radius=3,
                    fill=bar_color or t.ACCENT,
                )

    def _draw_kpi_grid(self, draw: ImageDraw.ImageDraw, y: int) -> int:
        t = self.theme
        summary = self.data.get("summary") or {}
        resource = summary.get("resource_fleet") or {}
        traffic_limit = self.data.get("traffic_limit") or {}
        cw = self._content_w()
        col_w = (cw - t.GAP) // 2
        row_h = self.KPI_ROW_H

        delta_pct = _parse_pct(summary.get("traffic_delta_pct"))
        delta_color = t.SUCCESS if delta_pct is not None and delta_pct <= 0 else t.WARNING
        if delta_pct is not None and delta_pct > 0:
            delta_color = t.DANGER
        delta_text = str(summary.get("traffic_delta_pct") or "-")
        compare = (self.data.get("compare_label") or "").strip()
        if compare:
            delta_text = f"{delta_text} {compare}"

        cards: list[dict] = [
            {
                "label": "Узлы онлайн",
                "value": f"{summary.get('nodes_online', 0)}/{summary.get('nodes_total', 0)}",
                "sub": "активные / всего",
            },
            {
                "label": "Трафик за 7 дней",
                "value": human_bytes(summary.get("period_traffic_bytes")) or "0 B",
                "sub": f"накопительно: {human_bytes(summary.get('total_traffic_bytes')) or '0 B'}",
            },
            {
                "label": "OpenVPN сессии",
                "value": f"{summary.get('total_openvpn', 0)} / {summary.get('total_openvpn_peak', 0)}",
                "sub": "среднее / пик",
            },
            {
                "label": "WireGuard сессии",
                "value": f"{summary.get('total_wireguard', 0)} / {summary.get('total_wireguard_peak', 0)}",
                "sub": "среднее / пик",
            },
            {
                "label": "Изм. трафика",
                "value": delta_text,
                "sub": "к предыдущему периоду",
                "value_color": delta_color,
                "mono_value": False,
            },
            {
                "label": "CPU",
                "value": _format_resource_avg_peak(resource.get("cpu_avg"), resource.get("cpu_peak")) or "-",
                "bar_pct": _metric_bar_pct(resource.get("cpu_avg"), resource.get("cpu_peak")),
                "bar_color": t.DANGER if (resource.get("cpu_peak") or 0) >= 85 else t.ACCENT,
            },
            {
                "label": "RAM",
                "value": _format_resource_avg_peak(resource.get("memory_avg"), resource.get("memory_peak")) or "-",
                "bar_pct": _metric_bar_pct(resource.get("memory_avg"), resource.get("memory_peak")),
                "bar_color": t.WARNING if (resource.get("memory_peak") or 0) >= 85 else t.ACCENT,
            },
            {
                "label": "Лимит трафика",
                "value": str(traffic_limit.get("blocks_in_period", 0)),
                "sub": f"заблокировано сейчас: {traffic_limit.get('blocked_now', 0)}",
            },
        ]

        x0 = t.PAD
        row = 0
        col = 0
        for card in cards:
            cx = x0 + col * (col_w + t.GAP)
            cy = y + row * (row_h + t.GAP)
            self._draw_kpi_card(draw, cx, cy, col_w, row_h, **card)
            col += 1
            if col >= 2:
                col = 0
                row += 1

        disk_y = y + row * (row_h + t.GAP)
        disk_val = _format_resource_avg_peak(resource.get("disk_avg"), resource.get("disk_peak")) or "-"
        self._draw_kpi_card(
            draw,
            x0,
            disk_y,
            cw,
            self.KPI_WIDE_H,
            "Диск",
            disk_val,
            bar_pct=_metric_bar_pct(resource.get("disk_avg"), resource.get("disk_peak")),
            bar_color=t.ACCENT_DIM,
        )
        return disk_y + self.KPI_WIDE_H + t.GAP

    def _draw_section_title(self, draw: ImageDraw.ImageDraw, y: int, title: str) -> int:
        draw.text((self.theme.PAD, y), title, fill=self.theme.TEXT, font=self.font_section)
        return y + 28

    def _draw_nodes(self, draw: ImageDraw.ImageDraw, y: int) -> int:
        t = self.theme
        summary = self.data.get("summary") or {}
        nodes = summary.get("nodes") or []
        if not nodes:
            return y

        y = self._draw_section_title(draw, y, "Узлы")
        x0 = t.PAD
        cw = self._content_w()
        cols = ["Узел", "Статус", "OVPN", "WG", "CPU", "RAM", "Диск", "7д", "Всего"]
        widths = [0.17, 0.07, 0.08, 0.08, 0.13, 0.13, 0.13, 0.09, 0.12]
        col_px = [int(cw * w) for w in widths]
        col_px[-1] = cw - sum(col_px[:-1])

        header_h = 32
        _rounded_rect(draw, (x0, y, x0 + cw, y + header_h), radius=8, fill=t.BAR_BG, outline=t.CARD_BORDER)
        cx = x0 + 10
        for idx, label in enumerate(cols):
            draw.text((cx, y + 9), label.upper(), fill=t.MUTED, font=self.font_table_head)
            cx += col_px[idx]

        y += header_h + 2
        for row_idx, node in enumerate(nodes):
            row_h = 30
            bg = t.ROW_ALT if row_idx % 2 else t.CARD
            _rounded_rect(draw, (x0, y, x0 + cw, y + row_h), radius=8, fill=bg, outline=t.CARD_BORDER)
            status = str(node.get("status") or "")
            status_color = t.SUCCESS if status.lower() == "online" else t.DANGER
            values = [
                str(node.get("name") or ""),
                status,
                f"{node.get('openvpn', 0)}/{node.get('openvpn_peak', 0)}",
                f"{node.get('wireguard', 0)}/{node.get('wireguard_peak', 0)}",
                _format_resource_avg_peak(node.get("cpu_percent"), node.get("cpu_peak")) or "-",
                _format_resource_avg_peak(node.get("memory_percent"), node.get("memory_peak")) or "-",
                _format_resource_avg_peak(node.get("disk_percent"), node.get("disk_peak")) or "-",
                human_bytes(node.get("period_traffic_bytes")) or "0 B",
                human_bytes(node.get("traffic_bytes")) or "0 B",
            ]
            cx = x0 + 10
            for idx, val in enumerate(values):
                color = status_color if idx == 1 else t.TEXT
                font = self.font_mono_sm if idx >= 2 else self.font_table
                text = _truncate(draw, val, font, col_px[idx] - 8)
                draw.text((cx, y + 8), text, fill=color, font=font)
                cx += col_px[idx]
            y += row_h + 3

        return y + t.GAP

    def _draw_top_clients(self, draw: ImageDraw.ImageDraw, y: int) -> int:
        t = self.theme
        top_clients = self.data.get("top_clients") or []
        y = self._draw_section_title(draw, y, "Топ клиентов по трафику")

        x0 = t.PAD
        cw = self._content_w()
        if not top_clients:
            draw.text((x0, y), "Нет данных за период", fill=t.MUTED, font=self.font_label)
            return y + 28 + t.GAP

        max_bytes = max(int(c.get("traffic_bytes") or 0) for c in top_clients) or 1
        rank_w = 24
        value_w = 96
        name_w = int(cw * 0.28)
        bar_x0 = x0 + rank_w + name_w + 10
        bar_x1 = x0 + cw - value_w - 12

        for idx, client in enumerate(top_clients):
            row_h = 32
            name = str(client.get("common_name") or "-")
            traffic = human_bytes(client.get("traffic_bytes")) or "0 B"
            bytes_val = int(client.get("traffic_bytes") or 0)
            pct = bytes_val / max_bytes

            bg = t.ROW_ALT if idx % 2 else t.CARD
            _rounded_rect(draw, (x0, y, x0 + cw, y + row_h), radius=8, fill=bg, outline=t.CARD_BORDER)

            draw.text((x0 + 10, y + 9), f"{idx + 1}.", fill=t.MUTED, font=self.font_small)
            draw.text(
                (x0 + rank_w + 4, y + 8),
                _truncate(draw, name, self.font_table, name_w - 8),
                fill=t.TEXT,
                font=self.font_table,
            )

            bar_top = y + 13
            bar_bottom = y + 20
            _rounded_rect(draw, (bar_x0, bar_top, bar_x1, bar_bottom), radius=3, fill=t.BAR_BG)
            bar_span = max(0, bar_x1 - bar_x0)
            fill_w = max(3, int(bar_span * pct))
            bar_color = t.ACCENT if idx < 3 else t.ACCENT_DIM
            _rounded_rect(draw, (bar_x0, bar_top, bar_x0 + fill_w, bar_bottom), radius=3, fill=bar_color)

            traffic_font, traffic_text = self._fit_value_font(
                draw, traffic, value_w - 8, mono=True,
            )
            draw.text(
                (x0 + cw - value_w, y + 8),
                traffic_text,
                fill=t.MUTED,
                font=traffic_font,
            )
            y += row_h + 4

        return y + t.GAP

    def _draw_footer(self, draw: ImageDraw.ImageDraw, y: int) -> int:
        t = self.theme
        incidents = self.data.get("incidents") or []
        cidr = self.data.get("cidr_failures") or []
        x0 = t.PAD
        cw = self._content_w()
        half = (cw - t.GAP) // 2
        panel_h = 72

        def _panel(px: int, title: str, lines: list[tuple[str, str]]) -> None:
            _rounded_rect(
                draw,
                (px, y, px + half, y + panel_h),
                radius=10,
                fill=t.CARD,
                outline=t.CARD_BORDER,
            )
            draw.text((px + 14, y + 12), title, fill=t.TEXT, font=self.font_label)
            ly = y + 32
            if not lines:
                draw.text((px + 14, ly), "Нет событий за период", fill=t.SUCCESS, font=self.font_small)
            else:
                for label, val in lines[:3]:
                    draw.text(
                        (px + 14, ly),
                        _truncate(draw, f"- {label}: {val}", self.font_small, half - 28),
                        fill=t.MUTED,
                        font=self.font_small,
                    )
                    ly += 18

        incident_lines = [
            (str(i.get("name") or "-"), str(i.get("condition") or "-"))
            for i in incidents
        ]
        cidr_lines = [
            (
                _fmt_dt(i.get("started_at")),
                f"{i.get('status', '-')} / err {i.get('providers_failed', 0)}",
            )
            for i in cidr
        ]

        _panel(x0, "Инциденты (alert rules)", incident_lines)
        _panel(x0 + half + t.GAP, "Ошибки CIDR", cidr_lines)
        return y + panel_h + t.PAD


def generate_weekly_image(report_data: dict[str, Any]) -> bytes:
    """Render weekly NOC report data to PNG bytes."""
    return NocWeeklyImageRenderer(report_data).render()

"""Weekly NOC PDF report generation (reportlab)."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.noc_report import _format_resource_avg_peak
from app.services.traffic_limit import human_bytes


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.strftime("%Y-%m-%d %H:%M")


def _section_title(text: str, styles) -> Paragraph:
    return Paragraph(text, styles["Heading2"])


def _table(data: list[list[str]], *, col_widths: list[float] | None = None) -> Table:
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1a1a1a")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
            ]
        )
    )
    return table


def generate_weekly_pdf(report_data: dict[str, Any]) -> bytes:
    """Render weekly NOC report data to PDF bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="AdminPanelAZ NOC Weekly Report",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Meta", parent=styles["Normal"], fontSize=9, textColor=colors.grey))
    story: list = []

    period = report_data.get("period") or {}
    period_start = period.get("start")
    period_end = period.get("end")
    title = "NOC Weekly Report"
    if period_start and period_end:
        title = f"NOC Weekly Report ({_fmt_dt(period_start)} — {_fmt_dt(period_end)})"
    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 6))

    summary = report_data.get("summary") or {}
    resource_fleet = summary.get("resource_fleet") or {}
    traffic_limit = report_data.get("traffic_limit") or {}
    story.append(_section_title("Overview", styles))
    overview_rows = [
        ["Metric", "Value"],
        ["Nodes online", f"{summary.get('nodes_online', 0)}/{summary.get('nodes_total', 0)}"],
        ["OpenVPN sessions (avg)", str(summary.get("total_openvpn", 0))],
        ["WireGuard sessions (avg)", str(summary.get("total_wireguard", 0))],
        ["OpenVPN peak concurrent", str(summary.get("total_openvpn_peak", 0))],
        ["WireGuard peak concurrent", str(summary.get("total_wireguard_peak", 0))],
        ["Traffic (7d)", human_bytes(summary.get("period_traffic_bytes")) or "0 B"],
    ]
    if summary.get("traffic_delta_pct"):
        overview_rows.append(["Traffic delta", f"{summary['traffic_delta_pct']} {report_data.get('compare_label', '')}"])
    overview_rows.extend([
        ["Traffic (cumulative)", human_bytes(summary.get("total_traffic_bytes")) or "0 B"],
        ["CPU avg / peak", _format_resource_avg_peak(resource_fleet.get("cpu_avg"), resource_fleet.get("cpu_peak")) or "—"],
        ["RAM avg / peak", _format_resource_avg_peak(resource_fleet.get("memory_avg"), resource_fleet.get("memory_peak")) or "—"],
        ["Disk avg / peak", _format_resource_avg_peak(resource_fleet.get("disk_avg"), resource_fleet.get("disk_peak")) or "—"],
        ["Traffic limit blocked now", str(traffic_limit.get("blocked_now", 0))],
        ["Traffic limit blocks (7d)", str(traffic_limit.get("blocks_in_period", 0))],
    ])
    story.append(_table(overview_rows, col_widths=[70 * mm, 90 * mm]))
    story.append(Spacer(1, 10))

    nodes = summary.get("nodes") or []
    if nodes:
        story.append(_section_title("Nodes", styles))
        node_rows = [["Node", "Status", "OVPN", "WG", "CPU", "RAM", "Disk", "Traffic (7d)", "Traffic (total)"]]
        for node in nodes:
            node_rows.append(
                [
                    str(node.get("name") or ""),
                    str(node.get("status") or ""),
                    f"{node.get('openvpn', 0)} / {node.get('openvpn_peak', 0)}",
                    f"{node.get('wireguard', 0)} / {node.get('wireguard_peak', 0)}",
                    _format_resource_avg_peak(node.get("cpu_percent"), node.get("cpu_peak")) or "—",
                    _format_resource_avg_peak(node.get("memory_percent"), node.get("memory_peak")) or "—",
                    _format_resource_avg_peak(node.get("disk_percent"), node.get("disk_peak")) or "—",
                    human_bytes(node.get("period_traffic_bytes")) or "0 B",
                    human_bytes(node.get("traffic_bytes")) or "0 B",
                ]
            )
        story.append(_table(node_rows))
        story.append(Spacer(1, 10))

    top_clients = report_data.get("top_clients") or []
    story.append(_section_title("Top clients (traffic)", styles))
    if top_clients:
        client_rows = [["#", "Client", "Traffic"]]
        for idx, client in enumerate(top_clients, start=1):
            client_rows.append(
                [
                    str(idx),
                    str(client.get("common_name") or ""),
                    human_bytes(client.get("traffic_bytes")) or "0 B",
                ]
            )
        story.append(_table(client_rows, col_widths=[12 * mm, 90 * mm, 50 * mm]))
    else:
        story.append(Paragraph("No traffic samples in the reporting window.", styles["Meta"]))
    story.append(Spacer(1, 10))

    incidents = report_data.get("incidents") or []
    story.append(_section_title("Incidents (alert rules)", styles))
    if incidents:
        incident_rows = [["Rule", "Condition", "Last triggered"]]
        for item in incidents:
            incident_rows.append(
                [
                    str(item.get("name") or ""),
                    str(item.get("condition") or ""),
                    _fmt_dt(item.get("last_triggered_at")),
                ]
            )
        story.append(_table(incident_rows))
    else:
        story.append(Paragraph("No alert rule triggers in the reporting window.", styles["Meta"]))
    story.append(Spacer(1, 10))

    cidr_failures = report_data.get("cidr_failures") or []
    story.append(_section_title("CIDR pipeline failures", styles))
    if cidr_failures:
        cidr_rows = [["Started", "Status", "Failed providers", "Error"]]
        for item in cidr_failures:
            cidr_rows.append(
                [
                    _fmt_dt(item.get("started_at")),
                    str(item.get("status") or ""),
                    str(item.get("providers_failed", 0)),
                    str(item.get("error") or "")[:120],
                ]
            )
        story.append(_table(cidr_rows))
    else:
        story.append(Paragraph("No CIDR refresh failures in the reporting window.", styles["Meta"]))

    doc.build(story)
    return buffer.getvalue()

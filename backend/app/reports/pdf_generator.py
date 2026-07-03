"""PDF audit report generation using reportlab.

Kept separate from main.py since building the report layout is a decent
chunk of formatting code that has nothing to do with routing/auth.
"""
import io
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
)

BRAND_INDIGO = colors.HexColor("#4F46E5")
BRAND_SLATE = colors.HexColor("#334155")
BRAND_SLATE_LIGHT = colors.HexColor("#64748B")
ROW_ALT = colors.HexColor("#F1F5F9")
SUCCESS_GREEN = colors.HexColor("#059669")
WARN_AMBER = colors.HexColor("#D97706")
ERROR_RED = colors.HexColor("#DC2626")


def _status_color(status_code: Optional[int]) -> colors.Color:
    if status_code is None:
        return BRAND_SLATE_LIGHT
    if 200 <= status_code < 300:
        return SUCCESS_GREEN
    if 300 <= status_code < 400:
        return colors.HexColor("#2563EB")
    if 400 <= status_code < 500:
        return WARN_AMBER
    return ERROR_RED


def generate_crawl_pdf(job, domain, urls: list, category_reports: list) -> bytes:
    """Build a PDF audit report for a completed crawl job.

    job/domain are Beanie documents; urls is a list of URL documents already
    scoped to this job's run; category_reports is a list of Report documents
    (one per SEO issue category) generated at the end of the crawl.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=20 * mm, bottomMargin=18 * mm,
        leftMargin=18 * mm, rightMargin=18 * mm,
        title=f"Audit Report - {domain.domain}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], textColor=BRAND_INDIGO, fontSize=22, spaceAfter=2)
    subtitle_style = ParagraphStyle("ReportSubtitle", parent=styles["Normal"], textColor=BRAND_SLATE_LIGHT, fontSize=10)
    section_style = ParagraphStyle("Section", parent=styles["Heading2"], textColor=BRAND_SLATE, fontSize=13, spaceBefore=14, spaceAfter=8)
    cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8, leading=10)
    cell_style_white = ParagraphStyle("CellWhite", parent=cell_style, textColor=colors.white)

    story = []

    # --- Header ---
    story.append(Paragraph("Popz AI Crawl", subtitle_style))
    story.append(Paragraph(f"SEO Audit Report &mdash; {domain.domain}", title_style))
    story.append(Paragraph(f"Audit URL: {domain.original_url}", subtitle_style))
    story.append(Paragraph(f"Generated {datetime.utcnow().strftime('%B %d, %Y at %H:%M UTC')}", subtitle_style))
    story.append(Spacer(1, 10 * mm))

    # --- Summary ---
    duration = "-"
    if job.started_at and job.completed_at:
        duration = f"{round((job.completed_at - job.started_at).total_seconds())}s"

    summary_rows = [
        ["Status", job.status.capitalize(), "Total URLs Checked", str(job.total_urls_checked)],
        ["Duration", duration, "Sitemaps Found", str(job.total_sitemaps_found)],
        ["Avg Response Time", f"{job.avg_response_time_ms or 0} ms", "Speed", f"{job.crawl_speed_urls_per_sec or 0} req/s"],
    ]
    summary_table = Table(summary_rows, colWidths=[42 * mm, 40 * mm, 42 * mm, 40 * mm])
    summary_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), BRAND_SLATE_LIGHT),
        ("TEXTCOLOR", (2, 0), (2, -1), BRAND_SLATE_LIGHT),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#E2E8F0")),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 6 * mm))

    # --- Response Status Distribution ---
    story.append(Paragraph("Response Status Distribution", section_style))
    dist_rows = [["2xx Success", "3xx Redirects", "4xx Client Errors", "5xx / Failed"],
                 [str(job.urls_2xx), str(job.urls_3xx), str(job.urls_4xx),
                  str(job.urls_5xx + job.urls_timeout + job.urls_dns_error)]]
    dist_table = Table(dist_rows, colWidths=[41 * mm] * 4)
    dist_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, 1), 16),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (-1, 0), BRAND_SLATE_LIGHT),
        ("TEXTCOLOR", (0, 1), (0, 1), SUCCESS_GREEN),
        ("TEXTCOLOR", (1, 1), (1, 1), colors.HexColor("#2563EB")),
        ("TEXTCOLOR", (2, 1), (2, 1), WARN_AMBER),
        ("TEXTCOLOR", (3, 1), (3, 1), ERROR_RED),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
    ]))
    story.append(dist_table)
    story.append(Spacer(1, 6 * mm))

    # --- SEO Issues by Category ---
    if category_reports:
        story.append(Paragraph("SEO Issues by Category", section_style))
        issue_rows = [["Category", "Issues Found"]]
        for r in sorted(category_reports, key=lambda r: -r.issues_count):
            issue_rows.append([r.title.replace(" Issues Report", ""), str(r.issues_count)])
        issue_table = Table(issue_rows, colWidths=[130 * mm, 34 * mm])
        issue_table.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_SLATE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ]))
        story.append(issue_table)

    # --- Audited URLs ---
    story.append(PageBreak())
    story.append(Paragraph(f"Audited URLs ({len(urls)})", section_style))

    url_rows = [[
        Paragraph("<b>URL</b>", cell_style_white),
        Paragraph("<b>Status</b>", cell_style_white),
        Paragraph("<b>Time</b>", cell_style_white),
        Paragraph("<b>Type</b>", cell_style_white),
    ]]
    for u in urls:
        status_text = str(u.status_code) if u.status_code else (u.crawl_status or "-")
        status_para = Paragraph(f'<font color="{_status_color(u.status_code).hexval()}"><b>{status_text}</b></font>', cell_style)
        url_rows.append([
            Paragraph(u.url, cell_style),
            status_para,
            Paragraph(f"{u.response_time_ms}ms" if u.response_time_ms else "-", cell_style),
            Paragraph((u.content_type or "-").split(";")[0], cell_style),
        ])

    url_table = Table(url_rows, colWidths=[100 * mm, 22 * mm, 20 * mm, 22 * mm], repeatRows=1)
    url_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_SLATE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
    ]))
    story.append(url_table)

    doc.build(story)
    return buffer.getvalue()

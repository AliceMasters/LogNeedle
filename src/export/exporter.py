"""
Report exporter for LogNeedle.

Converts a Report dataclass into Markdown, HTML, or plain text strings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..analysis.analyzer import Report, ReportSection, ReportBullet, Citation
from ..utils.redact import redact_secrets


class ReportExporter:
    """Export a Report to various text formats."""

    def __init__(self, redact: bool = False):
        self.redact = redact

    def _r(self, text: str) -> str:
        """Optionally redact."""
        return redact_secrets(text) if self.redact else text

    # ── Markdown ────────────────────────────────────────────────────

    def to_markdown(self, report: Report) -> str:
        lines: list[str] = []
        lines.append(f"# {report.window_label} leading to end of logs (working backwards)")
        lines.append("")
        lines.append(
            f"**End of logs:** {report.end_time}  \n"
            f"**Window start:** {report.start_time}  \n"
            f"**Total events:** {report.total_events}"
        )
        lines.append("")

        for section in report.sections:
            lines.append(f"## {section.heading}")
            lines.append("")
            for b in section.bullets:
                badges = " ".join(f"`{bg}`" for bg in b.badges) if b.badges else ""
                bullet_line = f"- **{b.timestamp_range}** — {self._r(b.summary)}"
                if badges:
                    bullet_line += f"  {badges}"
                if b.repeat_count:
                    bullet_line += f"  *(repeated {b.repeat_count:,} times)*"
                lines.append(bullet_line)
                for c in b.citations:
                    lines.append(f"  - _{c.format_text()}_")
            lines.append("")
        return "\n".join(lines)

    # ── HTML ────────────────────────────────────────────────────────

    def to_html(self, report: Report) -> str:
        parts: list[str] = []
        parts.append("<!DOCTYPE html><html><head><meta charset='utf-8'>")
        parts.append("<style>")
        parts.append(self._html_css())
        parts.append("</style></head><body>")
        parts.append(f"<h1>{report.window_label} leading to end of logs (working backwards)</h1>")
        parts.append(
            f"<p class='meta'>"
            f"End of logs: <strong>{report.end_time}</strong> · "
            f"Window start: <strong>{report.start_time}</strong> · "
            f"Total events: <strong>{report.total_events}</strong></p>"
        )

        for section in report.sections:
            parts.append(f"<h2>{section.heading}</h2><ul>")
            for b in section.bullets:
                badges = " ".join(
                    f"<code class='badge'>{bg}</code>" for bg in b.badges
                )
                repeat = (
                    f" <em>(repeated {b.repeat_count:,} times)</em>"
                    if b.repeat_count
                    else ""
                )
                parts.append(
                    f"<li>"
                    f"<strong>{b.timestamp_range}</strong> — "
                    f"<span class='msg'>{self._r(_html_esc(b.summary))}</span> "
                    f"{badges}{repeat}"
                )
                if b.citations:
                    parts.append("<ul class='citations'>")
                    for c in b.citations:
                        parts.append(f"<li class='cite'>{_html_esc(c.format_text())}</li>")
                    parts.append("</ul>")
                parts.append("</li>")
            parts.append("</ul>")
        parts.append("</body></html>")
        return "\n".join(parts)

    @staticmethod
    def _html_css() -> str:
        return """
            body { font-family: 'Segoe UI', system-ui, sans-serif;
                   background: #1e1e2e; color: #cdd6f4; padding: 2em; }
            h1 { color: #89b4fa; border-bottom: 1px solid #45475a; padding-bottom: .3em; }
            h2 { color: #f5c2e7; margin-top: 1.5em; }
            .meta { color: #a6adc8; }
            .badge { background: #313244; color: #fab387; padding: 2px 6px;
                     border-radius: 4px; font-family: monospace; font-size: .85em; }
            .msg { color: #cdd6f4; }
            .citations { list-style: none; padding-left: 1.2em; }
            .cite { color: #94e2d5; font-style: italic; font-size: .9em; }
            ul { list-style-type: '▸ '; }
            li { margin-bottom: .6em; line-height: 1.5; }
        """

    # ── Plain text ──────────────────────────────────────────────────

    def to_text(self, report: Report) -> str:
        lines: list[str] = []
        lines.append(
            f"{report.window_label} LEADING TO END OF LOGS (WORKING BACKWARDS)"
        )
        lines.append("=" * 70)
        lines.append(
            f"End of logs: {report.end_time}\n"
            f"Window start: {report.start_time}\n"
            f"Total events: {report.total_events}"
        )
        lines.append("")

        for section in report.sections:
            lines.append(f"--- {section.heading} ---")
            for b in section.bullets:
                badges = " ".join(b.badges) if b.badges else ""
                line = f"  * [{b.timestamp_range}] {self._r(b.summary)}"
                if badges:
                    line += f"  {badges}"
                if b.repeat_count:
                    line += f"  (repeated {b.repeat_count:,} times)"
                lines.append(line)
                for c in b.citations:
                    lines.append(f"      {c.format_text()}")
            lines.append("")
        return "\n".join(lines)

    # ── file helpers ────────────────────────────────────────────────

    def save(self, report: Report, path: str | Path, fmt: str = "md") -> None:
        p = Path(path)
        if fmt == "md":
            p.write_text(self.to_markdown(report), encoding="utf-8")
        elif fmt == "html":
            p.write_text(self.to_html(report), encoding="utf-8")
        else:
            p.write_text(self.to_text(report), encoding="utf-8")


def _html_esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

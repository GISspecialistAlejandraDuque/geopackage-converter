"""
HTML report generator for `ConversionResult`.

Loads `resources/report_template.html` (sibling of the plugin root),
performs simple `{{TOKEN}}` substitution (no Jinja, no extra deps),
and writes the file to disk. All dynamic content is HTML-escaped.
"""

from __future__ import annotations

import datetime as _dt
import html
from pathlib import Path
from typing import Optional

from .converter import ConversionResult

_RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"
_TEMPLATE_PATH = _RESOURCES_DIR / "report_template.html"


def _get_locale_template() -> Path:
    """Return the report template matching the resolved locale.

    Italian uses the base template; English and Spanish use their own;
    any other locale falls back to the English template (see
    ``_get_locale_code``), never to Italian.
    """
    locale = _get_locale_code()
    if locale == "it":
        return _TEMPLATE_PATH
    localized = _RESOURCES_DIR / f"report_template_{locale}.html"
    return localized if localized.is_file() else _TEMPLATE_PATH


def _format_duration(seconds: float) -> str:
    """Render a duration as 'HhMmSs' / 'MmSs' / 'Xs', plus milliseconds when short."""
    if seconds < 1.0:
        return f"{int(seconds * 1000)} ms"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


_I18N = {
    "it": {
        "no_files": "Nessun file generato.",
        "no_errors": "Nessun errore.",
        "source": "Sorgente",
        "message": "Messaggio",
        "no_warnings": "Nessun avviso.",
        "title": "Report di conversione GeoPackage Converter",
        "vectors": "vettoriali",
        "rasters": "raster",
    },
    "es": {
        "no_files": "No se generaron archivos.",
        "no_errors": "Sin errores.",
        "source": "Fuente",
        "message": "Mensaje",
        "no_warnings": "Sin avisos.",
        "title": "Reporte de conversión GeoPackage Converter",
        "vectors": "vectoriales",
        "rasters": "ráster",
    },
    "en": {
        "no_files": "No files generated.",
        "no_errors": "No errors.",
        "source": "Source",
        "message": "Message",
        "no_warnings": "No warnings.",
        "title": "GeoPackage Converter Conversion Report",
        "vectors": "vector",
        "rasters": "raster",
    },
}


_SUPPORTED_LOCALES = ("it", "en", "es")


def _get_locale_code() -> str:
    """Resolve the report language to one of it/en/es.

    Mirrors ``plugin._install_translator``: Italian is the source
    language; English and Spanish have their own translations; any other
    locale (or an undetectable one) falls back to English.
    """
    try:
        from qgis.PyQt.QtCore import QLocale, QSettings
        override = QSettings().value("locale/userLocale") or QLocale().name()
        locale = (override or "")[:2].lower()
    except Exception:
        locale = ""
    return locale if locale in _SUPPORTED_LOCALES else "en"


def _t(key: str) -> str:
    locale = _get_locale_code()
    return _I18N.get(locale, _I18N["en"]).get(key, _I18N["en"][key])


def _render_output_files(result: ConversionResult) -> str:
    if not result.output_files:
        return f'<p class="empty">{_t("no_files")}</p>'
    rows = "".join(
        f"<li><code>{html.escape(str(p))}</code></li>" for p in result.output_files
    )
    return f"<ul>{rows}</ul>"


def _render_errors_table(result: ConversionResult) -> str:
    if not result.errors:
        return f'<p class="empty">{_t("no_errors")}</p>'
    rows = []
    for err in result.errors:
        source = html.escape(str(err.get("source", "")))
        message = html.escape(str(err.get("message", "")))
        rows.append(
            f"<tr class='row-error'><td>{source}</td><td>{message}</td></tr>"
        )
    return (
        f"<table><thead><tr><th>{_t('source')}</th><th>{_t('message')}</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _render_detail_breakdown(result: ConversionResult) -> str:
    """Render a one-line vector/raster breakdown when both types are present."""
    v = result.vector_success_count
    r = result.raster_success_count
    if v == 0 and r == 0:
        return ""
    parts = []
    if v:
        parts.append(f"{v} {_t('vectors')}")
    if r:
        parts.append(f"{r} {_t('rasters')}")
    if len(parts) < 2:
        return ""  # no breakdown needed when only one type
    return f'<p style="color:#486581; margin-top:-0.5em;">{" + ".join(parts)}</p>'


def _render_warnings_list(result: ConversionResult) -> str:
    if not result.warnings:
        return f'<p class="empty">{_t("no_warnings")}</p>'
    items = "".join(f"<li>{html.escape(str(w))}</li>" for w in result.warnings)
    return f"<ul>{items}</ul>"


def generate_html_report(
    result: ConversionResult,
    output_path,
    title: Optional[str] = None,
    template_path: Optional[Path] = None,
) -> Path:
    """
    Render `result` into an HTML file at `output_path`.

    Args:
        result: a `ConversionResult` instance.
        output_path: destination `.html` path (str or Path). Parent
            directories are created if missing.
        title: optional report title. Defaults to "Report di conversione GeoPackage Converter".
        template_path: override the bundled template (mainly for tests).

    Returns:
        The absolute `Path` of the written file.
    """
    output_path = Path(output_path)
    template_file = Path(template_path) if template_path else _get_locale_template()
    template = template_file.read_text(encoding="utf-8")

    final_title = title or _t("title")
    timestamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = result.success_count + result.error_count
    if result.dry_run:
        final_title += " (dry-run)"

    substitutions = {
        "{{TITLE}}": html.escape(final_title),
        "{{TIMESTAMP}}": html.escape(timestamp),
        "{{DURATION}}": html.escape(_format_duration(result.duration_seconds)),
        "{{TOTAL}}": str(total),
        "{{SUCCESS}}": str(result.success_count),
        "{{ERRORS}}": str(result.error_count),
        "{{WARNINGS}}": str(len(result.warnings)),
        "{{OUTPUT_FILES}}": _render_output_files(result),
        "{{ERRORS_TABLE}}": _render_errors_table(result),
        "{{WARNINGS_LIST}}": _render_warnings_list(result),
        "{{DETAIL_BREAKDOWN}}": _render_detail_breakdown(result),
    }
    rendered = template
    for token, value in substitutions.items():
        rendered = rendered.replace(token, value)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    return output_path.resolve()


__all__ = ["generate_html_report"]

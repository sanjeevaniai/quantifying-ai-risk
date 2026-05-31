"""
report_generator.py

Generates a one-page AI Risk Assessment PDF report from the outputs of the
Monte Carlo pipeline built in Notebook 3.

The report is the artifact the methodology produces — the document a learner
walks away with, the kind of deliverable a CFO, a board, or a regulator would
accept as evidence.

Usage from Notebook 3:

    from utils.report_generator import generate_report

    results = {
        "expected_loss": expected_loss,
        "median_loss": median_loss,
        "p95": p95,
        "p99": p99,
        "tail_ce_95": tail_ce_95,
        "tail_ce_99": tail_ce_99,
        "total_losses": total_losses,
        "per_pillar_losses": per_pillar_losses,
        "tail_mask": tail_mask,
        "pillar_order": PILLAR_ORDER,
        "pillar_posteriors": PILLAR_POSTERIORS,
        "n_simulations": N_SIMULATIONS,
        "model_id": "credit_risk_v3.2",
        "reporting_period": "April 2026",
    }

    path = generate_report(results)
    print(f"Report saved to: {path}")
"""

from __future__ import annotations

import io
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import matplotlib
matplotlib.use("Agg")  # non-interactive backend, safe in any environment
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ---------------------------------------------------------------------------
# Brand palette
# Soft white background, clean black text, teal and orange accents.
# Restrained — federal-research-note aesthetic, not marketing.
# ---------------------------------------------------------------------------

BG_SOFT_WHITE = HexColor("#FAFAF7")
INK_BLACK = HexColor("#0F0F0F")
INK_GREY = HexColor("#4A4A4A")
INK_LIGHT_GREY = HexColor("#8A8A8A")
RULE_GREY = HexColor("#D6D6D2")

ACCENT_TEAL = HexColor("#18D6D6")
ACCENT_TEAL_DEEP = HexColor("#022424")
ACCENT_ORANGE = HexColor("#CC6B21")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _money(value: float) -> str:
    """Format a dollar amount for display."""
    if value >= 1_000_000:
        return f"${value/1_000_000:,.2f}M"
    elif value >= 1_000:
        return f"${value/1_000:,.0f}K"
    else:
        return f"${value:,.0f}"


def _money_precise(value: float) -> str:
    """Format a dollar amount with full precision."""
    return f"${value:,.0f}"


def _make_histogram_image(total_losses: np.ndarray, p95: float, p99: float,
                          expected_loss: float) -> str:
    """Render the Monte Carlo loss distribution to a PNG, return the file path."""
    # Filter to nonzero for log scale visualization
    nonzero = total_losses[total_losses > 0]
    zero_count = (total_losses == 0).sum()
    n_total = len(total_losses)

    fig, ax = plt.subplots(figsize=(6.5, 2.2), dpi=200)
    fig.patch.set_facecolor("#FAFAF7")
    ax.set_facecolor("#FAFAF7")

    if len(nonzero) > 0:
        # Log-scale bins capture the tail behavior properly
        bins = np.logspace(np.log10(max(1, nonzero.min())),
                           np.log10(nonzero.max()), 40)
        ax.hist(nonzero, bins=bins, color="#18D6D6", alpha=0.85,
                edgecolor="#022424", linewidth=0.4)
        ax.set_xscale("log")

        # Reference lines
        ax.axvline(expected_loss, color="#CC6B21", linestyle="-",
                   linewidth=1.2, label=f"Expected: {_money(expected_loss)}")
        ax.axvline(p95, color="#0F0F0F", linestyle="--",
                   linewidth=0.9, alpha=0.7, label=f"95% VaR: {_money(p95)}")
        ax.axvline(p99, color="#0F0F0F", linestyle=":",
                   linewidth=0.9, alpha=0.7, label=f"99% VaR: {_money(p99)}")

        ax.legend(loc="upper right", fontsize=7, frameon=False)

    ax.set_xlabel("Monthly loss (log scale)", fontsize=8, color="#4A4A4A")
    ax.set_ylabel("Simulated months", fontsize=8, color="#4A4A4A")
    ax.tick_params(axis="both", labelsize=7, colors="#4A4A4A")
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color("#D6D6D2")
    ax.grid(axis="y", color="#D6D6D2", linewidth=0.3, alpha=0.6)

    # Annotation: zero-incident share
    zero_share = zero_count / n_total * 100
    ax.text(0.02, 0.95, f"{zero_share:.1f}% of months: no incident",
            transform=ax.transAxes, fontsize=7, color="#4A4A4A",
            verticalalignment="top")

    plt.tight_layout()

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    plt.savefig(tmp.name, dpi=200, bbox_inches="tight",
                facecolor="#FAFAF7")
    plt.close(fig)
    return tmp.name


def _compute_pillar_status(posterior_mean: float) -> tuple[str, Color]:
    """Map a pillar posterior mean to a status label and color."""
    if posterior_mean >= 0.75:
        return "Strong", ACCENT_TEAL
    elif posterior_mean >= 0.55:
        return "Adequate", INK_GREY
    elif posterior_mean >= 0.40:
        return "Watch", ACCENT_ORANGE
    else:
        return "Critical", ACCENT_ORANGE


def _compute_tail_contributions(per_pillar_losses: np.ndarray,
                                tail_mask: np.ndarray,
                                pillar_order: list[str]) -> list[tuple[str, float]]:
    """Top 3 pillars by contribution to worst 5% of months."""
    tail_totals = per_pillar_losses[tail_mask].mean(axis=0)
    total = tail_totals.sum()
    contributions = []
    for i, pillar in enumerate(pillar_order):
        share = (tail_totals[i] / total * 100) if total > 0 else 0
        contributions.append((pillar, share))
    contributions.sort(key=lambda x: x[1], reverse=True)
    return contributions[:3]


# ---------------------------------------------------------------------------
# Main PDF builder
# ---------------------------------------------------------------------------

def generate_report(results: dict[str, Any], output_dir: str | Path = ".",
                    filename: str | None = None) -> str:
    """
    Generate a one-page AI Risk Assessment PDF report.

    Args:
        results: Dictionary containing pipeline outputs. Required keys:
            expected_loss, median_loss, p95, p99, tail_ce_95, tail_ce_99,
            total_losses, per_pillar_losses, tail_mask, pillar_order,
            pillar_posteriors, n_simulations.
            Optional keys: model_id, reporting_period.
        output_dir: Directory to save the PDF. Defaults to current directory.
        filename: Optional filename. If None, generates a timestamped name.

    Returns:
        Full path to the generated PDF file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ai_risk_report_{timestamp}.pdf"

    pdf_path = output_dir / filename

    # Generate histogram image (cleaned up after PDF is built)
    histogram_path = _make_histogram_image(
        results["total_losses"],
        results["p95"],
        results["p99"],
        results["expected_loss"],
    )

    try:
        _build_pdf(str(pdf_path), results, histogram_path)
    finally:
        if os.path.exists(histogram_path):
            os.unlink(histogram_path)

    return str(pdf_path)


def _build_pdf(pdf_path: str, results: dict, histogram_path: str) -> None:
    """Build the PDF document. All layout coordinates live here."""
    page_w, page_h = LETTER
    c = canvas.Canvas(pdf_path, pagesize=LETTER)

    # ---------------- Background ----------------
    c.setFillColor(BG_SOFT_WHITE)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    # ---------------- Top accent border ----------------
    # Thin teal-and-orange bar across the very top
    c.setFillColor(ACCENT_TEAL)
    c.rect(0, page_h - 6, page_w * 0.7, 6, fill=1, stroke=0)
    c.setFillColor(ACCENT_ORANGE)
    c.rect(page_w * 0.7, page_h - 6, page_w * 0.3, 6, fill=1, stroke=0)

    # ---------------- Header ----------------
    margin_x = 0.6 * inch
    y = page_h - 0.55 * inch

    c.setFillColor(INK_BLACK)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin_x, y, "AI Risk Assessment Report")

    c.setFont("Helvetica", 9)
    c.setFillColor(INK_GREY)
    y -= 0.18 * inch
    c.drawString(margin_x, y, "Telemetry-Driven Quantitative Risk Analysis")

    # "Prepared for" line — clearly marks the subject as a fictional company
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(INK_LIGHT_GREY)
    y -= 0.16 * inch
    client_name = results.get("client_name", "F-Corp (a fictional company)")
    c.drawString(margin_x, y, f"Prepared for: {client_name}")

    # Metadata row on the right
    metadata_x = page_w - margin_x
    c.setFont("Helvetica", 8)
    c.setFillColor(INK_LIGHT_GREY)
    generated_at = datetime.now().strftime("%B %d, %Y · %H:%M")
    c.drawRightString(metadata_x, page_h - 0.55 * inch, f"Generated: {generated_at}")
    model_id = results.get("model_id", "model_v1.0")
    # Strip any trailing version suffix (e.g. "credit_risk_v3.2" -> "credit_risk")
    model_id = re.sub(r"[_\-\s]*v?\d+(\.\d+)*$", "", model_id)
    reporting_period = results.get("reporting_period", "Current period")
    c.drawRightString(metadata_x, page_h - 0.70 * inch, f"Model: {model_id}")
    c.drawRightString(metadata_x, page_h - 0.85 * inch, f"Period: {reporting_period}")

    # Divider line
    y -= 0.25 * inch
    c.setStrokeColor(RULE_GREY)
    c.setLineWidth(0.5)
    c.line(margin_x, y, page_w - margin_x, y)

    # ---------------- Hero section: the headline number ----------------
    y -= 0.45 * inch
    c.setFont("Helvetica", 9)
    c.setFillColor(INK_LIGHT_GREY)
    c.drawString(margin_x, y, "EXPECTED MONTHLY LOSS EXPOSURE")

    y -= 0.42 * inch
    c.setFont("Helvetica-Bold", 36)
    c.setFillColor(INK_BLACK)
    c.drawString(margin_x, y, _money_precise(results["expected_loss"]))

    # Confidence range to the right of the headline
    ci_text = (f"95% VaR: {_money(results['p95'])}    "
               f"99% VaR: {_money(results['p99'])}    "
               f"Tail CE (95%): {_money(results['tail_ce_95'])}")
    c.setFont("Helvetica", 9)
    c.setFillColor(INK_GREY)
    y_ci = y - 0.20 * inch
    c.drawString(margin_x, y_ci, ci_text)

    # Footnote on methodology
    y_method = y_ci - 0.15 * inch
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(INK_LIGHT_GREY)
    n_sims = results.get("n_simulations", 10000)
    c.drawString(margin_x, y_method,
                 f"Based on {n_sims:,} Monte Carlo simulations of correlated pillar outcomes.")

    # ---------------- Governance Pillars Grid ----------------
    y = y_method - 0.35 * inch

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(INK_BLACK)
    c.drawString(margin_x, y, "GOVERNANCE PILLARS")
    c.setStrokeColor(ACCENT_TEAL)
    c.setLineWidth(1.5)
    c.line(margin_x, y - 0.05 * inch, margin_x + 1.5 * inch, y - 0.05 * inch)

    # Grid: 3 columns x 2 rows
    y -= 0.30 * inch
    grid_top = y
    pillar_order = results["pillar_order"]
    pillar_posteriors = results["pillar_posteriors"]

    n_cols = 3
    col_width = (page_w - 2 * margin_x) / n_cols
    row_height = 0.85 * inch

    for i, pillar in enumerate(pillar_order):
        row = i // n_cols
        col = i % n_cols
        cx = margin_x + col * col_width
        cy = grid_top - row * row_height

        # Pillar metadata
        post = pillar_posteriors[pillar]
        alpha = post["alpha"]
        beta = post["beta"]
        mean = alpha / (alpha + beta)
        status_label, status_color = _compute_pillar_status(mean)

        # Status pill (small filled circle)
        c.setFillColor(status_color)
        c.circle(cx + 0.08 * inch, cy - 0.05 * inch, 0.05 * inch,
                 fill=1, stroke=0)

        # Pillar name
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(INK_BLACK)
        c.drawString(cx + 0.22 * inch, cy - 0.05 * inch, pillar)

        # Score
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(INK_BLACK)
        c.drawString(cx + 0.22 * inch, cy - 0.28 * inch, f"{mean:.2f}")

        # Status label
        c.setFont("Helvetica", 8)
        c.setFillColor(status_color)
        c.drawString(cx + 0.78 * inch, cy - 0.28 * inch, status_label.upper())

        # Posterior detail
        c.setFont("Helvetica", 7)
        c.setFillColor(INK_LIGHT_GREY)
        c.drawString(cx + 0.22 * inch, cy - 0.45 * inch,
                     f"α={alpha:.0f}  β={beta:.0f}  n={alpha + beta:.0f}")

    # Move past grid (2 rows used)
    y = grid_top - 2 * row_height - 0.1 * inch

    # ---------------- Distribution Histogram ----------------
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(INK_BLACK)
    c.drawString(margin_x, y, "LOSS DISTRIBUTION")
    c.setStrokeColor(ACCENT_TEAL)
    c.setLineWidth(1.5)
    c.line(margin_x, y - 0.05 * inch, margin_x + 1.5 * inch, y - 0.05 * inch)

    y -= 0.15 * inch
    hist_height = 1.7 * inch
    hist_width = page_w - 2 * margin_x
    c.drawImage(histogram_path,
                margin_x, y - hist_height,
                width=hist_width, height=hist_height,
                preserveAspectRatio=True, mask="auto")
    y -= hist_height + 0.10 * inch

    # ---------------- Top Risk Drivers ----------------
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(INK_BLACK)
    c.drawString(margin_x, y, "TOP RISK DRIVERS")
    c.setStrokeColor(ACCENT_ORANGE)
    c.setLineWidth(1.5)
    c.line(margin_x, y - 0.05 * inch, margin_x + 1.5 * inch, y - 0.05 * inch)

    c.setFont("Helvetica", 8)
    c.setFillColor(INK_LIGHT_GREY)
    c.drawRightString(page_w - margin_x, y, "Contribution to worst 5% of months")

    y -= 0.22 * inch
    contributions = _compute_tail_contributions(
        results["per_pillar_losses"],
        results["tail_mask"],
        results["pillar_order"],
    )

    for rank, (pillar, share) in enumerate(contributions, start=1):
        # Rank number
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(ACCENT_ORANGE)
        c.drawString(margin_x, y, f"{rank}.")

        # Pillar name
        c.setFont("Helvetica", 10)
        c.setFillColor(INK_BLACK)
        c.drawString(margin_x + 0.25 * inch, y, pillar)

        # Bar visualization
        bar_x = margin_x + 3.2 * inch
        bar_w_max = 2.4 * inch
        bar_w = bar_w_max * (share / 100)
        c.setFillColor(RULE_GREY)
        c.rect(bar_x, y - 0.03 * inch, bar_w_max, 0.12 * inch, fill=1, stroke=0)
        c.setFillColor(ACCENT_ORANGE)
        c.rect(bar_x, y - 0.03 * inch, bar_w, 0.12 * inch, fill=1, stroke=0)

        # Percentage
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(INK_BLACK)
        c.drawRightString(page_w - margin_x, y, f"{share:.1f}%")

        y -= 0.22 * inch

    # ---------------- Methodology Note ----------------
    y -= 0.25 * inch
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(INK_BLACK)
    c.drawString(margin_x, y, "INTERPRETATION")
    c.setStrokeColor(ACCENT_TEAL)
    c.setLineWidth(1.5)
    c.line(margin_x, y - 0.05 * inch, margin_x + 1.5 * inch, y - 0.05 * inch)

    y -= 0.25 * inch
    interp_lines = [
        "Expected loss represents the average monthly exposure across all simulated outcomes.",
        "95% VaR identifies the threshold above which the worst 5% of months fall.",
        "Tail Conditional Expectation reports the average loss within that worst-5% tail.",
        "Top risk drivers identify the pillars where remediation investment most reduces catastrophic exposure.",
    ]
    c.setFont("Helvetica", 8.5)
    c.setFillColor(INK_GREY)
    for line in interp_lines:
        c.drawString(margin_x, y, "•  " + line)
        y -= 0.16 * inch

    # ---------------- Footer ----------------
    footer_y = 0.45 * inch

    # Divider — raised to make room for the framework glossary below the mapping
    c.setStrokeColor(RULE_GREY)
    c.setLineWidth(0.5)
    c.line(margin_x, footer_y + 1.05 * inch,
           page_w - margin_x, footer_y + 1.05 * inch)

    # Regulatory mapping label
    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(INK_GREY)
    c.drawString(margin_x, footer_y + 0.90 * inch, "REGULATORY MAPPING")

    # Regulatory mapping content
    c.setFont("Helvetica", 7)
    c.setFillColor(INK_LIGHT_GREY)
    reg_text = ("EU AI Act Articles 10, 13, 17  ·  "
                "NIST AI RMF MEASURE 2.4, 2.5, 2.7, 2.11, 4.2  ·  "
                "ISO 42001 Clauses 8.1, 8.3, 8.4, 9.1")
    c.drawString(margin_x, footer_y + 0.75 * inch, reg_text)

    # Framework glossary — one concise sentence each, footnote-style
    framework_glossary = [
        ("EU AI Act", "the EU's binding law for AI; classifies systems by risk "
         "level and imposes legal duties, with fines up to €35M or 7% of global "
         "annual turnover for the most serious violations."),
        ("NIST AI RMF", "the U.S. National Institute of Standards and Technology's "
         "voluntary AI Risk Management Framework, organized around the functions "
         "Govern, Map, Measure, and Manage."),
        ("ISO/IEC 42001", "the international management-system standard for AI "
         "against which an organization can be independently certified by an "
         "accredited body."),
    ]
    gloss_y = footer_y + 0.60 * inch
    for name, desc in framework_glossary:
        c.setFont("Helvetica-Bold", 6.5)
        c.setFillColor(INK_GREY)
        c.drawString(margin_x, gloss_y, name + ":")
        name_width = c.stringWidth(name + ": ", "Helvetica-Bold", 6.5)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(INK_LIGHT_GREY)
        c.drawString(margin_x + name_width, gloss_y, desc)
        gloss_y -= 0.14 * inch

    # Attribution on its own line at the very bottom
    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(INK_LIGHT_GREY)
    c.drawString(margin_x, footer_y - 0.05 * inch,
                 "Generated by the methodology from O'Reilly Live Training: "
                 "Quantifying AI Risk — Suneeta Modekurty")

    c.save()



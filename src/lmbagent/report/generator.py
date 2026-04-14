"""Report generation: combine data analysis and plots into a report."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import jinja2
import markdown as md

from lmbagent.data.models import BatteryDataset
from lmbagent.data.transformer import add_cycle_summary, compute_insights
from lmbagent.visualization.capacity_plot import plot_capacity_fade
from lmbagent.visualization.efficiency_plot import plot_coulombic_efficiency
from lmbagent.visualization.voltage_plot import plot_voltage_curves
from lmbagent.visualization.impedance_plot import plot_impedance

TEMPLATE_DIR = Path(__file__).parent / "templates"


def generate_report(
    dataset: BatteryDataset,
    output_format: str = "markdown",
    output_dir: str | Path | None = None,
    analysis_notes: str | None = None,
) -> str:
    """Generate a comprehensive analysis report.

    Args:
        dataset: BatteryDataset to analyze.
        output_format: "markdown", "html", or "pdf".
        output_dir: Directory for output files.
        analysis_notes: Optional custom analysis text.

    Returns:
        Path to the generated report file.
    """
    if output_dir is None:
        output_dir = Path("output")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Ensure cycle summary exists
    if dataset.cycle_summary.empty:
        add_cycle_summary(dataset)

    # Generate all plots (into plots/ subdirectory)
    plot_dir = output_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    _generate_plot_if_missing(plot_dir / "capacity_fade.png",
                              lambda p: plot_capacity_fade(dataset, output_path=p))
    _generate_plot_if_missing(plot_dir / "coulombic_efficiency.png",
                              lambda p: plot_coulombic_efficiency(dataset, output_path=p))
    _generate_plot_if_missing(plot_dir / "voltage_curves.png",
                              lambda p: plot_voltage_curves(dataset, output_path=p))
    _generate_plot_if_missing(plot_dir / "impedance.png",
                              lambda p: plot_impedance(dataset, output_path=p))

    # Use relative paths for images (relative to the report file)
    rel_cap = "plots/capacity_fade.png"
    rel_eff = "plots/coulombic_efficiency.png"
    rel_volt = "plots/voltage_curves.png"
    rel_imp = "plots/impedance.png"

    # Prepare template context
    raw = dataset.raw_data
    summary_records = dataset.cycle_summary.to_dict("records") if not dataset.cycle_summary.empty else []

    # Compute cross-cycle insights
    insights = compute_insights(dataset)

    context = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_file": dataset.source_file,
        "test_name": dataset.test_name,
        "start_datetime": str(dataset.start_datetime) if dataset.start_datetime else None,
        "num_data_points": dataset.num_data_points,
        "num_cycles": dataset.num_cycles,
        "voltage_min": f"{raw['voltage'].min():.3f}" if "voltage" in raw else "N/A",
        "voltage_max": f"{raw['voltage'].max():.3f}" if "voltage" in raw else "N/A",
        "current_min": f"{raw['current'].min():.3f}" if "current" in raw else "N/A",
        "current_max": f"{raw['current'].max():.3f}" if "current" in raw else "N/A",
        "cycle_summary": summary_records if summary_records else None,
        "capacity_plot": rel_cap,
        "efficiency_plot": rel_eff,
        "voltage_plot": rel_volt,
        "impedance_plot": rel_imp,
        "analysis_notes": analysis_notes,
        "insights": insights,
    }

    # Render template
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
        undefined=jinja2.StrictUndefined,
    )
    template = env.get_template("report.md.j2")
    md_content = template.render(**context)

    if output_format == "pdf":
        # Generate HTML first, then convert to PDF with weasyprint
        html_content = _wrap_html(md.markdown(md_content, extensions=["tables"]))
        report_path = output_dir / f"report_{dataset.data_id}.pdf"
        from weasyprint import HTML
        HTML(string=html_content, base_url=str(output_dir)).write_pdf(str(report_path))
    elif output_format == "html":
        html_content = _wrap_html(md.markdown(md_content, extensions=["tables"]))
        report_path = output_dir / f"report_{dataset.data_id}.html"
        report_path.write_text(html_content, encoding="utf-8")
    else:
        report_path = output_dir / f"report_{dataset.data_id}.md"
        report_path.write_text(md_content, encoding="utf-8")

    return str(report_path)


def _generate_plot_if_missing(path: Path, generate_fn) -> None:
    """Generate a plot only if it doesn't already exist (cache)."""
    if not path.exists():
        generate_fn(path)


def _wrap_html(body: str) -> str:
    """Wrap HTML body with dark-theme styling matching HKAI-Cycling UI."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: -apple-system, 'Helvetica Neue', 'PingFang SC', Arial, sans-serif; margin: 24px; background: #030d1f; color: #e8f4ff; line-height: 1.6; }}
h1 {{ color: #00e5ff; border-bottom: 1px solid rgba(0,168,255,0.3); padding-bottom: 8px; font-size: 18px; }}
h2 {{ color: #00a8ff; margin-top: 24px; font-size: 15px; }}
h3 {{ color: #7ab3d4; font-size: 13px; }}
p, li {{ font-size: 13px; color: #b0d4ef; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 12px; }}
th, td {{ border: 1px solid rgba(0,168,255,0.22); padding: 6px 10px; text-align: left; }}
th {{ background: rgba(0,168,255,0.15); color: #00e5ff; font-weight: 600; }}
tr:nth-child(even) {{ background: rgba(0,168,255,0.04); }}
img {{ max-width: 100%; height: auto; margin: 12px 0; border: 1px solid rgba(0,168,255,0.22); border-radius: 4px; }}
hr {{ border: none; border-top: 1px solid rgba(0,168,255,0.15); margin: 20px 0; }}
strong {{ color: #e8f4ff; }}
code {{ background: rgba(0,168,255,0.08); padding: 1px 4px; border-radius: 3px; font-size: 12px; color: #00e5ff; }}
</style>
</head>
<body>
{body}
</body>
</html>"""

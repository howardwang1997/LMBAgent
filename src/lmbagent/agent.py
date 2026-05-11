"""Tool definitions and backend integrations (Claude Agent SDK + LiteLLM)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")

from lmbagent.data.loader import load_csv
from lmbagent.data.store import DataStore
from lmbagent.data.transformer import add_cycle_summary
from lmbagent.output import get_output_dir, get_plots_dir, get_cached_or_new
from lmbagent.visualization.capacity_plot import plot_capacity_fade
from lmbagent.visualization.efficiency_plot import plot_coulombic_efficiency
from lmbagent.visualization.voltage_plot import plot_voltage_curves
from lmbagent.visualization.impedance_plot import plot_impedance
from lmbagent.report.generator import generate_report
from lmbagent.comparison.overlay import overlay_capacity_fade, overlay_coulombic_efficiency, overlay_voltage_curves
from lmbagent.comparison.delta import plot_delta_v
from lmbagent.comparison.metrics import build_comparison_table, rank_by_metric, summarize_differences
from lmbagent.degradation.decomposition import decompose_degradation_modes, plot_decomposition, format_decomposition_summary
from lmbagent.degradation.doe_checker import check_doe_coverage, analyze_design_impact
from lmbagent.data.catalog import scan_directory, batch_import
from lmbagent.search.engine import SearchEngine
from lmbagent.conclusions.models import Conclusion, ConclusionStatus
from lmbagent.conclusions.store import ConclusionStore
from lmbagent.conclusions.verifier import verify_conclusion, verify_all


store = DataStore()


def _text_result(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _error_result(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"Error: {text}"}], "isError": True}


# --- Handler Functions (testable, backend-agnostic) ---

async def _handle_load_battery_data(args: dict[str, Any]) -> dict[str, Any]:
    file_path = args.get("file_path")
    if not file_path:
        return _error_result("file_path is required")
    try:
        ds = load_csv(file_path, data_id=args.get("data_id"))
        ds = add_cycle_summary(ds)
        store.put(ds)
        summary = ds.cycle_summary
        ce_info = ""
        if not summary.empty and len(summary) > 1:
            ce_info = f"\nCycle 1 CE: {summary.iloc[1]['coulombic_efficiency']:.2f}%"
        return _text_result(
            f"Data loaded successfully.\n"
            f"data_id: {ds.data_id}\n"
            f"Test: {ds.test_name or 'N/A'}\n"
            f"Data points: {ds.num_data_points}\n"
            f"Cycles: {ds.num_cycles}\n"
            f"Voltage range: {ds.raw_data['voltage'].min():.3f} - {ds.raw_data['voltage'].max():.3f} V\n"
            f"Current range: {ds.raw_data['current'].min():.3f} - {ds.raw_data['current'].max():.3f} A"
            f"{ce_info}"
        )
    except Exception as e:
        return _error_result(str(e))


async def _handle_transform_data(args: dict[str, Any]) -> dict[str, Any]:
    data_id = args.get("data_id")
    if not data_id:
        return _error_result("data_id is required")
    ds = store.get(data_id)
    if ds is None:
        return _error_result(f"Dataset '{data_id}' not found. Available: {store.list_ids()}")

    cycle_range = args.get("cycle_range")
    if cycle_range:
        try:
            start, end = map(int, cycle_range.split("-"))
            ds.raw_data = ds.raw_data[
                (ds.raw_data["cycle_index"] >= start) & (ds.raw_data["cycle_index"] <= end)
            ].copy()
        except ValueError:
            return _error_result(f"Invalid cycle_range: {cycle_range}. Use format '1-50'.")

    ds = add_cycle_summary(ds)
    store.put(ds)

    summary_text = ds.cycle_summary.to_string(index=False)
    return _text_result(f"Cycle summary updated for {data_id}:\n{summary_text}")


async def _handle_plot_capacity_fade(args: dict[str, Any]) -> dict[str, Any]:
    data_id = args.get("data_id", "")
    ds = store.get(data_id)
    if ds is None:
        return _error_result(f"Dataset not found. Available: {store.list_ids()}")
    try:
        plots_dir = get_plots_dir(data_id)
        filename = "capacity_fade.png"
        filepath, cached = get_cached_or_new(plots_dir, filename)
        if cached:
            return _text_result(f"Capacity fade plot (cached): {filepath}")
        path = plot_capacity_fade(
            ds,
            normalize=args.get("normalize", False),
            output_path=filepath,
        )
        return _text_result(f"Capacity fade plot saved to: {path}")
    except Exception as e:
        return _error_result(str(e))


async def _handle_plot_coulombic_efficiency(args: dict[str, Any]) -> dict[str, Any]:
    data_id = args.get("data_id", "")
    ds = store.get(data_id)
    if ds is None:
        return _error_result(f"Dataset not found. Available: {store.list_ids()}")
    try:
        plots_dir = get_plots_dir(data_id)
        filename = "coulombic_efficiency.png"
        filepath, cached = get_cached_or_new(plots_dir, filename)
        if cached:
            return _text_result(f"CE plot (cached): {filepath}")
        y_range = None
        if args.get("y_range"):
            parts = args["y_range"].split("-")
            y_range = (float(parts[0]), float(parts[1]))
        path = plot_coulombic_efficiency(ds, y_range=y_range, output_path=filepath)
        summary = ds.cycle_summary
        ce_stats = ""
        if not summary.empty:
            ce = summary["coulombic_efficiency"]
            ce_stats = f"\nMean CE: {ce.mean():.2f}%, Min: {ce.min():.2f}%, Max: {ce.max():.2f}%"
        return _text_result(f"CE plot saved to: {path}{ce_stats}")
    except Exception as e:
        return _error_result(str(e))


async def _handle_plot_voltage_curves(args: dict[str, Any]) -> dict[str, Any]:
    data_id = args.get("data_id", "")
    ds = store.get(data_id)
    if ds is None:
        return _error_result(f"Dataset not found. Available: {store.list_ids()}")
    try:
        plots_dir = get_plots_dir(data_id)
        filename = "voltage_curves.png"
        filepath, cached = get_cached_or_new(plots_dir, filename)
        if cached:
            return _text_result(f"Voltage curves plot (cached): {filepath}")
        cycle_numbers = None
        if args.get("cycle_numbers"):
            cycle_numbers = [int(c.strip()) for c in args["cycle_numbers"].split(",")]
        path = plot_voltage_curves(ds, cycle_numbers=cycle_numbers, output_path=filepath)
        return _text_result(f"Voltage curves plot saved to: {path}")
    except Exception as e:
        return _error_result(str(e))


async def _handle_generate_report(args: dict[str, Any]) -> dict[str, Any]:
    data_id = args.get("data_id", "")
    ds = store.get(data_id)
    if ds is None:
        return _error_result(f"Dataset not found. Available: {store.list_ids()}")
    try:
        output_dir = get_output_dir(data_id)
        path = generate_report(
            ds,
            output_format=args.get("output_format", "markdown"),
            output_dir=output_dir,
        )
        return _text_result(f"Report generated: {path}")
    except Exception as e:
        return _error_result(str(e))


async def _handle_list_experiments(args: dict[str, Any]) -> dict[str, Any]:
    chemistry = args.get("chemistry")
    cell_id = args.get("cell_id")
    results = store.query(chemistry=chemistry, cell_id=cell_id)
    if not results:
        return _text_result(f"No experiments found. Total in store: {len(store.list_ids())}")
    table = store.list_as_table()
    cols_to_show = [c for c in ["data_id", "cell_id", "chemistry", "cycles", "source_file"] if c in table.columns]
    return _text_result(f"Found {len(results)} experiments:\n{table[cols_to_show].to_string(index=False)}")


async def _handle_compare_experiments(args: dict[str, Any]) -> dict[str, Any]:
    data_ids = args.get("data_ids", "")
    if isinstance(data_ids, str):
        data_ids = [d.strip() for d in data_ids.split(",") if d.strip()]
    datasets = []
    for did in data_ids:
        ds = store.get(did)
        if ds is None:
            return _error_result(f"Dataset '{did}' not found. Available: {store.list_ids()}")
        if ds.cycle_summary.empty:
            ds = add_cycle_summary(ds)
            store.put(ds)
        datasets.append(ds)
    if len(datasets) < 2:
        return _error_result("Need at least 2 datasets for comparison.")

    table = build_comparison_table(datasets)
    summary = summarize_differences(datasets)
    text = f"Comparison of {len(datasets)} experiments:\n\n"
    text += table.to_string(index=False)
    text += f"\n\nDiffering design factors: {summary['differing_design_factors'] or 'None (identical designs)'}"
    if summary["best_retention"]:
        text += f"\nBest retention: {summary['best_retention']}"
    if summary["worst_fade"]:
        text += f"\nWorst fade: {summary['worst_fade']}"
    return _text_result(text)


async def _handle_overlay_plot(args: dict[str, Any]) -> dict[str, Any]:
    data_ids = args.get("data_ids", "")
    if isinstance(data_ids, str):
        data_ids = [d.strip() for d in data_ids.split(",") if d.strip()]
    plot_type = args.get("plot_type", "capacity")
    datasets = []
    for did in data_ids:
        ds = store.get(did)
        if ds is None:
            return _error_result(f"Dataset '{did}' not found. Available: {store.list_ids()}")
        if ds.cycle_summary.empty:
            ds = add_cycle_summary(ds)
            store.put(ds)
        datasets.append(ds)
    if len(datasets) < 2:
        return _error_result("Need at least 2 datasets for overlay plot.")

    output_dir = get_output_dir("comparison")
    try:
        if plot_type == "ce":
            path = overlay_coulombic_efficiency(datasets, output_path=output_dir / "overlay_ce.png")
        elif plot_type == "voltage":
            cycle_num = int(args.get("cycle", 0))
            path = overlay_voltage_curves(datasets, cycle_number=cycle_num,
                                          output_path=output_dir / f"overlay_voltage_c{cycle_num}.png")
        else:
            normalize = args.get("normalize", False)
            path = overlay_capacity_fade(datasets, normalize=normalize,
                                         output_path=output_dir / "overlay_capacity.png")
        return _text_result(f"Overlay plot saved to: {path}")
    except Exception as e:
        return _error_result(str(e))


async def _handle_delta_analysis(args: dict[str, Any]) -> dict[str, Any]:
    data_id_a = args.get("data_id_a", "")
    data_id_b = args.get("data_id_b", "")
    ds_a = store.get(data_id_a)
    ds_b = store.get(data_id_b)
    if ds_a is None or ds_b is None:
        return _error_result(f"Dataset not found. Available: {store.list_ids()}")
    if ds_a.cycle_summary.empty:
        ds_a = add_cycle_summary(ds_a)
        store.put(ds_a)
    if ds_b.cycle_summary.empty:
        ds_b = add_cycle_summary(ds_b)
        store.put(ds_b)

    cycle_num = int(args.get("cycle", 0))
    output_dir = get_output_dir("comparison")
    try:
        path = plot_delta_v(ds_a, ds_b, cycle_number=cycle_num,
                            output_path=output_dir / f"delta_v_{data_id_a}_{data_id_b}_c{cycle_num}.png")
        return _text_result(f"Delta analysis plot saved to: {path}")
    except Exception as e:
        return _error_result(str(e))


async def _handle_analyze_failure_modes(args: dict[str, Any]) -> dict[str, Any]:
    data_id = args.get("data_id", "")
    ds = store.get(data_id)
    if ds is None:
        return _error_result(f"Dataset not found. Available: {store.list_ids()}")
    if ds.cycle_summary.empty:
        ds = add_cycle_summary(ds)
        store.put(ds)
    try:
        result = decompose_degradation_modes(ds)
        if "error" in result:
            return _error_result(result["error"])
        output_dir = get_output_dir(data_id)
        path = plot_decomposition(result, output_path=output_dir / "decomposition.png")
        summary = format_decomposition_summary(result)
        return _text_result(f"{summary}\n\nDecomposition plot saved to: {path}")
    except Exception as e:
        return _error_result(str(e))


async def _handle_analyze_design_impact(args: dict[str, Any]) -> dict[str, Any]:
    data_ids = args.get("data_ids", "")
    focus_factor = args.get("focus_factor")
    if isinstance(data_ids, str):
        data_ids = [d.strip() for d in data_ids.split(",") if d.strip()]
    datasets = []
    for did in data_ids:
        ds = store.get(did)
        if ds is None:
            return _error_result(f"Dataset '{did}' not found. Available: {store.list_ids()}")
        datasets.append(ds)
    if len(datasets) < 2:
        return _error_result("Need at least 2 experiments for design impact analysis.")
    try:
        result = analyze_design_impact(datasets, focus_factor=focus_factor)
        lines = [f"Design Impact Analysis ({result['n_experiments']} experiments)"]
        lines.append(f"Factors analyzed: {result['factors_analyzed']}")
        for factor, info in result.get("factor_analysis", {}).items():
            lines.append(f"\n  {factor}:")
            if "correlation_with_fade" in info:
                lines.append(f"    Correlation with fade: r={info['correlation_with_fade']}")
            if "interpretation" in info:
                lines.append(f"    {info['interpretation']}")
            if "groups" in info:
                for val, stats in info["groups"].items():
                    lines.append(f"    {val}: mean fade={stats['mean_fade']}% (n={stats['n']})")
        return _text_result("\n".join(lines))
    except Exception as e:
        return _error_result(str(e))


async def _handle_check_doe_coverage(args: dict[str, Any]) -> dict[str, Any]:
    data_ids = args.get("data_ids", "")
    if isinstance(data_ids, str):
        data_ids = [d.strip() for d in data_ids.split(",") if d.strip()]
    datasets = []
    for did in data_ids:
        ds = store.get(did)
        if ds is None:
            return _error_result(f"Dataset '{did}' not found. Available: {store.list_ids()}")
        datasets.append(ds)
    if len(datasets) < 2:
        return _error_result("Need at least 2 experiments for DOE coverage analysis.")
    try:
        result = check_doe_coverage(datasets)
        lines = [f"DOE Coverage Analysis ({result['n_experiments']} experiments)"]
        lines.append(f"Coverage score: {result['coverage_score']:.1%}")
        lines.append(f"Factors tested (varying): {result['factors_tested']}")
        lines.append(f"Factors constant/missing: {result['factors_constant']}")
        if result['missing_combinations']:
            lines.append(f"\nMissing combinations ({len(result['missing_combinations'])} total, showing first 5):")
            for combo in result['missing_combinations'][:5]:
                lines.append(f"  {combo}")
        if result['recommendations']:
            lines.append("\nRecommendations:")
            for rec in result['recommendations']:
                lines.append(f"  [{rec['priority']}] {rec['description']}")
        return _text_result("\n".join(lines))
    except Exception as e:
        return _error_result(str(e))


async def _handle_recommend_experiments(args: dict[str, Any]) -> dict[str, Any]:
    data_ids = args.get("data_ids", "")
    if isinstance(data_ids, str):
        data_ids = [d.strip() for d in data_ids.split(",") if d.strip()]
    if not data_ids:
        data_ids = store.list_ids()
    datasets = []
    for did in data_ids:
        ds = store.get(did)
        if ds is not None:
            datasets.append(ds)
    if len(datasets) < 2:
        return _error_result("Need at least 2 experiments to generate recommendations.")
    try:
        doe = check_doe_coverage(datasets)
        lines = [f"Experiment Recommendations (based on {len(datasets)} existing experiments)"]
        lines.append(f"Current DOE coverage: {doe['coverage_score']:.1%}\n")
        if doe['recommendations']:
            for i, rec in enumerate(doe['recommendations'], 1):
                lines.append(f"{i}. [{rec['priority'].upper()}] {rec['description']}")
        else:
            lines.append("DOE appears well-covered. No critical gaps found.")
        lines.append(f"\nFactors currently tested: {doe['factors_tested']}")
        lines.append(f"Factors not yet varied: {doe['factors_constant']}")
        return _text_result("\n".join(lines))
    except Exception as e:
        return _error_result(str(e))


async def _handle_template_doe(args: dict[str, Any]) -> dict[str, Any]:
    template_path = args.get("template_path", "")
    data_dir = args.get("data_dir", "")
    if not template_path:
        return _error_result("template_path is required (path to 电芯挂测表 xlsx)")
    from pathlib import Path as _P
    if not _P(template_path).exists():
        return _error_result(f"Template file not found: {template_path}")
    try:
        from lmbagent.data.cell_test_template import (
            load_cell_test_template, match_cycling_data_to_template,
            load_template_reference_sheets,
        )
        records = load_cell_test_template(template_path)
        if not records:
            return _error_result("No valid records found in template (empty 挂测表 sheet)")
        lines = [f"电芯挂测表: {len(records)} 条记录"]
        for r in records:
            lines.append(f"  {r.cell_id}: {r.cathode}/{r.anode}/{r.electrolyte}/{r.separator} "
                         f"T={r.test_temperature_c}C ch={r.charge_rate_c}C dis={r.discharge_rate_c}C")
        if data_dir and _P(data_dir).is_dir():
            matches = match_cycling_data_to_template(records, data_dir)
            lines.append(f"\n数据匹配: {len(matches)}/{sum(1 for _ in _P(data_dir).rglob('*.xlsx'))} xlsx 文件")
            for fp, rec in list(matches.items())[:10]:
                lines.append(f"  {_P(fp).name} → {rec.cell_id}")
        refs = load_template_reference_sheets(template_path)
        if refs:
            lines.append("\n参考值:")
            for key, vals in refs.items():
                lines.append(f"  {key}: {vals[:5]}...")
        if data_dir and _P(data_dir).is_dir():
            from lmbagent.data.cell_test_template import CellTestRecord
            from lmbagent.degradation.doe_checker import check_doe_from_template
            from lmbagent.data.loader import load_auto
            matched_records = match_cycling_data_to_template(records, data_dir)
            if matched_records:
                datasets = []
                for fp_str, rec in matched_records.items():
                    try:
                        ds = load_auto(fp_str, data_id=rec.cell_id)
                        ds.cell_id = rec.cell_id
                        ds = add_cycle_summary(ds)
                        datasets.append(ds)
                    except Exception:
                        pass
                if datasets:
                    doe = check_doe_from_template(records, datasets)
                    lines.append(f"\nDOE 分析 (模板模式, {doe['n_experiments']} 实验):")
                    lines.append(f"  覆盖度: {doe['coverage_score']:.1%}")
                    lines.append(f"  已变化因子: {doe['factors_tested']}")
                    lines.append(f"  固定/缺失因子: {doe['factors_constant']}")
                    if doe['missing_combinations']:
                        lines.append(f"  缺失组合 (共{len(doe['missing_combinations'])}个, 前5个):")
                        for combo in doe['missing_combinations'][:5]:
                            lines.append(f"    {combo}")
                    if doe['recommendations']:
                        lines.append("  推荐:")
                        for rec_item in doe['recommendations']:
                            lines.append(f"    [{rec_item['priority']}] {rec_item['description']}")
        return _text_result("\n".join(lines))
    except Exception as e:
        return _error_result(str(e))


async def _handle_scan_and_import(args: dict[str, Any]) -> dict[str, Any]:
    directory = args.get("directory", "")
    dry_run = args.get("dry_run", False)
    if not directory:
        return _error_result("directory is required")
    from pathlib import Path as _P
    if not _P(directory).is_dir():
        return _error_result(f"Not a directory: {directory}")
    try:
        candidates = scan_directory(directory)
        if not candidates:
            return _text_result(f"No data files found in {directory}")
        lines = [f"Found {len(candidates)} data files in {directory}:"]
        for c in candidates:
            design_tag = " [+design]" if c.design_path else ""
            lines.append(f"  {c.path.name} ({c.format}){design_tag}")
        if dry_run:
            return _text_result("\n".join(lines))
        imported = batch_import(candidates, store=store)
        n_ok = sum(1 for c in imported if c.imported)
        n_fail = sum(1 for c in imported if not c.imported and c.error)
        lines.append(f"\nImport: {n_ok} succeeded, {n_fail} failed")
        if n_ok > 0:
            lines.append(f"Total experiments in database: {len(store.list_ids())}")
        return _text_result("\n".join(lines))
    except Exception as e:
        return _error_result(str(e))


# --- Week 4: Search & Conclusion Handlers ---

async def _handle_search_similar(args: dict[str, Any]) -> dict[str, Any]:
    data_id = args.get("data_id")
    if not data_id:
        return _error_result("data_id is required")
    mode = args.get("mode", "similar")
    top_k = int(args.get("top_k", 5))
    try:
        engine = SearchEngine(store)
        ds = store.get(data_id)
        if ds is None:
            return _error_result(f"Dataset '{data_id}' not found")
        results = engine.search_similar(data_id, mode=mode, top_k=top_k)
        if not results:
            return _text_result("No similar/contrast experiments found.")
        lines = [f"Search results (mode={mode}, top {len(results)}):"]
        lines.append("")
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.data_id} — score: {r.score:.3f}")
            lines.append(f"   {r.reason}")
        return _text_result("\n".join(lines))
    except Exception as e:
        return _error_result(str(e))


async def _handle_manage_conclusion(args: dict[str, Any]) -> dict[str, Any]:
    action = args.get("action", "list")
    cs = ConclusionStore(store)
    try:
        if action == "list":
            conclusions = cs.list_all()
            if not conclusions:
                return _text_result("No conclusions found.")
            lines = [f"Conclusions ({len(conclusions)}):"]
            for c in conclusions:
                status_icon = {"active": "🟢", "supported": "✅", "challenged": "🔴",
                               "superseded": "⏭️", "retracted": "❌"}.get(c.status.value, "?")
                lines.append(f"\n{status_icon} [{c.conclusion_id}] ({c.status.value}, {c.confidence})")
                lines.append(f"   {c.statement}")
                if c.scope:
                    lines.append(f"   Scope: {c.scope}")
                if c.evidence_ids:
                    lines.append(f"   Evidence: {', '.join(c.evidence_ids)}")
            return _text_result("\n".join(lines))

        elif action == "add":
            cid = args.get("conclusion_id", f"C-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
            conclusion = Conclusion(
                conclusion_id=cid,
                statement=args.get("statement", ""),
                scope=args.get("scope", ""),
                evidence_ids=args.get("evidence_ids", "").split(",") if args.get("evidence_ids") else [],
                confidence=args.get("confidence", "medium"),
            )
            cs.add(conclusion)
            return _text_result(f"Conclusion added: {cid}")

        elif action == "update":
            cid = args.get("conclusion_id")
            if not cid:
                return _error_result("conclusion_id required for update")
            updated = cs.update(
                cid,
                statement=args.get("statement"),
                status=args.get("status"),
                confidence=args.get("confidence"),
                evidence_ids=args.get("evidence_ids", "").split(",") if args.get("evidence_ids") else None,
            )
            if updated is None:
                return _error_result(f"Conclusion '{cid}' not found")
            return _text_result(f"Conclusion updated: {cid} → {updated.status.value}")

        elif action == "delete":
            cid = args.get("conclusion_id")
            if not cid:
                return _error_result("conclusion_id required for delete")
            if cs.remove(cid):
                return _text_result(f"Conclusion deleted: {cid}")
            return _error_result(f"Conclusion '{cid}' not found")

        else:
            return _error_result(f"Unknown action: {action}. Use list/add/update/delete.")
    except Exception as e:
        return _error_result(str(e))


async def _handle_verify_with_new_data(args: dict[str, Any]) -> dict[str, Any]:
    data_id = args.get("data_id")
    if not data_id:
        return _error_result("data_id is required")
    try:
        results = verify_all(data_id, store=store)
        if not results:
            return _text_result("No active conclusions to verify.")
        lines = [f"Verification against '{data_id}' ({len(results)} conclusions):"]
        for r in results:
            icon = {"supported": "✅", "challenged": "🔴", "inconclusive": "❓"}.get(r.verdict, "?")
            lines.append(f"\n{icon} {r.conclusion_id}: {r.verdict.upper()}")
            lines.append(f"   {r.evidence_summary}")
            if r.details:
                lines.append(f"   Details: {r.details}")
            lines.append(f"   Confidence: {r.confidence_change}")
        return _text_result("\n".join(lines))
    except Exception as e:
        return _error_result(str(e))


# --- Unified Tool Registry (backend-agnostic) ---

TOOL_REGISTRY = [
    {
        "name": "load_battery_data",
        "description": (
            "Load battery cycling data from a CSV file. Supports PEC CSV format (from cellpy) "
            "and generic CSV with standard column names. Returns data_id for use with other tools."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the CSV data file"},
                "data_id": {"type": "string", "description": "Optional custom ID for the dataset"},
            },
            "required": ["file_path"],
        },
        "handler": _handle_load_battery_data,
    },
    {
        "name": "transform_data",
        "description": (
            "Compute or recompute cycle summary for loaded battery data. "
            "Can also filter to a specific cycle range."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_id": {"type": "string", "description": "Dataset ID from load_battery_data"},
                "cycle_range": {"type": "string", "description": "Optional cycle range, e.g. '1-50'"},
            },
            "required": ["data_id"],
        },
        "handler": _handle_transform_data,
    },
    {
        "name": "plot_capacity_fade",
        "description": "Generate a capacity fade plot showing charge and discharge capacity versus cycle number.",
        "parameters": {
            "type": "object",
            "properties": {
                "data_id": {"type": "string", "description": "Dataset ID"},
                "normalize": {"type": "boolean", "description": "Normalize to first cycle (default: false)"},
                "output_path": {"type": "string", "description": "Optional output file path"},
            },
            "required": ["data_id"],
        },
        "handler": _handle_plot_capacity_fade,
    },
    {
        "name": "plot_coulombic_efficiency",
        "description": "Generate a coulombic efficiency plot versus cycle number.",
        "parameters": {
            "type": "object",
            "properties": {
                "data_id": {"type": "string", "description": "Dataset ID"},
                "y_range": {"type": "string", "description": "Optional y-axis range, e.g. '95-101'"},
                "output_path": {"type": "string", "description": "Optional output file path"},
            },
            "required": ["data_id"],
        },
        "handler": _handle_plot_coulombic_efficiency,
    },
    {
        "name": "plot_voltage_curves",
        "description": "Generate voltage vs capacity curves for selected cycles.",
        "parameters": {
            "type": "object",
            "properties": {
                "data_id": {"type": "string", "description": "Dataset ID"},
                "cycle_numbers": {"type": "string", "description": "Comma-separated cycle numbers, e.g. '0,1,2'"},
                "output_path": {"type": "string", "description": "Optional output file path"},
            },
            "required": ["data_id"],
        },
        "handler": _handle_plot_voltage_curves,
    },
    {
        "name": "generate_report",
        "description": "Generate a comprehensive analysis report including all charts and cycle performance data.",
        "parameters": {
            "type": "object",
            "properties": {
                "data_id": {"type": "string", "description": "Dataset ID"},
                "output_format": {"type": "string", "description": "'markdown' (default) or 'html'"},
                "output_dir": {"type": "string", "description": "Optional output directory path"},
            },
            "required": ["data_id"],
        },
        "handler": _handle_generate_report,
    },
    {
        "name": "list_experiments",
        "description": (
            "List all loaded experiments, optionally filtered by chemistry or cell_id. "
            "Returns a table with data_id, cell_id, chemistry, cycles."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "chemistry": {"type": "string", "description": "Optional chemistry filter, e.g. 'NMC811'"},
                "cell_id": {"type": "string", "description": "Optional cell ID filter"},
            },
        },
        "handler": _handle_list_experiments,
    },
    {
        "name": "compare_experiments",
        "description": (
            "Compare multiple experiments side by side. Returns a metrics table with "
            "capacity, CE, fade, retention, and design factors. Also identifies differing "
            "design factors and best/worst performers."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_ids": {"type": "string", "description": "Comma-separated dataset IDs, e.g. 'abc123,def456'"},
            },
            "required": ["data_ids"],
        },
        "handler": _handle_compare_experiments,
    },
    {
        "name": "overlay_plot",
        "description": (
            "Generate overlay comparison plots for multiple experiments. "
            "Supports capacity fade, coulombic efficiency, and voltage curve overlays."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_ids": {"type": "string", "description": "Comma-separated dataset IDs"},
                "plot_type": {"type": "string", "description": "'capacity' (default), 'ce', or 'voltage'"},
                "normalize": {"type": "boolean", "description": "Normalize capacity (default: false)"},
                "cycle": {"type": "integer", "description": "Cycle number for voltage overlay (default: 0)"},
            },
            "required": ["data_ids"],
        },
        "handler": _handle_overlay_plot,
    },
    {
        "name": "delta_analysis",
        "description": (
            "Compute voltage difference (ΔV) between two experiments at a given cycle. "
            "Generates a two-panel plot: discharge curves + ΔV(mV)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_id_a": {"type": "string", "description": "First dataset ID"},
                "data_id_b": {"type": "string", "description": "Second dataset ID"},
                "cycle": {"type": "integer", "description": "Cycle number (default: 0)"},
            },
            "required": ["data_id_a", "data_id_b"],
        },
        "handler": _handle_delta_analysis,
    },
    {
        "name": "analyze_failure_modes",
        "description": (
            "Decompose degradation modes for a single experiment. Fits voltage change "
            "as a combination of 7 degradation signatures (SEI growth, Li plating, "
            "LAM_pos, LAM_neg, resistance growth, diffusion degradation, electrolyte depletion)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_id": {"type": "string", "description": "Dataset ID"},
            },
            "required": ["data_id"],
        },
        "handler": _handle_analyze_failure_modes,
    },
    {
        "name": "analyze_design_impact",
        "description": (
            "Analyze how design factors correlate with degradation outcomes across "
            "multiple experiments. Identifies which design factors significantly affect "
            "capacity fade and dominant degradation mode."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_ids": {"type": "string", "description": "Comma-separated dataset IDs"},
                "focus_factor": {"type": "string", "description": "Optional specific factor to focus on"},
            },
            "required": ["data_ids"],
        },
        "handler": _handle_analyze_design_impact,
    },
    {
        "name": "check_doe_coverage",
        "description": (
            "Check DOE completeness: which design factors have been varied, which are "
            "missing, what combinations are untested. Returns coverage score and missing combos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_ids": {"type": "string", "description": "Comma-separated dataset IDs"},
            },
            "required": ["data_ids"],
        },
        "handler": _handle_check_doe_coverage,
    },
    {
        "name": "recommend_experiments",
        "description": (
            "Recommend supplementary experiments to fill DOE gaps. Analyzes current "
            "experimental coverage and suggests missing combinations, midpoints, and "
            "new factors to test."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_ids": {"type": "string", "description": "Comma-separated dataset IDs (empty = use all)"},
            },
        },
        "handler": _handle_recommend_experiments,
    },
    {
        "name": "template_doe_analysis",
        "description": (
            "Parse a 电芯挂测表 (cell test template xlsx) and perform DOE analysis "
            "using real design factors: 电解液, 隔膜, 测试温度, 充放电电流, 电压窗口, "
            "阴极, 阳极, 注液系数, 夹具, 预紧力, 缓冲垫 etc. "
            "If data_dir is provided, matches cycling data files to template records "
            "by cell ID and runs full DOE coverage analysis."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "template_path": {"type": "string", "description": "Path to 电芯挂测表 template xlsx"},
                "data_dir": {"type": "string", "description": "Optional directory with cycling data xlsx files to match and analyze"},
            },
            "required": ["template_path"],
        },
        "handler": _handle_template_doe,
    },
    {
        "name": "scan_and_import",
        "description": (
            "Scan a directory for battery experiment data files and batch import them. "
            "Automatically detects formats (PEC, Neware, Arbin, generic CSV), matches "
            "design metadata YAML files, and computes cycle summaries."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directory path to scan"},
                "dry_run": {"type": "boolean", "description": "If true, only list files without importing (default: false)"},
            },
            "required": ["directory"],
        },
        "handler": _handle_scan_and_import,
    },
    {
        "name": "search_similar",
        "description": (
            "Search for similar or contrastive historical experiments. "
            "'similar' mode finds datasets with high cosine similarity in combined feature vectors. "
            "'contrast' mode finds datasets with similar design but different degradation patterns."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_id": {"type": "string", "description": "Query dataset ID"},
                "mode": {"type": "string", "description": "'similar' (default) or 'contrast'"},
                "top_k": {"type": "integer", "description": "Number of results (default: 5)"},
            },
            "required": ["data_id"],
        },
        "handler": _handle_search_similar,
    },
    {
        "name": "manage_conclusion",
        "description": (
            "Manage experimental conclusions: add, list, update status, or delete. "
            "Conclusions can be linked to evidence datasets and tracked for verification."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "'list' (default), 'add', 'update', or 'delete'"},
                "conclusion_id": {"type": "string", "description": "Conclusion ID (required for update/delete)"},
                "statement": {"type": "string", "description": "Conclusion statement text (for add/update)"},
                "scope": {"type": "string", "description": "Scope description (e.g., 'NMC811|2C|25C')"},
                "evidence_ids": {"type": "string", "description": "Comma-separated evidence dataset IDs"},
                "confidence": {"type": "string", "description": "low, medium, high"},
                "status": {"type": "string", "description": "active, supported, challenged, superseded, retracted"},
            },
        },
        "handler": _handle_manage_conclusion,
    },
    {
        "name": "verify_with_new_data",
        "description": (
            "Verify all active conclusions against new experimental data. Checks whether "
            "new data supports, challenges, or is inconclusive for each conclusion based on "
            "performance metrics, degradation patterns, and similarity to evidence."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_id": {"type": "string", "description": "New dataset ID to verify against"},
            },
            "required": ["data_id"],
        },
        "handler": _handle_verify_with_new_data,
    },
]

# Handler lookup map for tool calling
HANDLER_MAP = {t["name"]: t["handler"] for t in TOOL_REGISTRY}


# --- Claude Agent SDK Backend ---

def _build_claude_sdk_tools():
    """Build Claude Agent SDK tool objects from TOOL_REGISTRY."""
    from claude_agent_sdk import ToolAnnotations, create_sdk_mcp_server, tool

    sdk_tools = []
    for t in TOOL_REGISTRY:
        # Convert parameters to Claude SDK format (properties only, no "type"/"object" wrapper)
        params = {
            k: v for k, v in t["parameters"]["properties"].items()
        }
        sdk_tool = tool(t["name"], t["description"], params)(t["handler"])
        sdk_tools.append(sdk_tool)

    return create_sdk_mcp_server(name="lmb", version="1.0.0", tools=sdk_tools)


def get_agent_options(cwd: str | Path | None = None):
    """Create ClaudeAgentOptions with the LMB MCP server."""
    from claude_agent_sdk import ClaudeAgentOptions

    from lmbagent.config import SYSTEM_PROMPT

    lmb_server = _build_claude_sdk_tools()

    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"lmb": lmb_server},
        allowed_tools=[f"mcp__lmb__{t['name']}" for t in TOOL_REGISTRY],
        permission_mode="bypassPermissions",
        cwd=str(cwd) if cwd else None,
    )

"""Tool definitions and backend integrations (Claude Agent SDK + LiteLLM)."""

from __future__ import annotations

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

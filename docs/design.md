# LMBAgent - Architecture Design

## Overview

LMBAgent is a lithium metal battery data analysis agent built on the Claude Agent SDK. It provides natural language interaction for loading, analyzing, visualizing, and reporting on battery cycling data.

## Architecture

```
User (natural language) → Claude Agent SDK → MCP Tools → Core Modules → Output
```

### Core Modules

| Module | Responsibility |
|--------|---------------|
| `data/loader.py` | Load PEC CSV and generic CSV battery data |
| `data/transformer.py` | Unit normalization, cycle summary computation |
| `data/models.py` | Pydantic data models (BatteryDataset, etc.) |
| `data/store.py` | In-memory dataset storage |
| `visualization/` | matplotlib-based chart generation |
| `report/generator.py` | Jinja2 template-based report generation |
| `agent.py` | Claude Agent SDK tool definitions + MCP server |
| `main.py` | CLI entry point |

### MCP Tools

6 tools exposed via `create_sdk_mcp_server()`:
1. `load_battery_data` - Load CSV data
2. `transform_data` - Compute/filter cycle summaries
3. `plot_capacity_fade` - Capacity vs cycle chart
4. `plot_coulombic_efficiency` - CE vs cycle chart
5. `plot_voltage_curves` - V vs capacity profiles
6. `generate_report` - Full analysis report

### Data Flow

1. Load raw CSV → parse header + data rows → BatteryDataset
2. Transform: normalize units (mV→V, mA→A, mAh→Ah) → compute cycle summary
3. Visualize: generate matplotlib figures → save as PNG
4. Report: render Jinja2 template with data + chart paths → Markdown/HTML

### Future Interfaces (Phase 3)

Abstract base classes in `interfaces/`:
- `DatabaseInterface` - Query from SQL/NoSQL databases
- `RealtimeInterface` - Near-real-time data ingestion
- `LocalLoaderInterface` - Auto-detect new experiment files
- `MLPredictorInterface` - Cycle life prediction models
- `CloudInterface` - Cloud/AgentScope deployment

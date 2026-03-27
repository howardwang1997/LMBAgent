# LMBAgent

Lithium Metal Battery Data Analysis Agent — an AI-powered tool for loading, analyzing, visualizing, and reporting on battery cycling data.

## Features

- **Multi-model support**: Grok (default), OpenAI, DeepSeek, Claude via LiteLLM
- **PEC CSV parsing**: Auto-detects cellpy PEC format, handles metadata headers, unit conversion (mV→V, mA→A, mAh→Ah)
- **Cycle analysis**: Computes capacity, coulombic efficiency, energy efficiency, impedance per cycle
- **Visualization**: Capacity fade, CE, voltage curves, impedance plots (matplotlib)
- **Report generation**: Markdown, HTML, and PDF output with embedded charts
- **Caching**: Plots generated once per session per dataset
- **Organized output**: Each analysis in `output/<timestamp>_<data_id>/`

## Quick Start

```bash
# Install
conda create -n lmb python=3.12
conda activate lmb
conda install -c conda-forge glib pango  # for PDF export
pip install -e .

# Configure API keys
cp .env.example .env
# Edit .env with your API keys

# Run (default: Grok)
python -m lmbagent "Analyze data/examples/pec.csv and generate a report"

# Quick analyze with PDF output
python -m lmbagent --format pdf --analyze data/examples/pec.csv

# Use other models
python -m lmbagent --model gpt-4o "Analyze data/examples/pec.csv"
python -m lmbagent --model deepseek-chat "Analyze data/examples/pec.csv"
python -m lmbagent --model claude-sonnet "Analyze data/examples/pec.csv"
```

## CLI Options

```
python -m lmbagent [prompt] [options]

Options:
  --model MODEL       Model name (default: grok-4-1-fast-reasoning)
  --provider PROVIDER Provider override (OPENAI, GROK, DEEPSEEK, ANTHROPIC)
  --analyze FILE      Quick analyze: load file and generate full report
  --format FORMAT     Report format: markdown, html, pdf (default: markdown)
  --cwd DIR           Working directory
```

## Architecture

```
User prompt → LiteLLM/Claude Agent SDK → MCP Tools → Core Modules → Output

Core Modules:
  data/loader.py        PEC CSV + generic CSV loading
  data/transformer.py   Unit normalization, cycle summary
  data/models.py        BatteryDataset (Pydantic)
  visualization/        4 matplotlib chart modules
  report/generator.py   Jinja2 template → MD/HTML/PDF
  output.py             Output directory + caching
  config.py             Provider router (Grok/OpenAI/DeepSeek)
  litellm_backend.py    LiteLLM tool calling loop
  agent.py              Tool registry + Claude SDK backend
```

## Output Structure

```
output/20260328_010557_pec_test/
  report_pec_test.md
  report_pec_test.pdf
  plots/
    capacity_fade.png
    coulombic_efficiency.png
    voltage_curves.png
    impedance.png
```

## Environment Variables

```bash
GROK_API_KEY=xai-...          # Default backend
GROK_BASE_URL=https://api.x.ai/v1
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
ANTHROPIC_API_KEY=sk-ant-...  # For --model claude-*
DEFAULT_MODEL=grok-4-1-fast-reasoning
```

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v  # 38 tests
```

## Future (Phase 3 interfaces reserved)

- Database query interface (SQL/NoSQL)
- Real-time data stream analysis
- Local experiment file auto-loading
- ML model cycle life prediction
- Cloud / AgentScope deployment

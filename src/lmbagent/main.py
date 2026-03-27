"""CLI entry point for LMBAgent."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path


async def run_claude_agent(prompt: str, cwd: Path | None = None) -> str:
    """Run the LMB agent via Claude Agent SDK."""
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, query

    from lmbagent.agent import get_agent_options

    options = get_agent_options(cwd=cwd)
    result_text = ""

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)
        elif isinstance(message, ResultMessage):
            if message.subtype == "success":
                result_text = message.result
            elif message.subtype == "error":
                print(f"Agent error: {message.result}", file=sys.stderr)

    return result_text


def main():
    from lmbagent.config import DEFAULT_MODEL

    parser = argparse.ArgumentParser(
        description="LMBAgent: Lithium Metal Battery Data Analysis Agent"
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="Analysis prompt (e.g., 'Load data/examples/pec.csv and generate a full report')",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"Model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="Provider override (OPENAI, GROK, DEEPSEEK, ANTHROPIC)",
    )
    parser.add_argument(
        "--analyze",
        metavar="FILE",
        help="Quick analyze: load file and generate a full report",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "html", "pdf"],
        default="markdown",
        help="Report output format (default: markdown)",
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help="Working directory for the agent",
    )

    args = parser.parse_args()
    cwd = Path(args.cwd) if args.cwd else Path.cwd()

    # Build prompt
    if args.analyze:
        prompt = (
            f"Load the battery data from '{args.analyze}', compute cycle summaries, "
            f"generate all plots (capacity fade, coulombic efficiency, voltage curves, impedance), "
            f"and create a comprehensive report. "
            f"IMPORTANT: When calling generate_report, you MUST set output_format to '{args.format}'. "
            f"Explain the key findings from the data."
        )
    elif args.prompt:
        prompt = args.prompt
    else:
        prompt = (
            "Load the battery data from 'data/examples/pec.csv', compute cycle summaries, "
            "generate all plots, and create a comprehensive markdown report. "
            "Explain the key findings."
        )

    # Select backend: default LiteLLM (Grok), explicit claude-* -> Claude Agent SDK
    model = args.model or os.getenv("DEFAULT_MODEL", DEFAULT_MODEL)

    if model.startswith("claude"):
        print(f"[Backend] Claude Agent SDK")
        result = asyncio.run(run_claude_agent(prompt, cwd=cwd))
    else:
        print(f"[Backend] LiteLLM — model: {model}")
        from lmbagent.litellm_backend import run_litellm_agent
        result = asyncio.run(run_litellm_agent(
            prompt, model=model, provider=args.provider, cwd=str(cwd),
        ))

    if result:
        print(f"\nAgent completed.")


if __name__ == "__main__":
    main()

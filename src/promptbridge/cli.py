from __future__ import annotations

import argparse
from pathlib import Path
import sys

from promptbridge.gateway.orchestrator import PromptBridgeOrchestrator


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    orchestrator = PromptBridgeOrchestrator(args.workspace)

    if args.command == "init":
        workspace = orchestrator.init_workspace()
        print(f"Initialized PromptBridge workspace at: {workspace.root}")
        print(f"- memory: {workspace.memory_dir}")
        print(f"- ledger: {workspace.ledger_path}")
        print(f"- traces: {workspace.traces_dir}")
        return 0

    if args.command == "compile":
        text = " ".join(args.text)
        result = orchestrator.compile(
            text,
            project_id=args.project,
            max_tokens=args.max_tokens,
            translator=args.translator,
            model=args.model,
            endpoint=args.endpoint,
            target=args.target,
            translation_timeout=args.translation_timeout,
            api_key=args.api_key,
        )
        print(result.compiled_prompt.text)
        print(f"\n[PromptBridge] prompt: {result.prompt_path}", file=sys.stderr)
        print(f"[PromptBridge] trace: {result.trace_path}", file=sys.stderr)
        print(
            f"[PromptBridge] translation: {result.translation_result.provider}"
            f" model={result.translation_result.model or 'none'}",
            file=sys.stderr,
        )
        if result.target_package.artifact_path:
            print(f"[PromptBridge] target package: {result.target_package.artifact_path}", file=sys.stderr)
        if result.pii_findings:
            print("[PromptBridge] PII was redacted before prompt assembly.", file=sys.stderr)
        return 0

    if args.command == "search-memory":
        result = orchestrator.search_memory(args.query, limit=args.limit)
        if not result.hits:
            print("No memory hits.")
            return 0
        for hit in result.hits:
            print(f"[{hit.strategy}] {hit.title} score={hit.score:.2f}")
            print(f"  path: {hit.path}")
            print(f"  ref: {hit.ref_id}")
            print(f"  snippet: {hit.snippet}")
        return 0

    if args.command == "reconstruct":
        result = orchestrator.reconstruct(
            args.response_file,
            target_language=args.to,
            project_id=args.project,
        )
        print(result.response.text)
        print(f"\n[PromptBridge] reconstructed: {result.output_path}", file=sys.stderr)
        print(f"[PromptBridge] trace: {result.trace_path}", file=sys.stderr)
        return 0

    if args.command == "dream":
        patch = orchestrator.dream(project_id=args.project)
        print(patch.text)
        print(f"\n[PromptBridge] memory patch proposal: {patch.path}", file=sys.stderr)
        return 0

    if args.command == "trace":
        if args.trace_command == "show":
            if args.target != "latest":
                print("Only `pb trace show latest` is implemented in v0.", file=sys.stderr)
                return 2
            print(orchestrator.latest_trace_summary())
            return 0

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pb",
        description="PromptBridge local-first context gateway CLI.",
    )
    parser.add_argument(
        "--workspace",
        default="workspace",
        help="Workspace directory for memory, ledger, traces, and compiled prompts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create the local PromptBridge workspace.")

    compile_parser = subparsers.add_parser("compile", help="Compile user input into an execution prompt.")
    compile_parser.add_argument("text", nargs="+", help="User input to compile.")
    compile_parser.add_argument("--project", default="promptbridge", help="Active project id.")
    compile_parser.add_argument("--max-tokens", type=int, default=6000, help="Context token budget.")
    compile_parser.add_argument(
        "--translator",
        choices=["none", "ollama", "openai-compatible"],
        default="none",
        help="Local translation/rewrite provider to run before downstream prompt assembly.",
    )
    compile_parser.add_argument("--model", default=None, help="Local translator model name.")
    compile_parser.add_argument("--endpoint", default=None, help="Local translator endpoint URL.")
    compile_parser.add_argument(
        "--translation-timeout",
        type=int,
        default=60,
        help="Timeout in seconds for local translation provider calls.",
    )
    compile_parser.add_argument(
        "--api-key",
        default="local",
        help="API key for OpenAI-compatible local providers; ignored by Ollama.",
    )
    compile_parser.add_argument(
        "--target",
        choices=["stdout", "web-gpt", "cli-plugin"],
        default="stdout",
        help="Where to package the compiled prompt after local translation.",
    )

    search_parser = subparsers.add_parser("search-memory", help="Search local memory files.")
    search_parser.add_argument("query", help="Search query.")
    search_parser.add_argument("--limit", type=int, default=8, help="Maximum hits to return.")

    reconstruct_parser = subparsers.add_parser(
        "reconstruct",
        help="Reconstruct a model response while preserving code and locked terms.",
    )
    reconstruct_parser.add_argument("response_file", type=Path, help="Path to response markdown/text file.")
    reconstruct_parser.add_argument("--to", default="zh", help="Target output language.")
    reconstruct_parser.add_argument("--project", default="promptbridge", help="Active project id.")

    dream_parser = subparsers.add_parser("dream", help="Generate a reviewable MemoryPatch proposal.")
    dream_parser.add_argument("--project", default="promptbridge", help="Active project id.")

    trace_parser = subparsers.add_parser("trace", help="Trace commands.")
    trace_subparsers = trace_parser.add_subparsers(dest="trace_command", required=True)
    trace_show = trace_subparsers.add_parser("show", help="Show trace summary.")
    trace_show.add_argument("target", nargs="?", default="latest", help="Trace id or `latest`.")

    return parser


if __name__ == "__main__":
    raise SystemExit(main())

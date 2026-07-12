from __future__ import annotations

import argparse
from datetime import datetime
from getpass import getpass
import json
from pathlib import Path
import sys

from promptbridge.compiler import CompilationError
from promptbridge.config import (
    KeyringSecretStore,
    ProfileError,
    ProfileStore,
    ProviderProfile,
)
from promptbridge.gateway import PromptBridge
from promptbridge.providers import LLMClient, ProviderError
from promptbridge.storage import (
    AppPaths,
    GlossaryStore,
    GlossaryTerm,
    StorageMaintenance,
    TraceStore,
)


DEFAULT_HOME = Path.home() / ".promptbridge"


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except (CompilationError, ProfileError, ProviderError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"[PromptBridge] error: {exc}", file=sys.stderr)
        if isinstance(exc, ProviderError) and exc.request_id:
            print(f"[PromptBridge] request_id: {exc.request_id}", file=sys.stderr)
        return 1


def _main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = AppPaths(args.home)

    if args.command == "storage":
        return _storage_command(args, StorageMaintenance(paths))

    paths.ensure()
    profiles = ProfileStore(paths.providers_file)
    profiles.ensure()
    secrets = KeyringSecretStore()

    if args.command == "init":
        print(f"PromptBridge home: {paths.home}")
        print(f"Provider profiles: {paths.providers_file}")
        print(f"Glossary: {paths.glossary_file}")
        return 0

    if args.command == "provider":
        return _provider_command(args, profiles, secrets)

    if args.command == "glossary":
        return _glossary_command(args, GlossaryStore(paths.glossary_file))

    if args.command == "trace":
        print(TraceStore(paths.traces_dir).summary())
        return 0

    gateway = PromptBridge(paths.home, profile_store=profiles, secret_store=secrets)
    page_context = _read_optional_file(args.context_file)
    user_input = " ".join(args.text).strip()

    if args.command == "compile":
        result = gateway.compile(
            user_input,
            provider=args.provider,
            model=args.model,
            page_context=page_context,
            timeout_seconds=args.timeout,
            max_retries=args.max_retries,
        )
        print(result.prompt.text)
        print(f"[PromptBridge] prompt: {result.prompt_path}", file=sys.stderr)
        print(f"[PromptBridge] trace: {result.trace_path}", file=sys.stderr)
        return 0

    if args.command == "run":
        result = gateway.run(
            user_input,
            provider=args.provider,
            compiler_provider=args.compiler_provider,
            model=args.model,
            compiler_model=args.compiler_model,
            page_context=page_context,
            timeout_seconds=args.timeout,
            max_retries=args.max_retries,
            max_output_tokens=args.max_output_tokens,
        )
        print(result.answer)
        print(f"[PromptBridge] prompt: {result.prompt_path}", file=sys.stderr)
        print(f"[PromptBridge] response: {result.response_path}", file=sys.stderr)
        print(f"[PromptBridge] trace: {result.trace_path}", file=sys.stderr)
        return 0

    return 2


def _provider_command(
    args: argparse.Namespace,
    profiles: ProfileStore,
    secrets: KeyringSecretStore,
) -> int:
    if args.provider_command == "add":
        profile = ProviderProfile(
            name=args.name,
            protocol=args.protocol,
            base_url=args.base_url,
            default_model=args.model,
            auth=args.auth,
        )
        profiles.add(profile)
        print(f"Added provider {profile.name!r}. Active: {profiles.active_name()}")
        if profile.auth == "bearer":
            print(f"Next: pb provider set-key {profile.name}")
        return 0

    if args.provider_command == "list":
        active = profiles.active_name()
        items = profiles.list()
        if not items:
            print("No provider profiles configured.")
            return 0
        for profile in items:
            marker = "*" if profile.name == active else " "
            print(
                f"{marker} {profile.name}: {profile.protocol} {profile.base_url} "
                f"model={profile.default_model} auth={profile.auth}"
            )
        return 0

    if args.provider_command == "use":
        profiles.set_active(args.name)
        print(f"Active provider: {args.name}")
        return 0

    if args.provider_command == "set-key":
        profile = profiles.get(args.name)
        secret = getpass(f"API key for {profile.name} ({profile.origin}): ")
        secrets.set(profile, secret)
        print(f"Stored API key for {profile.name!r} in the system credential store.")
        return 0

    if args.provider_command == "remove":
        profile = profiles.get(args.name)
        secrets.delete(profile)
        profiles.remove(args.name)
        print(f"Removed provider {args.name!r}.")
        return 0

    if args.provider_command == "test":
        profile = profiles.get(args.name)
        client = LLMClient(
            profile,
            api_key=secrets.get(profile),
            timeout_seconds=args.timeout,
            max_retries=args.max_retries,
        )
        response = client.generate(
            instructions="Reply with exactly OK.",
            input_text="Connection test.",
            stage="connection-test",
        )
        print(response.text)
        print(f"provider={profile.name} model={response.model} latency_ms={response.latency_ms}")
        return 0
    return 2


def _glossary_command(args: argparse.Namespace, glossary: GlossaryStore) -> int:
    if args.glossary_command == "add":
        glossary.add(GlossaryTerm(args.term, args.translation, args.note))
        print(f"Saved glossary term: {args.term}")
        return 0
    if args.glossary_command == "list":
        terms = glossary.list()
        if not terms:
            print("No glossary terms configured.")
            return 0
        for term in terms:
            detail = f" -> {term.translation}" if term.translation else ""
            note = f" ({term.note})" if term.note else ""
            print(f"{term.term}{detail}{note}")
        return 0
    if args.glossary_command == "remove":
        glossary.remove(args.term)
        print(f"Removed glossary term: {args.term}")
        return 0
    return 2


def _storage_command(args: argparse.Namespace, storage: StorageMaintenance) -> int:
    if args.storage_command == "status":
        status = storage.status()
        print(f"PromptBridge storage: {status.home}")
        print(f"- home_exists: {str(status.home_exists).lower()}")
        print(f"- artifacts: {status.artifact_files} files ({_format_bytes(status.artifact_bytes)})")
        print(f"- traces: {status.trace_files} files ({_format_bytes(status.trace_bytes)})")
        print(f"- managed_groups: {status.managed_groups}")
        print(f"- orphan_artifacts: {status.orphan_artifacts}")
        print(f"- unmanaged_files: {status.unmanaged_files}")
        print(f"- total: {status.total_files} files ({_format_bytes(status.total_bytes)})")
        print(f"- oldest: {_format_timestamp(status.oldest)}")
        print(f"- newest: {_format_timestamp(status.newest)}")
        return 0

    if args.storage_command == "clean":
        plan = storage.cleanup_plan(args.older_than)
        mode = "apply" if args.apply else "dry-run"
        print(f"PromptBridge storage cleanup ({mode})")
        print(f"- cutoff: {plan.cutoff.astimezone().isoformat(timespec='seconds')}")
        print(f"- groups: {len(plan.groups)}")
        print(f"- files: {plan.files}")
        print(f"- bytes: {_format_bytes(plan.bytes)}")
        if not args.apply:
            print("No files deleted. Re-run with --apply after reviewing this plan.")
            return 0
        result = storage.apply(plan)
        print(f"Deleted {result.deleted_files} files ({_format_bytes(result.deleted_bytes)}).")
        return 0

    return 2


def _format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.2f} {unit}"
        amount /= 1024
    raise AssertionError("unreachable")


def _format_timestamp(value: datetime | None) -> str:
    return value.astimezone().isoformat(timespec="seconds") if value else "-"


def _read_optional_file(path: Path | None) -> str:
    return path.read_text(encoding="utf-8") if path else ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pb",
        description="PromptBridge local-first multilingual model gateway.",
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=DEFAULT_HOME,
        help=f"Local config, artifacts, and traces directory (default: {DEFAULT_HOME}).",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create the local PromptBridge directory.")

    provider = commands.add_parser("provider", help="Manage model provider profiles.")
    provider_commands = provider.add_subparsers(dest="provider_command", required=True)
    add = provider_commands.add_parser("add", help="Add an OpenAI-compatible provider profile.")
    add.add_argument("name")
    add.add_argument("--protocol", choices=["responses", "chat"], required=True)
    add.add_argument("--base-url", required=True, help="API base URL, usually ending in /v1.")
    add.add_argument("--model", required=True, help="Default model id for this profile.")
    add.add_argument("--auth", choices=["bearer", "none"], default="bearer")
    provider_commands.add_parser("list", help="List provider profiles.")
    use = provider_commands.add_parser("use", help="Set the active provider.")
    use.add_argument("name")
    set_key = provider_commands.add_parser("set-key", help="Save a key in the OS credential store.")
    set_key.add_argument("name")
    remove = provider_commands.add_parser("remove", help="Delete a provider and its stored key.")
    remove.add_argument("name")
    test = provider_commands.add_parser("test", help="Make a small live provider request.")
    test.add_argument("name", nargs="?", default=None)
    test.add_argument("--timeout", type=int, default=60)
    test.add_argument("--max-retries", type=int, default=2)

    glossary = commands.add_parser("glossary", help="Manage exact technical-term locks.")
    glossary_commands = glossary.add_subparsers(dest="glossary_command", required=True)
    glossary_add = glossary_commands.add_parser("add")
    glossary_add.add_argument("term")
    glossary_add.add_argument("--translation", default="")
    glossary_add.add_argument("--note", default="")
    glossary_commands.add_parser("list")
    glossary_remove = glossary_commands.add_parser("remove")
    glossary_remove.add_argument("term")

    storage = commands.add_parser("storage", help="Inspect and clean local runtime files.")
    storage_commands = storage.add_subparsers(dest="storage_command", required=True)
    storage_commands.add_parser("status", help="Show artifact and trace usage without writing files.")
    storage_clean = storage_commands.add_parser(
        "clean",
        help="Preview or delete managed runtime files older than a number of days.",
    )
    storage_clean.add_argument(
        "--older-than",
        type=int,
        default=30,
        metavar="DAYS",
        help="Select managed trace groups older than DAYS (default: 30).",
    )
    storage_clean.add_argument(
        "--apply",
        action="store_true",
        help="Delete the previewed files; without this flag the command is read-only.",
    )

    compile_parser = commands.add_parser("compile", help="Compile a request for a web or CLI model.")
    _add_request_arguments(compile_parser)

    run_parser = commands.add_parser("run", help="Compile and execute a request through configured APIs.")
    _add_request_arguments(run_parser)
    run_parser.add_argument(
        "--compiler-provider",
        default=None,
        help="Optional cheap/local profile for prompt compilation; defaults to --provider.",
    )
    run_parser.add_argument("--compiler-model", default=None)
    run_parser.add_argument("--max-output-tokens", type=int, default=None)

    commands.add_parser("trace", help="Show the latest metadata-only trace.")
    return parser


def _add_request_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("text", nargs="+", help="Request to compile or execute.")
    parser.add_argument("--provider", default=None, help="Provider profile; defaults to active.")
    parser.add_argument("--model", default=None, help="Override the profile's default model.")
    parser.add_argument("--context-file", type=Path, default=None, help="Optional untrusted page context.")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-retries", type=int, default=2)


if __name__ == "__main__":
    raise SystemExit(main())

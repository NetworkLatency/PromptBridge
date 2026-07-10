# PromptBridge

PromptBridge is a local-first, context-first multilingual Agent Gateway. Its first version focuses on a practical CLI loop:

1. Build a Context Kernel for the current user task.
2. Retrieve relevant local memory with exact lookup, SQLite FTS5, and grep-like scan.
3. Apply segment-level context transform policies.
4. Optionally call a local lightweight translation/rewrite model.
5. Compile a cache-aware execution prompt for a downstream web GPT or CLI plugin.
6. Package the prompt for a target surface.
7. Reconstruct model responses while preserving code and locked terms.
6. Record append-only memory events and trace artifacts.
7. Generate auditable `/dream` memory patch proposals.

The project intentionally starts without a vector database, browser extension, MCP catalog, or multi-agent supervisor. Those are later layers after the core context pipeline is observable and useful.

## Quick Start

From the repository root:

```powershell
$env:PYTHONPATH="src"
python -m promptbridge.cli init
python -m promptbridge.cli compile "我想让模型帮我优化一个支持 MCP 的 Agent 项目"
python -m promptbridge.cli compile "我想让模型帮我优化一个支持 MCP 的 Agent 项目" --translator ollama --model YOUR_LOCAL_MODEL --target web-gpt
python -m promptbridge.cli search-memory "工具成本"
python -m promptbridge.cli dream --project promptbridge
python -m promptbridge.cli trace show latest
```

After editable install:

```powershell
pip install -e .
pb compile "我想让模型帮我优化 Agent 架构"
```

## Current v0 Scope

- CLI-first workflow.
- File-based memory workspace under `workspace/memory`.
- Append-only event ledger under `workspace/ledger/events.jsonl`.
- Trace JSON under `workspace/traces`.
- Prompt outputs under `workspace/compiled`.
- Dream patch proposals under `workspace/patches`.
- Target packages under `workspace/outbox`.
- Standard-library implementation for easy inspection and portability.

## Local Translation Providers

PromptBridge does not hard-code a specific local model. v0.1 supports provider interfaces for:

- `none`: skip model-backed translation and keep the pipeline testable.
- `ollama`: call a local Ollama-compatible `/api/chat` endpoint.
- `openai-compatible`: call a local `/v1/chat/completions` endpoint, such as a local inference server.

Example:

```powershell
$env:PYTHONPATH="src"
python -m promptbridge.cli compile "我想优化 MCP 工具加载策略" --translator ollama --model YOUR_LOCAL_MODEL --target web-gpt
```

## Target Surfaces

- `stdout`: print the compiled prompt.
- `web-gpt`: write a paste-ready Markdown package under `workspace/outbox/web_gpt`.
- `cli-plugin`: write a machine-readable JSON package under `workspace/outbox/cli_plugin`.

See `PROJECT_ENGINEERING.md` for design notes, module responsibilities, current limitations, and next implementation steps.

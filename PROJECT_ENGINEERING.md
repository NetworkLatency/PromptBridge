# PromptBridge Engineering Notes

Last updated: 2026-07-05

## Product Positioning

PromptBridge is a context-first multilingual Agent Gateway. The core engineering problem is not "translate the prompt", but:

- what the model should see,
- what should stay as references,
- what should be compressed,
- what should remain in the original language,
- what should be excluded for safety or budget reasons,
- and how every context decision can be audited later.

## v0 Principle

Build the smallest complete local loop before adding heavier integrations:

```text
user input
  -> Context Kernel
  -> Retrieval Router
  -> Segment Policy
  -> Local Translation / Rewrite Provider
  -> Prompt Compiler
  -> Target Adapter
  -> compiled execution prompt
  -> response reconstruction
  -> MemoryLedger event
  -> trace replay / dream patch
```

## Why We Start From Scratch

Large open-source agent frameworks are useful references, but PromptBridge has a specific architecture:

- context-first rather than workflow-first,
- grep/BM25-first rather than vector-first,
- file-first memory rather than opaque database-first memory,
- thin BrowserBridge later rather than browser automation first,
- trace-first evaluation rather than UI demo first.

Starting from a small core keeps the project understandable for interviews and easier to extend with clear design decisions.

## Current Modules

| Module | Responsibility | v0 Status |
|---|---|---|
| `gateway.orchestrator` | Coordinates CLI workflows and writes traces/events | Implemented |
| `context.kernel` | Builds the structured Context Kernel | Implemented |
| `context.segment_policy` | Assigns transform actions per context segment | Implemented with rules |
| `retrieval.router` | Runs exact, FTS, and grep-like local retrieval | Implemented |
| `memory.files` | Manages Markdown/YAML memory workspace | Implemented |
| `memory.ledger` | Append-only JSONL memory events | Implemented |
| `memory.dream_compactor` | Produces auditable memory patch proposals | Implemented as proposal-only |
| `compiler.renderer` | Produces cache-aware execution prompt | Implemented |
| `compiler.reconstruct` | Preserves code blocks and locked terms in response flow | Implemented as deterministic pass-through |
| `translation.providers` | Calls local lightweight translation/rewrite providers | Implemented for `ollama` and `openai-compatible` |
| `targets.adapters` | Packages compiled prompts for downstream surfaces | Implemented for `web-gpt` and `cli-plugin` |
| `safety.pii` | Local PII redaction before prompt assembly | Implemented with basic regex |
| `traces.store` | Saves and displays trace JSON | Implemented |

## v0 Design Decisions

1. Use Python standard library first.
   This avoids dependency friction and makes the project easy to inspect.

2. Use file-based memory plus append-only ledger.
   Markdown/YAML files are grep-friendly and Git-friendly; JSONL events are replayable.

3. Use exact lookup and lexical retrieval first.
   Local project memory, glossary terms, trace records, and user preferences are usually better served by precise retrieval than embeddings.

4. Local translation is a first-class pipeline stage.
   PromptBridge should not rely on the downstream web GPT or CLI model to infer how to translate the user's original non-English input. v0.1 supports local `ollama` and `openai-compatible` providers, while keeping `none` for tests and offline development.

5. Dream compaction produces patches, not direct writes.
   Memory updates should be reviewable. The first implementation writes a proposal file under `workspace/patches`.

6. BrowserBridge and MCP are deferred.
   The core Context Kernel and prompt assembly loop must work before external integrations add complexity.

7. Exact glossary hits suppress duplicate glossary-file snippets.
   If a term such as `MCP` is already retrieved as a locked glossary term, `glossary.yaml` should not also be packed as a generic memory snippet.

8. Dream compaction excludes internal dream events.
   `dream_patch_proposed` events remain in the append-only ledger for audit, but they are not used as source material for the next patch proposal.

9. Target adapters are explicit.
   Web GPT and CLI plugin delivery are different surfaces. PromptBridge packages prompts for them through adapters instead of hiding delivery assumptions inside the prompt compiler.

## Current Commands

```powershell
python -m promptbridge.cli init
python -m promptbridge.cli compile "我想优化 Agent 架构"
python -m promptbridge.cli compile "我想优化 MCP 工具加载策略" --translator ollama --model YOUR_LOCAL_MODEL --target web-gpt
python -m promptbridge.cli search-memory "工具成本"
python -m promptbridge.cli reconstruct response.md --to zh
python -m promptbridge.cli dream --project promptbridge
python -m promptbridge.cli trace show latest
```

## Known Limitations

- Model-backed translation requires a running local provider when `--translator ollama` or `--translator openai-compatible` is selected.
- SQLite FTS5 support depends on the local Python SQLite build; the router falls back to LIKE/grep-like scanning.
- Token counting is heuristic.
- Dream compaction is deterministic and conservative.
- No browser extension, MCP adapter, vector fallback, or remote model provider is included yet.

## Current Verification

Verified on 2026-07-05:

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
python -m promptbridge.cli init
python -m promptbridge.cli compile "我想让模型帮我优化一个支持 MCP 的 Agent 项目"
python -m promptbridge.cli compile "我想优化 MCP 工具加载策略" --target cli-plugin
python -m promptbridge.cli search-memory "工具成本"
python -m promptbridge.cli dream --project promptbridge
python -m promptbridge.cli trace show latest
```

Observed behavior:

- `MCP` is retrieved through exact glossary lookup and marked as `lock_term`.
- Chinese query `工具成本` retrieves the Tool Economy memory decision.
- Compile traces record task type, source language, retrieval hits, selected context segments, and prompt token estimate.
- Compile traces record `translation_provider`, `translation_model`, and target package metadata.
- Dream patch proposals deduplicate repeated events and exclude internal dream maintenance events.
- `cli-plugin` target writes a machine-readable JSON package under `workspace/outbox/cli_plugin`.
- `web-gpt` target writes a paste-ready Markdown package under `workspace/outbox/web_gpt`; auto-submit is intentionally false.

## Requirement Correction From User

The user clarified that PromptBridge is not useful enough if it only compiles context and then starts eval replay. The real product path must first support:

- local lightweight model translation/rewrite,
- downstream web GPT usage,
- downstream CLI plugin usage,
- target-specific prompt packaging,
- and traceability across translation and delivery.

Therefore `pb eval replay` is intentionally postponed until the local translation and target adapter pipeline is stable.

## Next Milestones

1. Add response-side local reconstruction provider for translating downstream GPT/CLI output back to the user's language.
2. Add a thin BrowserBridge native-host protocol for capture/fill without auto-submit.
3. Add a concrete CLI plugin adapter contract and sample plugin.
4. Add tests for FTS fallback, PII redaction, and local provider error handling.
5. Add `pb eval replay` only after local translation and target delivery traces are stable.

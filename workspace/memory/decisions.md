# Project Decisions

- v0 is CLI-first.
- v0 uses Markdown/YAML memory files plus an append-only JSONL ledger.
- v0 compiles cache-aware execution prompts and records trace files for replay.
- Tool Economy Layer exists to control 工具成本 / tool-schema context cost by keeping always-on tools small and deferring heavy tools.
- Local translation/rewrite is a first-class stage before sending prompts to web GPT or CLI plugin targets.
- Target adapters should package prompts for `web-gpt` and `cli-plugin` without auto-submitting to remote models.

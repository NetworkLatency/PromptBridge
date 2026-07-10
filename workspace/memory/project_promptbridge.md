# Project PromptBridge

## Primary User Goal

Build PromptBridge as a resume-quality, context-first multilingual Agent Gateway.

## Current Product Direction

PromptBridge should help non-English users use strong web or API models more effectively through context engineering, selective translation, local retrieval, tool economy, structured memory compaction, and browser collaboration.

## Confirmed Decisions

- Context Kernel Manager is the core module.
- Retrieval should be exact/lexical-first, with vector search only as a later fallback.
- BrowserBridge should stay thin and human-in-the-loop.
- Dream compaction should produce MemoryPatch proposals rather than silently overwriting memory.


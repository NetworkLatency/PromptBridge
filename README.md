# PromptBridge

PromptBridge is a local-first multilingual model gateway for personal use. It compiles a
non-English or mixed-language request into a structured English execution prompt, preserves
code and user-controlled terminology, and either prints the prompt for a web model or executes
it through a configured API.

The current Python core is v0.4.0. A separate v0.1.0 browser extension adds an
offline capture path while keeping the overall scope intentionally small:

```text
selected page text
  -> explicit context-menu action
  -> session-only browser storage
  -> side-panel preview and copy

user request + optional captured context file
  -> exact glossary match
  -> unique protected code and term placeholders
  -> compiler model returns a semantic PromptIR JSON object
  -> strict schema and placeholder validation
  -> conditional English execution prompt assembly, with input material separated from the task
  -> optional raw downstream model execution
  -> local artifacts + metadata-only trace
```

There is no login, hosted backend, database, RAG, long-term memory, MCP, or multi-agent loop.
The extension does not yet call the Python core or any remote model.

## Install

Python 3.11 or newer is required.

```powershell
python -m pip install -e .
pb init
```

PromptBridge stores local configuration under `%USERPROFILE%\.promptbridge` by default.
Use `pb --home <path> ...` to create an isolated demo workspace.

## Provider Profiles

Provider names are user-defined. PromptBridge fixes only two wire protocols:

- `responses`: OpenAI Responses API compatible endpoints.
- `chat`: OpenAI-compatible Chat Completions endpoints.

Official OpenAI example:

```powershell
pb provider add openai `
  --protocol responses `
  --base-url https://api.openai.com/v1 `
  --model <openai-model-id>
pb provider set-key openai
```

OpenRouter or another compatible platform:

```powershell
pb provider add openrouter `
  --protocol chat `
  --base-url https://openrouter.ai/api/v1 `
  --model <provider/model-id>
pb provider set-key openrouter
```

Local Ollama:

```powershell
pb provider add ollama `
  --protocol chat `
  --base-url http://127.0.0.1:11434/v1 `
  --model <local-model-id> `
  --auth none
```

Useful profile commands:

```powershell
pb provider list
pb provider use openrouter
pb provider test openrouter
pb provider remove openrouter
```

API keys are entered through a hidden prompt and stored with the operating-system credential
store through `keyring`. They are not written to `providers.json`, shell history, artifacts,
or traces. Each credential is bound to both the profile name and API origin.

## Compile And Run

Compile a prompt for manual use in a web model:

```powershell
pb compile "请评审这段 API 设计" --provider openrouter
```

Run the full two-stage API path. The compiler can be a cheap or local model while the
downstream provider uses a stronger model:

```powershell
pb run "请评审这段 API 设计" `
  --compiler-provider ollama `
  --provider openrouter
```

Attach text selected from a page or saved response as untrusted context:

```powershell
pb run "根据页面内容总结关键结论" --context-file selected.txt
```

`pb compile` always produces an English execution prompt. It has no prompt-language or
response-language switch. `pb run` currently prints the downstream model's raw answer and does
not ask that model to answer in the user's language. Source language is retained only as local
trace metadata for the planned response-reconstruction stage.

Manage exact glossary locks:

```powershell
pb glossary add MCP --translation "Model Context Protocol"
pb glossary list
```

Inspect the latest metadata-only trace:

```powershell
pb trace
```

## Browser Extension

Node.js 22 or newer is recommended for the WXT toolchain.

```powershell
cd browser_extension
npm.cmd install
npm.cmd run build
```

Load `browser_extension/.output/chrome-mv3` as an unpacked extension from
`chrome://extensions`. Edge uses the equivalent `edge-mv3` output. For Firefox,
open `about:debugging`, choose **This Firefox**, and load
`browser_extension/.output/firefox-mv2/manifest.json` as a temporary add-on.

After loading it, select text on a page and choose **发送到 PromptBridge** from the
context menu. The extension stores the text for the current browser session and opens
the side panel, where the capture can be inspected, copied, or cleared.

The capture boundary is deliberately narrow:

- no content script or host permission;
- no automatic network request or model call;
- no complete page URL: only the HTTP(S) origin is retained;
- no persistent page capture: `storage.session` is cleared with the browser session.

Build and test all supported targets:

```powershell
npm.cmd test
npm.cmd run check
npm.cmd run build
npm.cmd run build:edge
npm.cmd run build:firefox
```

## Local Files

```text
~/.promptbridge/
  providers.json       non-secret provider profiles
  glossary.json        user-controlled exact term locks
  artifacts/           compiled prompts and model responses
  traces/              latency, usage, request ids, errors, and artifact paths
```

The trace stores an input hash and character counts, not the original prompt or response.
Full text exists only in the explicit local artifacts.

Inspect storage without creating or changing the PromptBridge home:

```powershell
pb storage status
```

Cleanup is a dry run by default. It groups each trace with its prompt/response artifacts,
ignores unknown files, and never touches provider profiles, glossary data, or OS credentials:

```powershell
pb storage clean --older-than 30
pb storage clean --older-than 30 --apply
```

## Verification

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
```

The tests use a local mock HTTP server and make no paid API calls.
The extension tests are pure local tests and its production builds make no network requests.

## Compiler Evaluation

Six focused cases cover minimal Chinese input, explicit architecture constraints, protected code
and terminology, an English format request, Spanish input, and malicious page context. Offline
mode uses reviewed golden PromptIR objects and makes no network requests or file writes:

```powershell
python evals/compiler_eval.py --list
python evals/compiler_eval.py --mode offline --show-prompts
```

Live mode runs the same checks against a configured compiler model. Each selected case makes one
model request, so live execution requires an explicit confirmation flag:

```powershell
python evals/compiler_eval.py `
  --mode live `
  --provider openrouter `
  --case minimal_zh `
  --confirm-live `
  --show-prompts
```

The runner calls `PromptCompiler` directly and does not create artifacts or traces. Automatic
checks cover structure, expected semantic keywords, protected content, dynamic sections, and
untrusted-context isolation. Fluency, subtle intent preservation, and plausible-but-invented
requirements still require human review.

## Documentation

- `PROJECT_ENGINEERING.md`: current code flow and module-by-module learning guide.
- `TECHNICAL_POSITIONING.md`: interview narrative, engineering concepts, and rejected alternatives.

Selected-text capture, side-panel preview, and semantic English prompt compilation are
implemented. The next standalone milestone is response reconstruction: translate the captured
downstream answer back to the detected source language while preserving code, terms, links, and
citations. Browser-to-core loopback integration follows after both transforms are independently
testable.

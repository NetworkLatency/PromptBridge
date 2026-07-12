# PromptBridge

PromptBridge is a local-first multilingual model gateway for personal use. It rewrites a
non-English request into an English execution prompt, preserves code and locked technical
terms, and either prints the prompt for a web model or executes it through a configured API.

The current Python core is v0.3.0. A separate v0.1.0 browser extension adds an
offline capture path while keeping the overall scope intentionally small:

```text
selected page text
  -> explicit context-menu action
  -> session-only browser storage
  -> side-panel preview and copy

user request + optional captured context file
  -> exact glossary match
  -> protected code and term placeholders
  -> compiler model rewrites only the task
  -> deterministic execution prompt assembly
  -> optional downstream model execution
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
pb compile "请评审这段 API 设计" --provider openrouter --to Chinese
```

Run the full two-stage API path. The compiler can be a cheap or local model while the
downstream provider uses a stronger model:

```powershell
pb run "请评审这段 API 设计" `
  --compiler-provider ollama `
  --provider openrouter `
  --to Chinese
```

Attach text selected from a page or saved response as untrusted context:

```powershell
pb run "根据页面内容总结关键结论" --context-file selected.txt --to Chinese
```

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

## Verification

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
```

The tests use a local mock HTTP server and make no paid API calls.
The extension tests are pure local tests and its production builds make no network requests.

## Documentation

- `PROJECT_ENGINEERING.md`: current code flow and module-by-module learning guide.
- `TECHNICAL_POSITIONING.md`: interview narrative, engineering concepts, and rejected alternatives.

Selected-text capture and side-panel preview are implemented. The next milestone is the
explicit loopback connection between the extension and the existing Python core.

# PromptBridge 当前代码逻辑说明

最后更新：2026-07-12
对应版本：Python Core v0.3.0 / Browser Extension v0.1.0

本文只描述仓库中已经实现并通过测试的代码，不把规划中的 BrowserBridge、
本地 HTTP 服务、长期记忆或评测系统写成已完成功能。当前 Browser Extension 只完成
用户主动捕获与侧栏预览，还没有和 Python Core 通信。

## 1. 当前产品边界

PromptBridge 目前是一个个人使用的本地 CLI 核心，解决三个问题：

1. 把非英语任务改写为适合下游强模型执行的英文任务。
2. 在改写过程中程序化保护代码块和用户术语表中的专业词。
3. 通过可切换的 Provider Profile 调用 OpenAI Responses API 或
   OpenAI-compatible Chat Completions API。
4. 通过浏览器右键菜单主动捕获选中文本，并在侧栏中预览、复制或清除。

它当前不负责：

- 登录、用户、权限和云端部署；
- 数据库、向量检索和长期会话记忆；
- MCP、工具调用和多 Agent 编排；
- 自动操作或自动提交第三方网页；
- 浏览器插件与 Python Core 之间的本机通信。

最后一项是下一里程碑。浏览器捕获与 Python 核心保持独立，避免在通信协议尚未确定时
把前后端耦合在一起。

## 2. 最终代码结构

```text
src/promptbridge/
  __init__.py       版本信息
  cli.py            所有命令行入口和参数解析
  config.py         Provider Profile 与系统凭据库
  providers.py      Responses / Chat 两种 HTTP 协议
  compiler.py       选择性改写、占位符保护、Prompt 组装
  gateway.py        compile / run 两条用例的编排
  storage.py        路径、Glossary、Trace
  utils.py          少量通用文件与 ID 函数

tests/
  test_config.py    配置和 URL 安全边界
  test_compiler.py  代码、术语和不可信上下文
  test_gateway.py   两种协议、两阶段调用、重试和 Trace

browser_extension/
  wxt.config.ts                 WXT 构建目标和最小权限
  lib/captured-context.ts       捕获数据的构造与运行时校验
  lib/capture-store.ts          storage.session 读写
  entrypoints/background.ts     右键菜单和跨浏览器侧栏打开逻辑
  entrypoints/sidepanel/        Vanilla TS 侧栏界面
  tests/captured-context.test.ts 纯数据边界测试
```

推荐按照下面的顺序阅读：

1. `compiler.py`
2. `config.py`
3. `providers.py`
4. `gateway.py`
5. `cli.py`
6. `storage.py`
7. `browser_extension/lib/captured-context.ts`
8. `browser_extension/entrypoints/background.ts`
9. `browser_extension/entrypoints/sidepanel/main.ts`

这样可以先理解产品核心，再看网络和命令行细节。

## 3. 五个核心数据结构

### 3.1 ProviderProfile

位置：`config.py`

```python
ProviderProfile(
    name="openrouter",
    protocol="chat",
    base_url="https://openrouter.ai/api/v1",
    default_model="vendor/model",
    auth="bearer",
)
```

字段含义：

- `name`：用户自己定义的配置名，不是写死的平台枚举。
- `protocol`：只能是 `responses` 或 `chat`。
- `base_url`：API 基础地址，通常以 `/v1` 结尾。
- `default_model`：该 Profile 默认使用的模型 ID。
- `auth`：`bearer` 表示需要密钥，`none` 用于 Ollama 等本地服务。

Profile 保存到 `providers.json`，其中没有 API Key。

### 3.2 RequestContext

位置：`compiler.py`

```python
RequestContext(
    user_input="用户任务",
    output_language="Chinese",
    page_context="用户从网页选中的文本",
    glossary=(...),
)
```

这取代了旧版 Context Kernel。它没有固定 token budget、任务分类、项目 ID、
retrieval refs 或 reasoning language，因为当前闭环没有真实需求使用这些字段。

### 3.3 LLMResponse

位置：`providers.py`

Responses 和 Chat 两种 API 最终都被归一化为：

```text
provider
protocol
model
text
usage
request_id
response_id
finish_reason
latency_ms
```

业务层因此不需要理解不同平台的原始 JSON 结构。

### 3.4 CompiledPrompt

位置：`compiler.py`

它包含：

- `text`：最终交给网页模型或 API 模型的完整 Prompt；
- `rewritten_task`：模型生成的英文任务；
- `locked_terms`：本轮实际匹配的术语；
- `rewrite_response`：编译阶段的标准化调用结果。

### 3.5 CapturedContext

位置：`browser_extension/lib/captured-context.ts`

```typescript
interface CapturedContext {
  text: string;
  pageTitle: string;
  sourceOrigin: string;
  capturedAt: string;
}
```

这个结构只表示用户本次主动捕获的数据：

- `text` 保留完整选中文本，不设置任意字符预算；
- `pageTitle` 用于人工确认来源；
- `sourceOrigin` 只保留 `https://example.com`，不保存可能含隐私参数的完整 URL；
- `capturedAt` 是 ISO 8601 时间，用于界面展示和后续通信去重。

从浏览器存储读取后会执行运行时 shape 校验，避免把损坏或旧版本数据直接渲染。

## 4. Provider 配置流程

### 4.1 添加 Profile

```powershell
pb provider add openrouter `
  --protocol chat `
  --base-url https://openrouter.ai/api/v1 `
  --model <model-id>
```

调用路径：

```text
cli._provider_command
  -> ProviderProfile.__post_init__
  -> ProfileStore.add
  -> providers.json
```

`ProviderProfile` 会立即检查：

- 名称是否合法；
- 协议和鉴权模式是否受支持；
- URL 是否为绝对地址；
- URL 中是否偷偷包含用户名或密码；
- 远程地址是否使用 HTTPS；
- HTTP 地址是否仅指向 `localhost`、`127.0.0.1` 或 `::1`。

### 4.2 保存密钥

```powershell
pb provider set-key openrouter
```

调用路径：

```text
getpass 隐藏输入
  -> KeyringSecretStore.set
  -> Windows Credential Locker / macOS Keychain / Linux Secret Service
```

凭据用户名由下面两部分组成：

```text
<profile-name>@<api-origin>
```

例如：

```text
openrouter@https://openrouter.ai
```

因此，即使以后重新创建了同名 Profile，只要 API Origin 改变，旧密钥就不会被
自动发送到新地址。

## 5. `pb compile` 完整流程

示例：

```powershell
pb compile "请使用 MCP 评审这段代码" --provider openrouter --to Chinese
```

### 第一步：解析命令

`cli.py` 负责解析文本、Provider、模型覆盖、目标语言和可选 `--context-file`。
CLI 不包含业务规则，只负责把参数交给 `PromptBridge.compile`。

### 第二步：读取本地上下文

`gateway.py` 从 `glossary.json` 做大小写不敏感的 exact match。

它不会：

- 搜索历史对话；
- 启动 SQLite FTS；
- 生成 embedding；
- 自动扩展上下文。

当前唯一的持久上下文是用户明确维护的术语表。

### 第三步：构造 RequestContext

```text
user_input
output_language
page_context
matched glossary terms
```

没有自动任务分类。没有声称控制模型的“推理语言”。没有按 memory、retrieval、
glossary 分配固定 token 配额。

### 第四步：保护不可变内容

`compiler._protect` 使用正则识别 fenced code block，并替换为：

```text
[[PB_CODE_0000]]
```

用户输入中匹配到的术语被替换为：

```text
[[PB_TERM_0000]]
```

原值只作为 JSON 中的参考数据提供给编译模型。编译模型被要求只输出英文任务，
同时原样返回所有 placeholder。

### 第五步：调用编译模型

`LLMClient.generate` 根据 Profile 的 `protocol` 选择请求格式：

```text
responses -> POST <base_url>/responses
chat      -> POST <base_url>/chat/completions
```

两者都支持：

- Bearer API Key；
- 每次请求 timeout；
- 对 408、409、429、5xx 的有限重试；
- `Retry-After`；
- request ID、usage 和 latency 提取；
- 非 JSON、空输出和异常响应结构的显式报错；
- 禁止 HTTP redirect，避免凭据被转发到另一个 URL。

### 第六步：恢复和验证

`compiler._restore` 检查每一个 placeholder 是否仍存在。

如果编译模型丢掉代码或术语，流程抛出 `CompilationError`，不会悄悄生成一个
可能缺少约束的 Prompt。验证通过后再恢复原始代码和术语。

### 第七步：确定性组装

最终 Prompt 的顺序固定为：

```text
Execution Policy
Task
Locked Terms
Untrusted Page Context
```

网页上下文不会参与任务改写，而是在最后作为 JSON string 附加，并明确标记为
`Untrusted Page Context`。这不能数学上消除 prompt injection，但建立了清晰的数据边界。

### 第八步：保存结果

```text
~/.promptbridge/artifacts/<trace_id>.prompt.md
~/.promptbridge/traces/<trace_id>.json
```

CLI 同时把编译结果打印到标准输出，方便粘贴到网页端模型。

## 6. `pb run` 完整流程

示例：

```powershell
pb run "请评审这个模块" `
  --compiler-provider ollama `
  --provider openrouter `
  --to Chinese
```

它执行两个阶段：

```text
阶段 1：compiler-provider 把任务编译为英文执行 Prompt
阶段 2：provider 执行 Prompt 并直接按目标语言回答
```

`compiler-provider` 未指定时，使用执行 Provider。两个阶段都可以通过参数覆盖模型。

当前不再做第三次 response reconstruction。原因是执行 Prompt 已包含目标语言要求，
每次强制回译会增加约 50% 的 API 调用次数、延迟和另一次内容失真机会。

成功后生成：

```text
artifacts/<trace_id>.prompt.md
artifacts/<trace_id>.response.md
traces/<trace_id>.json
```

## 7. Trace 内容

Trace 默认保存：

- command 和状态；
- 输入 SHA-256 与字符数；
- 是否包含 page context；
- 匹配到的 glossary terms；
- Provider、协议、模型和 base URL；
- latency、usage、request ID、response ID；
- artifact 路径；
- 失败阶段、异常类型和截断后的错误信息。

Trace 默认不保存：

- API Key；
- 原始用户输入；
- 编译后的正文；
- 模型回答正文。

正文只存在于用户本机明确可见的 artifact 文件中。

## 8. 本地文件

默认位置：`%USERPROFILE%\.promptbridge`

```text
.promptbridge/
  providers.json
  glossary.json
  artifacts/
  traces/
```

测试或演示时可以隔离目录：

```powershell
pb --home .demo init
pb --home .demo provider list
```

## 9. 测试覆盖

运行：

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
```

当前 Python Core 的 6 个测试覆盖：

1. Profile 添加、切换和删除。
2. 拒绝远程 HTTP 和 URL 内嵌凭据。
3. 代码块、术语和网页上下文的边界。
4. 编译模型丢失 placeholder 时 fail closed。
5. Responses 编译 + Chat 执行的两阶段组合。
6. 独立 Provider Key、metadata-only trace 和 429 重试。

测试启动本地 mock HTTP server，不发起计费请求。

Browser Extension 另有 6 个 Vitest 测试，覆盖空选择、文本保真、URL 隐私边界、
非网页 URL、无任意字符预算以及存储 payload 校验。运行：

```powershell
cd browser_extension
npm.cmd test
npm.cmd run check
```

## 10. Browser Extension 捕获流程

浏览器扩展使用 WXT 0.20.27 和 Vanilla TypeScript，没有 React/Vue，也没有 content script。

```text
用户在网页上选中文本
  -> contextMenus(selection)
  -> background 读取 selectionText 与 tab 元数据
  -> createCapturedContext 只保留正文、标题和 URL origin
  -> 在用户手势内发起打开 Chrome/Edge sidePanel 或 Firefox sidebarAction
  -> 同时写入 browser.storage.session
  -> side panel 读取并预览
  -> 用户主动复制或清除
```

关键边界：

- 不申请 `activeTab`、`scripting` 或任何 host permission；
- 不读取整页 DOM，浏览器只在用户手势后提供已选中的 `selectionText`；
- 不把网页内容当 HTML 渲染，只写入 `textContent` 或 `textarea.value`；
- 不自动调用 API，也不把捕获数据发送到插件外部；
- 使用 `storage.session`，浏览器会话结束后自动清除；
- Chrome 和 Edge 生成 MV3 `side_panel`，Firefox 生成 MV2 `sidebar_action`；
- Firefox manifest 明确声明 `data_collection_permissions.required = ["none"]`。

生产构建命令：

```powershell
cd browser_extension
npm.cmd run build
npm.cmd run build:edge
npm.cmd run build:firefox
```

三份 manifest 都不包含 host permissions。构建产物约 12 KB，位于 `.output/`，不提交 Git。

`package.json` 还对 WXT 开发工具链中的 `esbuild`、`shell-quote`、`tmp` 和 `uuid` 使用
精确安全 override。override 后完整 `npm audit` 为 0，且 TypeScript 检查、Vitest 和三份
生产构建均重新通过；没有采用会把 WXT 降级到旧主版本的 `npm audit fix --force`。

## 11. 已删除的旧代码

本次精简删除了：

- 固定 Context TokenBudget；
- task type 和 reasoning language 猜测；
- exact / FTS / grep Retrieval Router；
- Markdown Memory Workspace、MemoryLedger 和 DreamCompactor；
- 独立 execution / reconstruction / translation 三套 Provider；
- web-gpt / cli-plugin / openai-api Target Package；
- regex PII 层；
- 三次模型调用与 response reconstruction；
- 示例 memory 文件。

这些不是永远禁止，而是当前没有真实数据量、工具数量或用户行为证明它们值得存在。

## 12. 当前限制

- 浏览器主动捕获已实现，但 `127.0.0.1` 本机 HTTP 服务和 Python Core 通信尚未实现。
- 尚未在 Safari 上构建；Safari 需要额外的 macOS/Xcode 包装流程。
- 自动化测试覆盖数据变换和三浏览器构建，右键原生菜单仍需要真实浏览器人工验收。
- 只支持非流式文本请求。
- OpenAI-compatible 平台可能只实现部分字段，需要通过 `pb provider test` 验证。
- 还没有真实 API 的自动化 CI 测试，避免泄漏密钥和产生费用。
- fenced code block 已保护，inline code、数学公式、HTML 和 diff 尚未单独保护。
- Prompt injection 只能通过数据边界、预览和人工确认降低风险，不能完全消除。
- 本地 8GB 显存模型的质量和延迟尚未完成基准测试。

## 13. 下一里程碑

当前已完成：

```text
Chrome / Edge / Firefox
  -> 用户主动捕获选中文本
  -> 会话态侧栏预览和复制
```

下一阶段只增加余下的垂直链路：

```text
Side Panel 中的用户任务
  -> 127.0.0.1 本机 PromptBridge 服务
  -> 当前 compile / run 核心
  -> Side Panel 展示模型结果
```

在这条浏览器闭环稳定前，不恢复 Retrieval、Dream、MCP、多 Agent 或向量数据库。

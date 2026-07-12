# PromptBridge 当前代码逻辑说明

最后更新：2026-07-12
对应版本：Python Core v0.4.0 / Browser Extension v0.1.0

本文只描述仓库中已经实现并通过测试的代码，不把规划中的 BrowserBridge、
本地 HTTP 服务、长期记忆或评测系统写成已完成功能。当前 Browser Extension 只完成
用户主动捕获与侧栏预览，还没有和 Python Core 通信。

## 1. 当前产品边界

PromptBridge 目前是一个个人使用的本地 CLI 核心，解决四个问题：

1. 把非英语或混合语言任务语义重构为结构化英文执行 Prompt。
2. 用严格 PromptIR 和占位符契约验证模型输出，而不是直接接受自由文本。
3. 通过可切换的 Provider Profile 调用 OpenAI Responses API 或
   OpenAI-compatible Chat Completions API。
4. 通过浏览器右键菜单主动捕获选中文本，并在侧栏中预览、复制或清除。

它当前不负责：

- 登录、用户、权限和云端部署；
- 数据库、向量检索和长期会话记忆；
- MCP、工具调用和多 Agent 编排；
- 自动操作或自动提交第三方网页；
- 把下游英文回答转换回用户母语；
- 浏览器插件与 Python Core 之间的本机通信。

回答重构是下一个独立里程碑，本机通信随后实现。这样先分别验证输入编译和输出翻译，
再把浏览器与 Python 核心连接起来，失败时更容易定位是哪一侧的问题。

## 2. 最终代码结构

```text
src/promptbridge/
  __init__.py       版本信息
  cli.py            所有命令行入口和参数解析
  config.py         Provider Profile 与系统凭据库
  providers.py      Responses / Chat 两种 HTTP 协议
  compiler.py       PromptIR、占位符保护、严格校验与条件渲染
  gateway.py        compile / run 两条用例的编排
  storage.py        路径、Glossary、Trace 与安全清理计划
  utils.py          少量通用文件与 ID 函数

tests/
  test_cli.py       CLI 对外参数契约
  test_config.py    配置和 URL 安全边界
  test_compiler.py  PromptIR、动态章节、代码、术语和不可信上下文
  test_gateway.py   两种协议、两阶段调用、重试和 Trace
  test_storage.py   只读统计、dry-run 与受控清理

evals/
  compiler_eval.py  6 个离线 golden / 可选真实 Provider 语义评测样例

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

## 3. 六个核心数据结构

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
    page_context="用户从网页选中的文本",
    glossary=(...),
)
```

这取代了旧版 Context Kernel。它没有固定 token budget、任务分类、项目 ID、
retrieval refs、reasoning language 或 response language，因为当前闭环没有真实需求使用
这些字段。它只承载编译前已经确定的数据。

### 3.3 PromptIR

位置：`compiler.py`

编译模型不能再返回一段无法检查的自由文本，而必须返回下面的 JSON 语义结构：

```json
{
  "source_language": "Simplified Chinese",
  "objective": "Review the API architecture.",
  "context": [],
  "input_material": [],
  "constraints": ["Do not introduce a hosted database."],
  "expected_deliverable": null,
  "output_preferences": []
}
```

字段规则：

- `source_language` 和 `objective` 必填；
- `context`、`input_material`、`constraints` 和 `output_preferences` 是可选语义列表；
- `input_material` 用来承载代码或等待处理的用户材料，避免把代码块塞进目标句；
- `expected_deliverable` 只有请求确实定义具体交付物时才使用，否则为 `null`；
- `source_language` 使用英文语言名称，其余语义内容也必须是英文；
- 空字段不会在最终 Prompt 中生成空章节。

这里稳定的是数据契约，不是用户需求。系统不会默认添加表格、字数、语气、受众或固定
交付物。

### 3.4 LLMResponse

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

### 3.5 CompiledPrompt

位置：`compiler.py`

它包含：

- `text`：最终交给网页模型或 API 模型的完整 Prompt；
- `prompt_ir`：解析、类型检查并恢复占位符后的 PromptIR；
- `locked_terms`：本轮实际匹配的术语；
- `compiler_response`：编译阶段的标准化调用结果。

### 3.6 CapturedContext

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
pb compile "请使用 MCP 评审这段代码" --provider openrouter
```

### 第一步：解析命令

`cli.py` 负责解析文本、Provider、模型覆盖和可选 `--context-file`。
CLI 不包含业务规则，只负责把参数交给 `PromptBridge.compile`。

V0 没有 `--to`：Prompt Compiler 固定生成英文执行 Prompt，也不会要求下游模型使用某种
语言回答。

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

用户输入中每一次匹配到的术语都会得到独立占位符：

```text
[[PB_TERM_0000]]
```

术语有 `translation` 时，该值是恢复后的规范英文词；否则保留原词。代码原值和术语映射
作为 JSON 参考数据提供给编译模型，但模型输出中仍只能放 placeholder。

### 第五步：调用编译模型

编译模型不再返回自由文本，而是返回 PromptIR JSON。系统指令明确要求：

- 只重构任务，不回答任务；
- 英文化语义内容；
- 不虚构约束、输出格式、长度、事实或偏好；
- 每个 placeholder 恰好返回一次；
- 把代码等待处理材料放入 `input_material`，而不是嵌入目标句；
- `constraints`、`expected_deliverable` 和 `output_preferences` 根据实际请求填写。

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

`compiler._parse_prompt_ir` 首先执行结构校验：

- 必须是单个 JSON object；
- 拒绝未知字段和重复字段；
- 必填字符串不能是空值；
- 列表只能包含非空字符串；
- `expected_deliverable` 只能是 `null` 或非空字符串。

随后检查每个 placeholder 是否恰好出现一次，同时拒绝模型新造的 placeholder。

任何检查失败都会抛出 `CompilationError`，不会把半结构化或缺失内容的结果继续交给下游
模型。验证通过后才恢复原始代码和规范术语。

### 第七步：确定性组装

最终 Prompt 只有 `Task` 必定存在，其余章节按 PromptIR 和输入内容条件渲染：

```text
Task                   必选
Context                可选
Input Material         有用户材料时出现
Constraints            可选
Expected Deliverable   可选
Output Preferences     可选
Terminology            有术语命中时出现
Untrusted Page Context 有网页上下文时出现
```

这不是把用户请求套进固定模板：固定的是允许出现的章节顺序和验证规则，具体章节及内容由
本轮请求决定。网页上下文不会参与任务重构，而是在最后作为 JSON string 附加，并明确标记
为 `Untrusted Page Context`。这不能数学上消除 prompt injection，但建立了清晰的数据边界。

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
  --provider openrouter
```

它执行两个阶段：

```text
阶段 1：compiler-provider 生成并验证英文执行 Prompt
阶段 2：provider 执行 Prompt，PromptBridge 原样返回模型回答
```

`compiler-provider` 未指定时，使用执行 Provider。两个阶段都可以通过参数覆盖模型。

执行阶段没有 response-language 指令。英文 Prompt 通常会得到英文回答，但这不是代码保证；
当前 `run` 返回任何实际语言的原始回答。将回答转换回 `source_language` 是下一独立模块
`Response Reconstructor` 的责任，目前尚未实现。

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
- 编译模型识别的 source language 和固定的 English prompt language；
- 各可选 PromptIR 字段的条目数量或存在状态；
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

查看存储不会创建缺失的 home：

```powershell
pb storage status
```

清理按 `trace_id` 将 trace、prompt 和 response 作为一个组，以组内最新修改时间判断年龄：

```powershell
pb storage clean --older-than 30
pb storage clean --older-than 30 --apply
```

第一条命令只输出计划。只有显式 `--apply` 才调用 `Path.unlink()` 删除已识别文件。
未知文件、子目录、`providers.json`、`glossary.json` 和 Keyring 都不属于清理范围；存储目录
如果通过符号链接逃出 PromptBridge home，清理会 fail closed。

## 9. 测试覆盖

运行：

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
```

当前 Python Core 的 13 个测试覆盖：

1. CLI 已移除 prompt/response language 参数。
2. PromptIR 动态章节与 source language 元数据。
3. 非法 JSON、未知/重复字段和错误字段类型 fail closed。
4. 代码块、术语规范翻译和网页上下文边界。
5. placeholder 缺失、重复或伪造时 fail closed。
6. Profile 添加、切换和删除。
7. 拒绝远程 HTTP 和 URL 内嵌凭据。
8. Responses 编译 + Chat 执行的两阶段组合。
9. 独立 Provider Key、metadata-only trace 和 429 重试。
10. 在 home 不存在时只读统计不会创建文件。
11. 按年龄删除完整 trace group，同时保留近期文件、未知文件和配置。
12. CLI clean 默认 dry-run，只有显式 `--apply` 才删除。

这里列的是能力分组；`unittest` 当前实际报告 13 个 test methods。

测试启动本地 mock HTTP server，不发起计费请求。

Browser Extension 另有 6 个 Vitest 测试，覆盖空选择、文本保真、URL 隐私边界、
非网页 URL、无任意字符预算以及存储 payload 校验。运行：

```powershell
cd browser_extension
npm.cmd test
npm.cmd run check
```

### 9.1 Compiler Case Suite

单元测试证明程序契约，但不能证明真实模型是否正确理解用户意图。因此仓库增加了一个窄
评测入口，而不是完整 `eval replay` 平台：

```powershell
python evals/compiler_eval.py --list
python evals/compiler_eval.py --mode offline --show-prompts
```

当前 6 个场景覆盖：

1. 没有额外要求的最小中文问题，检查是否凭空生成章节。
2. 带约束、受众和交付物的中文架构任务。
3. 中文、Python 代码和规范英文术语混合输入。
4. 明确要求 decision table 的英文任务。
5. 西班牙语输入中的约束保真。
6. 含恶意指令的网页上下文隔离。

离线模式使用人工检查过的 golden PromptIR，只验证解析、恢复、渲染和评测器本身。真实
模型模式每个 case 发起一次请求，因此必须显式指定 `--confirm-live`：

```powershell
python evals/compiler_eval.py `
  --mode live `
  --provider openrouter `
  --case minimal_zh `
  --confirm-live `
  --show-prompts
```

脚本直接调用 `PromptCompiler`，不经过 Gateway，因此不会生成 artifact 或 trace。自动检查
只能覆盖字段、关键词、动态章节、placeholder 和不可信上下文边界；英文自然度、细微意图
偏移和“听起来合理但用户没说”的新增要求仍需人工按 0-2 分检查。

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
- 旧版无结构校验的 execution / reconstruction / translation 三套 Provider；
- web-gpt / cli-plugin / openai-api Target Package；
- regex PII 层；
- 每次请求都强制执行的第三次 response reconstruction；
- 示例 memory 文件。

这些不是永远禁止，而是当前没有真实数据量、工具数量或用户行为证明它们值得存在。

## 12. 当前限制

- 浏览器主动捕获已实现，但 `127.0.0.1` 本机 HTTP 服务和 Python Core 通信尚未实现。
- 尚未在 Safari 上构建；Safari 需要额外的 macOS/Xcode 包装流程。
- 自动化测试覆盖数据变换和三浏览器构建，右键原生菜单仍需要真实浏览器人工验收。
- 只支持非流式文本请求。
- OpenAI-compatible 平台可能只实现部分字段，需要通过 `pb provider test` 验证。
- 还没有真实 API 的自动化 CI 测试，避免泄漏密钥和产生费用。
- Response Reconstructor 尚未实现，因此 `pb run` 当前输出下游模型的原始回答。
- `source_language` 由 compiler model 识别，还没有独立语言检测基线。
- PromptIR schema 能验证结构和保真占位符，但尚不能确定性证明自然语言字段都是英文；
  这一质量约束目前依赖 compiler 指令，并需要真实多语言评测。
- 6 个 compiler case 已通过离线 golden 检查，但本机尚未配置 Provider，因此还没有真实模型
  的 case-suite 结果。
- fenced code block 已保护，inline code、数学公式、HTML 和 diff 尚未单独保护。
- Prompt injection 只能通过数据边界、预览和人工确认降低风险，不能完全消除。
- 本地 8GB 显存模型的质量和延迟尚未完成基准测试。

## 13. 下一里程碑

当前已完成两段可独立测试的输入链路：

```text
母语或混合语言请求
  -> PromptIR 语义重构与严格校验
  -> 条件渲染的英文执行 Prompt

Chrome / Edge / Firefox
  -> 用户主动捕获选中文本
  -> 会话态侧栏预览和复制
```

下一阶段只实现输出侧的 `Response Reconstructor`：

```text
下游模型原始回答
  -> 识别并保护代码、术语、链接和引用
  -> 翻译自然语言说明
  -> 恢复受保护内容
  -> 用户母语回答
```

该模块验收后再实现 `127.0.0.1` 浏览器闭环。在完整输入/输出变换稳定前，不恢复
Retrieval、Dream、MCP、多 Agent 或向量数据库。

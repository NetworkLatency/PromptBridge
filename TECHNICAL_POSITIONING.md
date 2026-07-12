# PromptBridge 技术观点与面试说明

最后更新：2026-07-12
对应版本：Python Core v0.3.0 / Browser Extension v0.1.0

本文用于解释 PromptBridge 采用了哪些当前 Agent 工程思想，以及为什么主动没有采用
一些更热门但不适合当前规模的方案。

## 1. 一句话定位

PromptBridge 是一个本地优先的多语言模型 Gateway。它通过选择性任务改写、代码与
术语保真、用户主动网页捕获、可切换的 OpenAI-compatible Provider Profile 和 metadata-only trace，
帮助非英语用户把网页上下文和任务可靠地交给 API 或网页端强模型。

它是 Gateway 和浏览器助手的核心，不是自主多 Agent 平台。

## 2. 90 秒面试介绍

> 多语言模型的能力并不完全均衡，但把所有内容无条件翻译成英文也会破坏代码、术语
> 和上下文细节。因此我实现了 PromptBridge：系统只改写用户任务，把代码块、API 名称
> 和术语作为不可变 segment 保护，把网页选中文本作为不可信数据单独附加，然后将结果
> 交给网页模型或可配置的 API Provider。Provider 层按协议而不是平台名称抽象，所以
> OpenAI、OpenRouter、PAI、Ollama 或 vLLM 可以通过配置切换。密钥保存在操作系统凭据库，
> 每次请求记录延迟、usage、request ID 和失败阶段，但默认不把原始正文写入 trace。
> 浏览器端使用一个没有 host permission 和 content script 的 WXT 薄插件，只有用户右键
> 确认时才捕获选中文本，并暂存在会话内存中。
> 我主动没有引入向量数据库、MCP、多 Agent 和复杂长期记忆，因为当前产品没有对应的
> 数据量或工具规模。这些取舍让项目保持可验证、可维护，也能说明每一层为何存在。

## 3. Context-first，但不做虚假的 Context Kernel

### 观点

Context engineering 的核心是决定模型看到什么，以及不同内容以什么身份进入请求，
而不是给一个大 JSON 起名叫 Context Kernel。

PromptBridge 当前只管理四类真实上下文：

```text
用户任务
目标输出语言
用户选中的网页文本
精确匹配的术语
```

### 为什么不用旧版固定 Budget

旧版包含 `reserved_for_memory`、`reserved_for_retrieval` 等固定配额，但当前项目既没有
大量 memory，也没有文档检索。固定配额会制造一种“已经实现精细上下文控制”的错觉，
还可能无理由截断用户内容。

当前策略是：

- 不自动截断；
- 记录字符数和 Provider 返回的真实 usage；
- 让 Provider 返回 context-length error；
- 将来出现多个竞争上下文来源时，再加入有数据支持的优先级和预算。

面试表达：

> 我保留了 context selection，但删除了没有运行时作用的 budget allocator。先测量，
> 再根据真实失败案例制定压缩策略，而不是预先分配看似精确的 token 数字。

## 4. Selective Transform，而不是全文翻译

### 当前方法

PromptBridge 将输入按语义角色处理：

- 用户自然语言任务：交给 compiler model 改写成英文；
- fenced code block：替换为不可变 placeholder；
- glossary term：精确匹配后锁定；
- page context：不参与任务改写，最后作为 untrusted reference data 附加。

### 为什么不用全文翻译

全文翻译实现简单，但容易：

- 改写代码、命令和路径；
- 翻译已有标准名称；
- 把网页中的 prompt injection 混入主指令；
- 让长网页上下文产生额外翻译成本。

### 为什么不用“只在 Prompt 中要求保留代码”

自然语言要求是软约束。PromptBridge 使用 placeholder contract，并在模型返回后验证所有
placeholder 是否存在。缺失时 fail closed，这把保真从“希望模型听话”变成了程序检查。

## 5. 协议适配，而不是平台枚举

### 当前方法

业务层只认识两种 wire protocol：

```text
responses -> /responses
chat      -> /chat/completions
```

OpenAI、OpenRouter、PAI、Ollama 和 vLLM 是 Provider Profile，而不是五套业务类。

### 为什么不为每个平台写一个 Provider 类

平台类会重复 timeout、retry、JSON 解析、usage 和错误处理。大多数文本生成平台共享
OpenAI-compatible 请求形状，真正需要变化的是地址、协议、模型和鉴权。

### 为什么仍然保留 protocol 字段

“OpenAI-compatible”不是完全一致的标准。Responses 和 Chat 的请求、响应、输出 token
字段不同，某些平台只实现部分参数。显式协议比根据 URL 猜测更可读，也更容易测试。

Ollama 和 vLLM 官方文档都提供 OpenAI-compatible endpoints：

- https://docs.ollama.com/api/openai-compatibility
- https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/

## 6. Provider Profile 与系统凭据库

### 为什么不只用环境变量

环境变量很适合单一部署环境，但个人浏览器助手需要频繁切换多个平台和 Key。大量
`OPENAI_API_KEY`、`BASE_URL`、`MODEL` 变量不方便查看、切换和绑定。

PromptBridge 将信息分开：

```text
providers.json       平台地址、协议、模型，不敏感
OS credential store  API Key，敏感
```

### 为什么不把 Key 放在浏览器插件或 JSON 中

OpenAI 明确建议不要把 API Key 部署在浏览器客户端代码中：

https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safet

Chrome 的扩展存储适合设置和会话状态，但它不是 PromptBridge 的长期密钥边界。因此未来
浏览器插件只把请求交给本机核心，不直接持有 Provider Key。

### 额外安全约束

- 远程 Provider 必须使用 HTTPS；
- HTTP 只允许 loopback；
- URL 不允许内嵌用户名或密码；
- API Key 与 `profile name + origin` 绑定；
- HTTP redirect 被拒绝，避免 Authorization 被转发到另一个地址；
- Key 不进入命令参数、artifact 或 trace。

## 7. 两阶段调用，而不是一阶段或三阶段

当前 `run`：

```text
compiler model -> English execution prompt
downstream model -> target-language answer
```

### 为什么不只调用一次

一阶段直接把原始多语言请求发给强模型最便宜，但无法独立观察和评测 PromptBridge 的
核心价值，也无法让本地轻量模型负责编译、远程强模型负责执行。

### 为什么删除第三次 reconstruction

旧版每轮执行 transform、execute、reconstruct 三次请求。执行 Prompt 已经要求目标输出
语言时，强制 reconstruction 通常只是重复回译，会增加延迟、费用和代码损坏风险。

未来只有在用户明确选择“翻译网页回答”时，才应单独触发 response transform。

## 8. Untrusted Context 与 Human-in-the-loop

网页内容可能包含恶意指令。PromptBridge 当前采取三层可解释措施：

1. page context 不参与 compiler model 的任务改写；
2. 下游 Prompt 将它标记为 `Untrusted Page Context`，并用 JSON string 建立边界；
3. 浏览器阶段只捕获、预览和复制，不自动提交第三方网页。

这不能彻底解决 prompt injection。正确的面试说法是“降低并暴露风险”，而不是
“已经防住所有注入”。

当前实现甚至不需要 `activeTab`：`contextMenus` 在用户对选中文本执行菜单操作时直接提供
`selectionText`。插件不读取整页 DOM，因此也不申请 `scripting` 或 `<all_urls>`。如果未来
需要解析网页结构，才应重新评估 `activeTab`，而不是预先取得全站访问权限：

https://developer.chrome.com/docs/extensions/develop/concepts/activeTab

## 9. WXT 跨浏览器薄层，而不是完整 Web Clipper

### 当前方法

浏览器扩展使用 WXT + Vanilla TypeScript：

```text
shared capture logic
  -> Chrome / Edge: Manifest V3 side_panel
  -> Firefox: Manifest V2 sidebar_action
```

WXT 负责入口发现、manifest 生成和多目标构建，但没有假装浏览器 API 完全相同。
`background.ts` 仍保留一处分支，在 Chromium 调用 `sidePanel`，在 Firefox 调用
`sidebarAction`。三份生产 manifest 都通过实际构建检查。

### 为什么不用纯原生双 manifest

纯原生方案的运行时代码可能再少几行，但需要手工同步 Chrome/Edge MV3、Firefox MV2、
侧栏字段和构建产物。WXT 在这里解决的是已经存在的发布差异，不是引入业务框架。

### 为什么不用 Plasmo 或完整 Web Clipper

当前侧栏没有 React 状态树，也不需要 Readability、Markdown 转换、模板系统或整页 DOM
抓取。引入完整 Clipper 会扩大权限和测试面。PromptBridge 只复用跨浏览器脚手架，捕获
payload、隐私边界和 UI 状态仍由本项目维护。

### 为什么暂不支持 Safari

Safari Web Extension 还需要 macOS、Xcode 和原生 App 包装。一个月项目中先验证 Chrome、
Edge 和 Firefox 更可控；Safari 被明确列为未实现，而不是声称“WXT 自动兼容所有浏览器”。

参考：

- https://wxt.dev/guide/essentials/target-different-browsers.html
- https://github.com/wxt-dev/examples/tree/main/examples/side-panel
- https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/sidebarAction

## 10. Trace-first，而不是先做 Eval 平台

当前 trace 记录：

- Provider、协议和模型；
- latency、usage、request ID；
- 输入 hash 与长度；
- glossary 命中；
- 失败阶段和 artifact 引用。

它不默认复制 prompt 和 response 正文。

只有先积累真实浏览器与 API 请求，才有数据做：

- glossary fidelity；
- code preservation；
- source-language direct inference 与 English compilation 对照；
- local compiler 与 remote compiler 的 latency / cost / quality 对照。

因此当前不实现 `eval replay`。先有 delivery path 和 trace，再做 ablation，顺序更合理。

## 11. 为什么不用 RAG、FTS 或向量数据库

当前可检索的数据只有少量术语，没有真实的长文档库或跨会话语料。为此部署 SQLite FTS、
BM25 或 vector database 不会提高用户体验，只会增加索引、同步和调试代码。

当前只做 exact glossary lookup，因为：

- 术语需要确定性，不需要语义相似；
- 无索引延迟；
- 用户可直接检查；
- 容易测试误匹配和漏匹配。

未来触发检索的条件应是出现真实需求，例如数百条保存内容、跨语言模糊召回，或用户反复
提出“找到之前类似的讨论”。届时优先评估 FTS/BM25，再决定是否需要 embedding。

## 12. 为什么不保留 9 段式 DreamCompactor

结构化压缩是有价值的思想，但固定九个字段不是通用行业标准。Claude Code 当前官方文档
强调的是：入口 memory 保持简洁、详细内容按需读取、长会话接近上限时压缩，而不是要求
所有产品复制固定九段：

- https://code.claude.com/docs/en/memory
- https://code.claude.com/docs/en/context-window

PromptBridge 还没有跨会话浏览器历史，因此 DreamCompactor 没有可整理的“上下文债务”。

未来更适合的最小记忆是用户可编辑的 Context Pack：

```text
goal
preferences
glossary
decisions
open_questions
```

模型只能提出 patch，用户确认后应用。只有浏览器闭环产生实际跨会话需求后才实现。

## 13. 为什么不用 MCP、Deferred Tool Search 和 Programmatic Tool Calling

这些思路本身合理，但解决的是大量工具带来的 schema 和中间结果膨胀。PromptBridge 当前
没有任何外部执行工具，因此不存在该问题。

Anthropic 公开说明 Tool Search 在工具少于约 10 个时收益较低，而 code execution 会新增
sandbox、资源限制和监控成本：

- https://www.anthropic.com/engineering/advanced-tool-use
- https://www.anthropic.com/engineering/code-execution-with-mcp

在没有工具的项目里实现“工具延迟加载层”，只会形成无法演示、无法评测的空抽象。

## 14. 为什么不用多 Agent

当前流程是确定性的两阶段 pipeline，没有需要并行探索、上下文隔离或独立权限的子任务。
增加 Translator Agent、Memory Agent、Browser Agent 和 Supervisor 只会增加：

- prompt 和状态数量；
- 失败组合；
- 调试难度；
- API 成本；
- 面试时无法解释的框架代码。

单 orchestrator 是当前正确选择。未来只有出现可独立执行且会污染主上下文的任务时，
例如大规模网页证据检索，才考虑隔离 worker。

## 15. 真正保留的现代工程理念

最终保留的不是热门模块名称，而是六个能在代码和测试中证明的原则：

1. Segment-aware context transform。
2. Provider protocol abstraction and capability boundaries。
3. Local secret isolation and origin scoping。
4. Untrusted-context boundary with human confirmation。
5. Trace-driven observability before evaluation。
6. Least-privilege browser integration with explicit user gestures。

每个原则都位于主调用链中，都有失败模式，并且可以通过测试或 trace 观察。

## 16. 面试中不要过度声称

不要说：

- “这是生产级多 Agent 平台”；
- “彻底解决了 prompt injection”；
- “所有 OpenAI-compatible 平台都完全兼容”；
- “实现了智能长期记忆”；
- “本地模型一定比直接推理效果好”。

推荐说：

> 这是 production-oriented personal tool。我实现了密钥隔离、协议归一化、有限重试、
> fail-closed 内容保护、metadata trace，以及无 host permission 的选中文本捕获；本机
> loopback 通信、真实多语言评测和本地模型基准仍是明确记录的下一阶段。

这种边界感比堆叠更多 Agent 名词更可信。

## 17. 可用于简历的表述

- Built PromptBridge, a local-first multilingual model gateway that selectively rewrites
  non-English tasks while preserving code blocks, technical terms, and untrusted page context.
- Designed configurable provider profiles over OpenAI Responses and Chat Completions protocols,
  supporting remote and local endpoints without hard-coding individual platforms.
- Isolated API credentials in the operating-system keyring with profile-and-origin scoping,
  HTTPS enforcement, redirect rejection, and metadata-only tracing.
- Built a WXT-based Chrome, Edge, and Firefox extension that captures only user-selected text,
  uses session-only storage, omits full URLs, and requires no host permissions or content scripts.
- Reduced a three-call prototype to a testable two-stage compile-and-execute pipeline, with
  deterministic placeholder validation, retry handling, and normalized usage telemetry.

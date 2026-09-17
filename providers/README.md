# 提供方元数据

每个 `<provider>/models.yaml` 记录一个提供方下我们跟踪的模型。
仓库根目录的 `providers.json` 由 `scripts/build_providers.py` 依据 LiteLLM 的
公开价格目录单独生成。

## 字段说明

- `id` / `name` — 提供方的模型 ID 与显示名称。
- `reasoning_levels` — 模型接受的 reasoning-effort 取值，以提供方文档为准。
- `reasoning_effort_aliases` — 额外接受的取值及各自映射到的等级，用于文档中
  描述了此类映射的提供方（例如 GLM-5.2 接受 `xhigh` 并映射为 `max`）；
  提供方未列出别名时省略。
- `default_reasoning_effort` — 请求未设置 effort 时 API 应用的等级；提供方
  未文档化默认值、或模型没有 effort 参数时省略。
- `reasoning_switch` — 对"思考仅为开关、没有 effort 等级"的模型取 `true`；
  此类条目不带 `reasoning_levels`。
- `default_reasoning_enabled` — 开关型模型中，请求未关闭思考时是否默认开启。

已退役的模型会从 YAML 中移除；已退役但仍在路由到后继者的名称
（如 `deepseek-v4-flash`）保留，并在注释中标注。

## 审计 — 2026-09-16

每个 `default_reasoning_effort` 都在 2026-09-16 对照第一方文档核实过；
出处就近标注在 YAML 中，摘要如下。

### Anthropic — 所有模型的 API 默认值都是 `high`

官方文档称"Claude 默认使用 high effort"，且 `high` 等同于不设置该参数。
- <https://platform.claude.com/docs/en/build-with-claude/effort>

### OpenAI — 默认值因模型而异，并不统一

官方原话："Defaults are also model-dependent rather than universal"：
- `medium` — GPT-5（家族默认）、GPT-5.4 Pro、GPT-5.5、GPT-5.6 Luna/Sol/Terra。
- `none` — GPT-5.1、GPT-5.2、GPT-5.4、GPT-5.4 Mini、GPT-5.4 Nano。
- `high` — GPT-5.5 Pro。
- 未文档化默认值 — o3、gpt-5.3-codex 系列、gpt-6-astra、codex-auto-review。
- <https://developers.openai.com/api/docs/guides/reasoning>
- <https://developers.openai.com/api/docs/changelog>（2025-11-13：GPT-5.1
  默认使用新的 `none` 推理设置，"different from the previous `medium`
  default setting in GPT-5"）

### Google (Gemini) — 逐模型的默认 `thinkingLevel`

- `medium` — Gemini 3.8/3.7/3.6/3.5 Flash。
- `minimal` — Gemini 3.5 Flash-Lite、Gemini 3.1 Flash Image。
- `high` — Gemini 3.1 Pro Preview、Gemini 3 Pro Image、Gemini 3 Flash Preview。
- <https://ai.google.dev/gemini-api/docs/generate-content/thinking>
- <https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/thinking>

### xAI — 逐模型

grok-4.6/4.5 官方说明 "If not specified, `reasoning_effort` defaults to
`\"high\"`"；grok-4.3 默认 `low`；grok-4.20-multi-agent 未文档化默认值。
- <https://docs.x.ai/developers/model-capabilities/text/reasoning>
- <https://docs.x.ai/developers/models/grok-4.3>

### DeepSeek — `high`

"思考模式默认打开，且 effort 默认为 `high`"。
- <https://api-docs.deepseek.com/zh-cn/guides/thinking_mode>

### Z.ai — `max`

`reasoning_effort` 默认 `max`（"深度思考（默认值）"）。GLM-5.2 接受 `xhigh`
并映射为 `max`；GLM-5.3/5.3-Flash 只接受 `low`/`high`/`max`。
- <https://docs.bigmodel.cn/cn/guide/start/concept-param>
- <https://docs.bigmodel.cn/cn/guide/models/text/glm-5.3>

### Moonshot — K3 为 `max`；K2.x 没有 `reasoning_effort`

K3："支持 `"low"` / `"high"` / `"max"` 三档，默认 `"max"`"。K2.6 改用
`thinking.type`；K2.7 Code 始终思考。`kimi-k2.8` 与 `kimi-k3-256k` 只出现在
Kimi Code 产品文档中，那里记录的是产品默认值（`max` / `high`）而非 API
默认值，因此这里不填。
- <https://platform.kimi.com/docs/guide/use-reasoning-effort>
- <https://platform.kimi.com/docs/models>
- <https://www.kimi.com/code/docs/kimi-code/models.html>

### MiniMax — `reasoning.effort` 是思考开关，不是深度等级

MiniMax 没有 reasoning-effort 深度等级。在 OpenAI 兼容端点（Codex 使用）上，
`reasoning.effort` 对 MiniMax-M3 是思考开关：任意非 `none` 值（如 `high`）
开启 Adaptive Thinking，`none` 关闭。Codex 模型目录模板默认
`default_reasoning_level: "high"`，OpenAI 兼容端点同样默认开启思考。M2.x
系列无法关闭思考，其条目以 `[high]`（推断值）作为有效默认。
- <https://platform.minimax.cn/docs/token-plan/codex>
- <https://platform.minimax.io/docs/api-reference/text-openai-api>

### QwenCloud — Qwen3.8 有深度等级，Qwen3.7 是开关（2026-09-17 核实）

在 QwenCloud 的 Qwen 模型中，只有 Qwen3.8 系列提供 `reasoning_effort` 深度
等级：`low` / `medium` / `xhigh`，默认 `xhigh`。同时接受 OpenAI 标准名并
映射：`minimal` → `low`、`high` → `xhigh`、`max` → `xhigh`；`none` 映射到
`enable_thinking=false`（关闭思考）。
- <https://docs.qwencloud.com/api-reference/chat/openai-chat>
- <https://docs.qwencloud.com/api-reference/chat/openai-responses>
- <https://qwen.ai/blog?id=qwen3.8>（发布博客："xhigh（默认）/ medium / low"）
- <https://docs.qoder.com/zh/cli/model>（Qoder CLI 一致：3.8-Max 标注
  "low / medium / xhigh"；3.7-Max/Plus 只有思考开关）
- <https://huggingface.co/Qwen/Qwen3.8-27B> /
  <https://huggingface.co/Qwen/Qwen3.8-2.4T-A95B>（开源成员文档写明同样三级）

Qwen3.7 系列——日常使用的另一个 Qwen 家族——完全没有 effort 等级：官方定义
是混合思考模型，`enable_thinking` 切换思考/不思考（默认开启，false = 直接
回复），另有 `thinking_budget` 思考 token 上限。因此其条目使用
`reasoning_switch: true` 与 `default_reasoning_enabled: true`，而不是
`reasoning_levels`；不为它杜撰任何 effort 值。
- <https://docs.qwencloud.com/developer-guides/text-generation/thinking>
- <https://help.aliyun.com/zh/model-studio/deep-thinking>（百炼把
  Qwen3.7-Max/Plus 列为混合思考模型）

更早的系列（Qwen3.6/3.5/3、Qwen3-VL、Qwen3-Coder、Qwen-Max/Plus/Flash/Turbo、
QwQ）行为相同，但暂未收录。

Qwen3.8 五个成员（商用 `qwen3.8-max`、`qwen3.8-max-0902`、`qwen3.8-flash` 与
开源 `qwen3.8-2.4t-a95b`、`qwen3.8-27b`）共享系列等级。目前只有
`qwen3.8-max` 存在于 LiteLLM 目录；其余四个在上游收录前不会发布。两个
Qwen3.7 条目已在目录中。

QwenCloud 上的第三方模型（DeepSeek、GLM、Kimi）不在此跟踪——它们分别由
`deepseek/`、`zai/`、`moonshot/` 文件覆盖。

## `reasoning_levels` 审计 — 2026-09-16

`reasoning_levels` 已于 2026-09-16 对照各提供方文档化的支持值核实。

以下模型的提供方未公布支持值列表，无法对照第一方文档核实
（此类条目在 YAML 中以"未核实"注释标记）：

- OpenAI：`gpt-5.3-codex-spark`、`codex-auto-review`、`o3`、`gpt-5-mini`、
  `gpt-5-nano`。LiteLLM 目录为其中部分模型带有来自 OpenAI 定价页的
  `supports_*_reasoning_effort` 标记，但官方没有逐模型列表。
- Anthropic：`claude-opus-4-5-20251101` 只能间接核实——effort 表没有它的
  逐等级行，`[low, medium, high]` 由它不在 `max` / `xhigh` 可用列表中推断。

## 注意事项

- **API 默认 ≠ 产品默认。** 自 Opus 4.7 起 Claude Code 把默认 effort 提升到
  `xhigh`；Kimi Code 在 K3 上默认 `high`、K2.8 Preview 默认 `max`。本字段
  只记录 API 行为。
- **Gemini 文档自相矛盾。** Gemini 3 开发者指南有句笼统的"默认 high"，与
  逐模型表格不符（Flash-Lite 默认 `minimal`）；此处以逐模型表格为准。
- **部分默认值只出现在更新日志/指南里，而非模型页面。** GPT-5 / GPT-5 Mini /
  GPT-5 Nano 依据 GPT-5.1 更新日志的表述。
- **xAI 提前列出了尚未生效的 `xhigh`。** `grok-4.3` / `grok-4.5` 模型页面把
  `xhigh` 列入支持的 effort，但推理指南说明它自 `grok-4.6` 起才生效（更早的
  模型按 `high` 处理）；这些条目因此不含 `xhigh`，并在注释中说明。
- **`deepseek-v4-flash` 是仍在路由的已退役名称。** 底层 V4 Flash 模型已于
  2026-09-10 退役，但对该名称的请求暂时由 V4.1 Flash 承接，因此名称仍在
  使用时条目保留。
- **MiniMax 的 `reasoning.effort` 是开关，不是深度等级。** 任意非 `none` 值
  在 MiniMax-M3 上开启 Adaptive Thinking 且不改变深度；MiniMax 不支持
  `output_config.effort`（Claude Code 通过 Anthropic 端点发送的参数）——
  effort 只在 OpenAI 兼容端点上生效。
- **LiteLLM 目录中只有少量条目带该字段。** 在 `providers.json` 中，
  `default_reasoning_effort` 出现在 39 个上游条目上（Azure/OpenRouter 的
  GPT-5.x 行，取值为 `none`/`medium`，各自带 `source` URL）。这些 YAML
  文件才是该字段的策展来源。

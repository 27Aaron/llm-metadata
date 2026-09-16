# Provider metadata

Each `<provider>/models.yaml` lists the models we track for one provider.
`providers.json` at the repository root is generated separately by
`scripts/build_providers.py` from LiteLLM's public price catalog.

## Field semantics

- `id` / `name` — provider model ID and display name.
- `reasoning_levels` — the reasoning-effort values the model accepts, as
  documented by the provider.
- `reasoning_effort_aliases` — extra accepted values and the level each one
  maps to, for providers that document such mappings (e.g. GLM-5.2 accepts
  `xhigh` and maps it to `max`); omitted when the provider lists no aliases.
- `default_reasoning_effort` — the effort the API applies when a request does
  not set one. Omitted when the provider does not document a default, or the
  model has no effort parameter.

Retired models are removed from the YAMLs; retired names that are still routed
to a successor (e.g. `deepseek-v4-flash`) stay and are labelled in the comments.

## Audit — 2026-09-16

Every `default_reasoning_effort` was checked against first-party documentation
on 2026-09-16. Sources are cited inline in the YAML files; summary below.

### Anthropic — API default is `high` for every model

"By default, Claude uses high effort", and `high` is "Equivalent to not setting
the parameter".
- <https://platform.claude.com/docs/en/build-with-claude/effort>

### OpenAI — defaults are per model, not uniform

"Defaults are also model-dependent rather than universal":
- `medium` — GPT-5 (family default), GPT-5.4 Pro, GPT-5.5, GPT-5.6 Luna/Sol/Terra.
- `none` — GPT-5.1, GPT-5.2, GPT-5.4, GPT-5.4 Mini, GPT-5.4 Nano.
- `high` — GPT-5.5 Pro.
- No documented default — o3, the gpt-5.3-codex models, gpt-6-astra,
  codex-auto-review.
- <https://developers.openai.com/api/docs/guides/reasoning>
- <https://developers.openai.com/api/docs/changelog> (2025-11-13: GPT-5.1
  "defaults to a new `none` reasoning setting ... different from the previous
  `medium` default setting in GPT-5").

### Google (Gemini) — per-model default `thinkingLevel`

- `medium` — Gemini 3.8/3.7/3.6/3.5 Flash.
- `minimal` — Gemini 3.5 Flash-Lite, Gemini 3.1 Flash Image.
- `high` — Gemini 3.1 Pro Preview, Gemini 3 Pro Image, Gemini 3 Flash Preview.
- <https://ai.google.dev/gemini-api/docs/generate-content/thinking>
- <https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/thinking>

### xAI — per model

"If not specified, `reasoning_effort` defaults to `"high"`" on grok-4.6/4.5;
grok-4.3 defaults to `low`; grok-4.20-multi-agent documents no default.
- <https://docs.x.ai/developers/model-capabilities/text/reasoning>
- <https://docs.x.ai/developers/models/grok-4.3>

### DeepSeek — `high`

"思考模式默认打开，且 effort 默认为 `high`".
- <https://api-docs.deepseek.com/zh-cn/guides/thinking_mode>

### Z.ai — `max`

`reasoning_effort` defaults to `max` ("深度思考（默认值）"). On GLM-5.2 `xhigh`
is accepted and maps to `max`; GLM-5.3/5.3-Flash only accept `low`/`high`/`max`.
- <https://docs.bigmodel.cn/cn/guide/start/concept-param>
- <https://docs.bigmodel.cn/cn/guide/models/text/glm-5.3>

### Moonshot — `max` on K3; K2.x have no `reasoning_effort`

K3: "支持 `"low"` / `"high"` / `"max"` 三档，默认 `"max"`". K2.6 uses
`thinking.type` instead; K2.7 Code always thinks. `kimi-k2.8*` and
`kimi-k3-256k` only appear in the Kimi Code product docs, which list product
defaults (`max` / `high`) rather than API defaults, so they carry no value here.
- <https://platform.kimi.com/docs/guide/use-reasoning-effort>
- <https://platform.kimi.com/docs/models>
- <https://www.kimi.com/code/docs/kimi-code/models.html>

## `reasoning_levels` audit — 2026-09-16

`reasoning_levels` was checked against each provider's documented supported
values on 2026-09-16.

Models whose provider does not publish a supported-values list, so
`reasoning_levels` cannot be verified against first-party docs (each such entry
is flagged with an `Unverified` comment in the YAML):

- OpenAI: `gpt-5.3-codex-spark`, `codex-auto-review`, `o3`, `gpt-5-mini`,
  `gpt-5-nano`. LiteLLM's catalog carries partial
  `supports_*_reasoning_effort` flags for some of these, sourced from OpenAI's
  pricing page, but there is no official per-model list.
- Anthropic: `claude-opus-4-5-20251101` is verified only indirectly — the
  effort table carries no per-level row for it, and `[low, medium, high]`
  follows from its absence in the `max` / `xhigh` availability lists.

## Caveats

- **API default ≠ product default.** Claude Code raises the default effort to
  `xhigh` since Opus 4.7, and Kimi Code defaults to `high` on K3 / `max` on
  K2.8 Preview. This field tracks the API only.
- **Gemini's docs contradict themselves.** The Gemini 3 developer guide has a
  blanket "defaults to high" line that disagrees with the per-model table
  (Flash-Lite defaults to `minimal`); the per-model table is used here.
- **Some defaults are only stated in changelogs/guides, not model pages.**
  GPT-5 / GPT-5 Mini / GPT-5 Nano rest on the GPT-5.1 changelog wording.
- **xAI lists `xhigh` before it takes effect.** The `grok-4.3` / `grok-4.5`
  model pages include `xhigh` under supported efforts, but the reasoning guide
  says it is only honoured from `grok-4.6` onward (earlier models treat it as
  `high`); those entries therefore omit `xhigh` and note it in the comments.
- **`deepseek-v4-flash` is a retired name that is still routed.** The
  underlying V4 Flash model was retired on 2026-09-10, but requests to the name
  are temporarily served by V4.1 Flash, so the entry stays while the name
  remains in active use.
- **LiteLLM carries this field on only a few rows.** In `providers.json`,
  `default_reasoning_effort` appears on 39 upstream entries (Azure/OpenRouter
  GPT-5.x rows with values `none`/`medium`, each tagged with a `source` URL).
  These YAML files are the curated source for the field.

## Open questions

- `kimi-k2.8-code` has no matching official model ID (Kimi Code lists
  `kimi-for-coding` for K2.8 Preview); confirm the naming source or drop the
  entry.

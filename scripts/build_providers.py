#!/usr/bin/env python3
"""从策展的 YAML 元数据和 LiteLLM 目录构建 ``providers.json``。

各提供方的策展 YAML 文件（``providers/<provider>/models.yaml``）是"发布哪些
模型"的权威来源。带有 ``reasoning_levels`` 字段的模型（或用于纯开关式思考
模型的 ``reasoning_switch`` 标记）会与 LiteLLM 目录中的对应条目合并（价格、
上下文窗口、能力字段）；LiteLLM 不认识的 YAML 模型会被跳过。作为例外，
LiteLLM 的图片模型（``supported_endpoints`` 含图片端点的条目）即使没有
``reasoning_levels`` 也会发布。

输出（``providers.json``，写入仓库根目录）按提供方分组::

    {
      "anthropic": {
        "claude-opus-4-6": {
          "provider": "anthropic",
          "...": "LiteLLM 字段",
          "reasoning_levels": ["low", "medium", "high", "max"],
          "default_reasoning_effort": "high"
        }
      }
    }

模型键会去掉多余的提供方前缀（``gemini/gemini-3-flash`` 存为
``gemini-3-flash``）。
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import yaml

# 上游目录：公开、频繁刷新，约 2.5 MB。
SOURCE_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
USER_AGENT = "llm-metadata/1.0"
SOURCE_TIMEOUT_SECONDS = 60

# `providers.json` 位于仓库根目录（本脚本所在目录的上一级），
# 因此默认输出不依赖调用者的工作目录。
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPOSITORY_ROOT / "providers.json"
DEFAULT_METADATA_DIR = REPOSITORY_ROOT / "providers"

# 输出提供方 -> 它所收集的上游 `litellm_provider` 值。一个桶可以收集多个
# 上游名称（例如同一厂商的 `vertex_ai-*` 变体）；每个上游名称必须只出现一次。
# 没有策展 YAML 目录的提供方不会被发布。
PROVIDER_GROUPS: dict[str, set[str]] = {
    "anthropic": {"anthropic"},
    "deepseek": {"deepseek"},
    "gemini": {"gemini"},
    "minimax": {"minimax"},
    "moonshot": {"moonshot"},
    "openai": {"openai"},
    "qwencloud": {"qwencloud"},
    "xai": {"xai"},
    "zai": {"zai"},
}

# 把同一个模型重复罗列很多次的行。LiteLLM 按分辨率和质量档位给图片模型定价，
# 那些条目不含额外能力信息，只会让目录变得臃肿。
SIZE_VARIANT_RE = re.compile(r"(?:^|/)\d{3,4}-x-\d{3,4}(?:/|$)", re.IGNORECASE)
QUALITY_VARIANT_RE = re.compile(r"^(?:low|high|medium|standard|ultra)/", re.IGNORECASE)
SORA_RE = re.compile(r"sora", re.IGNORECASE)
FINETUNE_RE = re.compile(r"(?:^|/)ft[:_/ -]", re.IGNORECASE)

# 描述文件格式而非模型的顶层条目。
NON_MODEL_KEYS = frozenset({"sample_spec"})


def build_alias_index(groups: dict[str, set[str]]) -> dict[str, str]:
    """把 ``groups`` 翻转成"上游名称 -> 输出提供方"的查找表。"""
    index: dict[str, str] = {}
    for provider, aliases in groups.items():
        for alias in aliases:
            if alias in index:
                raise ValueError(
                    f"upstream provider {alias!r} is claimed by both "
                    f"{index[alias]!r} and {provider!r}"
                )
            index[alias] = provider
    return index


ALIAS_TO_PROVIDER = build_alias_index(PROVIDER_GROUPS)


def load_source(source: str) -> dict:
    """从 http(s) URL 或本地文件路径读取上游目录。

    本地路径（以及 ``file://`` URL）让离线运行可复现。
    """
    if source.startswith(("http://", "https://")):
        request = Request(
            source,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        with urlopen(request, timeout=SOURCE_TIMEOUT_SECONDS) as response:
            return json.load(response)
    if source.startswith("file://"):
        source = urlsplit(source).path
    return json.loads(Path(source).read_text(encoding="utf-8"))


def load_curated_models(metadata_dir: Path) -> dict[str, list[dict]]:
    """读取 ``<provider>/models.yaml``，只保留可发布的模型。

    提供方名称来自 YAML 目录名；不带 ``reasoning_levels`` 或
    ``reasoning_switch`` 标记的模型不会进入目录。
    """
    curated: dict[str, list[dict]] = {}
    for yaml_file in sorted(metadata_dir.glob("*/models.yaml")):
        provider = yaml_file.parent.name
        if provider not in PROVIDER_GROUPS:
            continue
        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        models = [
            model
            for model in data.get("models", [])
            if model.get("reasoning_levels") or model.get("reasoning_switch")
        ]
        if models:
            curated[provider] = models
    return curated


def is_retired(entry: dict, today: date) -> bool:
    """当模型的弃用日期已到或已过时返回 True。

    缺失或无法解析的日期视为仍在服役，这样上游的格式变化会以需要人工检查的
    额外条目暴露出来，而不是静默丢模型。
    """
    raw = entry.get("deprecation_date")
    if not raw:
        return False
    try:
        return date.fromisoformat(str(raw)) <= today
    except ValueError:
        return False


def without_provider_prefix(model_key: str, provider: str) -> str:
    """去掉 LiteLLM 在部分模型键上重复添加的 ``provider/`` 前缀。"""
    prefix = f"{provider}/"
    while model_key.lower().startswith(prefix):
        model_key = model_key[len(prefix):]
    return model_key


def is_image_model(entry: dict) -> bool:
    """条目暴露图片生成端点时返回 True。"""
    return any(
        "images" in str(endpoint)
        for endpoint in entry.get("supported_endpoints") or ()
    )


def is_excluded_variant(provider: str, model_key: str) -> bool:
    """对按尺寸/质量区分的图片变体，以及 OpenAI 的微调/Sora 行返回 True。"""
    if SIZE_VARIANT_RE.search(model_key) or QUALITY_VARIANT_RE.match(model_key):
        return True
    return provider == "openai" and bool(
        SORA_RE.search(model_key) or FINETUNE_RE.search(model_key)
    )


def build_litellm_index(
    source: dict, providers: list[str]
) -> dict[str, dict[str, list[str]]]:
    """映射：提供方 -> 规范化模型键 -> 原始目录键列表。"""
    index: dict[str, dict[str, list[str]]] = {provider: {} for provider in providers}
    for source_key, entry in source.items():
        if source_key in NON_MODEL_KEYS or not isinstance(entry, dict):
            continue
        provider = ALIAS_TO_PROVIDER.get(str(entry.get("litellm_provider", "")).lower())
        if provider is None or provider not in index:
            continue
        normalized = without_provider_prefix(source_key, provider).casefold()
        index[provider].setdefault(normalized, []).append(source_key)
    return index


def pick_litellm_entry(source: dict, matches: list[str]) -> dict:
    """合并匹配到的目录条目；不带前缀的拼写优先。

    有些提供方把同一个模型发布在两个键下（例如 DeepSeek 同时有
    ``deepseek-v4-pro`` 与 ``deepseek/deepseek-v4-pro``），字段互为补充，
    因此合并时保留所有缺失字段。
    """
    ordered = sorted(matches, key=lambda key: "/" in key)
    merged: dict = {}
    for key in ordered:
        for field, value in source[key].items():
            merged.setdefault(field, value)
    return merged


def extract(
    source: dict,
    curated: dict[str, list[dict]],
    today: date,
    include_deprecated: bool,
    verbose: bool = False,
) -> dict:
    """把策展模型与 LiteLLM 目录合并，按提供方分组并排序。

    策展模型对弃用状态有最终决定权：由 YAML 决定保留哪些，因此目录的弃用
    检查不适用于它们。直接从目录拉取的图片模型会按 ``today`` 过滤，
    除非设置了 ``include_deprecated``。
    """
    index = build_litellm_index(source, list(curated))
    catalog: dict[str, dict[str, dict]] = {}
    skipped: list[str] = []

    for provider, models in curated.items():
        out: dict[str, dict] = {}

        # LiteLLM 也认识的策展模型（带 reasoning_levels 或 reasoning_switch）。
        for model in models:
            model_id = model["id"]
            matches = index[provider].get(model_id.casefold())
            if not matches:
                skipped.append(f"{provider}/{model_id}")
                continue
            entry = pick_litellm_entry(source, matches)
            row = {"provider": provider}
            row.update(
                {
                    key: value
                    for key, value in entry.items()
                    if key != "litellm_provider"
                }
            )
            for field in (
                "reasoning_levels",
                "default_reasoning_effort",
                "reasoning_switch",
                "default_reasoning_enabled",
            ):
                if field in model:
                    row[field] = model[field]
            out[model_id] = row

        # 直接从目录拉取的图片模型（没有 reasoning_levels）。
        for normalized, keys in index[provider].items():
            if normalized in out:
                continue  # 已被某个策展模型覆盖
            entry = source[keys[0]]
            if not is_image_model(entry):
                continue
            if not include_deprecated and is_retired(entry, today):
                continue
            if is_excluded_variant(provider, keys[0]):
                continue
            row = {"provider": provider}
            row.update(
                {
                    key: value
                    for key, value in entry.items()
                    if key != "litellm_provider"
                }
            )
            out[normalized] = row

        if out:
            catalog[provider] = dict(
                sorted(out.items(), key=lambda item: item[0].casefold())
            )

    if verbose and skipped:
        print("skipped (curated model absent from the LiteLLM catalog):")
        for item in sorted(skipped):
            print(f"  {item}")
    return catalog


def write_catalog(output: Path, catalog: dict) -> None:
    """以 UTF-8 JSON 写入目录，末尾带换行。"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="合并策展的 providers/*/models.yaml 与 LiteLLM 公开模型价格"
        "目录，生成 providers.json。",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="要写入的 JSON 文件路径（默认：仓库根目录的 providers.json）",
    )
    parser.add_argument(
        "--source",
        default=SOURCE_URL,
        help="LiteLLM 目录的 http(s) URL 或本地路径（默认：上游 main 分支）",
    )
    parser.add_argument(
        "--metadata-dir",
        type=Path,
        default=DEFAULT_METADATA_DIR,
        help="包含 <provider>/models.yaml 的目录（默认：本脚本旁的 providers/）",
    )
    parser.add_argument(
        "--include-deprecated",
        action="store_true",
        help="保留弃用日期已过的图片模型",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="列出各提供方提取的模型数量，以及被跳过的策展模型",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source = load_source(args.source)
    curated = load_curated_models(args.metadata_dir)
    # LiteLLM 发布的是普通日历日期，因此本地日期是"弃用日期是否已过"的正确
    # 参照点。
    today = date.today()  # noqa: DTZ011
    catalog = extract(source, curated, today, args.include_deprecated, args.verbose)
    write_catalog(args.output, catalog)

    total = sum(len(models) for models in catalog.values())
    print(f"wrote {total} models across {len(catalog)} providers to {args.output}")
    if args.verbose:
        for provider, models in catalog.items():
            print(f"  {provider:<10} {len(models):>4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Extract a provider allow-list from LiteLLM's public model price catalog.

This is deliberately a filter, not a price authority: every field is copied
verbatim from LiteLLM, so any number in the output can be traced back to its
upstream entry.  The source file is public and requires no API keys.

Output (``providers.json``, written to the repository root) is grouped by
provider::

    {
      "anthropic": {
        "claude-opus-4-6": {"provider": "anthropic", "...": "LiteLLM fields"}
      }
    }

Model keys drop the redundant provider prefix (``gemini/gemini-3-flash`` is
stored as ``gemini-3-flash``).  When two spellings genuinely disagree, the full
key is kept as a separate entry instead of being dropped silently.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

# Upstream catalog: public, refreshed frequently, ~2.5 MB.
SOURCE_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
USER_AGENT = "llm-metadata/1.0"
SOURCE_TIMEOUT_SECONDS = 60

# `providers.json` lives in the repository root, one level above this script, so
# the default output does not depend on the caller's working directory.
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPOSITORY_ROOT / "providers.json"

# Output provider -> the upstream `litellm_provider` values it collects.  One
# bucket may collect several upstream names (for example the `vertex_ai-*`
# variants of a single vendor); each upstream name must appear exactly once.
# Widen these groups to widen the allow-list.
PROVIDER_GROUPS: dict[str, set[str]] = {
    "anthropic": {"anthropic"},
    "deepseek": {"deepseek"},
    "gemini": {"gemini"},
    "minimax": {"minimax"},
    "moonshot": {"moonshot"},
    "openai": {"openai"},
    "xai": {"xai"},
    "zai": {"zai"},
}

# Rows that restate a single model many times over.  LiteLLM prices image
# models per resolution and fine-tunes per base model, which would bloat the
# catalog with entries that add no capability information.
SIZE_VARIANT_RE = re.compile(r"(?:^|/)\d{3,4}-x-\d{3,4}(?:/|$)", re.IGNORECASE)
SORA_RE = re.compile(r"sora", re.IGNORECASE)
FINETUNE_RE = re.compile(r"(?:^|/)ft[:_/ -]", re.IGNORECASE)

# Top-level entries that describe the file format rather than a model.
NON_MODEL_KEYS = frozenset({"sample_spec"})

# Fields that only record provenance.  They are ignored when comparing two
# spellings of the same model, because each spelling carries its own link.
PROVENANCE_FIELDS = frozenset({"source", "litellm_source"})


def build_alias_index(groups: dict[str, set[str]]) -> dict[str, str]:
    """Flip ``groups`` into an upstream-name -> output-provider lookup."""
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
    """Read the upstream catalog from an http(s) URL or a local file path.

    Local paths (and ``file://`` URLs) keep runs reproducible offline.
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


def is_retired(entry: dict, today: date) -> bool:
    """True when the model's deprecation date has arrived or passed.

    A missing or unparsable date counts as active, so a format change upstream
    surfaces as extra rows for review instead of silently dropping models.
    """
    raw = entry.get("deprecation_date")
    if not raw:
        return False
    try:
        return date.fromisoformat(str(raw)) <= today
    except ValueError:
        return False


def is_excluded_variant(provider: str, model_key: str) -> bool:
    """True for per-size image variants and OpenAI fine-tune / Sora rows."""
    if provider in {"openai", "xai"} and SIZE_VARIANT_RE.search(model_key):
        return True
    return provider == "openai" and bool(
        SORA_RE.search(model_key) or FINETUNE_RE.search(model_key)
    )


def without_provider_prefix(model_key: str, provider: str) -> str:
    """Drop repeated ``provider/`` prefixes LiteLLM adds to some model keys."""
    prefix = f"{provider}/"
    while model_key.lower().startswith(prefix):
        model_key = model_key[len(prefix) :]
    return model_key


def comparable(entry: dict) -> dict:
    """Entry without its provenance links, for duplicate detection."""
    return {key: value for key, value in entry.items() if key not in PROVENANCE_FIELDS}


def add_model(models: dict, provider: str, source_key: str, entry: dict) -> None:
    """Store one model, resolving provider-prefixed/unprefixed duplicates.

    The concise unprefixed name wins, because that is the name users type.  A
    differing full key is kept as its own entry so nothing disappears without a
    trace.
    """
    model_key = without_provider_prefix(source_key, provider)
    existing = models.get(model_key)
    if existing is None:
        models[model_key] = entry
    elif provider == "deepseek":
        # DeepSeek publishes both spellings with complementary detail: keep the
        # union, with the unprefixed entry winning on conflicts.
        models[model_key] = (
            {**existing, **entry} if source_key == model_key else {**entry, **existing}
        )
    elif comparable(existing) != comparable(entry):
        models[source_key] = entry


def extract(
    source: dict, providers: list[str], include_deprecated: bool, today: date
) -> dict:
    """Filter ``source`` down to ``providers``, grouped and alphabetised.

    ``today`` decides which deprecation dates have passed, so tests and callers
    can pin it instead of relying on the wall clock.
    """
    catalog = {provider: {} for provider in providers}
    for source_key, entry in source.items():
        if source_key in NON_MODEL_KEYS or not isinstance(entry, dict):
            continue
        provider = ALIAS_TO_PROVIDER.get(str(entry.get("litellm_provider", "")).lower())
        if provider is None or provider not in catalog:
            continue
        if not include_deprecated and is_retired(entry, today):
            continue
        if is_excluded_variant(provider, source_key):
            continue
        # The output bucket name replaces LiteLLM's own provider field, so a
        # consumer sees stable names even when upstream uses aliases.
        row = {"provider": provider}
        row.update(
            {key: value for key, value in entry.items() if key != "litellm_provider"}
        )
        add_model(catalog[provider], provider, source_key, row)

    # Provider first, then model name: this mirrors the hierarchical layout of
    # comparable catalogs and makes per-provider processing straightforward.
    return {
        provider: dict(sorted(models.items(), key=lambda item: item[0].casefold()))
        for provider, models in sorted(
            catalog.items(), key=lambda item: item[0].casefold()
        )
        if models
    }


def write_catalog(output: Path, catalog: dict) -> None:
    """Write the catalog as UTF-8 JSON with a trailing newline."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract a provider allow-list from LiteLLM's public model price catalog.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="path of the JSON file to write (default: providers.json in the repository root)",
    )
    parser.add_argument(
        "--source",
        default=SOURCE_URL,
        help="http(s) URL or local path of the LiteLLM catalog (default: upstream main)",
    )
    parser.add_argument(
        "--providers",
        nargs="+",
        choices=sorted(PROVIDER_GROUPS),
        default=sorted(PROVIDER_GROUPS),
        metavar="PROVIDER",
        help="providers to keep (default: all)",
    )
    parser.add_argument(
        "--include-deprecated",
        action="store_true",
        help="keep models whose deprecation date has already passed",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="list the number of models extracted per provider",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source = load_source(args.source)
    # LiteLLM publishes plain calendar dates, so the local date is the right
    # reference point for "deprecation date has passed".
    today = date.today()  # noqa: DTZ011
    catalog = extract(source, args.providers, args.include_deprecated, today)
    write_catalog(args.output, catalog)

    total = sum(len(models) for models in catalog.values())
    print(f"wrote {total} models across {len(catalog)} providers to {args.output}")
    if args.verbose:
        for provider, models in catalog.items():
            print(f"  {provider:<10} {len(models):>4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

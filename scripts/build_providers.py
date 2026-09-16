#!/usr/bin/env python3
"""Build ``providers.json`` from the curated YAML metadata and LiteLLM's catalog.

The curated per-provider YAML files (``providers/<provider>/models.yaml``) are
the source of truth for which models to publish. Models that carry a
``reasoning_levels`` field are merged with the matching LiteLLM catalog entry
(price, context window, capabilities); YAML models that LiteLLM does not know
about are skipped. As an exception, LiteLLM image models (entries whose
``supported_endpoints`` contains an images endpoint) are published even though
they have no ``reasoning_levels``.

Output (``providers.json``, written to the repository root) is grouped by
provider::

    {
      "anthropic": {
        "claude-opus-4-6": {
          "provider": "anthropic",
          "...": "LiteLLM fields",
          "reasoning_levels": ["low", "medium", "high", "max"],
          "default_reasoning_effort": "high"
        }
      }
    }

Model keys drop the redundant provider prefix (``gemini/gemini-3-flash`` is
stored as ``gemini-3-flash``).
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

# Upstream catalog: public, refreshed frequently, ~2.5 MB.
SOURCE_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
USER_AGENT = "llm-metadata/1.0"
SOURCE_TIMEOUT_SECONDS = 60

# `providers.json` lives in the repository root, one level above this script, so
# the default output does not depend on the caller's working directory.
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPOSITORY_ROOT / "providers.json"
DEFAULT_METADATA_DIR = REPOSITORY_ROOT / "providers"

# Output provider -> the upstream `litellm_provider` values it collects. One
# bucket may collect several upstream names (for example the `vertex_ai-*`
# variants of a single vendor); each upstream name must appear exactly once.
# Providers without a curated YAML directory are not published.
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

# Rows that restate a single model many times over. LiteLLM prices image models
# per resolution and quality tier, which would bloat the catalog with entries
# that add no capability information.
SIZE_VARIANT_RE = re.compile(r"(?:^|/)\d{3,4}-x-\d{3,4}(?:/|$)", re.IGNORECASE)
QUALITY_VARIANT_RE = re.compile(r"^(?:low|high|medium|standard|ultra)/", re.IGNORECASE)
SORA_RE = re.compile(r"sora", re.IGNORECASE)
FINETUNE_RE = re.compile(r"(?:^|/)ft[:_/ -]", re.IGNORECASE)

# Top-level entries that describe the file format rather than a model.
NON_MODEL_KEYS = frozenset({"sample_spec"})


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


def load_curated_models(metadata_dir: Path) -> dict[str, list[dict]]:
    """Read ``<provider>/models.yaml``, keeping only models with reasoning_levels.

    Provider names come from the YAML directory names; models without a
    ``reasoning_levels`` field are left out of the catalog.
    """
    curated: dict[str, list[dict]] = {}
    for yaml_file in sorted(metadata_dir.glob("*/models.yaml")):
        provider = yaml_file.parent.name
        if provider not in PROVIDER_GROUPS:
            continue
        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        models = [
            model for model in data.get("models", []) if model.get("reasoning_levels")
        ]
        if models:
            curated[provider] = models
    return curated


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


def without_provider_prefix(model_key: str, provider: str) -> str:
    """Drop repeated ``provider/`` prefixes LiteLLM adds to some model keys."""
    prefix = f"{provider}/"
    while model_key.lower().startswith(prefix):
        model_key = model_key[len(prefix):]
    return model_key


def is_image_model(entry: dict) -> bool:
    """True when the entry exposes an image-generation endpoint."""
    return any(
        "images" in str(endpoint)
        for endpoint in entry.get("supported_endpoints") or ()
    )


def is_excluded_variant(provider: str, model_key: str) -> bool:
    """True for per-size/per-quality image variants and OpenAI fine-tune/Sora rows."""
    if SIZE_VARIANT_RE.search(model_key) or QUALITY_VARIANT_RE.match(model_key):
        return True
    return provider == "openai" and bool(
        SORA_RE.search(model_key) or FINETUNE_RE.search(model_key)
    )


def build_litellm_index(
    source: dict, providers: list[str]
) -> dict[str, dict[str, list[str]]]:
    """Map provider -> normalized model key -> original catalog keys."""
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
    """Merge the matching catalog entries; the unprefixed spelling wins.

    Some providers publish one model under two keys (for example DeepSeek
    uses both ``deepseek-v4-pro`` and ``deepseek/deepseek-v4-pro``) with
    complementary detail, so the merge keeps every missing field.
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
    """Merge curated models with the LiteLLM catalog, grouped and alphabetised.

    Curated models are authoritative about deprecation: the YAML decides what
    stays, so the catalog deprecation check does not apply to them. Image
    models pulled straight from the catalog are filtered by ``today`` unless
    ``include_deprecated`` is set.
    """
    index = build_litellm_index(source, list(curated))
    catalog: dict[str, dict[str, dict]] = {}
    skipped: list[str] = []

    for provider, models in curated.items():
        out: dict[str, dict] = {}

        # Curated models (with reasoning_levels) that LiteLLM also knows about.
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
            row["reasoning_levels"] = model["reasoning_levels"]
            if "default_reasoning_effort" in model:
                row["default_reasoning_effort"] = model["default_reasoning_effort"]
            out[model_id] = row

        # Image models straight from the catalog (no reasoning_levels).
        for normalized, keys in index[provider].items():
            if normalized in out:
                continue  # a curated model already covers this key
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
    """Write the catalog as UTF-8 JSON with a trailing newline."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build providers.json by merging the curated "
        "providers/*/models.yaml with LiteLLM's public model price catalog.",
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
        "--metadata-dir",
        type=Path,
        default=DEFAULT_METADATA_DIR,
        help="directory containing <provider>/models.yaml files "
        "(default: providers/ next to this script)",
    )
    parser.add_argument(
        "--include-deprecated",
        action="store_true",
        help="keep image models whose deprecation date has already passed",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="list the number of models extracted per provider and skipped curated models",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source = load_source(args.source)
    curated = load_curated_models(args.metadata_dir)
    # LiteLLM publishes plain calendar dates, so the local date is the right
    # reference point for "deprecation date has passed".
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

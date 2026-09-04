"""File-backed prompt asset loading and strict template rendering."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import Template
import tomllib
from typing import Mapping


class PromptAssetError(RuntimeError):
    """Raised when the prompt catalog is missing or malformed."""


class PromptRenderError(ValueError):
    """Raised when a prompt template cannot be rendered strictly."""


@dataclass(frozen=True, slots=True)
class PromptAsset:
    asset_id: str
    version: str
    template: str


class PromptManager:
    """Load versioned prompt text from a TOML catalog outside Python source."""

    def __init__(self, catalog_path: Path | None = None) -> None:
        self.catalog_path = catalog_path or Path(__file__).with_name("assets") / "catalog.toml"
        self._assets: dict[tuple[str, str], PromptAsset] = {}
        self._defaults: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        try:
            catalog = tomllib.loads(self.catalog_path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise PromptAssetError(f"Unable to load prompt catalog: {self.catalog_path}") from exc

        if catalog.get("schema_version") != 1:
            raise PromptAssetError("Prompt catalog schema_version must be 1.")
        prompts = catalog.get("prompts")
        if not isinstance(prompts, dict) or not prompts:
            raise PromptAssetError("Prompt catalog must define a non-empty [prompts] table.")

        assets: dict[tuple[str, str], PromptAsset] = {}
        defaults: dict[str, str] = {}
        for asset_id, raw in prompts.items():
            if not isinstance(raw, dict):
                raise PromptAssetError(f"Prompt asset '{asset_id}' must be a table.")
            version = raw.get("version")
            template = raw.get("template")
            if not isinstance(version, str) or not version.strip():
                raise PromptAssetError(f"Prompt asset '{asset_id}' requires a version.")
            if not isinstance(template, str) or not template.strip():
                raise PromptAssetError(f"Prompt asset '{asset_id}' requires template text.")
            asset = PromptAsset(asset_id=asset_id, version=version, template=template.strip())
            key = (asset_id, version)
            if key in assets:
                raise PromptAssetError(f"Duplicate prompt asset '{asset_id}@{version}'.")
            assets[key] = asset
            defaults[asset_id] = version

        self._assets = assets
        self._defaults = defaults

    def get(self, asset_id: str, version: str | None = None) -> PromptAsset:
        resolved_version = version or self._defaults.get(asset_id)
        if resolved_version is None:
            raise LookupError(f"Prompt asset '{asset_id}' is not registered.")
        try:
            return self._assets[(asset_id, resolved_version)]
        except KeyError as exc:
            raise LookupError(
                f"Prompt asset '{asset_id}' version '{resolved_version}' is not registered."
            ) from exc

    def version(self, asset_id: str) -> str:
        return self.get(asset_id).version

    def assets(self) -> tuple[PromptAsset, ...]:
        return tuple(
            self._assets[key]
            for key in sorted(self._assets, key=lambda item: (item[0], item[1]))
        )

    def render(
        self,
        asset_id: str,
        variables: Mapping[str, object] | None = None,
        *,
        version: str | None = None,
    ) -> str:
        asset = self.get(asset_id, version)
        values = {key: str(value) for key, value in (variables or {}).items()}
        try:
            return Template(asset.template).substitute(values).strip()
        except KeyError as exc:
            missing = str(exc.args[0])
            raise PromptRenderError(
                f"Prompt asset '{asset.asset_id}@{asset.version}' requires variable '{missing}'."
            ) from exc
        except ValueError as exc:
            raise PromptRenderError(
                f"Prompt asset '{asset.asset_id}@{asset.version}' contains invalid template syntax."
            ) from exc


default_prompt_manager = PromptManager()

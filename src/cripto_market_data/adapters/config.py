"""Strict data configuration; no bot imports or implicit data-root discovery."""

import tomllib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cripto_market_data.domain.settings import MarketSettings

WORKSPACE = Path("/home/cams7/Dev/Cripto")


class MarketConfigError(ValueError):
    """Fixed configuration diagnostic without supplied values."""


class MarketInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    source: Literal["fixture", "binance_public"]
    symbol: Literal["BTCUSDT"] = "BTCUSDT"
    interval: Literal["15m"] = "15m"
    fixture_file: str | None = None
    data_dir: str
    page_limit: int = Field(default=1000, ge=1, le=1000)
    max_pages: int = Field(default=10, ge=1, le=10)


class ConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    mode: Literal["PAPER"] = "PAPER"
    market: MarketInput


def contained(path: str, root: Path) -> Path:
    if not path:
        raise MarketConfigError("caminho invalido")
    try:
        result = (Path.cwd() / path).resolve()
        if not result.is_relative_to(root.resolve()) or result == root.resolve():
            raise MarketConfigError("caminho fora da raiz")
        return result
    except (OSError, ValueError, RuntimeError):
        raise MarketConfigError("caminho invalido") from None


def market_settings(
    item: MarketInput,
    root: Path,
    resolve_path: Callable[[str, Path], Path] = contained,
) -> MarketSettings:
    if (item.source == "fixture") != (item.fixture_file is not None):
        raise MarketConfigError("fixture inconsistente")
    return MarketSettings(
        source=item.source,
        root=root,
        data_dir=resolve_path(item.data_dir, root),
        fixture_file=None if item.fixture_file is None else resolve_path(item.fixture_file, root),
        symbol=item.symbol,
        interval=item.interval,
        page_limit=item.page_limit,
        max_pages=item.max_pages,
    )


def explicit_root(root: Path) -> Path:
    try:
        if not root.is_absolute():
            raise MarketConfigError("raiz absoluta obrigatoria")
        resolved = root.resolve()
        if not resolved.is_dir() or not resolved.is_relative_to(WORKSPACE.resolve()):
            raise MarketConfigError("raiz indisponivel")
        return resolved
    except (OSError, RuntimeError):
        raise MarketConfigError("raiz indisponivel") from None


def load_config(path: Path, environ: Mapping[str, str], *, root: Path) -> MarketSettings:
    root = explicit_root(root)
    try:
        with path.open("rb") as stream:
            parsed = ConfigInput.model_validate(tomllib.load(stream))
    except (OSError, ValueError, ValidationError):
        raise MarketConfigError("configuracao nao suportada") from None
    if any(key in environ for key in ("BINANCE_API_KEY", "BINANCE_API_SECRET")):
        raise MarketConfigError("credenciais Binance nao permitidas")
    if any(key.startswith("CRIPTO_BOT_") and key != "CRIPTO_BOT_MODE" for key in environ):
        raise MarketConfigError("variavel de configuracao nao suportada")
    if "CRIPTO_BOT_MODE" in environ and environ["CRIPTO_BOT_MODE"] != "PAPER":
        raise MarketConfigError("modo nao permitido")
    return market_settings(parsed.market, root)

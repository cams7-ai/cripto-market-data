"""Explicit data paths and bounded source settings, without bot configuration."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class MarketSettings:
    source: Literal["fixture", "binance_public"]
    root: Path
    data_dir: Path
    fixture_file: Path | None = None
    symbol: Literal["BTCUSDT"] = "BTCUSDT"
    interval: Literal["15m"] = "15m"
    page_limit: int = 1000
    max_pages: int = 10

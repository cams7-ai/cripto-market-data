"""One collection workflow shared by standalone CLI and consuming applications."""

import sqlite3
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path

from cripto_market_data.adapters.binance.fixture import fixture_source
from cripto_market_data.adapters.binance.public import HOST, Budget, PublicSource
from cripto_market_data.adapters.config import MarketConfigError
from cripto_market_data.adapters.storage.export import export_market
from cripto_market_data.adapters.storage.sqlite import SQLiteMarketStore
from cripto_market_data.application.collect import Progress, collect_market
from cripto_market_data.domain.market import MarketError, canonical, digest, timestamp, window
from cripto_market_data.domain.settings import MarketSettings

Exporter = Callable[[SQLiteMarketStore, str, int, int, str, dict[str, object]], Path]


@dataclass(frozen=True)
class CollectionAdapters:
    public_factory: Callable[..., PublicSource]
    fixture_factory: Callable[[Path, Budget], tuple[str, PublicSource]]
    store_factory: Callable[[Path], SQLiteMarketStore]
    budget_factory: Callable[[], Budget]
    exporter: Exporter
    wall_time: Callable[[], float] = time.time


def defaults(package_version: str) -> CollectionAdapters:
    return CollectionAdapters(
        PublicSource,
        fixture_source,
        SQLiteMarketStore,
        Budget,
        partial(export_market, package_version=package_version),
    )


def execute_collection(
    config: MarketSettings,
    start_text: str,
    end_text: str,
    allow_network: bool,
    run_id: str,
    *,
    provenance: Callable[[], dict[str, object]],
    adapters: CollectionAdapters,
) -> tuple[int, dict[str, object]]:
    if allow_network != (config.source == "binance_public"):
        raise MarketConfigError("opt-in de rede inconsistente")
    try:
        start, end = timestamp(start_text), timestamp(end_text)
        window(start, end, config.page_limit * config.max_pages)
    except MarketError:
        raise MarketConfigError("janela invalida") from None
    progress = Progress(start)
    budget = adapters.budget_factory()
    budget.remaining()
    dataset = "binance_public:" + HOST + ":v1"
    result: dict[str, object] = {
        "dataset": None,
        "source": config.source,
        "symbol": config.symbol,
        "interval": config.interval,
        "start": start,
        "end": end,
        "orders_sent": 0,
    }
    source: PublicSource | None = None
    try:
        if config.source == "fixture":
            assert config.fixture_file is not None
            dataset, source = adapters.fixture_factory(config.fixture_file, budget)
        result["dataset"] = dataset
        with adapters.store_factory(config.data_dir) as store:
            checkpoint = store.checkpoint(dataset, start)
            store.verify_prefix(dataset, start, checkpoint)
            progress.next_open_time = min(checkpoint, end)
            if config.source == "binance_public":
                if store.not_before() > adapters.wall_time():
                    raise MarketError("SOURCE_BLOCKED")
                source = adapters.public_factory(budget=budget, blocked_until=store.block_until)
            assert source is not None
            collect_market(
                source,
                store,
                dataset,
                start,
                end,
                config.page_limit,
                config.max_pages,
                progress,
                budget.remaining,
            )
            budget.remaining()
            context: dict[str, object] = {
                "source": config.source,
                **provenance(),
                "fixture_sha256": dataset.split(":")[1] if config.source == "fixture" else None,
                "config_sha256": digest(
                    canonical(
                        {
                            "mode": "PAPER",
                            "source": config.source,
                            "symbol": config.symbol,
                            "interval": config.interval,
                            "page_limit": config.page_limit,
                            "max_pages": config.max_pages,
                            "data_dir": str(config.data_dir),
                            "fixture_file": str(config.fixture_file),
                        }
                    ).encode()
                ),
            }
            manifest = adapters.exporter(store, dataset, start, end, run_id, context)
            budget.remaining()
            result.update(status="COLLECTED", complete=True, manifest=str(manifest))
        code = 0
    except (MarketError, OSError, sqlite3.Error) as error:
        result.update(
            status="COLLECTION_FAILED",
            complete=False,
            error_code=str(error) if isinstance(error, MarketError) else "STORAGE_FAILURE",
        )
        code = 3
    finally:
        if source is not None:
            source.close()
    result.update(asdict(progress))
    return code, result

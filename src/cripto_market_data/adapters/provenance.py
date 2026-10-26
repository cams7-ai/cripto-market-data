"""Standalone producer identity; never inspect the bot or its Git/data-root as code."""

from cripto_core.serialization import canonical, digest

from cripto_market_data.adapters.inspection import inspect_package
from cripto_market_data.domain.settings import MarketSettings


def runtime_identity() -> dict[str, object]:
    return {
        "schema": "market-producer-v1",
        "packages": {
            "cripto_market_data": inspect_package(
                "cripto_market_data", "0.1.0", editable_names=frozenset({"cripto_market_data"})
            ),
            "cripto_core": inspect_package("cripto_core", "0.1.0"),
        },
    }


def producer_context(config: MarketSettings) -> dict[str, object]:
    identity = runtime_identity()
    return {
        "producer": "cripto-market-data",
        "code_revision": "package:cripto-market-data:0.1.0",
        "source_sha256": digest(canonical(identity).encode()),
        "data_root": str(config.root),
    }

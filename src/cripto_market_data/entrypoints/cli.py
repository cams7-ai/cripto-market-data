"""Explicit-root local PAPER market CLI with no financial module or bot dependency."""

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from typing import Never, TextIO
from uuid import uuid4

from cripto_market_data.adapters.clock import utc_now, utc_timestamp
from cripto_market_data.adapters.config import MarketConfigError, load_config
from cripto_market_data.adapters.provenance import producer_context
from cripto_market_data.application.collection import defaults, execute_collection


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise MarketConfigError("argumentos invalidos")


def emit(stream: TextIO, payload: dict[str, object]) -> None:
    stream.write(json.dumps(payload, ensure_ascii=True, allow_nan=False) + "\n")
    stream.flush()


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    clock: Callable[[], datetime] = utc_now,
    new_id: Callable[[], str] = lambda: str(uuid4()),
) -> int:
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    env = os.environ if environ is None else environ
    run_id = new_id()
    try:
        timestamp = utc_timestamp(clock())
        parser = SafeParser(prog="cripto-market-data", description="Dados Spot locais/PAPER")
        sub = parser.add_subparsers(dest="command", required=True)
        for name in ("check-config", "collect-market"):
            command = sub.add_parser(name)
            command.add_argument("--root", type=Path, required=True)
            command.add_argument("--config", type=Path, required=True)
            if name == "collect-market":
                command.add_argument("--start", required=True)
                command.add_argument("--end", required=True)
                command.add_argument("--allow-network", action="store_true")
        args = parser.parse_args(argv)
        config = load_config(args.config, env, root=args.root)
        common: dict[str, object] = {"run_id": run_id, "timestamp": timestamp, "mode": "PAPER"}
        code = 0
        if args.command == "check-config":
            result = {**common, "status": "VALID", "orders_sent": 0}
        else:
            code, collected = execute_collection(
                config,
                args.start,
                args.end,
                args.allow_network,
                run_id,
                provenance=lambda: producer_context(config),
                adapters=defaults(version("cripto-market-data")),
            )
            result = {**common, **collected}
        emit(err, {**common, "level": "INFO" if code == 0 else "ERROR", "event": args.command})
        emit(out, result)
        return code
    except MarketConfigError:
        emit(
            err,
            {
                "timestamp": utc_timestamp(clock()),
                "level": "ERROR",
                "event": "configuration_rejected",
                "run_id": run_id,
                "error_code": "INVALID_CONFIG",
            },
        )
        return 2
    except Exception:
        emit(
            err,
            {
                "timestamp": utc_timestamp(utc_now()),
                "level": "ERROR",
                "event": "internal_failure",
                "run_id": run_id,
                "error_code": "INTERNAL_ERROR",
            },
        )
        return 1

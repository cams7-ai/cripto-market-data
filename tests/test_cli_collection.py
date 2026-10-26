"""Standalone configuration, producer boundary and controller failure contracts."""

import ast
import importlib.util
import json
from dataclasses import replace
from io import StringIO
from pathlib import Path

import httpx
import pytest

from cripto_market_data.adapters.binance.public import PublicSource
from cripto_market_data.adapters.config import MarketConfigError, load_config
from cripto_market_data.adapters.storage.sqlite import SQLiteMarketStore
from cripto_market_data.application.collection import defaults, execute_collection
from cripto_market_data.entrypoints.cli import main
from tests.factories import fixture_file


def configuration(tmp_path, **changes):
    fixture = fixture_file(tmp_path / "fixture.json")
    values = {"source": "fixture", "fixture_file": str(fixture), "data_dir": str(tmp_path / "data")}
    values.update(changes)
    config = tmp_path / "config.toml"
    config.write_text(
        'mode="PAPER"\n[market]\n' + "\n".join(f"{k}={json.dumps(v)}" for k, v in values.items())
    )
    return config


def invoke(config, root, command="collect-market", more=(), env=None):
    args = [command, "--root", str(root), "--config", str(config)]
    if command == "collect-market":
        args += ["--start", "2026-10-01T00:00:00Z", "--end", "2026-10-01T00:30:00Z"]
    out, err = StringIO(), StringIO()
    code = main([*args, *more], environ={} if env is None else env, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def test_standalone_config_collection_and_producer(tmp_path):
    config = configuration(tmp_path)
    code, out, err = invoke(config, tmp_path, "check-config")
    assert code == 0 and json.loads(out)["status"] == "VALID"
    assert not (tmp_path / "data").exists()
    results = []
    for inserted in [2, 0]:
        code, out, err = invoke(config, tmp_path)
        result = json.loads(out)
        assert code == 0 and result["inserted"] == inserted and result["orders_sent"] == 0
        assert json.loads(err)["run_id"] == result["run_id"]
        manifest = json.loads(Path(result["manifest"]).read_text())
        assert manifest["producer"] == "cripto-market-data"
        assert manifest["package_version"] == "0.1.0"
        assert manifest["code_revision"] == "package:cripto-market-data:0.1.0"
        assert set(manifest["files"]) == {
            "candles.jsonl.gz",
            "raw.jsonl.gz",
            "snapshots.json",
            "provenance.json",
        }
        results.append(manifest)
    assert results[0]["data_sha256"] == results[1]["data_sha256"]
    assert results[0]["config_sha256"] == results[1]["config_sha256"]


@pytest.mark.parametrize(
    "changes",
    [
        {"symbol": "ETHUSDT"},
        {"interval": "1m"},
        {"page_limit": True},
        {"page_limit": 0},
        {"page_limit": 1001},
        {"max_pages": 11},
        {"data_dir": ""},
        {"data_dir": "/tmp/outside"},
        {"endpoint": "SYNTHETIC_SECRET"},
        {"source": "LIVE"},
        {"source": "binance_public"},
    ],
)
def test_invalid_market_is_sanitized_and_has_no_effect(tmp_path, changes):
    config = configuration(tmp_path, **changes)
    code, out, err = invoke(config, tmp_path)
    assert code == 2 and out == "" and "SYNTHETIC_SECRET" not in err
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize(
    "env",
    [
        {"BINANCE_API_KEY": ""},
        {"BINANCE_API_SECRET": "SYNTHETIC_SECRET"},
        {"CRIPTO_BOT_MODE": "LIVE"},
        {"CRIPTO_BOT_UNKNOWN": "SYNTHETIC_SECRET"},
    ],
)
def test_forbidden_environment(tmp_path, env):
    config = configuration(tmp_path)
    code, out, err = invoke(config, tmp_path, env=env)
    assert code == 2 and out == "" and "SYNTHETIC_SECRET" not in err
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize(
    "root", ["relative", "/tmp", "/home/cams7/Dev/Cripto/nonexistent-06b-root"]
)
def test_explicit_root_required_and_contained(tmp_path, root):
    config = configuration(tmp_path)
    assert invoke(config, Path(root))[0] == 2
    assert not (tmp_path / "data").exists()


def test_extra_financial_config_and_missing_file_are_rejected(tmp_path):
    config = configuration(tmp_path)
    config.write_text(config.read_text() + '\n[paper]\ninitial_usdt="1"\n')
    assert invoke(config, tmp_path)[0] == 2
    config.unlink()
    assert invoke(config, tmp_path)[0] == 2


def test_symlink_escape_and_missing_fixture_do_not_create_state(tmp_path):
    alias = tmp_path / "alias"
    alias.symlink_to("/tmp", target_is_directory=True)
    config = configuration(tmp_path, data_dir=str(alias / "outside"))
    assert invoke(config, tmp_path)[0] == 2
    config = configuration(tmp_path)
    (tmp_path / "fixture.json").unlink()
    code, out, err = invoke(config, tmp_path)
    assert code == 3 and json.loads(out)["error_code"] == "FIXTURE_UNREADABLE"
    assert not (tmp_path / "data").exists()


def test_precondition_checks_before_factories(tmp_path):
    config = configuration(tmp_path)
    settings = load_config(config, {}, root=tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("factory called before validation")

    adapters = replace(defaults("0.1.0"), public_factory=forbidden, store_factory=forbidden)
    for start, end, network in [("bad", "bad", False), ("bad", "bad", True)]:
        with pytest.raises(MarketConfigError):
            execute_collection(
                settings, start, end, network, "test", provenance=lambda: {}, adapters=adapters
            )
    config.write_text(f'[market]\nsource="binance_public"\ndata_dir="{tmp_path / "data"}"')
    settings = load_config(config, {}, root=tmp_path)
    with pytest.raises(MarketConfigError):
        execute_collection(
            settings,
            "2026-10-01T00:00:00Z",
            "2026-10-01T00:30:00Z",
            False,
            "test",
            provenance=lambda: {},
            adapters=adapters,
        )
    assert not settings.data_dir.exists()


def test_fixture_opt_in_rejected_and_shared_lock(tmp_path):
    config = configuration(tmp_path)
    assert invoke(config, tmp_path, more=["--allow-network"])[0] == 2
    assert not (tmp_path / "data").exists()
    with SQLiteMarketStore(tmp_path / "data"):
        code, out, err = invoke(config, tmp_path)
        assert code == 3 and json.loads(out)["error_code"] == "WRITER_BUSY"
    assert invoke(config, tmp_path)[0] == 0


def test_public_mock_ban_and_export_failure_recovery(tmp_path):
    config = configuration(tmp_path)
    settings = load_config(config, {}, root=tmp_path)

    def fail(*args, **kwargs):
        raise OSError("SYNTHETIC_SECRET")

    adapters = replace(defaults("0.1.0"), exporter=fail)
    args = (settings, "2026-10-01T00:00:00Z", "2026-10-01T00:30:00Z", False, "failed")
    code, result = execute_collection(*args, provenance=lambda: {}, adapters=adapters)
    assert code == 3 and "SYNTHETIC_SECRET" not in json.dumps(result)
    code, result = execute_collection(
        *args[:-1], "recovered", provenance=lambda: {}, adapters=defaults("0.1.0")
    )
    assert code == 0 and result["inserted"] == 0
    settings = replace(settings, source="binance_public", fixture_file=None)
    calls = []

    def factory(**kwargs):
        def handler(request):
            calls.append(request)
            return httpx.Response(418, headers={"Retry-After": "60"})

        return PublicSource(**kwargs, transport=httpx.MockTransport(handler))

    adapters = replace(defaults("0.1.0"), public_factory=factory)
    for error in ["IP_BANNED", "SOURCE_BLOCKED"]:
        code, result = execute_collection(
            settings, *args[1:3], True, error, provenance=lambda: {}, adapters=adapters
        )
        assert code == 3 and result["error_code"] == error
    assert len(calls) == 1


def test_no_bot_analytics_or_financial_dependency():
    assert importlib.util.find_spec("cripto_bot") is None
    assert importlib.util.find_spec("duckdb") is None
    root = Path(importlib.util.find_spec("cripto_market_data").origin).parent
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = (
                [n.name for n in node.names]
                if isinstance(node, ast.Import)
                else ([node.module] if isinstance(node, ast.ImportFrom) else [])
            )
            assert not any(
                n.split(".")[0] in {"cripto_bot", "duckdb", "boto3", "cripto_analytics"}
                for n in names
            )

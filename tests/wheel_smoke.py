"""Exercise the installed standalone wheel without a bot, under the socket audit guard."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path, required=True)
    args = parser.parse_args()
    console = args.python.absolute().parent / "cripto-market-data"
    runner = ROOT / "tests/offline_runner.py"
    parent = ROOT / "reports/sprint06b/standalone"
    scratch = Path(tempfile.mkdtemp(prefix="wheel-", dir=parent))
    fixture = scratch / "fixture.json"
    shutil.copyfile(ROOT / "config/fixtures/market-sample.json", fixture)
    config = scratch / "fixture.toml"
    config.write_text(
        'mode="PAPER"\n[market]\nsource="fixture"\n'
        f'fixture_file="{fixture}"\ndata_dir="{scratch / "data"}"'
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("CRIPTO_BOT_")
        and k not in {"PYTHONPATH", "BINANCE_API_KEY", "BINANCE_API_SECRET"}
    }
    # Use the environment's executable path, without resolving its interpreter symlink.
    python = args.python.absolute()
    proof_code = (
        "import importlib.util,json,cripto_market_data,cripto_core;"
        "from cripto_market_data.adapters.provenance import runtime_identity;"
        "assert importlib.util.find_spec('cripto_bot') is None;"
        "assert importlib.util.find_spec('duckdb') is None;"
        "print(json.dumps({'market':cripto_market_data.__file__,'core':cripto_core.__file__,"
        "'identity':runtime_identity()}))"
    )
    proc = subprocess.run(
        [str(python), "-I", str(runner), "--code", proof_code],
        cwd=scratch,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    proof = json.loads(proc.stdout)
    assert "site-packages/cripto_market_data/__init__.py" in proof["market"]
    assert "site-packages/cripto_core/__init__.py" in proof["core"]
    assert all(p["installation"] == "wheel" for p in proof["identity"]["packages"].values())
    checks = []

    def invoke(command, extra=(), expected=0):
        argv = [
            str(python),
            "-I",
            str(runner),
            str(console),
            command,
            "--root",
            str(scratch),
            "--config",
            str(config),
        ]
        if command == "collect-market":
            argv += ["--start", "2026-10-01T00:00:00Z", "--end", "2026-10-01T00:30:00Z"]
        result = subprocess.run(
            [*argv, *extra], cwd=scratch, env=env, text=True, capture_output=True
        )
        assert result.returncode == expected, result.stdout + result.stderr
        checks.append(
            {
                "command": command,
                "extra": list(extra),
                "exit": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        return json.loads(result.stdout) if result.stdout else None

    assert invoke("check-config")["status"] == "VALID"
    assert not (scratch / "data").exists()
    first = invoke("collect-market")
    second = invoke("collect-market")
    assert first["inserted"] == 2 and second["inserted"] == 0
    manifests = [json.loads(Path(x["manifest"]).read_text()) for x in [first, second]]
    assert manifests[0]["data_sha256"] == manifests[1]["data_sha256"]
    for result, manifest in zip([first, second], manifests, strict=True):
        assert result["orders_sent"] == 0 and manifest["producer"] == "cripto-market-data"
        for name, digest in manifest["files"].items():
            assert (
                hashlib.sha256((Path(result["manifest"]).parent / name).read_bytes()).hexdigest()
                == digest
            )
    invoke("collect-market", ["--allow-network"], 2)
    config.write_text(f'[market]\nsource="binance_public"\ndata_dir="{scratch / "public"}"')
    invoke("collect-market", expected=2)
    assert not (scratch / "public").exists()
    probe = subprocess.run(
        [str(python), "-I", str(runner), "--probe"],
        cwd=scratch,
        env=env,
        text=True,
        capture_output=True,
    )
    assert probe.returncode != 0 and "NETWORK_BLOCKED" in probe.stderr
    print(
        json.dumps(
            {
                "scratch": str(scratch),
                "origins": proof,
                "checks": checks,
                "data_sha256": manifests[0]["data_sha256"],
                "probe_blocked": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

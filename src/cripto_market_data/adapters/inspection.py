"""Check the actual loaded distribution; the caller owns composition policy."""

import base64
import hashlib
import json
from collections.abc import Callable
from importlib import import_module, metadata
from pathlib import Path
from types import ModuleType
from urllib.parse import unquote, urlsplit

from cripto_core.errors import PaperError


def inspect_package(
    name: str,
    expected_version: str | None = None,
    *,
    importer: Callable[[str], ModuleType] = import_module,
    editable_names: frozenset[str] = frozenset(),
) -> dict[str, object]:
    try:
        distribution = metadata.distribution(name.replace("_", "-"))
        if expected_version is not None and distribution.version != expected_version:
            raise PaperError("PACKAGE_VERSION_MISMATCH")
        module = importer(name)
        if module.__file__ is None:
            raise PaperError("SOURCE_IDENTITY_UNAVAILABLE")
        package = Path(module.__file__).resolve().parent
        sources = sorted(package.rglob("*.py"))
        if not sources or not (package / "__init__.py").is_file():
            raise PaperError("SOURCE_IDENTITY_UNAVAILABLE")
        direct = json.loads(distribution.read_text("direct_url.json") or "{}")
        editable = direct.get("dir_info", {}).get("editable") is True
        content = {
            str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
        }
        if editable:
            # An editable is accepted only when explicitly authorized by the caller.
            url = urlsplit(direct["url"])
            if name not in editable_names or url.scheme != "file" or url.netloc:
                raise PaperError("UNSUPPORTED_PACKAGE_INSTALLATION")
            origin = Path(unquote(url.path)).resolve() / "src" / name
            if origin != package:
                raise PaperError("PACKAGE_ORIGIN_MISMATCH")
        else:
            recorded = distribution.files
            if recorded is None:
                raise PaperError("PACKAGE_RECORD_MISSING")
            entries = {
                str(p): p
                for p in recorded
                if str(p).startswith(name + "/")
                and (str(p).endswith(".py") or str(p).endswith("py.typed"))
            }
            typed = package / "py.typed"
            if typed.is_file():
                content["py.typed"] = hashlib.sha256(typed.read_bytes()).hexdigest()
            if set(entries) != {name + "/" + p for p in content}:
                raise PaperError("PACKAGE_RECORD_MISMATCH")
            for relative, digest in content.items():
                entry = entries[name + "/" + relative]
                if Path(str(distribution.locate_file(entry))).resolve() != package / relative:
                    raise PaperError("PACKAGE_ORIGIN_MISMATCH")
                encoded = base64.urlsafe_b64encode(bytes.fromhex(digest)).rstrip(b"=").decode()
                if entry.hash is None or entry.hash.mode != "sha256" or entry.hash.value != encoded:
                    raise PaperError("PACKAGE_RECORD_MISMATCH")
        return {
            "version": distribution.version,
            "installation": "editable" if editable else "wheel",
            "files": content,
        }
    except PaperError:
        raise
    except (OSError, ValueError, KeyError, TypeError, ImportError, metadata.PackageNotFoundError):
        raise PaperError("SOURCE_IDENTITY_UNAVAILABLE") from None

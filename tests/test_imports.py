"""Import smoke test — every module in the package must import cleanly.

This is the safety net for structural refactors: a moved module with a stale
import breaks here immediately, even if no other test exercises that module.
Modules keep heavy/optional deps (moviepy, google-*) behind lazy imports, so
importing the module itself is always safe.
"""
import importlib
import pkgutil

import carshorts


def test_every_module_imports():
    failed = []
    for mod in pkgutil.walk_packages(carshorts.__path__, carshorts.__name__ + "."):
        try:
            importlib.import_module(mod.name)
        except Exception as exc:  # noqa: BLE001 — report all, don't stop at first
            failed.append(f"{mod.name}: {exc!r}")
    assert not failed, "modules failed to import:\n  " + "\n  ".join(failed)

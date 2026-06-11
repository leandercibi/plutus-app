from __future__ import annotations

import ast
import inspect

from plutus.data import universe


def test_get_live_universe_exists() -> None:
    assert hasattr(universe, "get_live_universe")


def test_get_universe_at_does_not_call_live_universe() -> None:
    """A17 CI rule: the PIT lookup must never recompute via the live universe."""
    src = inspect.getsource(universe.get_universe_at)
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        if isinstance(node, ast.Name):
            names.add(node.id)
    assert "get_live_universe" not in names


def test_build_snapshot_does_not_call_live_universe() -> None:
    src = inspect.getsource(universe.build_universe_snapshot)
    assert "get_live_universe" not in src


def test_module_source_isolation() -> None:
    # belt-and-suspenders: the PIT lookup body never calls the live universe builder
    body = inspect.getsource(universe.get_universe_at)
    assert "get_live_universe(" not in body

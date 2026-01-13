import importlib
import os
import sys
import types

# Ensure src can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _install_fake_assassyn(monkeypatch, calls):
    """Inject a minimal assassyn.frontend stub for testing."""
    fake_frontend = types.SimpleNamespace()

    def fake_log(fmt, *args):
        calls.append((fmt, args))

    fake_frontend.log = fake_log
    monkeypatch.setitem(sys.modules, "assassyn", types.SimpleNamespace(frontend=fake_frontend))
    monkeypatch.setitem(sys.modules, "assassyn.frontend", fake_frontend)


def test_log_register_snapshot_formats_index_without_int_operand(monkeypatch):
    calls = []
    _install_fake_assassyn(monkeypatch, calls)

    # Import module after installing the fake assassyn.frontend
    debug_utils = importlib.import_module("src.debug_utils")

    sample_register_file = [0x12345678]
    debug_utils.log_register_snapshot(sample_register_file)

    # First call is the snapshot header
    assert calls[0][0] == "Final register file state:"

    # Second call contains the register value, placeholder only for the value itself
    fmt, args = calls[1]
    assert fmt == "  x0 = 0x{:x}"
    assert args == (sample_register_file[0],)

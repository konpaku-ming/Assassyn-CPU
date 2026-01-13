import importlib
import os
import sys
import types

# 确保可以 import src
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

    # 重新加载模块以使用假的 assassyn.frontend
    sys.modules.pop("src.debug_utils", None)
    debug_utils = importlib.import_module("src.debug_utils")

    reg_file = [0x12345678]
    debug_utils.log_register_snapshot(reg_file)

    # 首行是快照标题
    assert calls[0][0] == "Final register file state:"

    # 第二行包含寄存器值，占位符仅针对值本身
    fmt, args = calls[1]
    assert fmt == "  x0 = 0x{:x}"
    assert args == (reg_file[0],)

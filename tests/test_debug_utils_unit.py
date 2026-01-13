import importlib
import os
import sys
import types

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_log_register_snapshot_outputs_all_registers():
    fake_assassyn = types.ModuleType("assassyn")
    fake_assassyn.__path__ = []
    fake_frontend = types.ModuleType("assassyn.frontend")

    logs = []

    def fake_log(fmt, *args):
        logs.append(fmt.format(*args))

    fake_frontend.log = fake_log
    fake_assassyn.frontend = fake_frontend

    sys.modules["assassyn"] = fake_assassyn
    sys.modules["assassyn.frontend"] = fake_frontend

    debug_utils = importlib.reload(importlib.import_module("src.debug_utils"))

    reg_file = list(range(8))
    debug_utils.log_register_snapshot(reg_file)

    assert logs[0] == "Final register file state:"
    assert logs[1:] == [f"  x{i} = 0x{i:x}" for i in range(len(reg_file))]

    sys.modules.pop("assassyn.frontend", None)
    sys.modules.pop("assassyn", None)
    sys.modules.pop("src.debug_utils", None)

from assassyn.frontend import log

MAX_REGISTERS = 32


def log_register_snapshot(reg_file):
    """
    打印寄存器文件的快照。若 reg_file 为空则跳过。
    会按 x0..x31 顺序直接以字符串形式输出到屏幕。
    """
    if reg_file is None:
        return
    log("Final register file state:")
    try:
        reg_count = min(len(reg_file), MAX_REGISTERS)
    except (TypeError, AttributeError):
        reg_count = MAX_REGISTERS
    for idx in range(reg_count):
        try:
            log(f"  x{idx} = {reg_file[idx]}")
        except (IndexError, TypeError, AttributeError):
            log(f"  x{idx} = <unavailable>")
            continue

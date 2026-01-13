from assassyn.frontend import log_file

MAX_REGISTERS = 32


def log_register_snapshot(reg_file):
    """
    打印寄存器文件的快照。若 reg_file 为空则跳过。
    会按 x0..x31 顺序输出十六进制值，写入到单独的 "reg" 文件中。
    """
    if reg_file is None:
        return
    log_file("reg", "Final register file state:")
    try:
        reg_count = min(len(reg_file), MAX_REGISTERS)
    except (TypeError, AttributeError):
        reg_count = MAX_REGISTERS
    for idx in range(reg_count):
        try:
            log_file("reg", f"  x{idx} = 0x{{:x}}", reg_file[idx])
        except (IndexError, TypeError, AttributeError):
            log_file("reg", f"  x{idx} = <unavailable>")
            continue

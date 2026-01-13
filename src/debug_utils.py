from assassyn.frontend import log


def log_register_snapshot(reg_file):
    """
    打印寄存器堆的快照。若 reg_file 为空则跳过。
    会按 x0..x31 顺序输出十六进制值，便于在结束日志中快速检查寄存器状态。
    """
    if reg_file is None:
        return
    log("Final register file state:")
    for idx in range(32):
        log("  x{} = 0x{:x}", idx, reg_file[idx])

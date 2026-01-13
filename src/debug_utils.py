from assassyn.frontend import log


def log_register_snapshot(reg_file):
    if reg_file is None:
        return
    log("Final register file state:")
    for idx in range(32):
        log("  x{} = 0x{:x}", idx, reg_file[idx])

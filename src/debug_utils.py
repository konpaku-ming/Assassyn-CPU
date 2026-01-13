from assassyn.frontend import log

MAX_REGISTERS = 32

# 调试模式开关，默认打开
# True: 打印所有日志（与当前行为相同）
# False: 只打印停机时的寄存器状态
DEBUG_MODE = False


def set_debug_mode(enabled: bool):
    """设置调试模式开关"""
    global DEBUG_MODE
    DEBUG_MODE = enabled


def get_debug_mode() -> bool:
    """获取当前调试模式状态"""
    return DEBUG_MODE


def debug_log(*args, **kwargs):
    """
    调试日志函数。仅当 DEBUG_MODE 为 True 时才打印日志。
    参数与 assassyn.frontend.log 相同。
    """
    if DEBUG_MODE:
        log(*args, **kwargs)


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
            log(f"  x{idx} = 0x{{:x}}", reg_file[idx])
        except (IndexError, TypeError, AttributeError):
            log(f"  x{idx} = <unavailable>")
            continue

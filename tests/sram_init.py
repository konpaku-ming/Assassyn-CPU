from assassyn.frontend import *
from assassyn.backend import elaborate, config
from assassyn import utils
from assassyn.frontend import SRAM
from src.control_signals import MemWidth, MemSign


class SRAMInitializer:
    """
    SRAM 初始化类，用于创建和初始化真正的 SRAM 实例
    替代 MockSRAM，提供真实的 SRAM 功能
    """
    
    def __init__(self, width=32, depth=1024):
        """
        初始化 SRAM
        
        参数:
            width: SRAM 的位宽 (默认: 32)
            depth: SRAM 的深度 (默认: 1024)
        """
        self.width = width
        self.depth = depth
        self.addr_width = (depth - 1).bit_length()  # 计算地址宽度
        self.sram = SRAM(width=width, depth=depth)
        
        # 初始化测试数据
        self._init_test_data()
    
    def _init_test_data(self):
        """
        初始化 SRAM 中的测试数据
        与 MockSRAM 中的测试数据保持一致:
        - 在地址 0x1000 处存储 0x12345678
        - 在地址 0x1004 处存储 0xABCDEF00
        - 在地址 0x1008 处存储 0x11223344
        """
        # 注意：SRAM 的地址是字地址，需要将字节地址转换为字地址
        # 例如：字节地址 0x1000 对应字地址 0x1000 >> 2 = 0x400
        self.sram.write(addr=0x400, data=Bits(32)(0x12345678))  # 地址 0x1000
        self.sram.write(addr=0x401, data=Bits(32)(0xABCDEF00))  # 地址 0x1004
        self.sram.write(addr=0x402, data=Bits(32)(0x11223344))  # 地址 0x1008
    
    def get_sram(self):
        """
        获取初始化好的 SRAM 实例
        
        返回:
            初始化好的 SRAM 实例
        """
        return self.sram
    
    def read(self, addr):
        """
        从 SRAM 中读取数据
        
        参数:
            addr: 要读取的地址（字节地址）
            
        返回:
            读取到的数据
        """
        # 将字节地址转换为字地址
        word_addr = addr >> 2
        return self.sram.read(addr=word_addr)
    
    def write(self, addr, data):
        """
        向 SRAM 中写入数据
        
        参数:
            addr: 要写入的地址（字节地址）
            data: 要写入的数据
        """
        # 将字节地址转换为字地址
        word_addr = addr >> 2
        self.sram.write(addr=word_addr, data=data)


def create_sram_with_test_data(width=32, depth=1024):
    """
    创建并初始化一个包含测试数据的 SRAM 实例
    
    参数:
        width: SRAM 的位宽 (默认: 32)
        depth: SRAM 的深度 (默认: 1024)
    
    返回:
        初始化好的 SRAM 实例
    """
    initializer = SRAMInitializer(width=width, depth=depth)
    return initializer.get_sram()


def initialize_sram_in_sysbuilder(sys_builder, sram_name="test_sram", width=32, depth=1024):
    """
    在 SysBuilder 环境中初始化 SRAM
    
    参数:
        sys_builder: SysBuilder 实例
        sram_name: SRAM 的名称 (默认: "test_sram")
        width: SRAM 的位宽 (默认: 32)
        depth: SRAM 的深度 (默认: 1024)
    
    返回:
        初始化好的 SRAM 实例，已添加到 SysBuilder 中
    """
    # 创建并初始化 SRAM
    sram = create_sram_with_test_data(width=width, depth=depth)
    
    # 将 SRAM 添加到 SysBuilder 中
    sys_builder.add_module(sram, name=sram_name)
    
    return sram


# 兼容性函数，与 common.py 中的 create_initialized_sram 保持一致的接口
def create_initialized_sram(width=32, depth=1024, init_file=None):
    """
    创建并初始化一个 SRAM 实例 (兼容性函数)
    
    参数:
        width: SRAM 的位宽 (例如: 32)
        depth: SRAM 的深度 (例如: 1024)
        init_file: 初始化文件路径 (可选，在此实现中忽略)
    
    返回:
        初始化好的 SRAM 实例
    """
    # 忽略 init_file 参数，因为我们使用硬编码的测试数据
    return create_sram_with_test_data(width=width, depth=depth)
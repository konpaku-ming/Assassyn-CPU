#!/usr/bin/env python3
"""
工具脚本：从二进制文件生成 dcache/icache 初始化文件

功能：
- 读取 my0to100_text.bin（指令段）生成 my0to100.exe（用于 icache 初始化）
- 读取 my0to100_data.bin（数据段）生成 my0to100.data（用于 dcache 初始化）

默认输出格式：
- 文本文件，每行一个 32-bit 十六进制数（8 位十六进制字符，不带 0x 前缀）
- 小端序（Little-endian）
- 自动填充到 32-bit 字对齐

使用方法：
  python3 generate_workloads.py                    # 使用默认参数
  python3 generate_workloads.py --binary           # 输出原始二进制文件（如果需要）
  python3 generate_workloads.py --word-size 4      # 指定字宽（2 或 4 字节）
  python3 generate_workloads.py --endian big       # 指定大端序
"""

import sys
import os
import argparse
import struct


def bin_to_hex_lines(infile, outfile, word_size=4, endian='little'):
    """
    将二进制文件转换为十六进制文本文件（每行一个字）
    
    参数：
        infile: 输入二进制文件路径
        outfile: 输出文本文件路径
        word_size: 字宽（字节数），默认 4（32-bit）
        endian: 字节序，'little' 或 'big'，默认 'little'
    """
    with open(infile, 'rb') as f:
        data = f.read()
    
    # 如果文件为空，创建空输出文件
    if len(data) == 0:
        with open(outfile, 'w') as f:
            pass
        print(f"[INFO] Input file {infile} is empty, created empty {outfile}")
        return
    
    # 填充到字宽的整数倍
    if len(data) % word_size != 0:
        padding = word_size - (len(data) % word_size)
        data += b'\x00' * padding
        print(f"[INFO] Padded {padding} bytes to align to {word_size}-byte boundary")
    
    # 选择结构解包格式
    format_map = {
        ('little', 4): '<I',  # 32-bit unsigned, little-endian
        ('big', 4): '>I',     # 32-bit unsigned, big-endian
        ('little', 2): '<H',  # 16-bit unsigned, little-endian
        ('big', 2): '>H',     # 16-bit unsigned, big-endian
    }
    
    fmt = format_map.get((endian, word_size))
    if fmt is None:
        raise ValueError(f"Unsupported combination: word_size={word_size}, endian={endian}")
    
    # 逐字解析并转换为十六进制字符串
    lines = []
    for i in range(0, len(data), word_size):
        chunk = data[i:i+word_size]
        value = struct.unpack(fmt, chunk)[0]
        # 32-bit 用 8 位十六进制，16-bit 用 4 位十六进制
        hex_width = word_size * 2
        lines.append(f"{value:0{hex_width}x}")
    
    # 写入输出文件
    with open(outfile, 'w') as f:
        for line in lines:
            f.write(line + '\n')
    
    print(f"[SUCCESS] Wrote {len(lines)} words to {outfile}")
    print(f"          Format: {word_size*8}-bit hex, {endian}-endian")


def copy_binary(infile, outfile):
    """
    直接复制二进制文件（用于 --binary 模式）
    
    参数：
        infile: 输入文件路径
        outfile: 输出文件路径
    """
    with open(infile, 'rb') as fr:
        content = fr.read()
    
    with open(outfile, 'wb') as fw:
        fw.write(content)
    
    print(f"[SUCCESS] Copied binary {infile} -> {outfile} ({len(content)} bytes)")


def main():
    parser = argparse.ArgumentParser(
        description='生成 dcache/icache 初始化文件工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法：
  %(prog)s                                 # 默认：生成文本十六进制格式
  %(prog)s --binary                        # 输出原始二进制格式
  %(prog)s --word-size 2 --endian big      # 16-bit 大端序文本格式
  %(prog)s --text-in custom.bin            # 使用自定义输入文件名
        """
    )
    
    # 输入文件参数
    parser.add_argument(
        '--text-in',
        default='my0to100_text.bin',
        help='指令段二进制文件（默认：my0to100_text.bin）'
    )
    parser.add_argument(
        '--data-in',
        default='my0to100_data.bin',
        help='数据段二进制文件（默认：my0to100_data.bin）'
    )
    
    # 输出文件参数
    parser.add_argument(
        '--text-out',
        default='../workloads/my0to100.exe',
        help='指令段输出文件，用于 icache（默认：../workloads/my0to100.exe）'
    )
    parser.add_argument(
        '--data-out',
        default='../workloads/my0to100.data',
        help='数据段输出文件，用于 dcache（默认：../workloads/my0to100.data）'
    )
    
    # 格式选项
    parser.add_argument(
        '--binary',
        action='store_true',
        help='输出原始二进制文件而非文本十六进制（用于直接二进制加载）'
    )
    parser.add_argument(
        '--word-size',
        type=int,
        choices=[2, 4],
        default=4,
        help='字宽（字节数）：2=16-bit, 4=32-bit（默认：4）'
    )
    parser.add_argument(
        '--endian',
        choices=['little', 'big'],
        default='little',
        help='字节序：little 或 big（默认：little）'
    )
    
    args = parser.parse_args()
    
    # 确保输出目录存在
    outdirs = set()
    for outfile in [args.text_out, args.data_out]:
        outdir = os.path.dirname(outfile)
        if outdir and outdir not in outdirs:
            outdirs.add(outdir)
            os.makedirs(outdir, exist_ok=True)
            if not os.path.exists(outfile):  # Only print if directory was just created
                print(f"[INFO] Ensured output directory exists: {outdir}")
    
    # 打印配置信息
    print("=" * 60)
    print("生成 dcache/icache 初始化文件")
    print("=" * 60)
    print(f"输入文件（指令段）: {args.text_in}")
    print(f"输入文件（数据段）: {args.data_in}")
    print(f"输出文件（指令段）: {args.text_out}")
    print(f"输出文件（数据段）: {args.data_out}")
    print(f"输出格式: {'原始二进制' if args.binary else f'文本十六进制 ({args.word_size*8}-bit, {args.endian}-endian)'}")
    print("=" * 60)
    
    try:
        if args.binary:
            # 二进制模式：直接复制
            copy_binary(args.text_in, args.text_out)
            copy_binary(args.data_in, args.data_out)
        else:
            # 文本模式：转换为十六进制行
            bin_to_hex_lines(args.text_in, args.text_out, 
                           word_size=args.word_size, endian=args.endian)
            bin_to_hex_lines(args.data_in, args.data_out, 
                           word_size=args.word_size, endian=args.endian)
        
        print("=" * 60)
        print("✅ 生成完成！")
        print("=" * 60)
        
    except FileNotFoundError as e:
        print(f"\n❌ 错误：找不到输入文件 - {e}")
        print("   请确保在 main_test 目录下运行此脚本，或使用 --text-in 和 --data-in 指定正确路径")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 错误：{e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

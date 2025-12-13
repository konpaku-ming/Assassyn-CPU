#!/usr/bin/env python3
"""
测试内存初始化文件的有效性

这个脚本验证生成的 .exe 文件格式正确，并且可以被 CPU 正确加载。
"""

import os
import sys


def test_file_format(filepath, expected_words):
    """
    测试文件格式是否正确
    
    参数:
        filepath: .exe 文件路径
        expected_words: 期望的字数量（-1 表示不检查）
    """
    print(f"\n📄 测试文件: {filepath}")
    
    if not os.path.exists(filepath):
        print(f"   ❌ 文件不存在")
        return False
    
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
        
        # 过滤空行
        lines = [line.strip() for line in lines if line.strip()]
        
        print(f"   ✅ 文件存在")
        print(f"   📊 行数: {len(lines)}")
        
        # 检查字数
        if expected_words >= 0:
            if len(lines) != expected_words:
                print(f"   ⚠️  预期 {expected_words} 字，实际 {len(lines)} 字")
                if expected_words > 0:
                    return False
        
        # 检查每行格式
        valid_format = True
        for i, line in enumerate(lines):
            # 每行应该是8位十六进制数
            if len(line) != 8:
                print(f"   ❌ 行 {i}: 长度错误 (期望8位，实际{len(line)}位): {line}")
                valid_format = False
                continue
            
            try:
                # 尝试解析为十六进制
                value = int(line, 16)
                # 检查范围 (32位)
                if value < 0 or value > 0xFFFFFFFF:
                    print(f"   ❌ 行 {i}: 数值超出32位范围: {line}")
                    valid_format = False
            except ValueError:
                print(f"   ❌ 行 {i}: 不是有效的十六进制数: {line}")
                valid_format = False
        
        if valid_format:
            print(f"   ✅ 格式正确（所有行均为8位十六进制数）")
        
        # 显示前几行示例
        if len(lines) > 0:
            print(f"   🔍 前几行内容:")
            for i in range(min(4, len(lines))):
                print(f"      [{i:2d}] 0x{lines[i]}")
        
        return valid_format
        
    except Exception as e:
        print(f"   ❌ 读取文件时出错: {e}")
        return False


def test_workspace_structure():
    """测试 .workspace 目录结构"""
    print("\n" + "="*70)
    print("测试 .workspace 目录结构")
    print("="*70)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_dir = os.path.join(os.path.dirname(script_dir), '.workspace')
    
    print(f"\n📁 Workspace 路径: {workspace_dir}")
    
    if not os.path.exists(workspace_dir):
        print("   ❌ .workspace 目录不存在")
        print("   💡 请先运行: python3 convert_bin_to_exe.py")
        return False
    
    print("   ✅ .workspace 目录存在")
    
    # 检查必需的文件
    required_files = [
        'workload_mem.exe',
        'workload_ins.exe',
        'workload.init'
    ]
    
    all_exist = True
    for filename in required_files:
        filepath = os.path.join(workspace_dir, filename)
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            print(f"   ✅ {filename:20s} ({size:6d} bytes)")
        else:
            print(f"   ❌ {filename:20s} (不存在)")
            all_exist = False
    
    return all_exist


def test_file_formats():
    """测试所有初始化文件的格式"""
    print("\n" + "="*70)
    print("测试初始化文件格式")
    print("="*70)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_dir = os.path.join(os.path.dirname(script_dir), '.workspace')
    
    results = []
    
    # 测试数据内存初始化文件（可以为空）
    data_file = os.path.join(workspace_dir, 'workload_mem.exe')
    results.append(test_file_format(data_file, -1))  # -1 表示可以是任意行数
    
    # 测试指令内存初始化文件
    # 注意：22 是 accumulate 程序的指令数量
    # 如果使用其他测试程序，这个数字会不同，可以设为 -1 跳过数量检查
    ins_file = os.path.join(workspace_dir, 'workload_ins.exe')
    expected_ins_count = 22  # accumulate 程序的指令数量
    results.append(test_file_format(ins_file, expected_ins_count))
    
    # 测试偏移量初始化文件（应该是 1 行）
    init_file = os.path.join(workspace_dir, 'workload.init')
    results.append(test_file_format(init_file, 1))
    
    return all(results)


def test_instruction_content():
    """
    测试指令内容的正确性
    
    注意：本测试专为 accumulate 程序设计。
    如果使用其他测试程序，请更新 expected_instructions 列表，
    或者注释掉这个测试函数的调用（在 main() 函数的 tests 列表中）。
    """
    print("\n" + "="*70)
    print("测试指令内容")
    print("="*70)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_dir = os.path.join(os.path.dirname(script_dir), '.workspace')
    ins_file = os.path.join(workspace_dir, 'workload_ins.exe')
    
    # accumulate 程序的预期指令（前4条）
    # 如果使用其他测试程序，请更新此列表
    expected_instructions = [
        'fe010113',  # addi sp, sp, -32
        '00812e23',  # sw s0, 28(sp)
        '02010413',  # addi s0, sp, 32
        'fe042423',  # sw zero, -24(s0)
    ]
    
    try:
        with open(ins_file, 'r') as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
        
        print(f"\n🔍 验证前 {len(expected_instructions)} 条指令:")
        
        all_match = True
        for i, expected in enumerate(expected_instructions):
            if i < len(lines):
                actual = lines[i]
                match = (actual == expected)
                status = "✅" if match else "❌"
                print(f"   {status} [{i}] 期望: 0x{expected}, 实际: 0x{actual}")
                if not match:
                    all_match = False
            else:
                print(f"   ❌ [{i}] 期望: 0x{expected}, 实际: (文件行数不足)")
                all_match = False
        
        if all_match:
            print("\n   ✅ 所有测试的指令都匹配！")
        else:
            print("\n   ❌ 某些指令不匹配，请检查转换过程")
        
        return all_match
        
    except Exception as e:
        print(f"   ❌ 读取指令文件时出错: {e}")
        return False


def test_cpu_can_load():
    """测试 CPU 能否正确引用初始化文件"""
    print("\n" + "="*70)
    print("测试 CPU 配置")
    print("="*70)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    main_file = os.path.join(os.path.dirname(script_dir), 'src', 'main.py')
    
    print(f"\n📄 检查 CPU 主文件: {main_file}")
    
    if not os.path.exists(main_file):
        print("   ❌ src/main.py 不存在")
        return False
    
    print("   ✅ src/main.py 存在")
    
    try:
        with open(main_file, 'r') as f:
            content = f.read()
        
        # 检查关键配置
        checks = [
            ('workspace', 'workspace 变量定义'),
            ('workload_mem.exe', '数据内存初始化文件'),
            ('workload_ins.exe', '指令内存初始化文件'),
            ('init_file=', 'SRAM init_file 参数'),
        ]
        
        print("\n   🔍 检查关键配置:")
        all_found = True
        for keyword, description in checks:
            if keyword in content:
                print(f"      ✅ {description}")
            else:
                print(f"      ❌ {description} (未找到 '{keyword}')")
                all_found = False
        
        return all_found
        
    except Exception as e:
        print(f"   ❌ 读取 main.py 时出错: {e}")
        return False


def main():
    """主测试流程"""
    print("="*70)
    print("Assassyn CPU 内存初始化测试")
    print("="*70)
    
    # 运行所有测试
    tests = [
        ("目录结构", test_workspace_structure),
        ("文件格式", test_file_formats),
        ("指令内容", test_instruction_content),
        ("CPU 配置", test_cpu_can_load),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n❌ 测试 '{test_name}' 时发生异常: {e}")
            results[test_name] = False
    
    # 汇总结果
    print("\n" + "="*70)
    print("测试结果汇总")
    print("="*70)
    
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {status:10s} - {test_name}")
    
    print("\n" + "="*70)
    
    all_passed = all(results.values())
    if all_passed:
        print("✅ 所有测试通过！内存初始化已就绪。")
        print("\n下一步:")
        print("   1. 运行 CPU: python src/main.py")
        print("   2. 运行测试: pytest tests/ -v")
        return 0
    else:
        print("❌ 部分测试失败，请检查上述错误信息。")
        print("\n建议:")
        print("   1. 重新运行转换: python3 main_test/convert_bin_to_exe.py")
        print("   2. 验证转换结果: python3 main_test/verify_conversion.py")
        print("   3. 查看详细文档: main_test/初始化报告.md")
        return 1


if __name__ == "__main__":
    sys.exit(main())

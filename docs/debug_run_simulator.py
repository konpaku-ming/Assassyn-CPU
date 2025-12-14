#!/usr/bin/env python3
"""
调试脚本：诊断 utils.run_simulator 的行为

使用方法：
    cd /home/runner/work/Assassyn-CPU/Assassyn-CPU/docs
    python3 debug_run_simulator.py

前提条件：
    - assassyn 模块已正确安装
    - 在有测试用例的环境中运行
"""
import sys
import os

# 添加 src 目录到路径以便导入模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    import inspect
    from assassyn import utils
    
    print("=" * 70)
    print("Diagnosing assassyn.utils.run_simulator")
    print("=" * 70)
    
    # 1. 检查函数签名
    print("\n[1] Function Signature:")
    try:
        sig = inspect.signature(utils.run_simulator)
        print(f"    {sig}")
    except Exception as e:
        print(f"    Error: {e}")
    
    # 2. 检查文档字符串
    print("\n[2] Docstring:")
    doc = utils.run_simulator.__doc__
    if doc:
        lines = doc.split('\n')
        for i, line in enumerate(lines):
            if i >= 20:  # 只显示前 20 行
                print(f"    ... ({len(lines) - 20} more lines)")
                break
            print(f"    {line}")
    else:
        print("    No docstring available")
    
    # 3. 检查源码位置
    print("\n[3] Source Location:")
    try:
        file_path = inspect.getfile(utils.run_simulator)
        print(f"    {file_path}")
        
        # 尝试读取源码
        try:
            source = inspect.getsource(utils.run_simulator)
            print("\n[3.1] Source Code (first 30 lines):")
            source_lines = source.split('\n')
            for i, line in enumerate(source_lines):
                if i >= 30:
                    print(f"    ... ({len(source_lines) - 30} more lines)")
                    break
                print(f"    {line}")
        except Exception as e:
            print(f"    Could not read source: {e}")
    except Exception as e:
        print(f"    Error: {e}")
    
    # 4. 检查 build_simulator 的签名和文档
    print("\n[4] build_simulator Function:")
    try:
        sig = inspect.signature(utils.build_simulator)
        print(f"    Signature: {sig}")
        doc = utils.build_simulator.__doc__
        if doc:
            print(f"    Docstring (first line): {doc.split(chr(10))[0]}")
    except Exception as e:
        print(f"    Error: {e}")
    
    # 5. 测试不同的调用方式（使用假路径）
    print("\n[5] Testing Calls (dry run with fake path):")
    test_path = "/tmp/fake_simulator_binary_for_testing"
    
    print("\n    a) Test with positional argument:")
    try:
        # 注意：这会失败因为文件不存在，但我们可以看到它如何失败
        result = utils.run_simulator(test_path)
        print(f"       Type: {type(result)}")
        print(f"       Value (truncated): {str(result)[:200]}")
    except TypeError as e:
        print(f"       TypeError (signature mismatch): {e}")
    except FileNotFoundError as e:
        print(f"       FileNotFoundError (expected): {e}")
    except Exception as e:
        print(f"       Other error: {type(e).__name__}: {e}")
    
    print("\n    b) Test with keyword argument 'binary_path':")
    try:
        result = utils.run_simulator(binary_path=test_path)
        print(f"       Type: {type(result)}")
        print(f"       Value (truncated): {str(result)[:200]}")
    except TypeError as e:
        print(f"       TypeError (signature mismatch): {e}")
    except FileNotFoundError as e:
        print(f"       FileNotFoundError (expected): {e}")
    except Exception as e:
        print(f"       Other error: {type(e).__name__}: {e}")
    
    print("\n" + "=" * 70)
    print("Diagnosis complete.")
    print("=" * 70)

except ImportError as e:
    print("=" * 70)
    print("❌ ERROR: Cannot import assassyn module")
    print("=" * 70)
    print(f"\nImportError: {e}")
    print("\n建议：")
    print("1. 确认 assassyn 模块已正确安装")
    print("2. 检查 Python 路径配置")
    print("3. 如果在虚拟环境中，确认已激活")
    print("\n运行以下命令检查：")
    print("    pip3 list | grep assassyn")
    print("    python3 -c 'import sys; print(sys.path)'")
    print("=" * 70)
    sys.exit(1)
except Exception as e:
    print("=" * 70)
    print(f"❌ Unexpected error: {type(e).__name__}")
    print("=" * 70)
    print(f"\n{e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

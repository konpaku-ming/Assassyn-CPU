#!/usr/bin/env python3
"""
Assassyn-CPU 构建脚本
用于构建 RV32I CPU 系统并提供友好的错误信息
"""

import sys
import os
import subprocess
from pathlib import Path


def print_header():
    """打印标题"""
    print("=" * 50)
    print("  Assassyn-CPU 构建工具")
    print("=" * 50)
    print()


def print_success(msg):
    """打印成功消息"""
    print(f"✓ {msg}")


def print_error(msg):
    """打印错误消息"""
    print(f"✗ {msg}", file=sys.stderr)


def print_warning(msg):
    """打印警告消息"""
    print(f"⚠ {msg}")


def print_info(msg):
    """打印信息消息"""
    print(f"ℹ {msg}")


def check_python_version():
    """检查 Python 版本"""
    print_info("检查 Python 版本...")
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print_error(f"Python 版本过低: {version_str}")
        print_error("需要 Python 3.10 或更高版本")
        return False
    
    print_success(f"Python 版本: {version_str}")
    return True


def check_virtual_env():
    """检查虚拟环境"""
    print_info("检查虚拟环境...")
    
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print_success("虚拟环境已激活")
        return True
    else:
        print_warning("未检测到虚拟环境")
        print_warning("建议使用虚拟环境: source .venv/bin/activate")
        
        venv_path = Path(".venv")
        if venv_path.exists():
            print_info("发现虚拟环境目录，但未激活")
        
        return False


def check_dependencies():
    """检查依赖包"""
    print_info("检查依赖包...")
    
    # 必需依赖
    required_dependencies = {
        "assassyn": "Assassyn HDL 框架",
    }
    
    # 可选依赖
    optional_dependencies = {
        "pytest": "pytest 测试框架",
    }
    
    missing_required = []
    
    # 检查必需依赖
    for module, description in required_dependencies.items():
        try:
            __import__(module)
            print_success(f"{description}已安装")
        except ImportError:
            print_error(f"未找到 {description}")
            missing_required.append(module)
    
    # 检查可选依赖（仅警告）
    for module, description in optional_dependencies.items():
        try:
            __import__(module)
            print_success(f"{description}已安装")
        except ImportError:
            print_warning(f"未找到 {description}（可选）")
    
    if missing_required:
        print()
        print_error("缺少必要依赖！")
        print()
        print_info("解决方法:")
        print("  1. 安装依赖: pip install -r requirements.txt")
        print("  2. 如果 Assassyn 是私有框架，请参考其官方文档安装")
        print()
        return False
    
    return True


def prepare_workspace():
    """准备工作目录"""
    print_info("准备工作目录...")
    
    workspace = Path(".workspace")
    workspace.mkdir(exist_ok=True)
    
    print_success(f"工作目录已准备: {workspace.absolute()}")
    return True


def build_cpu():
    """构建 CPU"""
    print()
    print("=" * 50)
    print_info("开始构建 CPU 系统...")
    print("=" * 50)
    print()
    
    try:
        # 使用 -m 运行模块，实时显示输出
        result = subprocess.run(
            [sys.executable, "-m", "src.main"],
            check=True,
            text=True
        )
        
        print()
        print("=" * 50)
        print_success("构建完成！")
        print("=" * 50)
        return True
        
    except subprocess.CalledProcessError as e:
        print()
        print("=" * 50)
        print_error("构建失败！")
        print("=" * 50)
        print_error(f"退出码: {e.returncode}")
        return False
    except Exception as e:
        print()
        print("=" * 50)
        print_error("构建失败！")
        print("=" * 50)
        print_error(f"错误: {e}")
        return False


def main():
    """主函数"""
    print_header()
    
    # 切换到脚本所在目录
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # 执行检查
    checks = [
        check_python_version,
        check_virtual_env,
        check_dependencies,
        prepare_workspace,
    ]
    
    for check in checks:
        if not check():
            if check == check_virtual_env:
                # 虚拟环境只是警告，可以继续
                pass
            elif check == check_dependencies:
                # 依赖缺失，不能继续
                sys.exit(1)
        print()
    
    # 构建 CPU
    if not build_cpu():
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print_warning("用户中断")
        sys.exit(130)
    except Exception as e:
        print()
        print_error(f"未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

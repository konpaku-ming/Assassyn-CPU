# Changelog

All notable changes to the Assassyn-CPU project will be documented in this file.

## [Unreleased]

### Fixed
- **ImportError 修复** - 修复了运行 `python src/main.py` 时出现的相对导入错误
  - 添加 `src/__init__.py` 使 src 成为正式的 Python 包
  - 更新 `src/main.py` 使用 `__package__` 检查，支持多种运行方式
  - 现在可以使用 `python -m src.main` 或 `python src/main.py` 运行

### Added
- **便捷运行脚本**
  - `run_cpu.py` - 跨平台 Python 脚本，自动检查环境和依赖
  - `run_cpu.sh` - Linux/macOS shell 脚本，支持 conda 等虚拟环境
  - `run_cpu.bat` - Windows 批处理脚本
  
- **文档改进**
  - 添加 `docs/ImportError修复说明.md` - 详细的修复说明文档
  - 更新 README.md 和 QUICKSTART.md，添加多种运行方式说明
  - 添加 ImportError 故障排除部分
  - 添加运行脚本使用说明

- **测试工具**
  - `main_test/test_import_fix.py` - 验证导入修复的测试脚本
  - 自动检查包结构、导入逻辑、脚本存在性等

### Changed
- **Makefile 更新** - 使用推荐的 `python -m src.main` 运行方式
- **代码质量提升** - 根据代码审查反馈改进了导入逻辑和错误处理

### Technical Details

#### 问题根源
当使用 `python src/main.py` 直接运行时，Python 将文件视为顶层脚本，`__package__` 为 `None`，导致相对导入失败。

#### 解决方案
1. 创建 `src/__init__.py` 使其成为包
2. 使用 `if __package__:` 条件判断运行方式
3. 提供多种便捷的运行方式
4. 更新文档和工具链

#### 支持的运行方式
```bash
# 方法 1: 便捷脚本（推荐）
python run_cpu.py

# 方法 2: 模块方式（推荐）
python -m src.main

# 方法 3: Makefile
make build

# 方法 4: 平台脚本
./run_cpu.sh        # Linux/macOS
run_cpu.bat         # Windows

# 方法 5: 直接运行（兼容）
python src/main.py
```

## [0.1.0] - 2025-12-12

### Initial Release
- 实现了完整的 RV32I 指令集支持
- 五级流水线架构（IF, ID, EX, MEM, WB）
- 数据冒险检测与前递
- 控制冒险处理
- 完善的单元测试覆盖

---

[Unreleased]: https://github.com/konpaku-ming/Assassyn-CPU/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/konpaku-ming/Assassyn-CPU/releases/tag/v0.1.0

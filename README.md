# Assassyn-CPU

基于 **Assassyn** 硬件描述框架实现的 RV32IM 五级流水线 CPU。项目包含分支预测器、数据/控制冒险处理、乘法器与 SRT4 除法器等组件，并附带完整的仿真测试与示例工作负载。

## 功能概览
- **指令集**：RV32I + M 扩展（乘/除/取模）。
- **流水线**：IF/ID/EX/MEM/WB 五级，包含旁路与冒险处理 (`DataHazardUnit`)。
- **预测器**：BTB + 结合本地/全局历史与选择器的 `TournamentPredictor`。
- **存储**：指令/数据 SRAM、寄存器堆与旁路寄存器。
- **工作负载**：`workloads/` 目录提供常见算术与向量示例。

## 仓库结构
- `src/`：CPU 各阶段及控制逻辑（`fetch.py`、`decoder.py`、`execution.py`、`memory.py`、`writeback.py` 等）。
- `tests/`：基于 Assassyn 仿真的单元/集成测试（除法器说明见 `tests/README_test_divider.md`，其余测试覆盖取指、译码、执行、访存、写回等阶段）。
- `workloads/`：示例指令/数据镜像，会被 `src/main.py` 的 `load_test_case` 复制到沙盒 `src/.workspace/`。
- `docs/`：设计文档与 Assassyn 语言说明（`docs/Assassyn_语言完整说明书.md`、`docs/Agent.md` 等）。
- `logs/`、`report/`：仿真输出与报告位置（按需生成）。

## 环境准备
1. **Python 3.10+**。
2. **Assassyn 框架**（必须）：建议使用 Apptainer/Singularity 镜像 `assassyn.sif`（获取与制作方式见 `docs/Agent.md`），或在本地已安装可用的 `assassyn` 包。
3. **测试依赖**：`pytest`（`pip install pytest`），用于收集和运行测试。

> 如果缺少 Assassyn 环境，运行测试会出现 `ModuleNotFoundError: No module named 'assassyn'`。

## 快速开始
```bash
cd /path/to/project/Assassyn-CPU

# 推荐在容器内运行，确保可访问 assassyn.sif（可从内部分发路径获取或按 docs/Agent.md 构建）
apptainer exec --bind $(pwd) /path/to/assassyn.sif python tests/test_fetch.py
```

- 更完整的除法器测试示例：
  ```bash
  apptainer exec --bind $(pwd) /path/to/assassyn.sif python tests/test_divider.py
  ```
- 如果本地已安装 `assassyn` 包，也可以直接运行：
  ```bash
  pytest
  ```

## 文档
- 语言与框架：`docs/Assassyn_语言完整说明书.md`
- 模块设计：`docs/Module/` 子目录
- Agent 指南与环境说明：`docs/Agent.md`

## 工作负载与仿真
- 示例程序位于 `workloads/`，可通过 `src/main.py` 的 `load_test_case(case_name)` 将二进制复制到 `src/.workspace/` 供仿真使用。
- `tests/common.py` 提供了统一的 `run_test_module` 仿真入口，便于为新模块添加测试。

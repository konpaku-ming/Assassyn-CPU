# Performance Analysis Reports

This folder contains performance analysis reports for the Assassyn-CPU.

## Contents

### 1. BTB Performance Analysis
- **BTB性能分析报告.md** - Complete BTB performance analysis report in Chinese
- **performance_data.json** - Raw BTB performance metrics extracted from log files

### 2. Bypass Performance Analysis
- **Bypass性能分析报告.md** - Complete Bypass mechanism performance analysis report in Chinese
- **bypass_performance_data.json** - Raw Bypass performance metrics extracted from log files

## Quick Summary

### BTB Performance Improvement

| Workload | Actual Cycles (BTB) | Theoretical Cycles (50% Error) | Improvement | BTB Hit Rate on Branches |
|----------|---------------------|--------------------------------|-------------|--------------------------|
| 0to100   | 412                 | 556                            | 25.90%      | 99.0%                   |
| multiply | 4,640               | 5,372                          | 13.63%      | 78.77%                  |
| vvadd    | 8,433               | 8,874                          | 4.97%       | 98.68%                  |

**Key Findings**:
1. **High BTB Hit Rate on Branch Instructions**: BTB achieves 78.77% to 99% hit rate on actual branch instructions
2. **Performance Gain Varies by Workload**: From **5%** to **26%** improvement depending on branch instruction density
3. **Low Misprediction Rate**: Actual pipeline flushes are extremely low (2-8 times) compared to theoretical expectations
4. **Effective for Loop-Intensive Programs**: Simple loop programs achieve near-perfect BTB hit rates (99%)

### Bypass Performance Improvement

| Workload | With Bypass | Without Bypass (Theory) | Improvement | Improvement % |
|----------|-------------|-------------------------|-------------|---------------|
| 0to100   | 412         | 616                     | 204         | **33.12%**   |
| multiply | 4,640       | 7,756                   | 3,116       | **40.18%**   |
| vvadd    | 8,433       | 15,949                  | 7,516       | **47.13%**   |

**Key Findings**:
1. **Significant Performance Gains**: Bypass mechanism provides 33-47% performance improvement across all workloads
2. **Eliminates Pipeline Stalls**: Bypass eliminates thousands of cycles that would be wasted on data hazard stalls
3. **Most Effective for Compute-Intensive Programs**: vvadd shows the highest improvement (47.13%) due to dense data dependencies
4. **Multi-level Bypass Essential**: All three bypass types (EX-MEM, MEM-WB, WB) are heavily used and necessary

## Data Sources

Performance data is extracted from the following log files:
- `/log/0to100_log.txt`
- `/log/multiply_log.txt`  
- `/log/vvadd_log.txt`

## Analysis Methodology

The analysis compares:
- **Actual performance**: CPU with 64-entry BTB running real workloads
- **Theoretical baseline**: Same workloads with 50% branch prediction error rate

The theoretical cycle count is calculated as:
```
Base Cycles = Actual Cycles - (Actual Flushes × 3)
Theoretical Cycles = Base Cycles + (Actual Branch Instructions × 50% × 3)
BTB Hit Rate = BTB Hits / Actual Branch Instructions × 100%
```

Where:
- 3 is the pipeline flush penalty in cycles
- Actual Branch Instructions refers to real branch instructions (excluding NO_BRANCH instructions)
- BTB Hit Rate measures how many branch instructions successfully hit in the BTB

## Report Date

Generated: December 17, 2025

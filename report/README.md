# BTB Performance Analysis Report

This folder contains the performance analysis report comparing BTB (Branch Target Buffer) performance with a theoretical 50% branch prediction error rate.

## Contents

- **BTB性能分析报告.md** - Complete performance analysis report in Chinese
- **performance_data.json** - Raw performance metrics extracted from log files

## Quick Summary

### Performance Improvement with BTB

| Workload | Actual Cycles (BTB) | Theoretical Cycles (50% Error) | Improvement | BTB Hit Rate on Branches |
|----------|---------------------|--------------------------------|-------------|--------------------------|
| 0to100   | 412                 | 556                            | 25.90%      | 99.0%                   |
| multiply | 4,640               | 5,372                          | 13.63%      | 78.77%                  |
| vvadd    | 8,433               | 8,874                          | 4.97%       | 98.68%                  |

### Key Findings

1. **High BTB Hit Rate on Branch Instructions**: BTB achieves 78.77% to 99% hit rate on actual branch instructions
2. **Performance Gain Varies by Workload**: From **5%** to **26%** improvement depending on branch instruction density
3. **Low Misprediction Rate**: Actual pipeline flushes are extremely low (2-8 times) compared to theoretical expectations
4. **Effective for Loop-Intensive Programs**: Simple loop programs achieve near-perfect BTB hit rates (99%)

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

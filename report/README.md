# BTB Performance Analysis Report

This folder contains the performance analysis report comparing BTB (Branch Target Buffer) performance with a theoretical 50% branch prediction error rate.

## Contents

- **BTB性能分析报告.md** - Complete performance analysis report in Chinese
- **performance_data.json** - Raw performance metrics extracted from log files

## Quick Summary

### Performance Improvement with BTB

| Workload | Actual Cycles (BTB) | Theoretical Cycles (50% Error) | Improvement |
|----------|---------------------|--------------------------------|-------------|
| 0to100   | 412                 | 1,021                          | 59.65%      |
| multiply | 4,640               | 11,573                         | 59.91%      |
| vvadd    | 8,433               | 21,063                         | 59.96%      |

### Key Findings

1. **Significant Performance Gain**: BTB reduces execution cycles by approximately **60%** on average
2. **Low Misprediction Rate**: Actual pipeline flushes are extremely low (2-8 times) compared to theoretical expectations
3. **Effective for Loop-Intensive Programs**: All three workloads show consistent performance improvement

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
Theoretical Cycles = Base Cycles + (Total Branches × 50% × 3)
```

Where 3 is the pipeline flush penalty in cycles.

## Report Date

Generated: December 17, 2025

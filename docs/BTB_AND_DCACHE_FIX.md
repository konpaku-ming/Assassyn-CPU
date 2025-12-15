# BTB Implementation and DCache Fix

## Overview

This document describes the fixes and enhancements made to the Assassyn CPU simulator to address a critical dcache panic and implement branch prediction via a Branch Target Buffer (BTB).

## Issues Addressed

### 1. DCache Index Out of Bounds Panic

**Problem**: The simulator panicked with:
```
thread 'main' panicked at src/modules/dcache.rs:78:27:
index out of bounds: the len is 65536 but the index is 262120
```

**Root Cause**: In `src/execution.py`, the dcache was being accessed with byte addresses directly instead of word indices. The SRAM has 65536 words (4 bytes each), supporting byte addresses from 0x00000000 to 0x0003FFFF. However, byte address 262120 (0x0003FFE8) was used directly as an index into a 65536-element array, causing the panic.

**Fix**: Convert byte addresses to word addresses by right-shifting by 2 bits:
```python
# Before (WRONG):
dcache.build(addr=alu_result, ...)  # alu_result is byte address

# After (CORRECT):
dcache_addr = alu_result >> UInt(32)(2)  # Convert to word address
dcache.build(addr=dcache_addr, ...)
```

This matches the addressing scheme used in the instruction cache (see `src/fetch.py` line 67).

### 2. Missing Branch Prediction

**Problem**: The CPU had no branch prediction mechanism, causing performance penalties on branch-heavy code like loops.

**Solution**: Implemented a direct-mapped Branch Target Buffer (BTB) that provides one-cycle branch target predictions.

## BTB Implementation Details

### Architecture

The BTB is a **direct-mapped** cache with the following characteristics:
- **64 entries** (configurable)
- **6 index bits** (log2(64))
- **Word-aligned PC addressing** (skip lowest 2 bits)
- Stores: valid bit, full PC as tag, and target address

### Components

#### 1. BTB Module (`src/btb.py`)

Two classes are implemented:

**BTB (Module)**: 
- Holds the storage arrays (valid bits, tags, targets)
- Initialized with all entries invalid

**BTBImpl (Downstream)**:
- **predict()**: Performs one-cycle lookup
  - Extracts index from PC[7:2] (bits 7-2 for 64 entries)
  - Extracts tag from PC[31:8] (upper bits)
  - Returns (hit, target) where hit indicates valid prediction
  
- **update()**: Updates BTB on branch resolution
  - Called when a branch is taken in the execution stage
  - Stores the full PC as tag and the branch target

### Integration Points

#### 1. Fetch Stage (`src/fetch.py`)

The `FetcherImpl.build()` method now:
1. Queries the BTB with the current PC
2. If BTB hits, uses the predicted target as next_pc
3. If BTB misses, uses PC+4 (sequential execution)

```python
btb_hit, btb_predicted_target = btb_impl.predict(
    pc=final_current_pc,
    btb_valid=btb_valid,
    btb_tags=btb_tags,
    btb_targets=btb_targets,
)

predicted_next_pc = btb_hit.select(btb_predicted_target, final_current_pc + UInt(32)(4))
```

#### 2. Execution Stage (`src/execution.py`)

The `Execution.build()` method now:
1. Resolves actual branch behavior
2. Updates BTB when a branch is taken
3. Flushes pipeline on misprediction (existing logic)

```python
should_update_btb = is_branch & is_taken & ~flush_if
btb_impl.update(
    pc=pc,
    target=calc_target,
    should_update=should_update_btb,
    btb_valid=btb_valid,
    btb_tags=btb_tags,
    btb_targets=btb_targets,
)
```

#### 3. Top Level (`src/main.py`)

The `build_cpu()` function now:
1. Instantiates BTB and BTBImpl modules
2. Builds BTB storage before pipeline stages
3. Passes BTB references to Fetch and Execution stages

## BTB Addressing Scheme

### Index Calculation
```
PC (32 bits):  [31...........8][7......2][1:0]
                                INDEX    OFFSET

index = (pc >> 2) & 0x3F          # Extract 6 bits (64 entries)
stored_tag = pc                    # Store full PC for exact matching
```

### Tag Matching (Simplified)
The BTB stores the full PC as the tag and compares full PCs:
```python
# In predict:
entry_tag = btb_tags[index]       # Full PC stored previously
tag_match = (entry_tag == pc)     # Exact PC comparison
hit = valid & tag_match

# In update:
btb_tags[index] = pc              # Store full PC
```

This approach is simpler and avoids bit-manipulation errors while maintaining correctness.

### Tag Matching
When looking up a PC:
1. Extract index to find BTB entry
2. Check valid bit
3. Compare stored PC with lookup PC (full PC comparison)
4. Hit if valid AND PCs match exactly

**Note**: The BTB uses full PC comparison for simplicity and correctness. This means:
- Each BTB index can hold one unique PC
- Different PCs mapping to the same index will cause replacements (conflict misses)
- No aliasing issues - only exact PC matches result in hits

## Testing and Validation

### Unit Testing
A validation script (`validate_fixes.py`) verifies:
1. DCache address conversion correctness
2. BTB indexing produces correct indices
3. BTB tag matching correctly identifies hits/misses

### Expected Results

With these changes:
- **DCache panic is fixed**: Addresses are properly converted to word indices
- **Branch prediction enabled**: BTB provides one-cycle predictions
- **0to100 and my0to100 should run**: Both workloads should execute without panics

## Performance Considerations

### BTB Benefits
- **One-cycle prediction**: No pipeline bubbles for predicted branches
- **Reduced misprediction penalty**: Correct predictions avoid flush
- **Simple implementation**: Direct-mapped, minimal complexity

### BTB Limitations
- **Capacity**: Only 64 entries, may thrash on large code
- **Conflict misses**: Multiple branches mapping to same index
- **No direction prediction**: Assumes branches taken (unconditional predict)

### Potential Enhancements
1. **Larger BTB**: Increase entries to 128 or 256
2. **2-bit saturating counter**: Add direction prediction
3. **Set-associative**: Reduce conflict misses
4. **Return address stack**: Optimize function returns

## Files Modified

1. **src/btb.py** (NEW): BTB implementation
   - BTB module with storage arrays
   - BTBImpl with predict and update methods

2. **src/execution.py**: 
   - Fixed dcache address conversion (line ~240)
   - Added BTB update on branch resolution

3. **src/fetch.py**:
   - Added BTB prediction in FetcherImpl
   - Uses BTB target when hit, else PC+4

4. **src/main.py**:
   - Import BTB modules
   - Instantiate BTB in build_cpu
   - Wire BTB through pipeline stages

## Debugging Notes

### If DCache Panic Still Occurs
1. Check that all memory accesses use word addressing
2. Verify address space doesn't exceed 256KB (64K words × 4 bytes)
3. Add bounds checking in execution stage

### If BTB Doesn't Work
1. Check BTB logs in simulation output
2. Verify tag comparison logic matches storage
3. Ensure branches are updating BTB correctly
4. Check for off-by-one errors in index calculation

## References

- Original issue: Index out of bounds in dcache.rs:78
- Panic address: 262120 (0x0003FFE8) → word index 65530 (valid)
- Solution: Address conversion prevents misuse of byte addresses as indices
- BTB design follows standard direct-mapped cache architecture

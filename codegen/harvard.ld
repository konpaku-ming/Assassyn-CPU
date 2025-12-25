OUTPUT_ARCH(riscv)
ENTRY(_start)

MEMORY
{
    /* 关键点：两个区域都从 0x0 开始，长度根据你的硬件调整 */
    IMEM (ax) : ORIGIN = 0x00000000, LENGTH = 4K 
    DMEM (rw) : ORIGIN = 0x00000000, LENGTH = 4K
}

SECTIONS
{
    /* ================= 指令部分 ================= */
    /* 放在 IMEM，逻辑地址从 0 开始 */
    .text : {
        *(.text.init)   /* 启动代码放最前 */
        *(.text*)
    } > IMEM

    /* ================= 数据部分 ================= */
    /* 放在 DMEM，逻辑地址也从 0 开始！ */
    /* 
       注意：RISC-V 默认把 .rodata (常量) 放在 text 段。
       既然你的数据都在 memory 初始化文件里，我们需要把 rodata 强制挪到 DMEM 中 
    */
    .data : {
        *(.rodata*)     /* 字符串常量等 */
        *(.data*)       /* 已初始化的全局变量 */
        *(.sdata*)
    } > DMEM

    /* BSS 段 (未初始化变量) */
    /* 也要放在 DMEM。虽然它不占初始化文件空间，但符号地址必须解析在 DMEM */
    .bss : {
        *(.bss*)
        *(.sbss*)
        *(COMMON)
    } > DMEM

    /* 栈放在 DMEM 的末尾 */
    __stack_top = ORIGIN(DMEM) + LENGTH(DMEM);
}
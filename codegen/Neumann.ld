/* link.ld */
OUTPUT_ARCH( "riscv" )
ENTRY( _start )

/* 定义内存布局 */
MEMORY
{
  /* 这里的 ORIGIN = 0x00000000 就是你要求的"固定的起始位置" */
  RAM (rwx) : ORIGIN = 0x00000000, LENGTH = 4K
}

SECTIONS
{
  /* 代码段 */
  .text :
  {
    /* 确保 _start 位于物理地址 0x0 (或其他你指定的 ORIGIN) */
    *(.text.init)
    *(.text)
    *(.text.*)

    . = ALIGN(4);
    LONG(0x00000013);
    LONG(0x00000013);
    LONG(0x00000013);
    LONG(0x00000013);
  } > RAM

  /* 只读数据段 (常量) */
  .rodata :
  {
    . = ALIGN(4);
    *(.rodata)
    *(.rodata.*)
  } > RAM

  /* 已初始化数据段 (全局变量) */
  .data :
  {
    . = ALIGN(4);
    *(.data)
    *(.data.*)
    *(.sdata)
  } > RAM

  /* 未初始化数据段 (BSS) - 裸机通常需要手动清零，这里简化处理 */
  .bss :
  {
    . = ALIGN(4);
    *(.bss)
    *(.bss.*)
    *(.sbss)
  } > RAM

  /* 定义栈顶：指向 RAM 的末尾 */
  /* 提供给 start.s 使用 */
  . = ALIGN(4);
  __stack_top = ORIGIN(RAM) + LENGTH(RAM);
}
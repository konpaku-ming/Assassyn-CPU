.section .text.init
.globl _start

_start:
    # 设置栈指针。链接脚本定义了 __stack_top
    la sp, __stack_top
    
    # 跳转到 C 的 main
    call main

    # 死循环
loop:
    sb x0 , -1(x0)
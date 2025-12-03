接下来，我们开始ID(Module)流水线模块的设计。请根据以下描述生成一份设计文档，尽可能详细且准确：
1. ID 模块职责：从SRAM中取出IF上一阶段给出地址的指令，解析成一系列控制信号并发送到 DataHazardUnit（DownStream）以及 Execution（Module，即下一阶段流水线）接口中。
2. ID 模块接口：__init__的port中暂时不放置任何输入接口，在build参数中传入一个Execution模块，一个DataHazardUnit的DownStream，以及一个RegArray作为SRAM接口（SRAM比较特殊，属于跨越流水线阶段的元件）。
3. build 内部实现：
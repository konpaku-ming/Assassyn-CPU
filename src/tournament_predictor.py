from assassyn.frontend import *
from .debug_utils import debug_log


class TournamentPredictor(Module):
    """
    竞赛预测器 - 结合局部（Bimodal）和全局（Gshare）预测器，
    并使用选择器在两者之间进行选择。

    架构：
    - Bimodal: 以PC为索引的2位饱和计数器
    - Gshare: 以（PC XOR 全局历史）为索引的2位计数器
    - Selector: 学习哪个预测器对每个分支更好的2位计数器

    2位饱和计数器状态：
    - 00: 强不跳转
    - 01: 弱不跳转
    - 10: 弱跳转
    - 11: 强跳转
    """

    def __init__(self, num_entries=64, index_bits=6, history_bits=6):
        """
        初始化竞赛预测器。

        参数：
            num_entries: 每个表的条目数（应为2的幂）
            index_bits: 用于索引的位数（log2(num_entries)）
            history_bits: 全局历史寄存器的位数
        """
        super().__init__(ports={}, no_arbiter=True)
        self.name = "TournamentPredictor"
        self.num_entries = num_entries
        self.index_bits = index_bits
        self.history_bits = history_bits

    @module.combinational
    def build(self):
        # Bimodal预测器：以PC为索引的2位计数器
        # 初始化为"弱跳转"(2)，以获得更好的循环初始行为
        bimodal_counters = RegArray(
            Bits(2), self.num_entries, initializer=[2] * self.num_entries
        )

        # Gshare预测器：以（PC XOR 全局历史）为索引的2位计数器
        # 初始化为"弱跳转"(2)
        gshare_counters = RegArray(
            Bits(2), self.num_entries, initializer=[2] * self.num_entries
        )

        # 全局历史寄存器（GHR）：分支结果的移位寄存器
        # 初始化为0
        global_history = RegArray(Bits(self.history_bits), 1, initializer=[0])

        # 选择器：用于在预测器之间选择的2位计数器
        # 00, 01: 使用Bimodal
        # 10, 11: 使用Gshare
        # 初始化为"弱Bimodal"(1) - 略微偏向局部预测器
        selector_counters = RegArray(
            Bits(2), self.num_entries, initializer=[1] * self.num_entries
        )

        return bimodal_counters, gshare_counters, global_history, selector_counters


class TournamentPredictorImpl:
    """
    竞赛预测器实现逻辑。
    包含纯组合逻辑方法的辅助类。
    """

    def __init__(self, num_entries=64, index_bits=6, history_bits=6):
        self.name = "TournamentPredictor_Impl"
        self.num_entries = num_entries
        self.index_bits = index_bits
        self.history_bits = history_bits
        self.index_mask = (1 << index_bits) - 1

    def _get_pc_index(self, pc: Bits(32)):
        """从PC中提取索引（跳过最低2位以进行字对齐）。"""
        index_32 = (pc >> UInt(32)(2)) & Bits(32)(self.index_mask)
        return index_32[0 : self.index_bits - 1].bitcast(Bits(self.index_bits))

    def _get_gshare_index(self, pc: Bits(32), global_history: Bits):
        """计算Gshare索引：PC[index_bits:2] XOR 全局历史。"""
        pc_bits = (pc >> UInt(32)(2)) & Bits(32)(self.index_mask)
        pc_index = pc_bits[0 : self.index_bits - 1].bitcast(Bits(self.index_bits))

        # 与全局历史进行XOR运算（扩展/截断历史以匹配索引位数）
        ghr = global_history[0 : self.history_bits - 1].bitcast(Bits(self.history_bits))

        # 填充或截断GHR以匹配索引位数
        if self.history_bits >= self.index_bits:
            ghr_matched = ghr[0 : self.index_bits - 1].bitcast(Bits(self.index_bits))
        else:
            # 将GHR零扩展到index_bits位
            ghr_matched = concat(
                Bits(self.index_bits - self.history_bits)(0), ghr
            ).bitcast(Bits(self.index_bits))

        return pc_index ^ ghr_matched

    def predict(
        self,
        pc: Bits(32),
        bimodal_counters: Array,
        gshare_counters: Array,
        global_history: Array,
        selector_counters: Array,
    ):
        """
        使用竞赛预测器预测分支方向。

        返回：
            predict_taken: Bits(1) - 如果预测跳转则为1，如果预测不跳转则为0
        """
        # 获取索引
        pc_index = self._get_pc_index(pc)
        ghr = global_history[0]
        gshare_index = self._get_gshare_index(pc, ghr)

        # 读取预测器状态
        bimodal_state = bimodal_counters[pc_index]
        gshare_state = gshare_counters[gshare_index]
        selector_state = selector_counters[pc_index]

        # Bimodal预测：如果计数器 >= 2则跳转
        bimodal_taken = bimodal_state[1:1]  # 最高位表示跳转/不跳转

        # Gshare预测：如果计数器 >= 2则跳转
        gshare_taken = gshare_state[1:1]

        # 选择器决策：如果选择器 >= 2则使用Gshare，否则使用Bimodal
        use_gshare = selector_state[1:1]

        # 最终预测
        predict_taken = use_gshare.select(gshare_taken, bimodal_taken)

        # 调试日志
        with Condition(predict_taken == Bits(1)(1)):
            debug_log(
                "TP: 预测跳转 PC=0x{:x}, Bimodal={}, Gshare={}, Selector={}, UseGshare={}",
                pc,
                bimodal_state,
                gshare_state,
                selector_state,
                use_gshare,
            )
        with Condition(predict_taken == Bits(1)(0)):
            debug_log(
                "TP: 预测不跳转 PC=0x{:x}, Bimodal={}, Gshare={}, Selector={}, UseGshare={}",
                pc,
                bimodal_state,
                gshare_state,
                selector_state,
                use_gshare,
            )

        return predict_taken

    def update(
        self,
        pc: Bits(32),
        actual_taken: Value,  # Bits(1): 实际分支结果
        is_branch: Value,  # Bits(1): 是否为分支指令
        bimodal_counters: Array,
        gshare_counters: Array,
        global_history: Array,
        selector_counters: Array,
    ):
        """
        使用实际分支结果更新竞赛预测器。

        更新内容：
        1. PC索引处的Bimodal计数器
        2. (PC XOR GHR)索引处的Gshare计数器
        3. 基于哪个预测器正确来更新选择器计数器
        4. 全局历史寄存器
        """
        # 获取索引
        pc_index = self._get_pc_index(pc)
        ghr = global_history[0]
        gshare_index = self._get_gshare_index(pc, ghr)

        with Condition(is_branch == Bits(1)(1)):
            # 读取当前计数器状态
            bimodal_state = bimodal_counters[pc_index]
            gshare_state = gshare_counters[gshare_index]
            selector_state = selector_counters[pc_index]

            # 确定每个预测器的预测结果
            bimodal_predicted_taken = bimodal_state[1:1]
            gshare_predicted_taken = gshare_state[1:1]

            # 检查每个预测器是否正确
            bimodal_correct = bimodal_predicted_taken == actual_taken
            gshare_correct = gshare_predicted_taken == actual_taken

            # --- 更新Bimodal计数器 ---
            # 如果跳转则增加，如果不跳转则减少（饱和）
            bimodal_new = actual_taken.select(
                # 跳转：增加（在3处饱和）
                (bimodal_state == Bits(2)(3)).select(
                    Bits(2)(3),
                    (bimodal_state.bitcast(UInt(2)) + UInt(2)(1)).bitcast(Bits(2)),
                ),
                # 不跳转：减少（在0处饱和）
                (bimodal_state == Bits(2)(0)).select(
                    Bits(2)(0),
                    (bimodal_state.bitcast(UInt(2)) - UInt(2)(1)).bitcast(Bits(2)),
                ),
            )
            bimodal_counters[pc_index] <= bimodal_new

            # --- 更新Gshare计数器 ---
            gshare_new = actual_taken.select(
                # 跳转：增加（在3处饱和）
                (gshare_state == Bits(2)(3)).select(
                    Bits(2)(3),
                    (gshare_state.bitcast(UInt(2)) + UInt(2)(1)).bitcast(Bits(2)),
                ),
                # 不跳转：减少（在0处饱和）
                (gshare_state == Bits(2)(0)).select(
                    Bits(2)(0),
                    (gshare_state.bitcast(UInt(2)) - UInt(2)(1)).bitcast(Bits(2)),
                ),
            )
            gshare_counters[gshare_index] <= gshare_new

            # --- 更新选择器计数器 ---
            # 如果Gshare正确且Bimodal错误，则增加（偏向Gshare）
            # 如果Bimodal正确且Gshare错误，则减少（偏向Bimodal）
            # 如果两者都正确或都错误，则不变
            gshare_better = gshare_correct & (~bimodal_correct)
            bimodal_better = bimodal_correct & (~gshare_correct)

            selector_new = gshare_better.select(
                # Gshare更好：增加偏向Gshare（在3处饱和）
                (selector_state == Bits(2)(3)).select(
                    Bits(2)(3),
                    (selector_state.bitcast(UInt(2)) + UInt(2)(1)).bitcast(Bits(2)),
                ),
                bimodal_better.select(
                    # Bimodal更好：减少偏向Bimodal（在0处饱和）
                    (selector_state == Bits(2)(0)).select(
                        Bits(2)(0),
                        (selector_state.bitcast(UInt(2)) - UInt(2)(1)).bitcast(Bits(2)),
                    ),
                    # 两者都正确或都错误：不变
                    selector_state,
                ),
            )
            selector_counters[pc_index] <= selector_new

            # --- 更新全局历史寄存器 ---
            # 左移1位并插入新结果
            ghr_shifted = (ghr << UInt(self.history_bits)(1)) | actual_taken.bitcast(
                Bits(self.history_bits)
            )
            # 只保留history_bits位
            ghr_new = ghr_shifted[0 : self.history_bits - 1].bitcast(
                Bits(self.history_bits)
            )
            global_history[0] <= ghr_new

            debug_log(
                "TP: 更新 PC=0x{:x}, Taken={}, Bimodal: {}->{}, Gshare: {}->{}, Selector: {}->{}, GHR->{}",
                pc,
                actual_taken,
                bimodal_state,
                bimodal_new,
                gshare_state,
                gshare_new,
                selector_state,
                selector_new,
                ghr_new,
            )

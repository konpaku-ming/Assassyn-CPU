#define DATA_SIZE 10

int input_1[DATA_SIZE] =
{
   1, 2, 3, 4, 5, 6, 7, 8, 9, 10
};

// =========================================================
// 主函数
// =========================================================
int main() {
    int result; // 存放结果
    int i;

    result = 1;

    // 向量乘法
    for (i = 0; i < DATA_SIZE; i++) {
        result = result * input_1[i];
    }

    // 3. 结束
    return result;
}
#ifndef GOBANG_CORE_H
#define GOBANG_CORE_H

#include <vector>
#include <string>
#include <utility>

// 权重结构体（对应Python的CWeights）
struct Weights {
    float FIVE;        // 五连
    float FOUR;        // 活四
    float BLOCKED_FOUR;// 冲四
    float THREE;       // 活三
    float BLOCKED_THREE;// 冲三
    float TWO;         // 活二
    float BLOCKED_TWO;  // 冲二
    float ONE;          // 活一
};

// 游戏结束结果结构体（对应Python的CGameEndResult）
struct GameEndResult {
    bool is_end;                  // 是否结束
    int winner;                   // 赢家（0=平局，1=黑，2=白）
    int win_line_size;            // 获胜线长度（固定5）
    std::vector<std::pair<int, int>> win_line; // 获胜线坐标
};

// 五子棋核心算法类
class GobangCore {
public:
    // 构造/析构
    GobangCore();
    ~GobangCore();

    // 1. 落子验证（x,y：落子坐标，current_player：当前玩家1/2，board_size：棋盘尺寸）
    std::pair<bool, std::string> validate_move(
        const std::vector<std::vector<int>>& board,
        int x, int y,
        int current_player,
        int board_size
    );

    // 2. 执行落子（返回更新后的棋盘）
    std::vector<std::vector<int>> place_piece(
        const std::vector<std::vector<int>>& board,
        int x, int y,
        int color,
        int board_size
    );

    // 3. 检查游戏结束（判断胜负/平局）
    GameEndResult check_game_end(
        const std::vector<std::vector<int>>& board,
        int board_size
    );

    // 4. 落子评估（计算得分：棋型识别+权重）
    float evaluate_move(
        const std::vector<std::vector<int>>& board,
        int x, int y,
        int color,
        const Weights& weights,
        int board_size
    );

    // 5. 查找必胜落子（立即获胜的落子位置）
    std::pair<int, int> find_winning_move(
        const std::vector<std::vector<int>>& board,
        int color,
        int board_size
    );

    // 6. MCTS优化落子（简化版：基于当前落子优化，提升决策精度）
    std::pair<int, int> mcts_optimize(
        const std::vector<std::vector<int>>& board,
        std::pair<int, int> init_move,
        int color,
        int depth,
        int iterations,
        int board_size
    );

private:
    // 辅助函数：检查某方向是否形成连续同色棋子（内部棋型识别）
    int check_line(
        const std::vector<std::vector<int>>& board,
        int x, int y,
        int dx, int dy,
        int color,
        int board_size
    );

    // 辅助函数：识别落子后的棋型得分（五连/四连/三连等）
    float get_pattern_score(
        const std::vector<std::vector<int>>& board,
        int x, int y,
        int color,
        const Weights& weights,
        int board_size
    );
};

// ------------- 对外C接口（供CPython调用，避免C++名称修饰）-------------
extern "C" {
    // 创建核心实例
    void* gobang_core_create();
    // 销毁核心实例
    void gobang_core_destroy(void* core);

    // 1. 落子验证（C风格参数：int** 棋盘）
    bool gobang_core_validate_move(
        void* core,
        int** board,
        int x, int y,
        int current_player,
        int board_size,
        char** error_msg
    );

    // 2. 执行落子（返回int** 棋盘，需通过free_board释放）
    int** gobang_core_place_piece(
        void* core,
        int** board,
        int x, int y,
        int color,
        int board_size
    );

    // 3. 检查游戏结束（返回GameEndResult结构体）
    GameEndResult gobang_core_check_game_end(
        void* core,
        int** board,
        int board_size
    );

    // 4. 落子评估
    float gobang_core_evaluate_move(
        void* core,
        int** board,
        int x, int y,
        int color,
        Weights weights,
        int board_size
    );

    // 5. 查找必胜落子（返回int[2]，需通过free_int_array释放）
    int* gobang_core_find_winning_move(
        void* core,
        int** board,
        int color,
        int board_size
    );

    // 6. MCTS优化落子（返回int[2]，需通过free_int_array释放）
    int* gobang_core_mcts_optimize(
        void* core,
        int** board,
        int init_x, int init_y,
        int color,
        int depth,
        int iterations,
        int board_size
    );

    // 内存释放函数
    void gobang_core_free_board(int** board, int board_size);
    void gobang_core_free_int_array(int* arr);
    void gobang_core_free_game_end_result(GameEndResult result);
}

#endif // GOBANG_CORE_H
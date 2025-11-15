#include "gobang_core.h"
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <cmath>

// ---------------- 类实现 ----------------
GobangCore::GobangCore() {}
GobangCore::~GobangCore() {}

// 1. 落子验证
std::pair<bool, std::string> GobangCore::validate_move(
    const std::vector<std::vector<int>>& board,
    int x, int y,
    int current_player,
    int board_size
) {
    // 坐标越界
    if (x < 0 || x >= board_size || y < 0 || y >= board_size) {
        return {false, "invalid_position"};
    }
    // 位置已占用
    if (board[x][y] != 0) {
        return {false, "occupied"};
    }
    // 玩家无效
    if (current_player != 1 && current_player != 2) {
        return {false, "invalid_player"};
    }
    return {true, "success"};
}

// 2. 执行落子
std::vector<std::vector<int>> GobangCore::place_piece(
    const std::vector<std::vector<int>>& board,
    int x, int y,
    int color,
    int board_size
) {
    std::vector<std::vector<int>> new_board = board;
    new_board[x][y] = color;
    return new_board;
}

// 3. 检查游戏结束（核心：横向/纵向/对角线五连判断）
GameEndResult GobangCore::check_game_end(
    const std::vector<std::vector<int>>& board,
    int board_size
) {
    GameEndResult result = {false, 0, 0, {}};
    const int win_len = 5;

    // 检查横向
    for (int i = 0; i < board_size; ++i) {
        for (int j = 0; j <= board_size - win_len; ++j) {
            int color = board[i][j];
            if (color == 0) continue;
            bool win = true;
            std::vector<std::pair<int, int>> win_line;
            for (int k = 0; k < win_len; ++k) {
                if (board[i][j + k] != color) {
                    win = false;
                    break;
                }
                win_line.emplace_back(i, j + k);
            }
            if (win) {
                result.is_end = true;
                result.winner = color;
                result.win_line_size = win_len;
                result.win_line = win_line;
                return result;
            }
        }
    }

    // 检查纵向
    for (int j = 0; j < board_size; ++j) {
        for (int i = 0; i <= board_size - win_len; ++i) {
            int color = board[i][j];
            if (color == 0) continue;
            bool win = true;
            std::vector<std::pair<int, int>> win_line;
            for (int k = 0; k < win_len; ++k) {
                if (board[i + k][j] != color) {
                    win = false;
                    break;
                }
                win_line.emplace_back(i + k, j);
            }
            if (win) {
                result.is_end = true;
                result.winner = color;
                result.win_line_size = win_len;
                result.win_line = win_line;
                return result;
            }
        }
    }

    // 检查对角线（左上→右下）
    for (int i = 0; i <= board_size - win_len; ++i) {
        for (int j = 0; j <= board_size - win_len; ++j) {
            int color = board[i][j];
            if (color == 0) continue;
            bool win = true;
            std::vector<std::pair<int, int>> win_line;
            for (int k = 0; k < win_len; ++k) {
                if (board[i + k][j + k] != color) {
                    win = false;
                    break;
                }
                win_line.emplace_back(i + k, j + k);
            }
            if (win) {
                result.is_end = true;
                result.winner = color;
                result.win_line_size = win_len;
                result.win_line = win_line;
                return result;
            }
        }
    }

    // 检查对角线（右上→左下）
    for (int i = 0; i <= board_size - win_len; ++i) {
        for (int j = win_len - 1; j < board_size; ++j) {
            int color = board[i][j];
            if (color == 0) continue;
            bool win = true;
            std::vector<std::pair<int, int>> win_line;
            for (int k = 0; k < win_len; ++k) {
                if (board[i + k][j - k] != color) {
                    win = false;
                    break;
                }
                win_line.emplace_back(i + k, j - k);
            }
            if (win) {
                result.is_end = true;
                result.winner = color;
                result.win_line_size = win_len;
                result.win_line = win_line;
                return result;
            }
        }
    }

    // 检查平局（棋盘满）
    bool is_full = true;
    for (int i = 0; i < board_size; ++i) {
        for (int j = 0; j < board_size; ++j) {
            if (board[i][j] == 0) {
                is_full = false;
                break;
            }
        }
        if (!is_full) break;
    }
    if (is_full) {
        result.is_end = true;
        result.winner = 0;
    }

    return result;
}

// 4. 落子评估（棋型识别+权重得分）
float GobangCore::evaluate_move(
    const std::vector<std::vector<int>>& board,
    int x, int y,
    int color,
    const Weights& weights,
    int board_size
) {
    // 临时落子，评估得分
    std::vector<std::vector<int>> temp_board = board;
    temp_board[x][y] = color;
    return get_pattern_score(temp_board, x, y, color, weights, board_size);
}

// 5. 查找必胜落子（立即形成五连的落子）
std::pair<int, int> GobangCore::find_winning_move(
    const std::vector<std::vector<int>>& board,
    int color,
    int board_size
) {
    for (int i = 0; i < board_size; ++i) {
        for (int j = 0; j < board_size; ++j) {
            if (board[i][j] != 0) continue;
            // 模拟落子
            std::vector<std::vector<int>> temp_board = board;
            temp_board[i][j] = color;
            // 检查是否获胜
            GameEndResult result = check_game_end(temp_board, board_size);
            if (result.is_end && result.winner == color) {
                return {i, j};
            }
        }
    }
    return {-1, -1}; // 无必胜落子
}

// 6. MCTS优化落子（简化版：基于迭代搜索优化）
std::pair<int, int> GobangCore::mcts_optimize(
    const std::vector<std::vector<int>>& board,
    std::pair<int, int> init_move,
    int color,
    int depth,
    int iterations,
    int board_size
) {
    // 简化版MCTS：迭代评估候选落子，返回得分最高的
    float best_score = -1e9;
    std::pair<int, int> best_move = init_move;

    // 只评估周边8格+初始落子（减少计算量）
    std::vector<std::pair<int, int>> candidates;
    candidates.push_back(init_move);
    int dx[] = {-1, 0, 1, -1, 1, -1, 0, 1};
    int dy[] = {-1, -1, -1, 0, 0, 1, 1, 1};
    for (int d = 0; d < 8; ++d) {
        int x = init_move.first + dx[d];
        int y = init_move.second + dy[d];
        if (x >= 0 && x < board_size && y >= 0 && y < board_size && board[x][y] == 0) {
            candidates.push_back({x, y});
        }
    }

    // 迭代评估
    for (auto& move : candidates) {
        float score = 0.0f;
        for (int iter = 0; iter < iterations; ++iter) {
            // 随机模拟对局，累加得分（简化版）
            std::vector<std::vector<int>> temp_board = board;
            temp_board[move.first][move.second] = color;
            score += evaluate_move(temp_board, move.first, move.second, color, Weights{}, board_size);
        }
        score /= iterations;
        if (score > best_score) {
            best_score = score;
            best_move = move;
        }
    }

    return best_move;
}

// ---------------- 辅助函数 ----------------
int GobangCore::check_line(
    const std::vector<std::vector<int>>& board,
    int x, int y,
    int dx, int dy,
    int color,
    int board_size
) {
    int count = 0;
    while (x >= 0 && x < board_size && y >= 0 && y < board_size && board[x][y] == color) {
        count++;
        x += dx;
        y += dy;
    }
    return count;
}

float GobangCore::get_pattern_score(
    const std::vector<std::vector<int>>& board,
    int x, int y,
    int color,
    const Weights& weights,
    int board_size
) {
    float score = 0.0f;
    int opponent = (color == 1) ? 2 : 1;

    // 检查8个方向的连续棋子（计算棋型）
    int dirs[4][2] = {{0, 1}, {1, 0}, {1, 1}, {1, -1}};
    for (auto& dir : dirs) {
        int dx = dir[0], dy = dir[1];
        // 正方向+反方向连续数
        int forward = check_line(board, x + dx, y + dy, dx, dy, color, board_size);
        int backward = check_line(board, x - dx, y - dy, -dx, -dy, color, board_size);
        int total = forward + backward + 1; // +1为当前落子

        // 检查两端是否被阻挡
        bool blocked = false;
        int fx = x + (forward + 1) * dx;
        int fy = y + (forward + 1) * dy;
        int bx = x - (backward + 1) * dx;
        int by = y - (backward + 1) * dy;
        if ((fx >= 0 && fx < board_size && fy >= 0 && fy < board_size && board[fx][fy] == opponent) ||
            (bx >= 0 && bx < board_size && by >= 0 && by < board_size && board[bx][by] == opponent)) {
            blocked = true;
        }

        // 按棋型加分
        if (total >= 5) {
            score += weights.FIVE;
        } else if (total == 4) {
            score += blocked ? weights.BLOCKED_FOUR : weights.FOUR;
        } else if (total == 3) {
            score += blocked ? weights.BLOCKED_THREE : weights.THREE;
        } else if (total == 2) {
            score += blocked ? weights.BLOCKED_TWO : weights.TWO;
        } else if (total == 1) {
            score += weights.ONE;
        }
    }

    return score;
}

// ---------------- 对外C接口实现（CPython调用） ----------------
extern "C" {
    void* gobang_core_create() {
        return new GobangCore();
    }

    void gobang_core_destroy(void* core) {
        delete static_cast<GobangCore*>(core);
    }

    // 转换C风格int** → C++ vector<vector<int>>
    std::vector<std::vector<int>> board_c_to_cpp(int** board, int board_size) {
        std::vector<std::vector<int>> cpp_board(board_size);
        for (int i = 0; i < board_size; ++i) {
            cpp_board[i].assign(board[i], board[i] + board_size);
        }
        return cpp_board;
    }

    // 转换C++ vector<vector<int>> → C风格int**
    int** board_cpp_to_c(const std::vector<std::vector<int>>& cpp_board, int board_size) {
        int** c_board = (int**)malloc(board_size * sizeof(int*));
        for (int i = 0; i < board_size; ++i) {
            c_board[i] = (int*)malloc(board_size * sizeof(int));
            memcpy(c_board[i], cpp_board[i].data(), board_size * sizeof(int));
        }
        return c_board;
    }

    bool gobang_core_validate_move(
        void* core,
        int** board,
        int x, int y,
        int current_player,
        int board_size,
        char** error_msg
    ) {
        auto* gc = static_cast<GobangCore*>(core);
        auto cpp_board = board_c_to_cpp(board, board_size);
        auto [valid, reason] = gc->validate_move(cpp_board, x, y, current_player, board_size);
        if (!valid) {
            *error_msg = (char*)malloc(reason.size() + 1);
            strcpy(*error_msg, reason.c_str());
        }
        return valid;
    }

    int** gobang_core_place_piece(
        void* core,
        int** board,
        int x, int y,
        int color,
        int board_size
    ) {
        auto* gc = static_cast<GobangCore*>(core);
        auto cpp_board = board_c_to_cpp(board, board_size);
        auto new_cpp_board = gc->place_piece(cpp_board, x, y, color, board_size);
        return board_cpp_to_c(new_cpp_board, board_size);
    }

    GameEndResult gobang_core_check_game_end(
        void* core,
        int** board,
        int board_size
    ) {
        auto* gc = static_cast<GobangCore*>(core);
        auto cpp_board = board_c_to_cpp(board, board_size);
        return gc->check_game_end(cpp_board, board_size);
    }

    float gobang_core_evaluate_move(
        void* core,
        int** board,
        int x, int y,
        int color,
        Weights weights,
        int board_size
    ) {
        auto* gc = static_cast<GobangCore*>(core);
        auto cpp_board = board_c_to_cpp(board, board_size);
        return gc->evaluate_move(cpp_board, x, y, color, weights, board_size);
    }

    int* gobang_core_find_winning_move(
        void* core,
        int** board,
        int color,
        int board_size
    ) {
        auto* gc = static_cast<GobangCore*>(core);
        auto cpp_board = board_c_to_cpp(board, board_size);
        auto [x, y] = gc->find_winning_move(cpp_board, color, board_size);
        int* move = (int*)malloc(2 * sizeof(int));
        move[0] = x;
        move[1] = y;
        return move;
    }

    int* gobang_core_mcts_optimize(
        void* core,
        int** board,
        int init_x, int init_y,
        int color,
        int depth,
        int iterations,
        int board_size
    ) {
        auto* gc = static_cast<GobangCore*>(core);
        auto cpp_board = board_c_to_cpp(board, board_size);
        auto best_move = gc->mcts_optimize(cpp_board, {init_x, init_y}, color, depth, iterations, board_size);
        int* move = (int*)malloc(2 * sizeof(int));
        move[0] = best_move.first;
        move[1] = best_move.second;
        return move;
    }

    // 内存释放
    void gobang_core_free_board(int** board, int board_size) {
        for (int i = 0; i < board_size; ++i) {
            free(board[i]);
        }
        free(board);
    }

    void gobang_core_free_int_array(int* arr) {
        free(arr);
    }

    void gobang_core_free_game_end_result(GameEndResult result) {
        // 无需释放（vector自动析构）
    }
}
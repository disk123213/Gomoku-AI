import numpy as np
from typing import List, Tuple, Dict, Optional, Callable
from Common.constants import AI_LEVELS, EVAL_WEIGHTS, PIECE_COLORS
from Common.logger import Logger
from AI.base_ai import BaseAI
from Compute.cpp_interface import CppCore

class MinimaxAI(BaseAI):
    """Minimax+Alpha-Beta剪枝AI（C++加速核心）"""
    def __init__(self, color: int, level: str = AI_LEVELS['HARD'], use_cpp: bool = True):
        super().__init__(color, level)
        self.logger = Logger.get_instance()
        self.cpp_core = CppCore() if use_cpp else None
        self.max_depth = self._get_max_depth()  # 动态深度适配难度
        self.alpha = -float('inf')
        self.beta = float('inf')
        self.best_move: Tuple[int, int] = (0, 0)
        self.eval_cache = {}  # 评估缓存（减少重复计算）

    def _get_max_depth(self) -> int:
        """根据难度获取最大搜索深度"""
        depth_map = {
            AI_LEVELS['EASY']: 3,
            AI_LEVELS['MEDIUM']: 4,
            AI_LEVELS['HARD']: 5,
            AI_LEVELS['EXPERT']: 6
        }
        return depth_map.get(self.level, 5)

    def _evaluate(self, board: List[List[int]], color: int) -> float:
        """评估棋盘（优先调用C++核心）"""
        if self.cpp_core:
            # 找当前最佳落子位置评估（C++高效计算）
            empty_pos = self._get_empty_positions(board)[:10]  # 取前10个候选位
            best_score = -float('inf')
            for (x, y) in empty_pos:
                cache_key = (tuple(tuple(row) for row in board), x, y, color)
                if cache_key in self.eval_cache:
                    score = self.eval_cache[cache_key]
                else:
                    score = self.cpp_core.evaluate_move(board, x, y, color, EVAL_WEIGHTS)
                    self.eval_cache[cache_key] = score
                if score > best_score:
                    best_score = score
            return best_score
        else:
            # Python降级实现（备用）
            return self._python_evaluate(board, color)

    def _python_evaluate(self, board: List[List[int]], color: int) -> float:
        """Python降级评估（无C++核心时使用）"""
        score = 0.0
        # 简单棋型评分（仅作兼容，性能较差）
        for x in range(self.board_size):
            for y in range(self.board_size):
                if board[x][y] == color:
                    score += self._calc_pos_score(board, x, y, color)
                elif board[x][y] == self.opponent_color:
                    score -= self._calc_pos_score(board, x, y, self.opponent_color)
        return score

    def _calc_pos_score(self, board: List[List[int]], x: int, y: int, color: int) -> float:
        """计算单个位置得分（棋型识别）"""
        # 简化实现：检查横/竖/斜向连续棋子
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        score = 0.0
        for dx, dy in directions:
            count = 1
            blocked = 0
            # 正向计数
            nx, ny = x + dx, y + dy
            while 0 <= nx < self.board_size and 0 <= ny < self.board_size and board[nx][ny] == color:
                count += 1
                nx += dx
                ny += dy
            if 0 <= nx < self.board_size and 0 <= ny < self.board_size and board[nx][ny] != PIECE_COLORS['EMPTY']:
                blocked += 1
            # 反向计数
            nx, ny = x - dx, y - dy
            while 0 <= nx < self.board_size and 0 <= ny < self.board_size and board[nx][ny] == color:
                count += 1
                nx -= dx
                ny -= dy
            if 0 <= nx < self.board_size and 0 <= ny < self.board_size and board[nx][ny] != PIECE_COLORS['EMPTY']:
                blocked += 1
            # 棋型评分
            if count >= 5:
                score += 10000.0
            elif count == 4 and blocked == 0:
                score += 1000.0
            elif count == 4 and blocked == 1:
                score += 100.0
            elif count == 3 and blocked == 0:
                score += 100.0
            elif count == 3 and blocked == 1:
                score += 10.0
        return score

    def _minimax(self, board: List[List[int]], depth: int, alpha: float, beta: float, is_maximizing: bool) -> float:
        """Minimax核心算法（Alpha-Beta剪枝）"""
        # 检查游戏结束
        win, _ = self._is_win(board, self.color if is_maximizing else self.opponent_color)
        if win:
            return 10000.0 * (1 + depth / 10) if is_maximizing else -10000.0 * (1 + depth / 10)
        # 搜索深度终止
        if depth == 0:
            return self._evaluate(board, self.color)
        # 空位置排序（提升剪枝效率）
        empty_pos = self._get_empty_positions(board)
        empty_pos.sort(key=lambda pos: self._evaluate(self._simulate_move(board, pos[0], pos[1], self.color if is_maximizing else self.opponent_color), self.color), reverse=is_maximizing)
        # 最大化玩家（己方）
        if is_maximizing:
            max_score = -float('inf')
            for (x, y) in empty_pos[:15]:  # 限制候选位数量，提升速度
                new_board = self._simulate_move(board, x, y, self.color)
                score = self._minimax(new_board, depth - 1, alpha, beta, False)
                if score > max_score:
                    max_score = score
                    if depth == self.max_depth:
                        self.best_move = (x, y)
                alpha = max(alpha, max_score)
                if beta <= alpha:
                    break  # Beta剪枝
            return max_score
        # 最小化玩家（对手）
        else:
            min_score = float('inf')
            for (x, y) in empty_pos[:15]:
                new_board = self._simulate_move(board, x, y, self.opponent_color)
                score = self._minimax(new_board, depth - 1, alpha, beta, True)
                if score < min_score:
                    min_score = score
                beta = min(beta, min_score)
                if beta <= alpha:
                    break  # Alpha剪枝
            return min_score

    def _simulate_move(self, board: List[List[int]], x: int, y: int, color: int) -> List[List[int]]:
        """模拟落子（深拷贝棋盘）"""
        new_board = [row.copy() for row in board]
        new_board[x][y] = color
        return new_board

    def move(self, board: List[List[int]], thinking_callback: Optional[Callable[[Dict], None]] = None) -> Tuple[int, int]:
        """AI落子（C++加速+剪枝）"""
        self.thinking_callback = thinking_callback
        self.eval_cache.clear()
        self.best_move = (self.board_size//2, self.board_size//2)  # 默认天元落子
        
        # 思维可视化：初始化数据
        thinking_data = {
            'scores': np.zeros((self.board_size, self.board_size)),
            'best_move': self.best_move,
            'considering_moves': [],
            'depth': self.max_depth,
            'iteration': 0
        }
        self._notify_thinking(thinking_data)

        # 检查必胜落子（C++快速判断）
        if self.cpp_core:
            winning_move = self.cpp_core.find_winning_move(board, self.color, self.board_size)
            if winning_move:
                thinking_data['best_move'] = winning_move
                self._notify_thinking(thinking_data)
                return winning_move

        # 启动Minimax搜索
        score = self._minimax(board, self.max_depth, self.alpha, self.beta, True)

        # 思维可视化：更新最终数据
        empty_pos = self._get_empty_positions(board)[:10]
        for (x, y) in empty_pos:
            thinking_data['scores'][x][y] = self._evaluate(board, self.color) * 20
        thinking_data['best_move'] = self.best_move
        thinking_data['considering_moves'] = empty_pos[:5]
        self._notify_thinking(thinking_data)

        self.logger.info(f"Minimax AI落子：{self.best_move}，局势评分：{score:.2f}")
        return self.best_move
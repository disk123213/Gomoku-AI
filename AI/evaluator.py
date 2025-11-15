import numpy as np
from typing import List, Tuple, Dict
from Common.constants import PIECE_COLORS, EVAL_WEIGHTS
from Common.logger import Logger
from Compute.cpp_interface import CppCore

class BoardEvaluator:
    """棋盘评估器（棋型识别、位置权重、局势评分）"""
    def __init__(self, board_size: int = 15):
        self.board_size = board_size
        self.logger = Logger.get_instance()
        self.cpp_core = CppCore()
        # 位置权重矩阵（天元及周边权重高）
        self.position_weights = self._init_position_weights()

    def _init_position_weights(self) -> np.ndarray:
        """初始化位置权重矩阵"""
        weights = np.ones((self.board_size, self.board_size), dtype=np.float32)
        center = self.board_size // 2
        for x in range(self.board_size):
            for y in range(self.board_size):
                # 距离天元越近，权重越高
                dist = np.sqrt((x - center)**2 + (y - center)**2)
                weights[x][y] = max(0.3, 1.0 - dist / (self.board_size / 2))
        # 星位和天元额外加权
        star_positions = [(3, 3), (3, 11), (7, 7), (11, 3), (11, 11)]
        for (x, y) in star_positions:
            weights[x][y] *= 1.2
        return weights

    def _recognize_pattern(self, board: List[List[int]], x: int, y: int, color: int) -> Tuple[str, int]:
        """识别落子位置的棋型（C++加速）"""
        if self.cpp_core:
            # 调用C++核心识别棋型（高效）
            score = self.cpp_core.evaluate_move(board, x, y, color, EVAL_WEIGHTS)
            # 根据得分判断棋型
            if score >= EVAL_WEIGHTS['FIVE']:
                return ('FIVE', score)
            elif score >= EVAL_WEIGHTS['FOUR']:
                return ('FOUR', score)
            elif score >= EVAL_WEIGHTS['BLOCKED_FOUR']:
                return ('BLOCKED_FOUR', score)
            elif score >= EVAL_WEIGHTS['THREE']:
                return ('THREE', score)
            elif score >= EVAL_WEIGHTS['BLOCKED_THREE']:
                return ('BLOCKED_THREE', score)
            elif score >= EVAL_WEIGHTS['TWO']:
                return ('TWO', score)
            elif score >= EVAL_WEIGHTS['BLOCKED_TWO']:
                return ('BLOCKED_TWO', score)
            else:
                return ('ONE', score)
        else:
            # Python降级实现
            return self._python_recognize_pattern(board, x, y, color)

    def _python_recognize_pattern(self, board: List[List[int]], x: int, y: int, color: int) -> Tuple[str, int]:
        """Python降级棋型识别"""
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        max_score = 0
        best_pattern = 'ONE'
        for dx, dy in directions:
            # 计算该方向的连续棋子和阻挡情况
            count = 1
            blocked = 0
            # 正向
            nx, ny = x + dx, y + dy
            while 0 <= nx < self.board_size and 0 <= ny < self.board_size and board[nx][ny] == color:
                count += 1
                nx += dx
                ny += dy
            if 0 <= nx < self.board_size and 0 <= ny < self.board_size and board[nx][ny] != PIECE_COLORS['EMPTY']:
                blocked += 1
            # 反向
            nx, ny = x - dx, y - dy
            while 0 <= nx < self.board_size and 0 <= ny < self.board_size and board[nx][ny] == color:
                count += 1
                nx -= dx
                ny -= dy
            if 0 <= nx < self.board_size and 0 <= ny < self.board_size and board[nx][ny] != PIECE_COLORS['EMPTY']:
                blocked += 1
            # 计算得分
            pattern_score = self._calc_pattern_score(count, blocked)
            if pattern_score > max_score:
                max_score = pattern_score
                best_pattern = self._get_pattern_name(count, blocked)
        return (best_pattern, max_score * self.position_weights[x][y])

    def _calc_pattern_score(self, count: int, blocked: int) -> float:
        """根据连续棋子数和阻挡数计算得分"""
        if count >= 5:
            return EVAL_WEIGHTS['FIVE']
        elif count == 4:
            return EVAL_WEIGHTS['FOUR'] if blocked == 0 else EVAL_WEIGHTS['BLOCKED_FOUR']
        elif count == 3:
            return EVAL_WEIGHTS['THREE'] if blocked == 0 else EVAL_WEIGHTS['BLOCKED_THREE']
        elif count == 2:
            return EVAL_WEIGHTS['TWO'] if blocked == 0 else EVAL_WEIGHTS['BLOCKED_TWO']
        else:
            return EVAL_WEIGHTS['ONE']

    def _get_pattern_name(self, count: int, blocked: int) -> str:
        """根据连续棋子数和阻挡数获取棋型名称"""
        if count >= 5:
            return 'FIVE'
        elif count == 4:
            return 'FOUR' if blocked == 0 else 'BLOCKED_FOUR'
        elif count == 3:
            return 'THREE' if blocked == 0 else 'BLOCKED_THREE'
        elif count == 2:
            return 'TWO' if blocked == 0 else 'BLOCKED_TWO'
        else:
            return 'ONE'

    def evaluate_board(self, board: List[List[int]], color: int) -> float:
        """评估整个棋盘的局势得分"""
        total_score = 0.0
        for x in range(self.board_size):
            for y in range(self.board_size):
                if board[x][y] == color:
                    pattern, score = self._recognize_pattern(board, x, y, color)
                    total_score += score
                elif board[x][y] == (PIECE_COLORS['WHITE'] if color == PIECE_COLORS['BLACK'] else PIECE_COLORS['BLACK']):
                    pattern, score = self._recognize_pattern(board, x, y, board[x][y])
                    total_score -= score
        return total_score

    def evaluate_move(self, board: List[List[int]], x: int, y: int, color: int) -> float:
        """评估单个落子的得分"""
        # 模拟落子
        temp_board = [row.copy() for row in board]
        temp_board[x][y] = color
        # 计算落子后的局势得分变化
        new_score = self.evaluate_board(temp_board, color)
        old_score = self.evaluate_board(board, color)
        return new_score - old_score + self.position_weights[x][y]

    def analyze_move_quality(self, board: List[List[int]], x: int, y: int, color: int) -> Dict:
        """分析落子质量（用于复盘）"""
        pattern, score = self._recognize_pattern(board, x, y, color)
        max_possible_score = 0.0
        best_move = (x, y)
        # 查找最优落子
        for nx in range(self.board_size):
            for ny in range(self.board_size):
                if board[nx][ny] == PIECE_COLORS['EMPTY']:
                    temp_score = self.evaluate_move(board, nx, ny, color)
                    if temp_score > max_possible_score:
                        max_possible_score = temp_score
                        best_move = (nx, ny)
        # 计算落子质量（0-100分）
        move_score = self.evaluate_move(board, x, y, color)
        quality = min(100, (move_score / max_possible_score) * 100) if max_possible_score > 0 else 0
        return {
            'move': (x, y),
            'pattern': pattern,
            'score': move_score,
            'best_move': best_move,
            'best_score': max_possible_score,
            'quality': round(quality, 2),
            'position_weight': round(self.position_weights[x][y], 2)
        }
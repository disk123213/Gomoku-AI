from typing import List, Tuple, Dict
from Common.constants import PIECE_COLORS
from Common.logger import Logger
from Compute.cpp_interface import CppCore

class RuleEngine:
    """规则引擎（落子校验、获胜判断、规则校验）"""
    def __init__(self, board_size: int = 15):
        self.board_size = board_size
        self.logger = Logger.get_instance()
        self.cpp_core = CppCore()
        self.valid_rules = {
            'position': self._validate_position,
            'occupied': self._validate_occupied,
            'player_turn': self._validate_player_turn
        }

    def validate_move(self, board: List[List[int]], x: int, y: int, current_player: int) -> Tuple[bool, str]:
        """综合校验落子合法性（调用C++核心加速）"""
        # 优先使用C++核心校验（高效）
        if self.cpp_core:
            valid, reason = self.cpp_core.validate_move(board, x, y, current_player, self.board_size)
            return (valid, reason)

        # Python降级校验（备用）
        for rule_name, rule_func in self.valid_rules.items():
            valid, reason = rule_func(board, x, y, current_player)
            if not valid:
                return (False, reason)
        return (True, 'success')

    def check_game_end(self, board: List[List[int]]) -> Dict:
        """检查游戏是否结束（获胜/平局）"""
        # 优先使用C++核心判断（高效）
        if self.cpp_core:
            return self.cpp_core.check_game_end(board, self.board_size)

        # Python降级判断（备用）
        # 检查横向获胜
        for i in range(self.board_size):
            for j in range(self.board_size - 4):
                color = board[i][j]
                if color == PIECE_COLORS['EMPTY']:
                    continue
                if all(board[i][j + k] == color for k in range(5)):
                    win_line = [(i, j + k) for k in range(5)]
                    return {'is_end': True, 'winner': color, 'win_line': win_line}

        # 检查纵向获胜
        for j in range(self.board_size):
            for i in range(self.board_size - 4):
                color = board[i][j]
                if color == PIECE_COLORS['EMPTY']:
                    continue
                if all(board[i + k][j] == color for k in range(5)):
                    win_line = [(i + k, j) for k in range(5)]
                    return {'is_end': True, 'winner': color, 'win_line': win_line}

        # 检查正对角线获胜
        for i in range(self.board_size - 4):
            for j in range(self.board_size - 4):
                color = board[i][j]
                if color == PIECE_COLORS['EMPTY']:
                    continue
                if all(board[i + k][j + k] == color for k in range(5)):
                    win_line = [(i + k, j + k) for k in range(5)]
                    return {'is_end': True, 'winner': color, 'win_line': win_line}

        # 检查反对角线获胜
        for i in range(4, self.board_size):
            for j in range(self.board_size - 4):
                color = board[i][j]
                if color == PIECE_COLORS['EMPTY']:
                    continue
                if all(board[i - k][j + k] == color for k in range(5)):
                    win_line = [(i - k, j + k) for k in range(5)]
                    return {'is_end': True, 'winner': color, 'win_line': win_line}

        # 检查平局（棋盘满）
        is_full = all(board[i][j] != PIECE_COLORS['EMPTY'] for i in range(self.board_size) for j in range(self.board_size))
        if is_full:
            return {'is_end': True, 'winner': 0, 'win_line': []}

        return {'is_end': False, 'winner': 0, 'win_line': []}

    def is_valid_board(self, board: List[List[int]]) -> Tuple[bool, str]:
        """校验棋盘状态合法性（用于联机同步校验）"""
        # 检查棋盘尺寸
        if len(board) != self.board_size or any(len(row) != self.board_size for row in board):
            return (False, 'invalid_board_size')

        # 检查棋子颜色
        for i in range(self.board_size):
            for j in range(self.board_size):
                if board[i][j] not in [PIECE_COLORS['EMPTY'], PIECE_COLORS['BLACK'], PIECE_COLORS['WHITE']]:
                    return (False, f'invalid_piece_color_at_({i},{j})')

        # 检查黑白棋子数量差（黑棋最多多1颗）
        black_count = sum(row.count(PIECE_COLORS['BLACK']) for row in board)
        white_count = sum(row.count(PIECE_COLORS['WHITE']) for row in board)
        if abs(black_count - white_count) > 1:
            return (False, f'piece_count_mismatch: black={black_count}, white={white_count}')

        # 检查是否存在多个获胜线
        win_lines = self._find_all_win_lines(board)
        if len(win_lines) > 1:
            return (False, f'multiple_win_lines: {len(win_lines)}')

        return (True, 'success')

    # ------------------------------ 基础规则校验 ------------------------------
    def _validate_position(self, board: List[List[int]], x: int, y: int, current_player: int) -> Tuple[bool, str]:
        """校验坐标是否在棋盘范围内"""
        if x < 0 or x >= self.board_size or y < 0 or y >= self.board_size:
            return (False, 'invalid_position')
        return (True, 'success')

    def _validate_occupied(self, board: List[List[int]], x: int, y: int, current_player: int) -> Tuple[bool, str]:
        """校验位置是否已被占用"""
        if board[x][y] != PIECE_COLORS['EMPTY']:
            return (False, 'occupied')
        return (True, 'success')

    def _validate_player_turn(self, board: List[List[int]], x: int, y: int, current_player: int) -> Tuple[bool, str]:
        """校验是否为当前玩家回合（通过棋子数量判断）"""
        black_count = sum(row.count(PIECE_COLORS['BLACK']) for row in board)
        white_count = sum(row.count(PIECE_COLORS['WHITE']) for row in board)

        if current_player == PIECE_COLORS['BLACK'] and black_count > white_count:
            return (False, 'black_turn_invalid')
        if current_player == PIECE_COLORS['WHITE'] and white_count > black_count:
            return (False, 'white_turn_invalid')
        return (True, 'success')

    def _find_all_win_lines(self, board: List[List[int]]) -> List[List[Tuple[int, int]]]:
        """查找所有获胜线（用于合法性校验）"""
        win_lines = []
        # 横向
        for i in range(self.board_size):
            for j in range(self.board_size - 4):
                color = board[i][j]
                if color == PIECE_COLORS['EMPTY']:
                    continue
                if all(board[i][j + k] == color for k in range(5)):
                    win_lines.append([(i, j + k) for k in range(5)])
        # 纵向
        for j in range(self.board_size):
            for i in range(self.board_size - 4):
                color = board[i][j]
                if color == PIECE_COLORS['EMPTY']:
                    continue
                if all(board[i + k][j] == color for k in range(5)):
                    win_lines.append([(i + k, j) for k in range(5)])
        # 正对角线
        for i in range(self.board_size - 4):
            for j in range(self.board_size - 4):
                color = board[i][j]
                if color == PIECE_COLORS['EMPTY']:
                    continue
                if all(board[i + k][j + k] == color for k in range(5)):
                    win_lines.append([(i + k, j + k) for k in range(5)])
        # 反对角线
        for i in range(4, self.board_size):
            for j in range(self.board_size - 4):
                color = board[i][j]
                if color == PIECE_COLORS['EMPTY']:
                    continue
                if all(board[i - k][j + k] == color for k in range(5)):
                    win_lines.append([(i - k, j + k) for k in range(5)])
        return win_lines
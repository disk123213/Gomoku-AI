import abc
from typing import List, Tuple, Dict, Optional, Callable
from Common.constants import PIECE_COLORS
from Common.config import Config

class BaseAI(metaclass=abc.ABCMeta):
    """AI抽象基类（统一接口规范）"""
    def __init__(self, color: int, level: str):
        self.color = color  # 棋子颜色（BLACK/WHITE）
        self.opponent_color = PIECE_COLORS['WHITE'] if color == PIECE_COLORS['BLACK'] else PIECE_COLORS['BLACK']
        self.level = level
        self.config = Config.get_instance()
        self.board_size = self.config.board_size
        self.thinking_callback: Optional[Callable[[Dict], None]] = None  # 思维可视化回调

    @abc.abstractmethod
    def move(self, board: List[List[int]], thinking_callback: Optional[Callable[[Dict], None]] = None) -> Tuple[int, int]:
        """核心落子方法（必须实现）"""
        pass

    def set_thinking_callback(self, callback: Optional[Callable[[Dict], None]]):
        """设置思维可视化回调"""
        self.thinking_callback = callback

    def _notify_thinking(self, data: Dict):
        """通知思维过程（给可视化组件）"""
        if self.thinking_callback:
            self.thinking_callback(data)

    def _get_empty_positions(self, board: List[List[int]]) -> List[Tuple[int, int]]:
        """获取棋盘空位置（通用实现）"""
        empty_pos = []
        for x in range(self.board_size):
            for y in range(self.board_size):
                if board[x][y] == PIECE_COLORS['EMPTY']:
                    empty_pos.append((x, y))
        return empty_pos

    def _is_win(self, board: List[List[int]], color: int) -> Tuple[bool, List[Tuple[int, int]]]:
        """检查是否获胜（通用实现，对接C++核心）"""
        from Compute.cpp_interface import CppCore
        cpp_core = CppCore()
        result = cpp_core.check_game_end(board, self.board_size)
        return (result['is_end'] and result['winner'] == color, result['win_line'])
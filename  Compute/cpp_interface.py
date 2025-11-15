import ctypes
import numpy as np
import platform
from typing import List, Tuple, Dict, Optional
from Common.constants import PIECE_COLORS
from Common.logger import Logger

class CppCore:
    """C++核心算法接口（CPython封装，跨平台支持）"""
    def __init__(self):
        self.logger = Logger.get_instance()
        self.lib = None
        self.core = None
        self._load_library()
        self._define_c_types()
        self._init_core()

    def _load_library(self):
        """加载C++动态库（Windows/Linux/macOS兼容）"""
        system = platform.system()
        lib_names = {
            'Windows': 'gobang_core.dll',
            'Linux': 'libgobang_core.so',
            'Darwin': 'libgobang_core.dylib'
        }
        if system not in lib_names:
            raise RuntimeError(f"不支持的操作系统：{system}")

        lib_path = f'./cpp/build/{lib_names[system]}'
        try:
            self.lib = ctypes.CDLL(lib_path)
            self.logger.info(f"加载C++核心库成功：{lib_path}")
        except Exception as e:
            raise RuntimeError(f"加载C++核心库失败：{str(e)}")

    def _define_c_types(self):
        """定义C++数据类型映射（结构体+函数签名）"""
        # 权重结构体（对应C++ Weights）
        class CWeights(ctypes.Structure):
            _fields_ = [
                ("FIVE", ctypes.c_float),
                ("FOUR", ctypes.c_float),
                ("BLOCKED_FOUR", ctypes.c_float),
                ("THREE", ctypes.c_float),
                ("BLOCKED_THREE", ctypes.c_float),
                ("TWO", ctypes.c_float),
                ("BLOCKED_TWO", ctypes.c_float),
                ("ONE", ctypes.c_float)
            ]
        self.CWeights = CWeights

        # 游戏结束结果结构体（对应C++ GameEndResult）
        class CGameEndResult(ctypes.Structure):
            _fields_ = [
                ("is_end", ctypes.c_bool),
                ("winner", ctypes.c_int),
                ("win_line_size", ctypes.c_int),
                ("win_line", ctypes.POINTER(ctypes.POINTER(ctypes.c_int)))
            ]
        self.CGameEndResult = CGameEndResult

        # 函数签名定义
        # 1. 核心实例创建/销毁
        self.lib.gobang_core_create.restype = ctypes.c_void_p
        self.lib.gobang_core_destroy.argtypes = [ctypes.c_void_p]

        # 2. 落子验证
        self.lib.gobang_core_validate_move.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_int)),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_char_p)
        ]
        self.lib.gobang_core_validate_move.restype = ctypes.c_bool

        # 3. 执行落子
        self.lib.gobang_core_place_piece.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_int)),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int
        ]
        self.lib.gobang_core_place_piece.restype = ctypes.POINTER(ctypes.POINTER(ctypes.c_int))

        # 4. 检查游戏结束
        self.lib.gobang_core_check_game_end.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_int)),
            ctypes.c_int
        ]
        self.lib.gobang_core_check_game_end.restype = self.CGameEndResult

        # 5. 落子评估
        self.lib.gobang_core_evaluate_move.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_int)),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            self.CWeights
        ]
        self.lib.gobang_core_evaluate_move.restype = ctypes.c_float

        # 6. 查找必胜落子
        self.lib.gobang_core_find_winning_move.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_int)),
            ctypes.c_int,
            ctypes.c_int
        ]
        self.lib.gobang_core_find_winning_move.restype = ctypes.POINTER(ctypes.c_int)

        # 7. MCTS优化落子
        self.lib.gobang_core_mcts_optimize.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_int)),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int
        ]
        self.lib.gobang_core_mcts_optimize.restype = ctypes.POINTER(ctypes.c_int)

        # 8. 内存释放函数
        self.lib.gobang_core_free_board.argtypes = [
            ctypes.POINTER(ctypes.POINTER(ctypes.c_int)),
            ctypes.c_int
        ]
        self.lib.gobang_core_free_int_array.argtypes = [ctypes.POINTER(ctypes.c_int)]
        self.lib.gobang_core_free_game_end_result.argtypes = [self.CGameEndResult]

    def _init_core(self):
        """初始化C++核心实例"""
        self.core = self.lib.gobang_core_create()
        if not self.core:
            raise RuntimeError("创建C++核心实例失败")
        self.logger.info("C++核心实例初始化成功")

    def _convert_board_to_c(self, board: List[List[int]]) -> Tuple[ctypes.POINTER(ctypes.POINTER(ctypes.c_int)), int]:
        """Python棋盘 → C++二维数组"""
        board_size = len(board)
        c_board = (ctypes.POINTER(ctypes.c_int) * board_size)()
        for i in range(board_size):
            row = (ctypes.c_int * board_size)(*board[i])
            c_board[i] = row
        return c_board, board_size

    def _convert_board_from_c(self, c_board: ctypes.POINTER(ctypes.POINTER(ctypes.c_int)), board_size: int) -> List[List[int]]:
        """C++二维数组 → Python棋盘"""
        board = []
        for i in range(board_size):
            row = [c_board[i][j] for j in range(board_size)]
            board.append(row)
        return board

    def validate_move(self, board: List[List[int]], x: int, y: int, current_player: int, board_size: int) -> Tuple[bool, str]:
        """验证落子有效性（C++加速）"""
        c_board, _ = self._convert_board_to_c(board)
        error_msg = ctypes.c_char_p()
        valid = self.lib.gobang_core_validate_move(
            self.core, c_board, x, y, current_player, board_size, ctypes.byref(error_msg)
        )
        reason = error_msg.decode('utf-8') if error_msg else "success"
        return valid, reason

    def place_piece(self, board: List[List[int]], x: int, y: int, color: int) -> List[List[int]]:
        """执行落子（C++更新棋盘）"""
        board_size = len(board)
        c_board, _ = self._convert_board_to_c(board)
        c_new_board = self.lib.gobang_core_place_piece(
            self.core, c_board, x, y, color, board_size
        )
        new_board = self._convert_board_from_c(c_new_board, board_size)
        self.lib.gobang_core_free_board(c_new_board, board_size)
        return new_board

    def check_game_end(self, board: List[List[int]], board_size: int) -> Dict:
        """检查游戏结束（C++快速判断）"""
        c_board, _ = self._convert_board_to_c(board)
        c_result = self.lib.gobang_core_check_game_end(self.core, c_board, board_size)
        result = {
            'is_end': c_result.is_end,
            'winner': c_result.winner,
            'win_line': []
        }
        if c_result.is_end and c_result.winner != 0 and c_result.win_line_size == 5:
            win_line = []
            for k in range(5):
                x = c_result.win_line[k][0]
                y = c_result.win_line[k][1]
                win_line.append((x, y))
            result['win_line'] = win_line
        self.lib.gobang_core_free_game_end_result(c_result)
        return result

    def evaluate_move(self, board: List[List[int]], x: int, y: int, color: int, weights: Dict[str, float]) -> float:
        """评估落子得分（C++棋型识别）"""
        c_weights = self.CWeights(
            FIVE=weights['FIVE'],
            FOUR=weights['FOUR'],
            BLOCKED_FOUR=weights['BLOCKED_FOUR'],
            THREE=weights['THREE'],
            BLOCKED_THREE=weights['BLOCKED_THREE'],
            TWO=weights['TWO'],
            BLOCKED_TWO=weights['BLOCKED_TWO'],
            ONE=weights['ONE']
        )
        c_board, board_size = self._convert_board_to_c(board)
        score = self.lib.gobang_core_evaluate_move(
            self.core, c_board, x, y, color, c_weights
        )
        return float(score)

    def find_winning_move(self, board: List[List[int]], color: int, board_size: int) -> Optional[Tuple[int, int]]:
        """查找必胜落子（C++快速搜索）"""
        c_board, _ = self._convert_board_to_c(board)
        c_move = self.lib.gobang_core_find_winning_move(self.core, c_board, color, board_size)
        if not c_move:
            return None
        x, y = c_move[0], c_move[1]
        self.lib.gobang_core_free_int_array(c_move)
        return (x, y)

    def mcts_optimize(self, board: List[List[int]], init_move: Tuple[int, int], color: int, depth: int, iterations: int) -> Tuple[int, int]:
        """MCTS优化落子（C++加速搜索）"""
        board_size = len(board)
        c_board, _ = self._convert_board_to_c(board)
        init_x, init_y = init_move
        c_best_move = self.lib.gobang_core_mcts_optimize(
            self.core, c_board, init_x, init_y, color, depth, iterations, board_size
        )
        if not c_best_move:
            return init_move
        x, y = c_best_move[0], c_best_move[1]
        self.lib.gobang_core_free_int_array(c_best_move)
        return (x, y)

    def __del__(self):
        """析构函数：释放C++核心实例"""
        if hasattr(self, 'lib') and hasattr(self, 'core') and self.core:
            self.lib.gobang_core_destroy(self.core)
            self.logger.info("C++核心实例已释放")
import random
import numpy as np
from typing import List, Tuple, Dict, Optional, Callable
from Common.constants import AI_LEVELS, EVAL_WEIGHTS, PIECE_COLORS
from Common.logger import Logger
from AI.base_ai import BaseAI
from Compute.cpp_interface import CppCore
from Compute.parallel_compute import ParallelWorker

class MCTSNode:
    """MCTS节点类"""
    def __init__(self, board: List[List[int]], parent: Optional['MCTSNode'] = None, move: Optional[Tuple[int, int]] = None, color: int = PIECE_COLORS['BLACK']):
        self.board = board  # 节点对应的棋盘状态
        self.parent = parent  # 父节点
        self.move = move  # 到达该节点的落子
        self.color = color  # 当前落子玩家
        self.children: List['MCTSNode'] = []  # 子节点
        self.visits = 0  # 访问次数
        self.wins = 0  # 获胜次数
        self.untried_moves = self._get_empty_positions(board)  # 未尝试落子
        self.value = 0.0  # 节点价值

    def _get_empty_positions(self, board: List[List[int]]) -> List[Tuple[int, int]]:
        """获取空位置"""
        empty_pos = []
        for x in range(len(board)):
            for y in range(len(board)):
                if board[x][y] == PIECE_COLORS['EMPTY']:
                    empty_pos.append((x, y))
        return empty_pos

    def select(self, exploration_constant: float = 1.414) -> 'MCTSNode':
        """选择子节点（UCT算法）"""
        return max(self.children, key=lambda node: node.get_uct_score(exploration_constant))

    def get_uct_score(self, exploration_constant: float) -> float:
        """计算UCT评分"""
        if self.visits == 0:
            return float('inf')
        return (self.wins / self.visits) + exploration_constant * np.sqrt(np.log(self.parent.visits) / self.visits)

    def expand(self) -> 'MCTSNode':
        """扩展节点（随机选择未尝试落子）"""
        move = random.choice(self.untried_moves)
        self.untried_moves.remove(move)
        new_board = [row.copy() for row in self.board]
        new_board[move[0]][move[1]] = self.color
        next_color = PIECE_COLORS['WHITE'] if self.color == PIECE_COLORS['BLACK'] else PIECE_COLORS['BLACK']
        child_node = MCTSNode(new_board, self, move, next_color)
        self.children.append(child_node)
        return child_node

    def backpropagate(self, result: float):
        """回溯更新节点数据"""
        self.visits += 1
        self.wins += result
        if self.parent:
            self.parent.backpropagate(1 - result)  # 父节点结果反转

class MCTSAI(BaseAI):
    """MCTS蒙特卡洛树搜索AI（并行迭代）"""
    def __init__(self, color: int, level: str = AI_LEVELS['HARD'], use_cpp: bool = True):
        super().__init__(color, level)
        self.logger = Logger.get_instance()
        self.cpp_core = CppCore() if use_cpp else None
        self.iterations = self._get_iterations()  # 迭代次数（适配难度）
        self.exploration_constant = 1.414  # UCT探索常数
        self.parallel_workers = self.config.get_int('AI', 'mcts_parallel_workers', 4)  # 并行工作线程数

    def _get_iterations(self) -> int:
        """根据难度获取迭代次数"""
        iter_map = {
            AI_LEVELS['EASY']: 300,
            AI_LEVELS['MEDIUM']: 600,
            AI_LEVELS['HARD']: 1000,
            AI_LEVELS['EXPERT']: 2000
        }
        return iter_map.get(self.level, 1000)

    def _simulate(self, board: List[List[int]], current_color: int) -> float:
        """模拟对局（快速rollout）"""
        temp_board = [row.copy() for row in board]
        while True:
            # 检查游戏结束
            win, _ = self._is_win(temp_board, self.color)
            if win:
                return 1.0
            win, _ = self._is_win(temp_board, self.opponent_color)
            if win:
                return 0.0
            # 检查平局
            if not self._get_empty_positions(temp_board):
                return 0.5
            # 随机落子（C++加速棋型评估优化）
            empty_pos = self._get_empty_positions(temp_board)
            if self.cpp_core:
                # 基于棋型评分选择落子（提升模拟质量）
                scores = [self.cpp_core.evaluate_move(temp_board, x, y, current_color, EVAL_WEIGHTS) for x, y in empty_pos]
                best_idx = np.argmax(scores)
                move = empty_pos[best_idx]
            else:
                move = random.choice(empty_pos)
            # 执行落子
            temp_board[move[0]][move[1]] = current_color
            current_color = PIECE_COLORS['WHITE'] if current_color == PIECE_COLORS['BLACK'] else PIECE_COLORS['BLACK']

    def _mcts_iteration(self, root: MCTSNode) -> None:
        """单次MCTS迭代（选择→扩展→模拟→回溯）"""
        node = root
        # 选择：直到叶子节点
        while node.children and not node.untried_moves:
            node = node.select(self.exploration_constant)
        # 扩展：如果不是终局节点
        if not self._is_win(node.board, self.color)[0] and not self._is_win(node.board, self.opponent_color)[0] and self._get_empty_positions(node.board):
            node = node.expand()
        # 模拟：获取结果
        result = self._simulate(node.board, node.color)
        # 回溯：更新节点
        node.backpropagate(result)

    def _parallel_iterations(self, root: MCTSNode, iterations: int) -> None:
        """并行执行MCTS迭代"""
        if self.parallel_workers <= 1:
            # 单线程执行
            for _ in range(iterations):
                self._mcts_iteration(root)
            return
        # 多线程并行
        worker = ParallelWorker(
            target=self._mcts_iteration,
            args=(root,),
            num_workers=self.parallel_workers,
            total_tasks=iterations
        )
        worker.run()

    def move(self, board: List[List[int]], thinking_callback: Optional[Callable[[Dict], None]] = None) -> Tuple[int, int]:
        """AI落子（并行MCTS+C++加速）"""
        self.thinking_callback = thinking_callback
        root = MCTSNode(board, color=self.color)

        # 思维可视化：初始化数据
        thinking_data = {
            'scores': np.zeros((self.board_size, self.board_size)),
            'best_move': (self.board_size//2, self.board_size//2),
            'considering_moves': [],
            'depth': 0,
            'iteration': 0,
            'total_iterations': self.iterations
        }
        self._notify_thinking(thinking_data)

        # 检查必胜落子（C++快速判断）
        if self.cpp_core:
            winning_move = self.cpp_core.find_winning_move(board, self.color, self.board_size)
            if winning_move:
                thinking_data['best_move'] = winning_move
                self._notify_thinking(thinking_data)
                return winning_move

        # 并行MCTS迭代
        self._parallel_iterations(root, self.iterations)

        # 选择最佳落子（访问次数最多的子节点）
        best_node = max(root.children, key=lambda node: node.visits)
        best_move = best_node.move

        # 思维可视化：更新数据
        for child in root.children[:10]:
            x, y = child.move
            thinking_data['scores'][x][y] = child.visits / root.visits * 100
        thinking_data['best_move'] = best_move
        thinking_data['considering_moves'] = [child.move for child in root.children[:5]]
        thinking_data['depth'] = self._get_node_depth(root)
        thinking_data['iteration'] = self.iterations
        self._notify_thinking(thinking_data)

        self.logger.info(f"MCTS AI落子：{best_move}，访问次数：{best_node.visits}/{root.visits}")
        return best_move

    def _get_node_depth(self, node: MCTSNode) -> int:
        """计算节点深度（用于可视化）"""
        depth = 0
        current = node
        while current.children:
            current = current.children[0]
            depth += 1
        return depth
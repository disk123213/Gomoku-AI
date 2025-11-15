import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import random
from collections import deque
from typing import List, Tuple, Dict, Optional, Callable
from Common.constants import PIECE_COLORS, AI_LEVELS, EVAL_WEIGHTS
from Common.config import Config
from Common.logger import Logger
from AI.base_ai import BaseAI
from AI.evaluator import BoardEvaluator
from Compute.cpp_interface import CppCore
from Compute.gpu_accelerator import GPUAccelerator
from Storage.model_storage import ModelStorage
from Storage.train_data_storage import TrainDataStorage

class DQNNetwork(nn.Module):
    """深度Q网络（强化学习核心）"""
    def __init__(self, input_size: int = 225, hidden_size: int = 512, output_size: int = 225):
        super().__init__()
        self.input_size = input_size
        self.output_size = output_size
        self.layers = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, output_size)
        )
        self.apply(self._init_weights)

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            nn.init.xavier_uniform_(m.weight)
            if m.bias is not None:
                nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.layers(x)

class RLAI(BaseAI):
    """强化学习AI（DQN+自我对弈+GPU加速）"""
    def __init__(self, color: int, level: str = AI_LEVELS['HARD'], use_cpp: bool = True):
        super().__init__(color, level)
        self.config = Config.get_instance()
        self.logger = Logger.get_instance()
        self.evaluator = BoardEvaluator(self.board_size)
        self.cpp_core = CppCore() if use_cpp else None
        self.gpu_accelerator = GPUAccelerator()
        self.device = self.gpu_accelerator.get_device()
        self.model_storage = ModelStorage()
        self.train_data_storage = TrainDataStorage()

        # 网络参数
        self.input_size = self.board_size ** 2
        self.hidden_size = self.config.get_int('AI', 'rl_hidden_size', 512)
        self.output_size = self.board_size ** 2

        # 初始化DQN网络
        self.policy_net = DQNNetwork(self.input_size, self.hidden_size, self.output_size).to(self.device)
        self.target_net = DQNNetwork(self.input_size, self.hidden_size, self.output_size).to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()

        # 训练参数
        self.gamma = 0.99  # 折扣因子
        self.epsilon = 0.1  # 探索率（专家级低探索）
        self.learning_rate = self.config.get_float('AI', 'rl_learning_rate', 1e-4)
        self.batch_size = self.config.get_int('AI', 'rl_batch_size', 64)
        self.target_update = self.config.get_int('AI', 'rl_target_update', 100)  # 目标网络更新频率
        self.memory = deque(maxlen=self.config.get_int('AI', 'rl_memory_size', 100000))  # 经验回放池

        # 优化器与损失函数
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=self.learning_rate)
        self.criterion = nn.MSELoss()
        self.scaler = torch.cuda.amp.GradScaler() if self.gpu_accelerator.use_gpu else None

        # 训练状态
        self.train_step = 0
        self.self_play_games = 0
        self.best_win_rate = 0.0
        self.running = True

        # 加载预训练模型
        self.load_best_model()

    def _preprocess_board(self, board: List[List[int]]) -> torch.Tensor:
        """预处理棋盘：转换为网络输入"""
        board_np = np.array(board, dtype=np.float32)
        board_np[board_np == self.color] = 1.0
        board_np[board_np == self.opponent_color] = -1.0
        board_np[board_np == PIECE_COLORS['EMPTY']] = 0.0
        return torch.tensor(board_np.flatten(), dtype=torch.float32).unsqueeze(0).to(self.device)

    def _get_action(self, board: List[List[int]], training: bool = False) -> Tuple[int, int]:
        """获取落子动作（探索/利用）"""
        state = self._preprocess_board(board)
        # 探索：随机落子
        if training and random.random() < self.epsilon:
            empty_pos = self._get_empty_positions(board)
            return random.choice(empty_pos)
        # 利用：网络预测
        with torch.no_grad():
            q_values = self.policy_net(state)
            q_values = q_values.cpu().numpy()[0]
            # 过滤已落子位置
            board_flat = np.array(board).flatten()
            q_values[board_flat != PIECE_COLORS['EMPTY']] = -float('inf')
            best_idx = np.argmax(q_values)
            return self._idx_to_move(best_idx)

    def _idx_to_move(self, idx: int) -> Tuple[int, int]:
        """索引→落子坐标"""
        x = idx // self.board_size
        y = idx % self.board_size
        return (x, y)

    def _move_to_idx(self, move: Tuple[int, int]) -> int:
        """落子坐标→索引"""
        return move[0] * self.board_size + move[1]

    def _get_reward(self, board: List[List[int]], done: bool) -> float:
        """计算奖励函数"""
        if not done:
            return 0.0
        ai_win, _ = self._is_win(board, self.color)
        if ai_win:
            return 10.0  # 获胜奖励
        opponent_win, _ = self._is_win(board, self.opponent_color)
        if opponent_win:
            return -10.0  # 失败惩罚
        return 0.5  # 平局奖励

    def store_experience(self, state: List[List[int]], action: Tuple[int, int], reward: float, next_state: List[List[int]], done: bool):
        """存储经验到回放池"""
        state_tensor = self._preprocess_board(state)
        next_state_tensor = self._preprocess_board(next_state)
        action_idx = self._move_to_idx(action)
        self.memory.append((state_tensor, action_idx, reward, next_state_tensor, done))

    def train_batch(self) -> Optional[float]:
        """批量训练网络（GPU加速+混合精度）"""
        if len(self.memory) < self.batch_size:
            return None

        # 采样批次
        batch = random.sample(self.memory, self.batch_size)
        state_batch = torch.cat([exp[0] for exp in batch])
        action_batch = torch.tensor([exp[1] for exp in batch], dtype=torch.long).to(self.device)
        reward_batch = torch.tensor([exp[2] for exp in batch], dtype=torch.float32).to(self.device)
        next_state_batch = torch.cat([exp[3] for exp in batch])
        done_batch = torch.tensor([exp[4] for exp in batch], dtype=torch.float32).to(self.device)

        # 混合精度训练
        if self.gpu_accelerator.use_gpu and self.scaler:
            with torch.cuda.amp.autocast():
                q_current = self.policy_net(state_batch).gather(1, action_batch.unsqueeze(1)).squeeze(1)
                with torch.no_grad():
                    q_next = self.target_net(next_state_batch).max(1)[0]
                    q_target = reward_batch + self.gamma * q_next * (1 - done_batch)
                loss = self.criterion(q_current, q_target)
            # 反向传播
            self.optimizer.zero_grad()
            self.scaler.scale(loss).backward()
            self.scaler.step(self.optimizer)
            self.scaler.update()
        else:
            q_current = self.policy_net(state_batch).gather(1, action_batch.unsqueeze(1)).squeeze(1)
            with torch.no_grad():
                q_next = self.target_net(next_state_batch).max(1)[0]
                q_target = reward_batch + self.gamma * q_next * (1 - done_batch)
            loss = self.criterion(q_current, q_target)
            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()

        # 更新目标网络
        self.train_step += 1
        if self.train_step % self.target_update == 0:
            self.target_net.load_state_dict(self.policy_net.state_dict())
            self.logger.info(f"目标网络更新完成，训练步数：{self.train_step}")

        return loss.item()

    def self_play(self, num_games: int = 100):
        """自我对弈训练"""
        self.policy_net.train()
        total_loss = 0.0
        total_wins = 0

        for game_idx in range(num_games):
            board = [[PIECE_COLORS['EMPTY'] for _ in range(self.board_size)] for _ in range(self.board_size)]
            current_color = self.color
            done = False
            move_count = 0
            game_memory = []

            while not done and move_count < self.board_size ** 2:
                # 获取落子动作
                if current_color == self.color:
                    action = self._get_action(board, training=True)
                else:
                    # 对手：镜像AI
                    opponent_ai = RLAI(self.opponent_color, self.level, use_cpp=False)
                    opponent_ai.policy_net.load_state_dict(self.policy_net.state_dict())
                    action = opponent_ai._get_action(board, training=True)

                # 执行落子
                x, y = action
                board[x][y] = current_color
                move_count += 1

                # 检查游戏结束
                ai_win, _ = self._is_win(board, self.color)
                opponent_win, _ = self._is_win(board, self.opponent_color)
                done = ai_win or opponent_win or (move_count == self.board_size ** 2)

                # 计算奖励并存储经验
                reward = self._get_reward(board, done)
                if current_color == self.color:
                    next_board = [row.copy() for row in board]
                    game_memory.append((board, action, reward, next_board, done))
                    # 批量训练
                    loss = self.train_batch()
                    if loss is not None:
                        total_loss += loss

                # 切换玩家
                current_color = self.opponent_color if current_color == self.color else self.color

            # 统计胜负
            if ai_win:
                total_wins += 1
            self.self_play_games += 1

            # 进度日志
            if (game_idx + 1) % 10 == 0:
                avg_loss = total_loss / 10 if game_idx > 0 else 0.0
                win_rate = total_wins / (game_idx + 1)
                self.logger.info(f"自我对弈进度：{game_idx+1}/{num_games}，平均损失：{avg_loss:.4f}，胜率：{win_rate:.2%}")
                total_loss = 0.0

        # 保存最优模型
        final_win_rate = total_wins / num_games
        if final_win_rate > self.best_win_rate:
            self.best_win_rate = final_win_rate
            self.save_model(f"rl_best_model_winrate_{final_win_rate:.2%}.pth")
            # 保存训练数据
            self.train_data_storage.save_self_play_data([
                {'board': DataUtils.board_to_str(exp[0]), 'move': exp[1], 'score': exp[2], 'result': 'win' if ai_win else 'lose', 'timestamp': time.time()}
                for exp in game_memory
            ])

        self.logger.info(f"自我对弈完成：{num_games}局，总胜率：{final_win_rate:.2%}")

    def move(self, board: List[List[int]], thinking_callback: Optional[Callable[[Dict], None]] = None) -> Tuple[int, int]:
        """AI落子（DQN+MCTS优化）"""
        self.thinking_callback = thinking_callback

        # 思维可视化数据
        thinking_data = {
            'scores': np.zeros((self.board_size, self.board_size)),
            'best_move': None,
            'considering_moves': [],
            'depth': 6 if self.level == AI_LEVELS['EXPERT'] else 4,
            'iteration': 1000,
            'value_estimate': 0.0
        }
        self._notify_thinking(thinking_data)

        # 检查必胜落子（C++快速判断）
        if self.cpp_core:
            winning_move = self.cpp_core.find_winning_move(board, self.color, self.board_size)
            if winning_move:
                thinking_data['best_move'] = winning_move
                self._notify_thinking(thinking_data)
                return winning_move

        # DQN预测落子
        self.policy_net.eval()
        init_move = self._get_action(board, training=False)

        # C++ MCTS优化落子
        if self.cpp_core:
            mcts_depth = 6 if self.level == AI_LEVELS['EXPERT'] else 4
            best_move = self.cpp_core.mcts_optimize(
                board=board,
                init_move=init_move,
                color=self.color,
                depth=mcts_depth,
                iterations=1000
            )
        else:
            best_move = init_move

        # 思维可视化：更新评分热力图
        empty_pos = self._get_empty_positions(board)[:10]
        for (x, y) in empty_pos:
            state = self._preprocess_board(board)
            with torch.no_grad():
                q_values = self.policy_net(state).cpu().numpy()[0]
                idx = self._move_to_idx((x, y))
                thinking_data['scores'][x][y] = q_values[idx] * 20
        thinking_data['best_move'] = best_move
        thinking_data['considering_moves'] = empty_pos[:5]
        thinking_data['value_estimate'] = self._evaluate(board, self.color)
        self._notify_thinking(thinking_data)

        return best_move

    def save_model(self, filename: str):
        """保存模型（带版本控制）"""
        model_path = self.model_storage.save_model_with_version(
            model_data={
                'policy_net_state_dict': self.policy_net.state_dict(),
                'target_net_state_dict': self.target_net.state_dict(),
                'optimizer_state_dict': self.optimizer.state_dict(),
                'train_step': self.train_step,
                'self_play_games': self.self_play_games,
                'best_win_rate': self.best_win_rate
            },
            model_name=filename.split('.')[0],
            metadata={
                'model_type': 'rl_dqn',
                'win_rate': self.best_win_rate,
                'train_data_count': len(self.memory),
                'train_params': {
                    'gamma': self.gamma,
                    'epsilon': self.epsilon,
                    'learning_rate': self.learning_rate
                }
            }
        )
        self.logger.info(f"模型保存成功：{model_path[0]}")

    def load_best_model(self):
        """加载最优模型"""
        best_model_path = self.model_storage.find_best_model('rl')
        if best_model_path:
            checkpoint = torch.load(best_model_path, map_location=self.device)
            self.policy_net.load_state_dict(checkpoint['policy_net_state_dict'])
            self.target_net.load_state_dict(checkpoint['target_net_state_dict'])
            self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            self.train_step = checkpoint['train_step']
            self.self_play_games = checkpoint['self_play_games']
            self.best_win_rate = checkpoint['best_win_rate']
            self.logger.info(f"加载最优RL模型成功：{best_model_path}，胜率：{self.best_win_rate:.2%}")

    def stop_training(self):
        """停止训练"""
        self.running = False
import torch
import torch.nn as nn
import numpy as np
from typing import List, Tuple, Dict, Optional, Callable
from Common.constants import AI_LEVELS, PIECE_COLORS
from Common.config import Config
from Common.logger import Logger
from AI.base_ai import BaseAI
from Storage.model_storage import ModelStorage
from Compute.gpu_accelerator import GPUAccelerator

class NNNetwork(nn.Module):
    """神经网络模型（棋盘→落子概率）"""
    def __init__(self, input_size: int = 225, hidden_size: int = 1024, output_size: int = 225):
        super().__init__()
        self.input_size = input_size
        self.output_size = output_size
        # 网络结构：输入→卷积→全连接→输出
        self.conv_layers = nn.Sequential(
            nn.Conv2d(2, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv2d(128, 256, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Flatten()
        )
        # 计算卷积层输出维度
        conv_out_size = self.conv_layers(torch.zeros(1, 2, 15, 15)).shape[1]
        self.fc_layers = nn.Sequential(
            nn.Linear(conv_out_size, hidden_size),
            nn.ReLU(),
            nn.Dropout(0.4),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Dropout(0.4),
            nn.Linear(hidden_size, output_size),
            nn.Softmax(dim=-1)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """前向传播：x shape=(batch, 2, 15, 15)"""
        conv_out = self.conv_layers(x)
        return self.fc_layers(conv_out)

class NNAI(BaseAI):
    """神经网络AI（PyTorch实现）"""
    def __init__(self, color: int, level: str = AI_LEVELS['HARD'], model_path: Optional[str] = None):
        super().__init__(color, level)
        self.logger = Logger.get_instance()
        self.gpu_accelerator = GPUAccelerator()
        self.device = self.gpu_accelerator.get_device()
        self.model_storage = ModelStorage()
        # 初始化模型
        self.model = NNNetwork(input_size=self.board_size**2, output_size=self.board_size**2).to(self.device)
        self.model.eval()
        # 加载预训练模型
        if model_path:
            self.load_model(model_path)
        else:
            self.load_best_model()

    def _preprocess_board(self, board: List[List[int]]) -> torch.Tensor:
        """预处理棋盘：转换为模型输入（batch, 2, 15, 15）"""
        # 己方为1，对手为0（通道1）；对手为1，己方为0（通道2）
        board_np = np.array(board, dtype=np.float32)
        own_channel = (board_np == self.color).astype(np.float32)
        opp_channel = (board_np == self.opponent_color).astype(np.float32)
        input_tensor = torch.tensor(np.stack([own_channel, opp_channel], axis=0), dtype=torch.float32).unsqueeze(0)
        return input_tensor.to(self.device)

    def _idx_to_move(self, idx: int) -> Tuple[int, int]:
        """索引→落子坐标"""
        x = idx // self.board_size
        y = idx % self.board_size
        return (x, y)

    def load_model(self, model_path: str):
        """加载模型"""
        checkpoint = torch.load(model_path, map_location=self.device)
        if 'model_state_dict' in checkpoint:
            self.model.load_state_dict(checkpoint['model_state_dict'])
        else:
            self.model.load_state_dict(checkpoint)
        self.model.eval()
        self.logger.info(f"加载神经网络模型成功：{model_path}")

    def load_best_model(self):
        """加载最优模型"""
        best_model_path = self.model_storage.find_best_model('nn')
        if best_model_path:
            self.load_model(best_model_path)
        else:
            self.logger.warning("未找到预训练模型，使用随机初始化模型")

    def move(self, board: List[List[int]], thinking_callback: Optional[Callable[[Dict], None]] = None) -> Tuple[int, int]:
        """AI落子（神经网络预测）"""
        self.thinking_callback = thinking_callback
        input_tensor = self._preprocess_board(board)

        # 思维可视化：初始化数据
        thinking_data = {
            'scores': np.zeros((self.board_size, self.board_size)),
            'best_move': (self.board_size//2, self.board_size//2),
            'considering_moves': [],
            'depth': 1,
            'iteration': 1
        }
        self._notify_thinking(thinking_data)

        # 模型预测
        with torch.no_grad():
            output = self.model(input_tensor)
            prob = output.cpu().numpy()[0]  # 落子概率分布

        # 过滤已落子位置
        board_flat = np.array(board).flatten()
        prob[board_flat != PIECE_COLORS['EMPTY']] = 0.0
        # 选择概率最高的落子
        best_idx = np.argmax(prob)
        best_move = self._idx_to_move(best_idx)

        # 思维可视化：更新概率热力图
        for x in range(self.board_size):
            for y in range(self.board_size):
                idx = self._move_to_idx((x, y))
                thinking_data['scores'][x][y] = prob[idx] * 100
        thinking_data['best_move'] = best_move
        thinking_data['considering_moves'] = [self._idx_to_move(np.argsort(prob)[-i-1]) for i in range(5)]
        self._notify_thinking(thinking_data)

        self.logger.info(f"神经网络AI落子：{best_move}，预测概率：{prob[best_idx]:.2%}")
        return best_move

    def _move_to_idx(self, move: Tuple[int, int]) -> int:
        """落子坐标→索引"""
        return move[0] * self.board_size + move[1]
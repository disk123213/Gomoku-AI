import pygame
import numpy as np
from typing import List, Tuple, Dict, Optional
from Common.constants import PIECE_COLORS, COLORS
from Common.config import Config
from Common.logger import Logger
from Game.game_core import GameCore
from UI.piece import Piece

class Board:
    """棋盘组件：负责落子、动画、获胜线绘制，兼容GameCore/CppCore"""
    def __init__(self, x: int, y: int, size: int = 15, cell_size: int = 40):
        self.x = x  # 棋盘左上角x坐标
        self.y = y  # 棋盘左上角y坐标
        self.size = size  # 棋盘尺寸（15×15）
        self.cell_size = cell_size  # 单元格大小
        self.config = Config.get_instance()
        self.logger = Logger.get_instance()
        self.game_core = GameCore()  # 对接游戏核心
        self.pieces: Dict[Tuple[int, int], Piece] = {}  # 已落棋子：(x,y)→Piece实例
        self.win_line: List[Tuple[int, int]] = []  # 获胜线坐标
        self.animating = False  # 落子动画状态
        self.animation_piece: Optional[Piece] = None  # 动画中的棋子
        self.animation_progress = 0  # 动画进度（0-100）
        self.animation_speed = 5  # 动画速度

    def convert_board_to_screen(self, board_x: int, board_y: int) -> Tuple[int, int]:
        """棋盘坐标→屏幕坐标（居中对齐）"""
        screen_x = self.x + board_y * self.cell_size + self.cell_size // 2
        screen_y = self.y + board_x * self.cell_size + self.cell_size // 2
        return (screen_x, screen_y)

    def convert_screen_to_board(self, screen_x: int, screen_y: int) -> Tuple[int, int]:
        """屏幕坐标→棋盘坐标（容错处理）"""
        board_x = round((screen_y - self.y - self.cell_size // 2) / self.cell_size)
        board_y = round((screen_x - self.x - self.cell_size // 2) / self.cell_size)
        # 边界校验
        board_x = max(0, min(self.size - 1, board_x))
        board_y = max(0, min(self.size - 1, board_y))
        return (board_x, board_y)

    def place_piece(self, board_x: int, board_y: int, is_ai: bool = False) -> str:
        """落子（对接GameCore，带动画）"""
        # 验证落子合法性（调用GameCore）
        result = self.game_core.place_piece(board_x, board_y, is_ai)
        if result != 'success' and result != 'game_end':
            return result
        
        # 创建棋子实例（带3D效果）
        color = self.game_core.current_player
        screen_x, screen_y = self.convert_board_to_screen(board_x, board_y)
        self.animation_piece = Piece(
            x=screen_x, 
            y=self.y - 50,  # 动画起始位置（上方）
            color=color,
            size=self.cell_size - 6,
            has_3d=True
        )
        self.animating = True
        self.animation_progress = 0
        self.pieces[(board_x, board_y)] = self.animation_piece
        
        # 检查游戏结束，记录获胜线
        if result == 'game_end' and self.game_core.game_result:
            self.win_line = self.game_core.game_result.get('win_line', [])
        
        return result

    def update_animation(self):
        """更新落子动画"""
        if not self.animating or not self.animation_piece:
            return
        
        # 计算动画目标位置
        target_x, target_y = self.convert_board_to_screen(
            *next(iter(self.pieces.keys()))  # 动画棋子的棋盘坐标
        )
        # 线性插值动画
        self.animation_progress += self.animation_speed
        if self.animation_progress >= 100:
            self.animation_progress = 100
            self.animating = False
            self.animation_piece.set_position(target_x, target_y)
        else:
            # 下落动画（带轻微弹跳）
            progress = self.animation_progress / 100
            bounce = np.sin(progress * np.pi) * 10  # 弹跳偏移
            current_y = self.y - 50 + (target_y - (self.y - 50)) * progress - bounce
            self.animation_piece.set_position(target_x, current_y)

    def draw_board_lines(self, surface: pygame.Surface):
        """绘制棋盘网格线"""
        # 绘制横线和竖线
        for i in range(self.size):
            # 横线
            y = self.y + i * self.cell_size
            pygame.draw.line(
                surface, COLORS['BOARD_LINE'],
                (self.x, y), (self.x + (self.size - 1) * self.cell_size, y),
                2 if i in [3, 7, 11] else 1  # 天元和星位加粗
            )
            # 竖线
            x = self.x + i * self.cell_size
            pygame.draw.line(
                surface, COLORS['BOARD_LINE'],
                (x, self.y), (x, self.y + (self.size - 1) * self.cell_size),
                2 if i in [3, 7, 11] else 1
            )
        
        # 绘制天元和星位
        star_positions = [(3, 3), (3, 11), (7, 7), (11, 3), (11, 11)]
        for (bx, by) in star_positions:
            sx, sy = self.convert_board_to_screen(bx, by)
            pygame.draw.circle(surface, COLORS['BOARD_LINE'], (sx, sy), 4)

    def draw_pieces(self, surface: pygame.Surface):
        """绘制所有棋子（含动画）"""
        # 绘制已落棋子（排除动画中的棋子）
        for (bx, by), piece in self.pieces.items():
            if piece != self.animation_piece:
                piece.draw(surface)
        # 绘制动画中的棋子
        if self.animating and self.animation_piece:
            self.animation_piece.draw(surface)

    def draw_win_line(self, surface: pygame.Surface):
        """绘制获胜线"""
        if not self.win_line or len(self.win_line) < 5:
            return
        
        # 转换获胜线坐标为屏幕坐标
        screen_points = [self.convert_board_to_screen(bx, by) for (bx, by) in self.win_line]
        # 绘制粗线（渐变颜色）
        for i in range(len(screen_points) - 1):
            start = screen_points[i]
            end = screen_points[i + 1]
            # 绘制外层发光效果
            glow_surface = pygame.Surface((self.cell_size * 2, self.cell_size * 2), pygame.SRCALPHA)
            pygame.draw.line(glow_surface, (*COLORS['WIN_LINE'], 80), (self.cell_size, self.cell_size), 
                           (end[0] - start[0] + self.cell_size, end[1] - start[1] + self.cell_size), 8)
            surface.blit(glow_surface, (start[0] - self.cell_size, start[1] - self.cell_size))
            # 绘制内层实线
            pygame.draw.line(surface, COLORS['WIN_LINE'], start, end, 4)

    def draw(self, surface: pygame.Surface):
        """绘制完整棋盘（线条→棋子→获胜线）"""
        self.draw_board_lines(surface)
        self.draw_pieces(surface)
        self.draw_win_line(surface)
        # 更新动画
        self.update_animation()

    def reset(self):
        """重置棋盘（对接GameCore重置）"""
        self.pieces.clear()
        self.win_line = []
        self.animating = False
        self.animation_piece = None
        self.game_core.reset_game()
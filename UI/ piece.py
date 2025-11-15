import pygame
from typing import Tuple
from Common.constants import COLORS, PIECE_COLORS

class Piece:
    """棋子组件：支持下落动画、高亮状态、3D渐变效果"""
    def __init__(self, x: int, y: int, color: int, size: int = 34, has_3d: bool = True):
        self.x = x  # 屏幕中心x坐标
        self.y = y  # 屏幕中心y坐标
        self.color = color  # 棋子颜色（BLACK/WHITE）
        self.size = size  # 棋子直径
        self.has_3d = has_3d  # 是否启用3D效果
        self.highlighted = False  # 是否高亮（最佳落子/选中）
        self.highlight_alpha = 150  # 高亮透明度

    def set_position(self, x: int, y: int):
        """设置棋子位置"""
        self.x = x
        self.y = y

    def set_highlight(self, highlighted: bool):
        """设置高亮状态"""
        self.highlighted = highlighted

    def draw_3d_effect(self, surface: pygame.Surface):
        """绘制3D效果（阴影+渐变）"""
        if not self.has_3d:
            return
        
        # 绘制底部阴影
        shadow_offset = 3
        shadow_surface = pygame.Surface((self.size, self.size), pygame.SRCALPHA)
        pygame.draw.circle(shadow_surface, (*COLORS['SHADOW'], 100), 
                         (self.size//2, self.size//2), self.size//2 - 1)
        surface.blit(shadow_surface, (self.x - self.size//2 + shadow_offset, self.y - self.size//2 + shadow_offset))
        
        # 绘制3D渐变（中心亮，边缘暗）
        for r in range(self.size//2, 0, -1):
            alpha = 255 - (self.size//2 - r) * 8
            if self.color == PIECE_COLORS['BLACK']:
                shade = 20 + (self.size//2 - r) * 10
                circle_color = (shade, shade, shade, alpha)
            else:
                shade = 255 - (self.size//2 - r) * 8
                circle_color = (shade, shade, shade, alpha)
            pygame.draw.circle(surface, circle_color, (self.x, self.y), r)

    def draw_highlight(self, surface: pygame.Surface):
        """绘制高亮效果（最佳落子/选中）"""
        if not self.highlighted:
            return
        
        # 绘制外层高亮环
        highlight_surface = pygame.Surface((self.size + 10, self.size + 10), pygame.SRCALPHA)
        pygame.draw.circle(highlight_surface, (*COLORS['HIGHLIGHT'], self.highlight_alpha),
                         (self.size//2 + 5, self.size//2 + 5), self.size//2 + 3)
        pygame.draw.circle(highlight_surface, (*COLORS['BACKGROUND'], 100),
                         (self.size//2 + 5, self.size//2 + 5), self.size//2 - 1)
        surface.blit(highlight_surface, (self.x - self.size//2 - 5, self.y - self.size//2 - 5))

    def draw(self, surface: pygame.Surface):
        """绘制完整棋子（3D→本体→高亮）"""
        # 绘制3D效果
        self.draw_3d_effect(surface)
        # 绘制棋子本体
        pygame.draw.circle(surface, COLORS['BLACK'] if self.color == PIECE_COLORS['BLACK'] else COLORS['WHITE'],
                         (self.x, self.y), self.size//2)
        pygame.draw.circle(surface, COLORS['PIECE_BORDER'], (self.x, self.y), self.size//2, 1)
        # 绘制高亮效果
        self.draw_highlight(surface)
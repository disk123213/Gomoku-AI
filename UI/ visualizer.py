import pygame
import numpy as np
from typing import List, Dict, Optional
from Common.constants import COLORS, PIECE_COLORS
from Common.config import Config

class AIVisualizer:
    """AI思考可视化：热力图、博弈树、评分曲线"""
    def __init__(self, x: int, y: int, board_size: int = 15, cell_size: int = 40):
        self.x = x  # 可视化区域左上角x坐标（棋盘右侧）
        self.y = y  # 可视化区域左上角y坐标
        self.board_size = board_size
        self.cell_size = cell_size
        self.config = Config.get_instance()
        self.fonts = {
            'small': pygame.font.SysFont('Arial', 10),
            'normal': pygame.font.SysFont('Arial', 12),
            'bold': pygame.font.SysFont('Arial', 12, bold=True)
        }

        # 可视化数据（由AI思考回调更新）
        self.thinking_data = {
            'scores': np.zeros((board_size, board_size)),  # 评分热力图数据
            'best_move': None,  # 最佳落子 (x,y)
            'considering_moves': [],  # 候选落子列表
            'game_tree': {'root': {'win_rate': 0.5, 'children': []}},  # 博弈树数据
            'score_history': []  # 局势评分历史
        }

        # 动画状态
        self.animation_frame = 0
        self.animation_speed = 3

    def update_thinking_data(self, data: Dict):
        """更新AI思考数据（对接AI的thinking_callback）"""
        if 'scores' in data:
            self.thinking_data['scores'] = self._normalize_scores(data['scores'])
        if 'best_move' in data:
            self.thinking_data['best_move'] = data['best_move']
        if 'considering_moves' in data:
            self.thinking_data['considering_moves'] = data['considering_moves']
        if 'game_tree' in data:
            self.thinking_data['game_tree'] = data['game_tree']
        if 'score_history' in data:
            self.thinking_data['score_history'] = data['score_history'][:20]  # 保留最近20个评分
        self.animation_frame = (self.animation_frame + 1) % self.animation_speed

    def _normalize_scores(self, scores: np.ndarray) -> np.ndarray:
        """归一化评分到0-255（用于热力图）"""
        if scores.max() == scores.min():
            return np.zeros_like(scores)
        return (scores - scores.min()) / (scores.max() - scores.min()) * 255

    def draw_heatmap(self, surface: pygame.Surface):
        """绘制评分热力图"""
        cell_half = self.cell_size // 2
        scores = self.thinking_data['scores']
        for bx in range(self.board_size):
            for by in range(self.board_size):
                score = scores[bx][by]
                if score <= 0:
                    continue
                # 颜色映射（蓝→红）
                color_idx = int(min(score, 255))
                if color_idx < 64:
                    color = (0, color_idx*4, 255)
                elif color_idx < 128:
                    color = (0, 255, 255 - (color_idx-64)*4)
                elif color_idx < 192:
                    color = ((color_idx-128)*4, 255, 0)
                else:
                    color = (255, 255 - (color_idx-192)*4, 0)
                # 绘制半透明圆形（评分越高，半径越大）
                sx, sy = self.x + by * self.cell_size + cell_half, self.y + bx * self.cell_size + cell_half
                radius = int(cell_half * (score / 255))
                if radius > 0:
                    heat_surface = pygame.Surface((self.cell_size, self.cell_size), pygame.SRCALPHA)
                    pygame.draw.circle(heat_surface, (*color, 180), (cell_half, cell_half), radius)
                    surface.blit(heat_surface, (sx - cell_half, sy - cell_half))

    def draw_game_tree(self, surface: pygame.Surface):
        """绘制博弈树分支图"""
        tree_x = self.x + self.board_size * self.cell_size + 30
        tree_y = self.y
        node_radius = 6
        level_spacing = 35
        node_spacing = 25

        # 递归绘制节点和分支
        def draw_node(node: Dict, level: int, x_offset: int):
            # 节点颜色（胜率>0.7=绿，<0.3=红，否则黄）
            win_rate = node.get('win_rate', 0.5)
            node_color = COLORS['GREEN'] if win_rate > 0.7 else COLORS['RED'] if win_rate < 0.3 else COLORS['YELLOW']
            sx = tree_x + x_offset
            sy = tree_y + level * level_spacing
            # 绘制节点
            pygame.draw.circle(surface, node_color, (sx, sy), node_radius)
            # 绘制胜率文本
            win_text = self.fonts['small'].render(f"{win_rate:.1%}", True, COLORS['BLACK'])
            surface.blit(win_text, (sx - 10, sy + node_radius + 2))
            # 绘制子节点
            children = node.get('children', [])
            if children:
                child_count = len(children)
                total_width = (child_count - 1) * node_spacing
                start_x = x_offset - total_width / 2
                for i, child in enumerate(children):
                    child_x = start_x + i * node_spacing
                    # 绘制分支（最佳路径加粗）
                    line_width = 2 if child.get('is_best', False) else 1
                    pygame.draw.line(surface, COLORS['GRAY'], (sx, sy + node_radius),
                                   (tree_x + child_x, tree_y + (level+1)*level_spacing - node_radius), line_width)
                    draw_node(child, level + 1, child_x)

        # 绘制博弈树根节点
        draw_node(self.thinking_data['game_tree']['root'], 0, 0)
        # 绘制标题
        tree_title = self.fonts['bold'].render("博弈树搜索路径", True, COLORS['TEXT_LIGHT'])
        surface.blit(tree_title, (tree_x, tree_y - 20))

    def draw_score_curve(self, surface: pygame.Surface):
        """绘制局势评分变化曲线"""
        curve_x = self.x + self.board_size * self.cell_size + 30
        curve_y = self.y + 220
        curve_width = 200
        curve_height = 100

        # 绘制背景框
        pygame.draw.rect(surface, (*COLORS['PANEL_BG'], 200), (curve_x, curve_y, curve_width, curve_height))
        pygame.draw.rect(surface, COLORS['GRAY'], (curve_x, curve_y, curve_width, curve_height), 1)

        # 绘制曲线（至少2个点才绘制）
        score_history = self.thinking_data['score_history']
        if len(score_history) >= 2:
            # 归一化评分
            max_score = max(score_history)
            min_score = min(score_history)
            normalized = [(s - min_score) / (max_score - min_score) for s in score_history]
            # 计算点坐标
            points = []
            step = curve_width / (len(normalized) - 1)
            for i, val in enumerate(normalized):
                x = curve_x + i * step
                y = curve_y + curve_height - (val * curve_height)
                points.append((x, y))
            # 绘制曲线和点
            pygame.draw.lines(surface, COLORS['BLUE'], False, points, 2)
            for (x, y) in points:
                pygame.draw.circle(surface, COLORS['BLUE'], (x, y), 3)

        # 绘制坐标轴标签
        min_text = self.fonts['small'].render(f"{min(score_history):.1f}" if score_history else "0.0", True, COLORS['TEXT_LIGHT'])
        max_text = self.fonts['small'].render(f"{max(score_history):.1f}" if score_history else "1.0", True, COLORS['TEXT_LIGHT'])
        surface.blit(min_text, (curve_x, curve_y + curve_height - 15))
        surface.blit(max_text, (curve_x, curve_y + 5))
        # 绘制标题
        curve_title = self.fonts['bold'].render("局势评分变化", True, COLORS['TEXT_LIGHT'])
        surface.blit(curve_title, (curve_x, curve_y - 20))

    def draw_best_move(self, surface: pygame.Surface):
        """绘制最佳落子标记"""
        best_move = self.thinking_data['best_move']
        if not best_move:
            return
        bx, by = best_move
        sx = self.x + by * self.cell_size + self.cell_size // 2
        sy = self.y + bx * self.cell_size + self.cell_size // 2
        # 绘制红色闪烁边框
        alpha = 150 + 100 * np.sin(pygame.time.get_ticks() / 150)
        best_surface = pygame.Surface((self.cell_size, self.cell_size), pygame.SRCALPHA)
        pygame.draw.circle(best_surface, (*COLORS['WIN_LINE'], int(alpha)), (self.cell_size//2, self.cell_size//2), self.cell_size//2 - 2, 3)
        surface.blit(best_surface, (sx - self.cell_size//2, sy - self.cell_size//2))

    def draw(self, surface: pygame.Surface):
        """绘制所有可视化元素"""
        self.draw_heatmap(surface)
        self.draw_best_move(surface)
        self.draw_game_tree(surface)
        self.draw_score_curve(surface)
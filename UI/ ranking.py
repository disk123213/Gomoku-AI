import pygame
from typing import List, Dict
from Common.constants import COLORS
from Core.ranking_system import ELORankingSystem

class RankingPanel:
    """排行榜组件：本地/全球排名展示"""
    def __init__(self, x: int, y: int, width: int = 300, height: int = 500):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.ranking_system = ELORankingSystem()
        self.fonts = {
            'title': pygame.font.SysFont('Arial', 18, bold=True),
            'normal': pygame.font.SysFont('Arial', 14),
            'small': pygame.font.SysFont('Arial', 12),
            'rank': pygame.font.SysFont('Arial', 16, bold=True)
        }

        # 排行榜类型：local/global
        self.rank_type = 'local'
        self.rank_list: List[Dict] = []
        # 切换按钮
        self.switch_btn = pygame.Rect(x + width - 120, y + 10, 100, 30)
        # 刷新按钮
        self.refresh_btn = pygame.Rect(x + 20, y + 10, 80, 30)

    def load_ranking(self):
        """加载排行榜数据（对接ELORankingSystem）"""
        self.rank_list = self.ranking_system.get_ranking_list(
            top_n=10,
            is_global=(self.rank_type == 'global')
        )

    def switch_rank_type(self):
        """切换本地/全球排行榜"""
        self.rank_type = 'global' if self.rank_type == 'local' else 'local'
        self.load_ranking()

    def draw_header(self, surface: pygame.Surface):
        """绘制排行榜表头"""
        # 标题
        title = self.fonts['title'].render(f"{'全球排行榜' if self.rank_type == 'global' else '本地排行榜'}", True, COLORS['TEXT_LIGHT'])
        surface.blit(title, (self.x + 20, self.y - 30))
        # 切换按钮
        switch_text = self.fonts['small'].render(f"切换到{'本地' if self.rank_type == 'global' else '全球'}", True, COLORS['TEXT_DARK'])
        pygame.draw.rect(surface, COLORS['BUTTON'], self.switch_btn, border_radius=3)
        pygame.draw.rect(surface, COLORS['BUTTON_BORDER'], self.switch_btn, width=2, border_radius=3)
        surface.blit(switch_text, (self.switch_btn.x + 5, self.switch_btn.y + 7))
        # 刷新按钮
        refresh_text = self.fonts['small'].render("刷新", True, COLORS['TEXT_DARK'])
        pygame.draw.rect(surface, COLORS['BUTTON'], self.refresh_btn, border_radius=3)
        pygame.draw.rect(surface, COLORS['BUTTON_BORDER'], self.refresh_btn, width=2, border_radius=3)
        surface.blit(refresh_text, (self.refresh_btn.x + 25, self.refresh_btn.y + 7))
        # 表头列名
        headers = ['排名', '昵称', '积分', '胜率']
        x_offsets = [20, 80, 200, 250]
        for i, (header, x_off) in enumerate(zip(headers, x_offsets)):
            text = self.fonts['small'].render(header, True, COLORS['TEXT_LIGHT'])
            surface.blit(text, (self.x + x_off, self.y + 50))
        # 分隔线
        pygame.draw.line(surface, COLORS['GRAY'], (self.x + 20, self.y + 70), (self.x + self.width - 20, self.y + 70), 1)

    def draw_rank_items(self, surface: pygame.Surface):
        """绘制排行榜条目"""
        item_height = 40
        for i, item in enumerate(self.rank_list):
            y_pos = self.y + 80 + i * item_height
            # 交替背景色
            bg_color = (*COLORS['PANEL_BG'], 150) if i % 2 == 0 else (*COLORS['PANEL_BG'], 100)
            pygame.draw.rect(surface, bg_color, (self.x + 20, y_pos, self.width - 40, item_height - 5), border_radius=3)
            # 排名（前3名特殊颜色）
            rank_color = COLORS['GOLD'] if i == 0 else COLORS['SILVER'] if i == 1 else COLORS['BRONZE'] if i == 2 else COLORS['TEXT_LIGHT']
            rank_text = self.fonts['rank'].render(f"{item['rank']}", True, rank_color)
            surface.blit(rank_text, (self.x + 25, y_pos + 5))
            # 昵称
            name_text = self.fonts['normal'].render(item['name'], True, COLORS['TEXT_LIGHT'])
            surface.blit(name_text, (self.x + 80, y_pos + 5))
            # 积分
            score_text = self.fonts['normal'].render(f"{item['score']}", True, COLORS['TEXT_LIGHT'])
            surface.blit(score_text, (self.x + 200, y_pos + 5))
            # 胜率
            win_rate_text = self.fonts['normal'].render(f"{item['win_rate']:.1f}%", True, COLORS['TEXT_LIGHT'])
            surface.blit(win_rate_text, (self.x + 250, y_pos + 5))

    def handle_click(self, pos: Tuple[int, int]):
        """处理点击事件"""
        if self.switch_btn.collidepoint(pos):
            self.switch_rank_type()
        elif self.refresh_btn.collidepoint(pos):
            self.load_ranking()

    def draw(self, surface: pygame.Surface):
        """绘制完整排行榜"""
        # 绘制背景
        pygame.draw.rect(surface, (*COLORS['PANEL_BG'], 230), (self.x, self.y, self.width, self.height), border_radius=8)
        pygame.draw.rect(surface, COLORS['GRAY'], (self.x, self.y, self.width, self.height), width=2, border_radius=8)
        # 绘制表头和条目
        self.draw_header(surface)
        self.draw_rank_items(surface)
        # 首次加载数据
        if not self.rank_list:
            self.load_ranking()
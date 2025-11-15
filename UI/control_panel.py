import pygame
from typing import List, Dict, Callable
from Common.constants import GAME_MODES, AI_LEVELS, COLORS
from Common.config import Config
from Storage.model_storage import ModelStorage
from Game.game_core import GameCore

class ControlPanel:
    """控制面板：模式切换、AI配置、模型管理"""
    def __init__(self, x: int, y: int, width: int = 200, height: int = 600):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.config = Config.get_instance()
        self.game_core = GameCore()
        self.model_storage = ModelStorage()
        self.fonts = {
            'normal': pygame.font.SysFont('Arial', 14),
            'bold': pygame.font.SysFont('Arial', 16, bold=True),
            'small': pygame.font.SysFont('Arial', 12)
        }

        # 模式切换按钮
        self.mode_buttons = [
            {'name': '人机对战', 'mode': GAME_MODES['PVE'], 'rect': pygame.Rect(x+20, y+30, 160, 40)},
            {'name': '人人对战', 'mode': GAME_MODES['PVP'], 'rect': pygame.Rect(x+20, y+80, 160, 40)},
            {'name': '联机对战', 'mode': GAME_MODES['ONLINE'], 'rect': pygame.Rect(x+20, y+130, 160, 40)},
            {'name': '训练模式', 'mode': GAME_MODES['TRAIN'], 'rect': pygame.Rect(x+20, y+180, 160, 40)}
        ]
        self.selected_mode = GAME_MODES['PVE']

        # AI配置
        self.ai_levels = list(AI_LEVELS.values())
        self.selected_ai_level = AI_LEVELS['HARD']
        self.ai_level_rect = pygame.Rect(x+20, y+250, 160, 40)

        # 模型管理按钮
        self.model_buttons = [
            {'name': '导入模型', 'rect': pygame.Rect(x+20, y+320, 160, 40)},
            {'name': '导出模型', 'rect': pygame.Rect(x+20, y+370, 160, 40)},
            {'name': '开始训练', 'rect': pygame.Rect(x+20, y+420, 160, 40)},
            {'name': '重置模型', 'rect': pygame.Rect(x+20, y+470, 160, 40)}
        ]

        # 回调函数
        self.on_mode_change: Optional[Callable[[str], None]] = None
        self.on_ai_config_change: Optional[Callable[[str], None]] = None

    def draw_buttons(self, surface: pygame.Surface):
        """绘制所有按钮"""
        # 模式按钮
        for btn in self.mode_buttons:
            color = COLORS['SELECTED'] if btn['mode'] == self.selected_mode else COLORS['BUTTON']
            pygame.draw.rect(surface, color, btn['rect'], border_radius=5)
            pygame.draw.rect(surface, COLORS['BUTTON_BORDER'], btn['rect'], width=2, border_radius=5)
            text = self.fonts['normal'].render(btn['name'], True, COLORS['TEXT_DARK'])
            text_rect = text.get_rect(center=btn['rect'].center)
            surface.blit(text, text_rect)

        # AI难度选择
        pygame.draw.rect(surface, COLORS['BUTTON'], self.ai_level_rect, border_radius=5)
        pygame.draw.rect(surface, COLORS['BUTTON_BORDER'], self.ai_level_rect, width=2, border_radius=5)
        level_text = self.fonts['normal'].render(f"AI难度：{self.selected_ai_level}", True, COLORS['TEXT_DARK'])
        surface.blit(level_text, (self.ai_level_rect.x + 15, self.ai_level_rect.y + 10))

        # 模型管理按钮
        for btn in self.model_buttons:
            pygame.draw.rect(surface, COLORS['BUTTON'], btn['rect'], border_radius=5)
            pygame.draw.rect(surface, COLORS['BUTTON_BORDER'], btn['rect'], width=2, border_radius=5)
            text = self.fonts['normal'].render(btn['name'], True, COLORS['TEXT_DARK'])
            text_rect = text.get_rect(center=btn['rect'].center)
            surface.blit(text, text_rect)

    def draw_title(self, surface: pygame.Surface):
        """绘制面板标题"""
        title = self.fonts['bold'].render("控制面板", True, COLORS['TEXT_LIGHT'])
        surface.blit(title, (self.x + 20, self.y - 25))
        pygame.draw.line(surface, COLORS['GRAY'], (self.x, self.y - 10), (self.x + self.width, self.y - 10), 2)

    def handle_click(self, pos: Tuple[int, int]):
        """处理点击事件"""
        # 模式按钮点击
        for btn in self.mode_buttons:
            if btn['rect'].collidepoint(pos):
                self.selected_mode = btn['mode']
                self.game_core.set_mode(btn['mode'], user_id="default_user")
                if self.on_mode_change:
                    self.on_mode_change(btn['mode'])
                return

        # AI难度切换
        if self.ai_level_rect.collidepoint(pos):
            current_idx = self.ai_levels.index(self.selected_ai_level)
            next_idx = (current_idx + 1) % len(self.ai_levels)
            self.selected_ai_level = self.ai_levels[next_idx]
            self.game_core.ai_level = self.selected_ai_level
            if self.on_ai_config_change:
                self.on_ai_config_change(self.selected_ai_level)
            return

        # 模型管理按钮点击
        for btn in self.model_buttons:
            if btn['rect'].collidepoint(pos):
                self.handle_model_action(btn['name'])
                return

    def handle_model_action(self, action: str):
        """处理模型管理动作"""
        if action == '导入模型':
            # 简化实现：读取默认目录下的模型文件
            model_files = self.model_storage.get_all_models()
            if model_files:
                self.game_core.load_ai_model(model_files[0]['path'])
                print("导入模型成功：", model_files[0]['name'])
        elif action == '导出模型':
            self.model_storage.save_model_with_version(
                self.game_core.current_ai.policy_net.state_dict(),
                model_name="custom_model",
                metadata={'model_type': 'rl+mcts', 'win_rate': 0.85}
            )
            print("导出模型成功")
        elif action == '开始训练':
            if self.game_core.current_mode == GAME_MODES['TRAIN']:
                self.game_core.current_ai.self_play(num_games=100)
                print("开始训练...")
        elif action == '重置模型':
            self.game_core.current_ai.load_best_model()
            print("重置模型成功")

    def draw(self, surface: pygame.Surface):
        """绘制完整面板"""
        # 绘制背景
        pygame.draw.rect(surface, (*COLORS['PANEL_BG'], 230), (self.x, self.y, self.width, self.height), border_radius=8)
        pygame.draw.rect(surface, COLORS['GRAY'], (self.x, self.y, self.width, self.height), width=2, border_radius=8)
        # 绘制标题和按钮
        self.draw_title(surface)
        self.draw_buttons(surface)
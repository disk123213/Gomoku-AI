import pygame
from typing import List, Dict, Optional
from Common.constants import COLORS
from Network.live_stream import LiveStreamManager
from UI.board import Board
from UI.piece import Piece

class LiveViewer:
    """直播观看组件：弹幕、对局同步、直播间信息"""
    def __init__(self, x: int, y: int, board_size: int = 15, cell_size: int = 40):
        self.x = x
        self.y = y
        self.board_size = board_size
        self.cell_size = cell_size
        self.live_manager = LiveStreamManager()
        self.fonts = {
            'normal': pygame.font.SysFont('Arial', 14),
            'small': pygame.font.SysFont('Arial', 12),
            'bold': pygame.font.SysFont('Arial', 16, bold=True)
        }

        # 直播状态
        self.is_watching = False
        self.current_room_id = ""
        self.host_name = ""
        self.viewer_count = 0
        self.board = Board(x + 50, y + 80, board_size, cell_size)  # 直播棋盘
        # 弹幕相关
        self.danmaku_list: List[Dict] = []
        self.danmaku_input_rect = pygame.Rect(x + 50, y + 600, 400, 35)
        self.danmaku_input_text = ""
        self.send_btn = pygame.Rect(x + 460, y + 600, 80, 35)
        # 直播间信息面板
        self.info_panel_rect = pygame.Rect(x + 600, y + 80, 200, 300)

    def join_live_room(self, room_id: str, user_id: str, user_name: str):
        """加入直播间（对接LiveStreamManager）"""
        self.current_room_id = room_id
        self.is_watching = self.live_manager.join_live_room(
            room_id=room_id,
            user_id=user_id,
            user_name=user_name,
            callback=self._on_live_data_received
        )

    def _on_live_data_received(self, data: Dict):
        """直播数据回调：同步棋盘、弹幕等"""
        msg_type = data.get('type')
        if msg_type == 'game_update':
            # 同步棋盘状态
            game_data = data.get('data', {})
            if 'move' in game_data:
                move = game_data['move']
                self.board.place_piece(move['x'], move['y'], is_ai=move.get('is_ai', False))
            if 'win_line' in game_data:
                self.board.win_line = game_data['win_line']
        elif msg_type == 'chat_message':
            # 接收弹幕
            chat_data = data.get('data', {})
            self.danmaku_list.append({
                'user_name': chat_data.get('user_name', '匿名'),
                'content': chat_data.get('content', ''),
                'x': self.x + 50 + self.board_size * self.cell_size * 0.2,
                'y': self.y + 80 + len(self.danmaku_list) * 20,
                'alpha': 255
            })
            # 限制弹幕数量
            if len(self.danmaku_list) > 15:
                self.danmaku_list.pop(0)
        elif msg_type == 'join_success':
            # 初始化直播间信息
            self.host_name = data.get('host_name', '未知主播')
            self.viewer_count = data.get('viewer_count', 0)
            # 同步初始棋盘状态
            current_game = data.get('current_game', {})
            if 'board_state' in current_game:
                # 简化实现：假设board_state为字符串格式，转换为棋盘
                pass

    def send_danmaku(self, user_name: str):
        """发送弹幕（对接LiveStreamManager）"""
        if not self.is_watching or not self.danmaku_input_text.strip():
            return
        # 发送弹幕到直播服务器
        import asyncio
        asyncio.run(self.live_manager._handle_viewer_chat(
            room_id=self.current_room_id,
            user_name=user_name,
            content=self.danmaku_input_text.strip()
        ))
        # 本地显示自己的弹幕
        self.danmaku_list.append({
            'user_name': user_name,
            'content': self.danmaku_input_text.strip(),
            'x': self.x + 50 + self.board_size * self.cell_size * 0.2,
            'y': self.y + 80 + len(self.danmaku_list) * 20,
            'alpha': 255
        })
        self.danmaku_input_text = ""

    def draw_live_info(self, surface: pygame.Surface):
        """绘制直播间信息"""
        # 标题
        title = self.fonts['bold'].render(f"直播间 {self.current_room_id}", True, COLORS['TEXT_LIGHT'])
        surface.blit(title, (self.x + 50, self.y + 20))
        # 主播和观众信息
        info_text = self.fonts['small'].render(f"主播：{self.host_name} | 观众：{self.viewer_count}人", True, COLORS['TEXT_LIGHT'])
        surface.blit(info_text, (self.x + 50, self.y + 50))
        # 信息面板背景
        pygame.draw.rect(surface, (*COLORS['PANEL_BG'], 230), self.info_panel_rect, border_radius=8)
        pygame.draw.rect(surface, COLORS['GRAY'], self.info_panel_rect, width=2, border_radius=8)
        # 面板标题
        panel_title = self.fonts['bold'].render("直播信息", True, COLORS['TEXT_LIGHT'])
        surface.blit(panel_title, (self.info_panel_rect.x + 20, self.info_panel_rect.y + 15))
        # 面板内容
        content_lines = [
            f"房间ID：{self.current_room_id}",
            f"主播：{self.host_name}",
            f"观众数：{self.viewer_count}",
            "",
            "操作说明：",
            "• 点击棋盘同步观看",
            "• 输入弹幕后按发送",
            "• 支持实时互动"
        ]
        for i, line in enumerate(content_lines):
            text = self.fonts['small'].render(line, True, COLORS['TEXT_LIGHT'])
            surface.blit(text, (self.info_panel_rect.x + 20, self.info_panel_rect.y + 40 + i * 20))

    def draw_danmaku(self, surface: pygame.Surface):
        """绘制弹幕"""
        # 更新弹幕位置和透明度
        for danmaku in self.danmaku_list:
            danmaku['x'] -= 1  # 弹幕左移
            danmaku['alpha'] -= 1  # 透明度降低
        # 过滤消失的弹幕
        self.danmaku_list = [d for d in self.danmaku_list if d['alpha'] > 0]
        # 绘制弹幕
        for danmaku in self.danmaku_list:
            # 随机弹幕颜色
            color = (
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255),
                danmaku['alpha']
            )
            text = self.fonts['small'].render(f"{danmaku['user_name']}: {danmaku['content']}", True, color)
            surface.blit(text, (danmaku['x'], danmaku['y']))

    def draw_danmaku_input(self, surface: pygame.Surface):
        """绘制弹幕输入框"""
        # 输入框
        pygame.draw.rect(surface, COLORS['INPUT_BG'], self.danmaku_input_rect, border_radius=3)
        pygame.draw.rect(surface, COLORS['BUTTON_BORDER'], self.danmaku_input_rect, width=2, border_radius=3)
        input_text = self.fonts['normal'].render(self.danmaku_input_text, True, COLORS['TEXT_DARK'])
        surface.blit(input_text, (self.danmaku_input_rect.x + 10, self.danmaku_input_rect.y + 5))
        # 发送按钮
        send_text = self.fonts['small'].render("发送", True, COLORS['TEXT_DARK'])
        pygame.draw.rect(surface, COLORS['BUTTON'], self.send_btn, border_radius=3)
        pygame.draw.rect(surface, COLORS['BUTTON_BORDER'], self.send_btn, width=2, border_radius=3)
        surface.blit(send_text, (self.send_btn.x + 25, self.send_btn.y + 7))

    def handle_click(self, pos: Tuple[int, int], user_name: str):
        """处理点击事件"""
        if self.send_btn.collidepoint(pos):
            self.send_danmaku(user_name)
        elif self.danmaku_input_rect.collidepoint(pos):
            # 激活输入框（简化实现）
            pass

    def handle_text_input(self, text: str):
        """处理文本输入（弹幕）"""
        self.danmaku_input_text += text

    def handle_backspace(self):
        """处理退格键（弹幕输入）"""
        self.danmaku_input_text = self.danmaku_input_text[:-1]

    def draw(self, surface: pygame.Surface):
        """绘制完整直播组件"""
        if not self.is_watching:
            # 未观看直播时显示提示
            tip_text = self.fonts['bold'].render("请输入直播间ID加入直播", True, COLORS['TEXT_LIGHT'])
            surface.blit(tip_text, (self.x + 200, self.y + 300))
            return
        
        # 绘制直播间信息、棋盘、弹幕、输入框
        self.draw_live_info(surface)
        self.board.draw(surface)
        self.draw_danmaku(surface)
        self.draw_danmaku_input(surface)
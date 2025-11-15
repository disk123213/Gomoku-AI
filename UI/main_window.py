import pygame
import sys
import os
from typing import Optional, Dict, List, Tuple, Callable
from Common.config import Config
from Common.constants import COLORS, GAME_MODES, AI_LEVELS, TRAIN_STATUSES, MSG_TYPES
from Common.logger import Logger
from Common.error_handler import UIError, ErrorHandler
from Common.event import EventManager, Event
from Common.data_utils import DataUtils
from Common.security import SecurityUtils
from UI.board import Board
from UI.piece import Piece
from UI.control_panel import ControlPanel
from UI.visualizer import AdvancedAIVisualizer
from UI.menu import MainMenu, GameMenu
from UI.ranking import RankingPanel
from UI.live_viewer import LiveViewer
from UI.resources import ResourceManager
from Game.game_core import GameCore
from Game.game_mode import GameModeManager
from Storage.user_storage import UserStorage
from Storage.game_record_storage import GameRecordStorage
from Storage.model_storage import ModelStorage

class MainWindow:
    """程序主窗口（Win11深度适配：高DPI、系统字体、窗口缩放、流畅动画）"""
    def __init__(self):
        # 核心依赖初始化
        self.config = Config.get_instance()
        self.logger = Logger.get_instance()
        self.event_manager = EventManager()
        self.resource_manager = ResourceManager()  # 资源管理器
        self.user_storage = UserStorage()
        self.game_record_storage = GameRecordStorage()
        self.model_storage = ModelStorage()

        # 窗口基础配置（Win11优化）
        self.base_width = self.config.get_int('WINDOW', 'DEFAULT_WIDTH')
        self.base_height = self.config.get_int('WINDOW', 'DEFAULT_HEIGHT')
        self.min_width = self.config.get_int('WINDOW', 'MIN_WIDTH')
        self.min_height = self.config.get_int('WINDOW', 'MIN_HEIGHT')
        self.fps = self.config.get_int('WINDOW', 'FPS')
        self.window_title = self.config.get('WINDOW', 'TITLE')

        # Pygame初始化（Win11兼容配置）
        pygame.init()
        pygame.display.set_caption(self.window_title)
        # 高DPI适配 + 硬件加速 + 双缓冲
        self.screen = pygame.display.set_mode(
            (self.base_width, self.base_height),
            pygame.RESIZABLE | pygame.DOUBLEBUF | pygame.HWSURFACE | pygame.SCALED
        )
        self.clock = pygame.time.Clock()
        self.scale_factor = 1.0  # 窗口缩放因子
        self._adapt_high_dpi()  # Win11高DPI适配

        # 组件布局参数（基于缩放因子动态调整）
        self.panel_width = int(320 * self.scale_factor)
        self.sidebar_width = int(280 * self.scale_factor)
        self.board_margin = int(20 * self.scale_factor)
        self.component_spacing = int(10 * self.scale_factor)

        # 核心组件初始化
        self._init_components()

        # 游戏核心关联
        self.game_core = GameCore(self.event_manager)
        self.mode_manager = GameModeManager(self.game_core, self.event_manager)

        # 状态变量
        self.running = True
        self.current_mode = None
        self.current_user: Optional[Dict] = None
        self.show_main_menu = True  # 主菜单显示状态
        self.show_control_panel = True  # 控制面板显示状态
        self.show_ranking = False  # 排行榜显示状态
        self.show_live_viewer = False  # 直播观看显示状态
        self.show_ai_visualizer = self.config.get_bool('AI', 'show_thinking_visual', True)
        self.is_fullscreen = False  # 全屏状态
        self.is_ai_thinking = False  # AI思考中状态
        self.game_active = False  # 游戏激活状态

        # 加载资源（Win11系统字体优先）
        self._load_resources()

        # 注册全局事件监听
        self._register_events()

        # 初始化完成日志
        self.logger.info("主窗口初始化完成（Win11适配版）")

    def _adapt_high_dpi(self):
        """Win11高DPI适配（自动调整缩放因子）"""
        try:
            # Windows系统高DPI感知
            if os.name == 'nt':
                import ctypes
                # 设置进程DPI感知（Per-Monitor V2）
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
                # 获取当前DPI缩放比例
                dpi_x = ctypes.windll.user32.GetDpiForWindow(pygame.display.get_wm_info()['window'])
                self.scale_factor = dpi_x / 96.0  # 96为标准DPI
                self.logger.info(f"Win11高DPI适配：DPI={dpi_x}，缩放因子={self.scale_factor:.2f}")
            else:
                self.scale_factor = 1.0
        except Exception as e:
            self.logger.warning(f"高DPI适配失败：{str(e)}，使用默认缩放因子1.0")
            self.scale_factor = 1.0

    def _init_components(self):
        """初始化所有UI组件（基于缩放因子布局）"""
        # 1. 主菜单（居中显示）
        menu_width = int(440 * self.scale_factor)
        menu_height = int(360 * self.scale_factor)
        self.main_menu = MainMenu(
            x=(self.base_width - menu_width) // 2,
            y=(self.base_height - menu_height) // 2,
            width=menu_width,
            height=menu_height,
            event_manager=self.event_manager,
            scale_factor=self.scale_factor,
            on_login=self._on_login,
            on_register=self._on_register,
            on_guest_login=self._on_guest_login,
            on_exit=self._on_exit
        )

        # 2. 游戏菜单（右上角）
        game_menu_width = int(150 * self.scale_factor)
        game_menu_height = int(220 * self.scale_factor)
        self.game_menu = GameMenu(
            x=self.base_width - game_menu_width - self.board_margin,
            y=self.board_margin,
            width=game_menu_width,
            height=game_menu_height,
            event_manager=self.event_manager,
            scale_factor=self.scale_factor,
            on_new_game=self._on_new_game,
            on_change_mode=self._on_change_mode_menu,
            on_settings=self._on_settings,
            on_back_menu=self._on_back_menu,
            on_fullscreen=self._on_toggle_fullscreen
        )

        # 3. 控制面板（左侧）
        self.control_panel = ControlPanel(
            x=self.board_margin,
            y=self.board_margin,
            width=self.panel_width,
            height=self.base_height - 2 * self.board_margin,
            event_manager=self.event_manager,
            scale_factor=self.scale_factor,
            on_mode_change=self._on_mode_change,
            on_ai_level_change=self._on_ai_level_change,
            on_ai_first_toggle=self._on_ai_first_toggle,
            on_start_game=self._on_start_game,
            on_stop_game=self._on_stop_game,
            on_save_model=self._on_save_model,
            on_load_model=self._on_load_model,
            on_train_model=self._on_train_model,
            on_analyze_board=self._on_analyze_board,
            on_toggle_ranking=self._on_toggle_ranking,
            on_toggle_live=self._on_toggle_live,
            on_join_live=self._on_join_live
        )

        # 4. 棋盘组件（中间）
        self.board_size = self.config.get_int('GAME', 'BOARD_SIZE')
        self.cell_size = int(self.config.get_int('GAME', 'CELL_SIZE') * self.scale_factor)
        self.board_x = self.panel_width + 2 * self.board_margin
        self.board_y = self.board_margin
        self.board = Board(
            x=self.board_x,
            y=self.board_y,
            size=self.board_size,
            cell_size=self.cell_size,
            scale_factor=self.scale_factor,
            event_manager=self.event_manager,
            on_piece_place=self._on_piece_place
        )

        # 5. 棋子组件（关联棋盘）
        self.piece = Piece(
            cell_size=self.cell_size,
            scale_factor=self.scale_factor
        )

        # 6. AI思考可视化（叠加棋盘）
        self.ai_visualizer = AdvancedAIVisualizer(
            x=self.board_x,
            y=self.board_y,
            size=self.board_size,
            cell_size=self.cell_size,
            scale_factor=self.scale_factor
        )

        # 7. 排行榜面板（右侧）
        self.ranking_panel = RankingPanel(
            x=self.base_width - self.sidebar_width - self.board_margin,
            y=self.board_margin,
            width=self.sidebar_width,
            height=self.base_height - 2 * self.board_margin,
            scale_factor=self.scale_factor,
            event_manager=self.event_manager
        )

        # 8. 直播观看组件（右侧，与排行榜切换）
        self.live_viewer = LiveViewer(
            x=self.base_width - self.sidebar_width - self.board_margin,
            y=self.board_margin,
            width=self.sidebar_width,
            height=self.base_height - 2 * self.board_margin,
            scale_factor=self.scale_factor,
            event_manager=self.event_manager
        )

    def _load_resources(self):
        """加载资源（Win11系统字体 + 本地资源）"""
        # 1. 字体加载（优先使用Win11系统字体）
        self.fonts = self.resource_manager.load_fonts([
            ('title', 28, True),
            ('sub_title', 22, True),
            ('normal', 18, False),
            ('small', 14, False),
            ('tiny', 12, False)
        ])

        # 2. 图标资源（本地+默认绘制）
        self.icons = self.resource_manager.load_icons([
            'black_piece', 'white_piece', 'ai_icon', 'user_icon',
            'rank_icon', 'live_icon', 'settings_icon', 'train_icon',
            'save_icon', 'load_icon', 'analyze_icon'
        ])

        # 3. 背景图（Win11适配分辨率）
        self.background = self.resource_manager.load_background(
            width=self.base_width,
            height=self.base_height
        )

        # 4. 音效资源（可选，默认关闭）
        self.sounds = self.resource_manager.load_sounds([
            'place_piece', 'win', 'lose', 'draw', 'button_click'
        ])

    def _register_events(self):
        """注册全局事件监听（事件驱动解耦）"""
        # 游戏核心事件
        self.event_manager.register('game_start', self._on_game_start_event)
        self.event_manager.register('game_end', self._on_game_end_event)
        self.event_manager.register('move_made', self._on_move_made_event)
        self.event_manager.register('ai_thinking_start', self._on_ai_thinking_start)
        self.event_manager.register('ai_thinking_end', self._on_ai_thinking_end)
        self.event_manager.register('model_saved', self._on_model_saved_event)
        self.event_manager.register('train_progress', self._on_train_progress_event)
        self.event_manager.register('train_complete', self._on_train_complete_event)

        # 网络/直播事件
        self.event_manager.register('online_connected', self._on_online_connected)
        self.event_manager.register('online_disconnected', self._on_online_disconnected)
        self.event_manager.register('live_room_created', self._on_live_room_created)
        self.event_manager.register('live_room_joined', self._on_live_room_joined)
        self.event_manager.register('live_message', self._on_live_message)

        # 错误事件
        self.event_manager.register('error_occurred', self._on_error_occurred)

    # ------------------------------ 窗口生命周期管理 ------------------------------
    def run(self):
        """主窗口运行循环（Win11流畅度优化）"""
        while self.running:
            # 事件处理（优先响应）
            self._handle_events()

            # 绘制界面（双缓冲优化）
            self._draw_interface()

            # 控制帧率（Win11下稳定60FPS）
            self.clock.tick(self.fps)

        # 退出清理
        self._cleanup()

    def _handle_events(self):
        """处理所有Pygame事件（Win11交互适配）"""
        for event in pygame.event.get():
            # 退出事件
            if event.type == pygame.QUIT:
                self.running = False

            # 窗口缩放事件（动态调整组件布局）
            elif event.type == pygame.VIDEORESIZE:
                self._handle_window_resize(event.w, event.h)

            # 鼠标事件（点击+悬停）
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._handle_mouse_click(pygame.mouse.get_pos(), event.button)
            elif event.type == pygame.MOUSEMOTION:
                self._handle_mouse_hover(pygame.mouse.get_pos())

            # 键盘事件（快捷键支持）
            elif event.type == pygame.KEYDOWN:
                self._handle_keyboard(event.key, event.mod)

            # 自定义事件（通过事件管理器分发）
            elif event.type == pygame.USEREVENT:
                self.event_manager.emit(Event(event.custom_type, event.dict))

    def _draw_interface(self):
        """绘制完整界面（分层绘制，提升性能）"""
        # 1. 绘制背景（最底层）
        if self.background:
            self.screen.blit(self.background, (0, 0))
        else:
            self.screen.fill(COLORS.BOARD_BG)

        # 2. 绘制棋盘（中间层）
        if not self.show_main_menu:
            self.board.draw(self.screen)
            # 绘制AI思考可视化（叠加）
            if self.show_ai_visualizer and self.is_ai_thinking:
                self.ai_visualizer.draw(self.screen)
            # 绘制控制面板
            if self.show_control_panel:
                self.control_panel.draw(self.screen)
            # 绘制游戏菜单
            self.game_menu.draw(self.screen)
            # 绘制排行榜/直播（二选一）
            if self.show_ranking:
                self.ranking_panel.draw(self.screen)
            elif self.show_live_viewer:
                self.live_viewer.draw(self.screen)

        # 3. 绘制主菜单（顶层，覆盖其他组件）
        if self.show_main_menu:
            self.main_menu.draw(self.screen)

        # 4. 刷新显示（双缓冲切换）
        pygame.display.flip()

    def _cleanup(self):
        """退出清理（释放资源）"""
        # 停止游戏和直播
        self.game_core.stop_game()
        self.game_core.stop_live()
        # 保存配置
        self.config.save_ini()
        self.config.save_json()
        # 释放Pygame资源
        pygame.font.quit()
        pygame.mixer.quit()
        pygame.quit()
        self.logger.info("程序正常退出，资源已释放")

    # ------------------------------ 交互事件处理 ------------------------------
    def _handle_window_resize(self, new_w: int, new_h: int):
        """处理窗口缩放（组件自适应调整）"""
        # 限制最小尺寸
        self.base_width = max(new_w, self.min_width)
        self.base_height = max(new_h, self.min_height)
        # 更新屏幕尺寸
        self.screen = pygame.display.set_mode(
            (self.base_width, self.base_height),
            pygame.RESIZABLE | pygame.DOUBLEBUF | pygame.HWSURFACE | pygame.SCALED
        )
        # 重新计算布局参数
        self.panel_width = int(320 * self.scale_factor)
        self.sidebar_width = int(280 * self.scale_factor)
        self.board_margin = int(20 * self.scale_factor)
        self.cell_size = int(self.config.get_int('GAME', 'CELL_SIZE') * self.scale_factor)
        # 更新组件位置和尺寸
        self._update_component_layout()
        # 重新加载背景图
        self.background = self.resource_manager.load_background(
            width=self.base_width,
            height=self.base_height
        )
        self.logger.info(f"窗口缩放：{self.base_width}x{self.base_height}")

    def _update_component_layout(self):
        """更新所有组件布局（窗口缩放后）"""
        # 控制面板
        self.control_panel.resize(
            x=self.board_margin,
            y=self.board_margin,
            width=self.panel_width,
            height=self.base_height - 2 * self.board_margin
        )
        # 棋盘
        self.board_x = self.panel_width + 2 * self.board_margin
        self.board_y = self.board_margin
        self.board.resize(
            x=self.board_x,
            y=self.board_y,
            cell_size=self.cell_size
        )
        # AI可视化
        self.ai_visualizer.resize(
            x=self.board_x,
            y=self.board_y,
            cell_size=self.cell_size
        )
        # 排行榜/直播
        sidebar_x = self.base_width - self.sidebar_width - self.board_margin
        self.ranking_panel.resize(
            x=sidebar_x,
            y=self.board_margin,
            width=self.sidebar_width,
            height=self.base_height - 2 * self.board_margin
        )
        self.live_viewer.resize(
            x=sidebar_x,
            y=self.board_margin,
            width=self.sidebar_width,
            height=self.base_height - 2 * self.board_margin
        )
        # 游戏菜单
        game_menu_width = self.game_menu.width
        self.game_menu.move(
            x=self.base_width - game_menu_width - self.board_margin,
            y=self.board_margin
        )
        # 主菜单（居中）
        menu_width = self.main_menu.width
        menu_height = self.main_menu.height
        self.main_menu.move(
            x=(self.base_width - menu_width) // 2,
            y=(self.base_height - menu_height) // 2
        )

    def _handle_mouse_click(self, mouse_pos: Tuple[int, int], button: int):
        """处理鼠标点击事件"""
        # 主菜单显示时，仅响应主菜单
        if self.show_main_menu:
            self.main_menu.handle_click(mouse_pos, button)
            return

        # 游戏菜单响应
        if self.game_menu.is_hover(mouse_pos):
            self.game_menu.handle_click(mouse_pos, button)
            self._play_sound('button_click')
            return

        # 控制面板响应
        if self.control_panel.is_hover(mouse_pos):
            self.control_panel.handle_click(mouse_pos, button)
            self._play_sound('button_click')
            return

        # 排行榜/直播响应
        if self.show_ranking and self.ranking_panel.is_hover(mouse_pos):
            self.ranking_panel.handle_click(mouse_pos, button)
            return
        if self.show_live_viewer and self.live_viewer.is_hover(mouse_pos):
            self.live_viewer.handle_click(mouse_pos, button)
            self._play_sound('button_click')
            return

        # 棋盘响应（落子）
        if self.board.is_hover(mouse_pos) and self.game_active and not self.is_ai_thinking:
            x, y = self.board.get_board_pos(mouse_pos)
            self._on_piece_place(x, y)

    def _handle_mouse_hover(self, mouse_pos: Tuple[int, int]):
        """处理鼠标悬停事件（Win11风格高亮）"""
        # 主菜单悬停
        if self.show_main_menu:
            self.main_menu.handle_hover(mouse_pos)
            return

        # 游戏菜单悬停
        self.game_menu.handle_hover(mouse_pos)

        # 控制面板悬停
        self.control_panel.handle_hover(mouse_pos)

        # 排行榜/直播悬停
        if self.show_ranking:
            self.ranking_panel.handle_hover(mouse_pos)
        if self.show_live_viewer:
            self.live_viewer.handle_hover(mouse_pos)

        # 棋盘悬停（预览落子）
        if self.board.is_hover(mouse_pos) and self.game_active and not self.is_ai_thinking:
            x, y = self.board.get_board_pos(mouse_pos)
            self.board.set_preview_pos(x, y, self.game_core.current_player)
        else:
            self.board.clear_preview()

    def _handle_keyboard(self, key: int, mod: int):
        """处理键盘事件（快捷键支持）"""
        # 退出快捷键（ESC）
        if key == pygame.K_ESCAPE:
            if self.show_main_menu:
                self.running = False
            else:
                self._on_back_menu()

        # 全屏快捷键（F11）
        if key == pygame.K_F11:
            self._on_toggle_fullscreen()

        # 新游戏快捷键（F2）
        if key == pygame.K_F2 and not self.show_main_menu:
            self._on_new_game()

        # 开始/停止游戏（空格）
        if key == pygame.K_SPACE and not self.show_main_menu:
            if self.game_active:
                self._on_stop_game()
            else:
                self._on_start_game()

        # 直播快捷键（F9）
        if key == pygame.K_F9 and not self.show_main_menu and self.current_mode == GAME_MODES['ONLINE']:
            self._on_toggle_live()

    # ------------------------------ 核心业务回调 ------------------------------
    def _on_login(self, username: str, password: str):
        """登录回调（安全验证）"""
        try:
            # 验证验证码（如果启用）
            if self.main_menu.captcha_enabled:
                input_captcha = self.main_menu.get_captcha_input()
                if not self.main_menu.verify_captcha(input_captcha):
                    self.main_menu.show_error("验证码错误")
                    self.main_menu.refresh_captcha()
                    return

            # 安全登录（加密验证）
            user = self.user_storage.login(username, password)
            if user:
                # 生成访问令牌
                token = SecurityUtils.generate_token(user['user_id'])
                self.current_user = {**user, 'token': token}
                self.show_main_menu = False
                # 更新组件用户信息
                self.control_panel.update_user_info(self.current_user)
                self.ranking_panel.load_ranking(user['user_id'])
                self.game_core.set_train_user_id(user['user_id'])
                # 更新窗口标题
                pygame.display.set_caption(f"{self.window_title} - {user['nickname']}（登录）")
                self.logger.info(f"用户登录成功：{username}（ID：{user['user_id']}）")
                self._play_sound('button_click')
            else:
                self.main_menu.show_error("用户名或密码错误")
                self.main_menu.refresh_captcha()
        except Exception as e:
            error_msg = ErrorHandler.handle_ui_error(e)
            self.main_menu.show_error(error_msg)
            self.logger.error(f"登录失败：{str(e)}")

    def _on_register(self, username: str, password: str, nickname: str):
        """注册回调（安全加密）"""
        try:
            # 验证用户名格式
            if len(username) < 4 or len(username) > 20:
                self.main_menu.show_error("用户名长度4-20字符")
                return
            # 验证密码强度
            if len(password) < 6 or not any(c.isdigit() for c in password) or not any(c.isalpha() for c in password):
                self.main_menu.show_error("密码需6位以上，含字母和数字")
                return
            # 安全注册（密码加密存储）
            success = self.user_storage.register(username, password, nickname)
            if success:
                self.main_menu.show_message("注册成功，请登录")
                self.main_menu.switch_to_login()
                self.logger.info(f"用户注册成功：{username}")
                self._play_sound('button_click')
            else:
                self.main_menu.show_error("用户名已存在")
        except Exception as e:
            error_msg = ErrorHandler.handle_ui_error(e)
            self.main_menu.show_error(error_msg)
            self.logger.error(f"注册失败：{str(e)}")

    def _on_guest_login(self):
        """游客登录回调"""
        self.current_user = {
            'user_id': '-1',
            'username': 'guest_' + DataUtils.generate_unique_id(6),
            'nickname': '游客_' + DataUtils.generate_unique_id(4),
            'win_count': 0,
            'lose_count': 0,
            'draw_count': 0,
            'score': self.config.get_int('GAME', 'BASE_RATING'),
            'token': SecurityUtils.generate_token('-1', 86400)  # 有效期1天
        }
        self.show_main_menu = False
        self.control_panel.update_user_info(self.current_user)
        self.ranking_panel.load_ranking('-1')
        self.game_core.set_train_user_id('-1')
        pygame.display.set_caption(f"{self.window_title} - 游客模式")
        self.logger.info(f"游客登录成功：{self.current_user['username']}")
        self._play_sound('button_click')

    def _on_exit(self):
        """退出回调"""
        self.running = False

    def _on_mode_change(self, mode: str):
        """游戏模式切换回调"""
        if mode not in GAME_MODES.values():
            self.control_panel.show_error("不支持的游戏模式")
            return
        self.current_mode = mode
        # 切换模式时重置状态
        self.game_core.stop_game()
        self.board.reset()
        self.ai_visualizer.reset()
        self.game_active = False
        self.is_ai_thinking = False
        # 设置游戏模式
        self.mode_manager.set_mode(mode, self.current_user['user_id'])
        self.control_panel.update_mode_info(mode)
        # 切换直播/排行榜显示
        self.show_live_viewer = (mode == GAME_MODES['ONLINE'])
        self.show_ranking = (mode != GAME_MODES['ONLINE'])
        if self.show_ranking:
            self.ranking_panel.load_ranking(self.current_user['user_id'])
        self.logger.info(f"切换游戏模式：{mode}")

    def _on_ai_level_change(self, level: str):
        """AI难度切换回调"""
        if level not in AI_LEVELS.values():
            self.control_panel.show_error("不支持的AI难度")
            return
        self.game_core.set_ai_level(level)
        self.control_panel.update_ai_level(level)
        self.logger.info(f"切换AI难度：{level}")

    def _on_ai_first_toggle(self, ai_first: bool):
        """AI先手切换回调"""
        self.game_core.set_ai_first(ai_first)
        self.control_panel.update_ai_first(ai_first)
        self.logger.info(f"AI先手：{'开启' if ai_first else '关闭'}")

    def _on_start_game(self):
        """开始游戏回调"""
        if not self.current_mode:
            self.control_panel.show_error("请先选择游戏模式")
            return
        if not self.current_user:
            self.control_panel.show_error("请先登录或游客登录")
            return

        # 启动游戏
        self.game_core.start_game()
        self.game_active = True
        self.control_panel.update_game_status("游戏中")
        self.board.set_game_active(True)
        self.logger.info("游戏开始")
        self._play_sound('button_click')

        # AI先手时自动落子
        if self.current_mode == GAME_MODES['PVE'] and self.game_core.ai_first:
            self.game_core.ai_move(self.ai_visualizer.update_thinking_data)

    def _on_stop_game(self):
        """停止游戏回调"""
        self.game_core.stop_game()
        self.game_active = False
        self.is_ai_thinking = False
        self.ai_visualizer.reset()
        self.board.reset()
        self.board.clear_preview()
        self.control_panel.update_game_status("已停止")
        self.logger.info("游戏停止")
        self._play_sound('button_click')

    def _on_new_game(self):
        """新游戏回调"""
        self._on_stop_game()
        self._on_start_game()

    def _on_change_mode_menu(self):
        """游戏菜单切换模式回调"""
        self.control_panel.show_mode_selection()

    def _on_settings(self):
        """设置回调（打开设置窗口）"""
        self.control_panel.show_settings()

    def _on_back_menu(self):
        """返回主菜单回调"""
        self._on_stop_game()
        self.show_main_menu = True
        self.show_ranking = False
        self.show_live_viewer = False
        pygame.display.set_caption(self.window_title)
        self.logger.info("返回主菜单")

    def _on_toggle_fullscreen(self):
        """切换全屏回调（Win11兼容）"""
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.screen = pygame.display.set_mode(
                (pygame.display.Info().current_w, pygame.display.Info().current_h),
                pygame.FULLSCREEN | pygame.DOUBLEBUF | pygame.HWSURFACE
            )
        else:
            self.screen = pygame.display.set_mode(
                (self.base_width, self.base_height),
                pygame.RESIZABLE | pygame.DOUBLEBUF | pygame.HWSURFACE | pygame.SCALED
            )
        self.logger.info(f"全屏状态：{'开启' if self.is_fullscreen else '关闭'}")

    def _on_toggle_ranking(self):
        """切换排行榜显示回调"""
        self.show_ranking = not self.show_ranking
        self.show_live_viewer = False
        if self.show_ranking:
            self.ranking_panel.load_ranking(self.current_user['user_id'])
        self.logger.info(f"排行榜显示：{'开启' if self.show_ranking else '关闭'}")

    def _on_toggle_live(self):
        """切换直播显示回调"""
        if self.current_mode != GAME_MODES['ONLINE']:
            self.control_panel.show_error("仅联机模式支持直播")
            return
        self.show_live_viewer = not self.show_live_viewer
        self.show_ranking = False
        if self.show_live_viewer:
            # 创建直播间
            room_id = self.game_core.start_live(
                user_id=self.current_user['user_id'],
                user_name=self.current_user['nickname']
            )
            self.control_panel.show_message(f"直播间创建成功：{room_id}")
            self.live_viewer.start_host(room_id, self.current_user['nickname'])
        else:
            # 关闭直播间
            self.game_core.stop_live()
            self.live_viewer.stop_host()
            self.control_panel.show_message("直播已停止")
        self.logger.info(f"直播显示：{'开启' if self.show_live_viewer else '关闭'}")

    def _on_join_live(self, room_id: str):
        """加入直播回调"""
        if not self.current_user:
            self.control_panel.show_error("请先登录或游客登录")
            return
        try:
            success = self.game_core.join_live_room(
                room_id=room_id,
                user_id=self.current_user['user_id'],
                user_name=self.current_user['nickname'],
                callback=self.live_viewer.update_live_data
            )
            if success:
                self.show_live_viewer = True
                self.show_ranking = False
                self.live_viewer.start_viewer(room_id)
                self.control_panel.show_message(f"成功加入直播间：{room_id}")
            else:
                self.control_panel.show_error("直播间不存在或已关闭")
        except Exception as e:
            error_msg = ErrorHandler.handle_ui_error(e)
            self.control_panel.show_error(error_msg)

    def _on_save_model(self):
        """保存模型回调"""
        if not self.current_user or self.current_user['user_id'] == '-1':
            self.control_panel.show_error("游客无法保存模型")
            return
        if self.current_mode != GAME_MODES['TRAIN']:
            self.control_panel.show_error("仅训练模式支持保存模型")
            return

        model_name = self.control_panel.get_model_name().strip()
        if not model_name:
            self.control_panel.show_error("请输入模型名称")
            return

        try:
            # 获取模型元数据
            metadata = {
                'model_type': self.game_core.ai_type,
                'train_data_count': len(self.game_core.move_history),
                'win_rate': self.game_core.get_ai_win_rate(),
                'train_params': self.config.get_json('rl_params'),
                'description': self.control_panel.get_model_desc()
            }
            # 保存模型（带版本控制）
            model_path, meta_path = self.model_storage.save_model_with_version(
                model_data=self.game_core.get_ai_model(),
                model_name=model_name,
                metadata=metadata,
                user_id=self.current_user['user_id']
            )
            self.control_panel.show_message(f"模型保存成功：{model_name}")
            self.logger.info(f"模型保存成功：{model_path}")
            self._play_sound('save_icon')
        except Exception as e:
            error_msg = ErrorHandler.handle_ui_error(e)
            self.control_panel.show_error(error_msg)
            self.logger.error(f"保存模型失败：{str(e)}")

    def _on_load_model(self):
        """加载模型回调"""
        if not self.current_user:
            self.control_panel.show_error("请先登录或游客登录")
            return
        if self.game_active:
            self.control_panel.show_error("请先停止当前游戏")
            return

        # 获取选中的模型
        model_id = self.control_panel.get_selected_model()
        if not model_id:
            self.control_panel.show_error("请选择要加载的模型")
            return

        try:
            # 加载模型
            model_data = self.model_storage.load_model_by_id(model_id, self.current_user['user_id'])
            if model_data:
                self.game_core.load_ai_model(model_data)
                self.control_panel.show_message("模型加载成功")
                self.logger.info(f"模型加载成功：{model_id}")
                self._play_sound('load_icon')
            else:
                self.control_panel.show_error("模型不存在或已损坏")
        except Exception as e:
            error_msg = ErrorHandler.handle_ui_error(e)
            self.control_panel.show_error(error_msg)
            self.logger.error(f"加载模型失败：{str(e)}")

    def _on_train_model(self):
        """训练模型回调"""
        if not self.current_user or self.current_user['user_id'] == '-1':
            self.control_panel.show_error("游客无法训练模型")
            return
        if self.current_mode != GAME_MODES['TRAIN']:
            self.control_panel.show_error("请切换到训练模式")
            return
        if self.game_active:
            self.control_panel.show_error("请先停止当前游戏")
            return

        # 获取训练参数
        epochs = self.control_panel.get_train_epochs()
        batch_size = self.control_panel.get_train_batch_size()
        if epochs <= 0 or epochs > 100:
            self.control_panel.show_error("训练轮次1-100")
            return
        if batch_size <= 0 or batch_size > 256:
            self.control_panel.show_error("批次大小1-256")
            return

        self.control_panel.show_message("开始训练，请勿关闭程序...")
        self.control_panel.set_train_status(TRAIN_STATUSES['TRAINING'])

        # 异步训练（避免阻塞UI）
        def train_thread():
            try:
                self.game_core.train_ai_model(
                    user_id=self.current_user['user_id'],
                    epochs=epochs,
                    batch_size=batch_size,
                    progress_callback=self._on_train_progress_event
                )
                # 训练完成事件
                pygame.event.post(pygame.event.Event(
                    pygame.USEREVENT,
                    custom_type='train_complete',
                    dict={'success': True}
                ))
            except Exception as e:
                pygame.event.post(pygame.event.Event(
                    pygame.USEREVENT,
                    custom_type='train_complete',
                    dict={'success': False, 'error': str(e)}
                ))

        import threading
        train_thread = threading.Thread(target=train_thread, daemon=True)
        train_thread.start()

    def _on_analyze_board(self):
        """棋盘分析回调"""
        if not self.game_active:
            self.control_panel.show_error("请先开始游戏")
            return

        try:
            analysis_report = self.game_core.analyze_board()
            self.control_panel.show_analysis_report(analysis_report)
            # 标记关键落子位置
            if analysis_report.get('key_move'):
                x, y = analysis_report['key_move']
                self.board.mark_key_position(x, y)
            self.logger.info("棋盘分析完成")
            self._play_sound('analyze_icon')
        except Exception as e:
            error_msg = ErrorHandler.handle_ui_error(e)
            self.control_panel.show_error(error_msg)
            self.logger.error(f"棋盘分析失败：{str(e)}")

    def _on_piece_place(self, x: int, y: int):
        """落子回调"""
        if not self.game_active or self.is_ai_thinking:
            return

        try:
            result = self.game_core.place_piece(x, y)
            if result == 'success':
                # 更新棋盘
                self.board.update_board(self.game_core.board)
                self.control_panel.update_move_count(len(self.game_core.move_history))
                self._play_sound('place_piece')

                # 检查游戏结束
                game_result = self.game_core.game_result
                if game_result:
                    self._on_game_end_event(Event('game_end', {'data': game_result}))
                    return

                # 人机/训练模式：AI落子
                if self.current_mode in [GAME_MODES['PVE'], GAME_MODES['TRAIN']]:
                    self.game_core.ai_move(self.ai_visualizer.update_thinking_data)

            elif result == 'invalid_position':
                self.control_panel.show_error("落子位置超出棋盘")
            elif result == 'occupied':
                self.control_panel.show_error("该位置已被占用")
            elif result == 'not_your_turn':
                self.control_panel.show_error("不是你的回合")
        except Exception as e:
            error_msg = ErrorHandler.handle_ui_error(e)
            self.control_panel.show_error(error_msg)
            self.logger.error(f"落子失败：{str(e)}")

    # ------------------------------ 事件驱动回调 ------------------------------
    def _on_game_start_event(self, event: Event):
        """游戏开始事件回调"""
        self.game_active = True
        self.control_panel.update_game_status("游戏中")
        self.board.set_game_active(True)
        self.logger.info("游戏开始（事件驱动）")

    def _on_game_end_event(self, event: Event):
        """游戏结束事件回调"""
        game_result = event.data['data']
        self.game_active = False
        self.is_ai_thinking = False
        self.ai_visualizer.reset()

        # 解析结果
        winner = game_result['winner']
        win_line = game_result.get('win_line', [])
        ranking_update = game_result.get('ranking_update')

        # 绘制获胜线
        if win_line:
            self.board.draw_win_line(win_line)

        # 更新状态和提示
        if winner == 'draw':
            status = "平局"
            msg = "游戏结束，平局！"
            self._play_sound('draw')
        elif winner == 'black':
            status = "黑方获胜"
            msg = "游戏结束，黑方获胜！"
            self._play_sound('win' if self.game_core.current_player == PIECE_COLORS['BLACK'] else 'lose')
        elif winner == 'white':
            status = "白方获胜"
            msg = "游戏结束，白方获胜！"
            self._play_sound('win' if self.game_core.current_player == PIECE_COLORS['WHITE'] else 'lose')
        else:
            status = "游戏结束"
            msg = "游戏结束！"

        # 显示排行榜更新
        if ranking_update:
            msg += f"\n{ranking_update['message']}"
            self.ranking_panel.load_ranking(self.current_user['user_id'])

        self.control_panel.update_game_status(status)
        self.control_panel.show_message(msg)
        self.logger.info(f"游戏结束：{status}")

    def _on_move_made_event(self, event: Event):
        """落子事件回调"""
        move_data = event.data
        self.board.update_board(self.game_core.board)
        self.control_panel.update_move_count(len(self.game_core.move_history))
        self.logger.debug(f"落子事件：({move_data['x']},{move_data['y']})，颜色：{move_data['color']}")

    def _on_ai_thinking_start(self, event: Event):
        """AI思考开始事件回调"""
        self.is_ai_thinking = True
        self.control_panel.update_game_status("AI思考中...")
        self.board.set_ai_thinking(True)

    def _on_ai_thinking_end(self, event: Event):
        """AI思考结束事件回调"""
        self.is_ai_thinking = False
        self.control_panel.update_game_status("游戏中" if self.game_active else "已停止")
        self.board.set_ai_thinking(False)

    def _on_model_saved_event(self, event: Event):
        """模型保存事件回调"""
        model_data = event.data
        self.control_panel.show_message(f"模型保存成功：{model_data['name']}")
        self.logger.info(f"模型保存事件：{model_data['path']}")

    def _on_train_progress_event(self, event: Event):
        """训练进度事件回调"""
        progress_data = event.data
        self.control_panel.update_train_progress(progress_data['progress'])
        self.logger.debug(f"训练进度：{progress_data['progress']:.1f}%，损失：{progress_data['loss']:.4f}")

    def _on_train_complete_event(self, event: Event):
        """训练完成事件回调"""
        train_data = event.data
        if train_data['success']:
            self.control_panel.show_message("模型训练完成！")
            self.control_panel.set_train_status(TRAIN_STATUSES['COMPLETED'])
            self._play_sound('win')
        else:
            error_msg = train_data.get('error', '未知错误')
            self.control_panel.show_error(f"训练失败：{error_msg}")
            self.control_panel.set_train_status(TRAIN_STATUSES['FAILED'])
        self.logger.info(f"训练完成：{'成功' if train_data['success'] else '失败'}")

    def _on_online_connected(self, event: Event):
        """联机连接事件回调"""
        self.control_panel.show_message("联机连接成功")
        self.logger.info("联机连接成功")

    def _on_online_disconnected(self, event: Event):
        """联机断开事件回调"""
        self.control_panel.show_error("联机连接断开")
        self.game_active = False
        self.board.reset()
        self.logger.warning("联机连接断开")

    def _on_live_room_created(self, event: Event):
        """直播间创建事件回调"""
        live_data = event.data
        self.show_live_viewer = True
        self.live_viewer.start_host(live_data['room_id'], live_data['host_name'])
        self.control_panel.show_message(f"直播间创建成功：{live_data['room_id']}")

    def _on_live_room_joined(self, event: Event):
        """加入直播间事件回调"""
        live_data = event.data
        self.show_live_viewer = True
        self.live_viewer.start_viewer(live_data['room_id'])
        self.control_panel.show_message(f"成功加入直播间：{live_data['room_id']}")

    def _on_live_message(self, event: Event):
        """直播消息事件回调"""
        msg_data = event.data
        self.live_viewer.add_message(msg_data['user_name'], msg_data['content'])

    def _on_error_occurred(self, event: Event):
        """错误事件回调"""
        error_data = event.data
        self.control_panel.show_error(f"错误：{error_data['message']}（错误码：{error_data['code']}）")
        self.logger.error(f"错误事件：{error_data}")

    # ------------------------------ 辅助方法 ------------------------------
    def _play_sound(self, sound_name: str):
        """播放音效（可选）"""
        if self.config.get_bool('GAME', 'enable_sound', True) and sound_name in self.sounds:
            self.sounds[sound_name].play()
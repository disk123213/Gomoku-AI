from typing import Dict, Optional
from Common.constants import GAME_MODES, AI_LEVELS, PIECE_COLORS
from Common.logger import Logger
from Common.error_handler import GameError
from AI.base_ai import BaseAI
from AI.ai_fleet import AIFleet
from AI.rl_ai import RLAI
from AI.mcts_ai import MCTSAI
from AI.minimax_ai import MinimaxAI
from AI.nn_ai import NNAI
from Network.online_client import OnlineClient
from Network.p2p_client import P2PClient

class GameModeManager:
    """游戏模式管理器（统一管理PVE/PVP/ONLINE/TRAIN模式）"""
    def __init__(self, game_core):
        self.game_core = game_core
        self.logger = Logger.get_instance()
        self.mode_initializers = {
            GAME_MODES['PVE']: self._init_pve_mode,
            GAME_MODES['PVP']: self._init_pvp_mode,
            GAME_MODES['ONLINE']: self._init_online_mode,
            GAME_MODES['TRAIN']: self._init_train_mode
        }

    def init_mode(self, mode: str):
        """初始化指定模式"""
        if mode not in self.mode_initializers:
            raise GameError(f"不支持的模式：{mode}", 2001)
        self.mode_initializers[mode]()

    # ------------------------------ 模式初始化 ------------------------------
    def _init_pve_mode(self):
        """初始化PVE模式（人机对战）"""
        self.game_core.is_online = False
        self.game_core.is_training = False

        # 初始化AI（专家级启用多AI协同）
        ai_color = PIECE_COLORS['WHITE'] if self.game_core.ai_first else PIECE_COLORS['BLACK']
        if self.game_core.ai_level == AI_LEVELS['EXPERT']:
            self.game_core.current_ai = AIFleet(ai_color, self.game_core.ai_level)
        else:
            self.game_core.current_ai = self._create_single_ai(ai_color)

        self.logger.info(f"PVE模式初始化完成：AI颜色={ai_color}，AI类型={self.game_core.ai_type}")

    def _init_pvp_mode(self):
        """初始化PVP模式（人人对战）"""
        self.game_core.is_online = False
        self.game_core.is_training = False
        self.game_core.current_ai = None
        self.game_core.ai_team = None
        self.logger.info("PVP模式初始化完成：双人本地对战")

    def _init_online_mode(self):
        """初始化联机模式（P2P+服务器转发）"""
        self.game_core.is_online = True
        self.game_core.is_training = False
        self.game_core.current_ai = None

        # 初始化联机客户端（P2P优先）
        self.game_core.online_client = OnlineClient(
            host=self.game_core.config.server_host,
            port=self.game_core.config.server_port,
            reconnect_interval=5
        )
        self.game_core.online_client.set_callback(self._handle_online_message)
        self.game_core.online_client.start()

        # 初始化P2P客户端
        self.game_core.p2p_client = P2PClient()

        self.logger.info(f"联机模式初始化完成：服务器={self.game_core.config.server_host}:{self.game_core.config.server_port}")

    def _init_train_mode(self):
        """初始化训练模式（AI辅助+复盘）"""
        self.game_core.is_online = False
        self.game_core.is_training = True

        # 初始化训练用AI（默认RL+MCTS混合）
        ai_color = PIECE_COLORS['WHITE']
        self.game_core.current_ai = RLAI(ai_color, self.game_core.ai_level)

        # 加载用户自定义模型（如果存在）
        if self.game_core.train_user_id:
            user_models = self.game_core.model_manager.get_user_models(self.game_core.train_user_id)
            if user_models:
                latest_model = user_models[0]
                self.game_core.load_ai_model(latest_model['path'])

        self.logger.info(f"训练模式初始化完成：AI类型={self.game_core.ai_type}，支持自我对弈和复盘分析")

    # ------------------------------ 辅助方法 ------------------------------
    def _create_single_ai(self, color: int) -> BaseAI:
        """创建单一AI实例（根据类型选择）"""
        ai_map = {
            'rl': RLAI,
            'mcts': MCTSAI,
            'minimax': MinimaxAI,
            'nn': NNAI,
            'rl+mcts': lambda c, l: RLAI(c, l)  # RL为主，MCTS优化落子
        }
        ai_cls = ai_map.get(self.game_core.ai_type, MCTSAI)
        return ai_cls(color, self.game_core.ai_level)

    def _handle_online_message(self, data: Dict):
        """处理联机消息回调"""
        msg_type = data.get('type')
        if msg_type == 'move':
            # 接收对手落子
            x, y = data['x'], data['y']
            self.game_core.place_piece(x, y, is_ai=False)
        elif msg_type == 'room_join':
            # 对手加入房间
            self.game_core.online_opponent_id = data['user_id']
            self.game_core.online_opponent_name = data['user_name']
            self.game_core.event_manager.emit(Event('ui_update', {
                'type': 'opponent_join',
                'data': {'user_name': self.game_core.online_opponent_name}
            }))
        elif msg_type == 'game_end':
            # 对手发起游戏结束
            self.game_core.game_result = data['result']
            self.game_core.event_manager.emit(Event('game_end', self.game_core.game_result))
        elif msg_type == 'disconnect':
            # 对手断开连接
            self.game_core.event_manager.emit(Event('ui_update', {'type': 'opponent_disconnect'}))
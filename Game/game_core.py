import time
import threading
from typing import List, Tuple, Dict, Optional, Callable
from Common.constants import PIECE_COLORS, GAME_MODES, AI_LEVELS, EVAL_WEIGHTS
from Common.config import Config
from Common.logger import Logger
from Common.data_utils import DataUtils
from Common.error_handler import GameError
from Common.event import EventManager, Event
from AI.base_ai import BaseAI
from AI.ai_fleet import AIFleet
from AI.model_manager import ModelManager
from AI.evaluator import BoardEvaluator
from Storage.user_storage import UserStorage
from Storage.game_record_storage import GameRecordStorage
from Storage.ranking_storage import RankingStorage
from Compute.cpp_interface import CppCore
from Game.game_mode import GameModeManager
from Game.rule_engine import RuleEngine
from Game.ranking_system import ELORankingSystem

class GameCore:
    """游戏核心管理器（单例模式+事件驱动，统筹所有游戏逻辑）"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True

        # 基础配置与工具
        self.config = Config.get_instance()
        self.logger = Logger.get_instance()
        self.event_manager = EventManager()
        self.cpp_core = CppCore()
        self.data_utils = DataUtils()

        # 核心组件
        self.mode_manager = GameModeManager(self)
        self.rule_engine = RuleEngine(self.config.board_size)
        self.model_manager = ModelManager()
        self.evaluator = BoardEvaluator(self.config.board_size)
        self.ranking_system = ELORankingSystem()

        # 存储组件
        self.user_storage = UserStorage()
        self.game_storage = GameRecordStorage()
        self.ranking_storage = RankingStorage()

        # 游戏状态（线程安全）
        self.state_lock = threading.Lock()
        self.board_size = self.config.board_size
        self.board = [[PIECE_COLORS['EMPTY'] for _ in range(self.board_size)] for _ in range(self.board_size)]
        self.move_history = []  # 落子历史：[(x,y,color,is_ai,timestamp,score,quality)]
        self.game_active = False
        self.current_player = PIECE_COLORS['BLACK']
        self.game_result = None  # 最终结果：{'winner': 'black/white/draw', 'win_line': [], 'ranking_update': {}}

        # 模式配置
        self.current_mode = None
        self.ai_level = AI_LEVELS['HARD']
        self.ai_type = 'rl+mcts'
        self.ai_first = False
        self.current_ai: Optional[BaseAI] = None
        self.ai_team: Optional[AIFleet] = None

        # 联机相关
        self.is_online = False
        self.online_client = None
        self.current_room_id = None
        self.online_opponent_id = None
        self.online_opponent_name = None
        self.online_callback: Optional[Callable[[Dict], None]] = None

        # 训练相关
        self.is_training = False
        self.train_user_id = None
        self.train_progress = 0.0  # 训练进度（0-100）

        # 性能优化：评估缓存
        self.eval_cache = {}
        self.cache_max_size = 1000

        # 注册事件监听
        self._register_events()

    def _register_events(self):
        """注册核心事件回调"""
        self.event_manager.register('game_start', self._on_game_start)
        self.event_manager.register('game_stop', self._on_game_stop)
        self.event_manager.register('move_made', self._on_move_made)
        self.event_manager.register('game_end', self._on_game_end)
        self.event_manager.register('model_saved', self._on_model_saved)
        self.event_manager.register('mode_changed', self._on_mode_changed)

    # ------------------------------ 事件回调 ------------------------------
    def _on_game_start(self, event: Event):
        """游戏开始事件"""
        self.logger.info(f"游戏启动：模式={self.current_mode}，AI类型={self.ai_type}，AI难度={self.ai_level}")
        self.event_manager.emit(Event('ui_update', {
            'type': 'game_start',
            'data': {
                'mode': self.current_mode,
                'board_size': self.board_size,
                'ai_first': self.ai_first,
                'current_player': self.current_player
            }
        }))

    def _on_game_stop(self, event: Event):
        """游戏停止事件"""
        self.game_active = False
        self.logger.info("游戏停止")
        self.event_manager.emit(Event('ui_update', {'type': 'game_stop'}))

    def _on_move_made(self, event: Event):
        """落子事件"""
        move_data = event.data
        self.logger.info(f"落子记录：({move_data['x']},{move_data['y']})，颜色={move_data['color']}，AI={move_data['is_ai']}")
        self.event_manager.emit(Event('ui_update', {'type': 'move_made', 'data': move_data}))

    def _on_game_end(self, event: Event):
        """游戏结束事件"""
        self.game_active = False
        self.logger.info(f"游戏结束：结果={self.game_result}")

        # 保存对战记录
        self.game_storage.save_game_record({
            'user_id': self.train_user_id,
            'mode': self.current_mode,
            'move_history': self.move_history,
            'result': self.game_result,
            'timestamp': time.time(),
            'ai_level': self.ai_level,
            'ai_type': self.ai_type
        })

        # 联机模式更新排行榜
        if self.is_online and self.game_result and self.game_result['winner'] != 'draw':
            self._update_online_ranking()

        # 训练模式生成复盘报告
        if self.current_mode == GAME_MODES['TRAIN']:
            self._generate_replay_report()

        self.event_manager.emit(Event('ui_update', {'type': 'game_end', 'data': self.game_result}))

    def _on_model_saved(self, event: Event):
        """模型保存事件"""
        model_data = event.data
        self.logger.info(f"模型保存成功：路径={model_data['path']}")
        self.event_manager.emit(Event('ui_update', {'type': 'model_saved', 'data': model_data}))

    def _on_mode_changed(self, event: Event):
        """模式切换事件"""
        mode = event.data['mode']
        self.logger.info(f"模式切换完成：{mode}")
        self.event_manager.emit(Event('ui_update', {'type': 'mode_changed', 'data': {'mode': mode}}))

    # ------------------------------ 核心逻辑 ------------------------------
    def set_mode(self, mode: str, user_id: Optional[str] = None):
        """设置游戏模式（线程安全）"""
        with self.state_lock:
            if mode not in GAME_MODES.values():
                raise GameError(f"不支持的游戏模式：{mode}", 2001)

            self.current_mode = mode
            self.train_user_id = user_id
            self.is_online = (mode == GAME_MODES['ONLINE'])
            self.is_training = (mode == GAME_MODES['TRAIN'])

            # 初始化对应模式组件
            self.mode_manager.init_mode(mode)

            # 重置游戏状态
            self.reset_game()

            # 触发模式切换事件
            self.event_manager.emit(Event('mode_changed', {'mode': mode}))

    def reset_game(self):
        """重置游戏状态"""
        with self.state_lock:
            self.board = [[PIECE_COLORS['EMPTY'] for _ in range(self.board_size)] for _ in range(self.board_size)]
            self.move_history.clear()
            self.game_active = True
            self.current_player = PIECE_COLORS['BLACK']
            self.game_result = None
            self.eval_cache.clear()

            # AI先手逻辑
            if self.ai_first and self.current_ai:
                threading.Thread(target=self.ai_move, daemon=True).start()

    def place_piece(self, x: int, y: int, is_ai: bool = False) -> str:
        """玩家落子（含合法性校验）"""
        with self.state_lock:
            if not self.game_active:
                return 'game_not_active'

            # 规则校验（调用规则引擎）
            valid, reason = self.rule_engine.validate_move(self.board, x, y, self.current_player)
            if not valid:
                self.logger.warning(f"落子失败：{reason}")
                return reason

            # 执行落子（C++核心加速）
            self.board = self.cpp_core.place_piece(self.board, x, y, self.current_player)

            # 落子质量评估
            eval_result = self.evaluator.analyze_move_quality(self.board, x, y, self.current_player)

            # 记录落子历史
            move_data = {
                'x': x,
                'y': y,
                'color': self.current_player,
                'is_ai': is_ai,
                'timestamp': time.time(),
                'score': eval_result['score'],
                'quality': eval_result['quality'],
                'pattern': eval_result['pattern']
            }
            self.move_history.append(move_data)
            self.event_manager.emit(Event('move_made', move_data))

            # 检查游戏结束
            end_result = self.rule_engine.check_game_end(self.board)
            if end_result['is_end']:
                self.game_result = {
                    'winner': 'black' if end_result['winner'] == PIECE_COLORS['BLACK'] else 'white' if end_result['winner'] else 'draw',
                    'win_line': end_result['win_line'],
                    'move_count': len(self.move_history)
                }
                self.event_manager.emit(Event('game_end', self.game_result))
                return 'game_end'

            # 切换玩家
            self.current_player = PIECE_COLORS['WHITE'] if self.current_player == PIECE_COLORS['BLACK'] else PIECE_COLORS['BLACK']

            # 联机模式同步落子
            if self.is_online:
                self._sync_online_move(move_data)

            return 'success'

    def ai_move(self, thinking_callback: Optional[Callable[[Dict], None]] = None) -> Tuple[int, int]:
        """AI落子（支持多AI协同）"""
        if not self.game_active or not self.current_ai:
            raise GameError("AI落子失败：游戏未激活或AI未初始化", 2002)

        if self.current_player != self.current_ai.color:
            raise GameError("当前不是AI回合", 2003)

        # 多AI协同落子
        if isinstance(self.current_ai, AIFleet):
            x, y = self.current_ai.move(self.board, thinking_callback)
        else:
            x, y = self.current_ai.move(self.board, thinking_callback)

        # 执行落子
        self.place_piece(x, y, is_ai=True)
        return (x, y)

    # ------------------------------ 辅助功能 ------------------------------
    def _update_online_ranking(self):
        """更新联机对战排行榜（ELO积分）"""
        try:
            # 获取双方玩家信息
            player1_id = self.train_user_id
            player1_data = self.user_storage.load_user(player1_id)
            if not player1_data:
                raise GameError(f"用户数据不存在：{player1_id}", 3001)

            player2_id = self.online_opponent_id
            player2_data = self.user_storage.load_user(player2_id)
            if not player2_data:
                raise GameError(f"对手数据不存在：{player2_id}", 3002)

            # 判断胜负
            player1_win = (self.game_result['winner'] == 'black' and self.current_player == PIECE_COLORS['BLACK']) or \
                          (self.game_result['winner'] == 'white' and self.current_player == PIECE_COLORS['WHITE'])

            # 更新全球+本地排行榜
            ranking_result = self.ranking_system.update_player_rating(
                player1_id=player1_id,
                player1_name=player1_data['nickname'],
                player2_id=player2_id,
                player2_name=player2_data['nickname'],
                player1_win=player1_win,
                is_global=True
            )
            self.ranking_system.update_player_rating(
                player1_id=player1_id,
                player1_name=player1_data['nickname'],
                player2_id=player2_id,
                player2_name=player2_data['nickname'],
                player1_win=player1_win,
                is_global=False
            )

            # 记录积分变化
            self.game_result['ranking_update'] = {
                'player1': ranking_result['player1'],
                'player2': ranking_result['player2']
            }

        except Exception as e:
            self.logger.error(f"更新排行榜失败：{str(e)}")

    def _generate_replay_report(self):
        """生成训练模式复盘报告"""
        if not self.move_history:
            return

        # 分析落子质量统计
        total_quality = sum(move['quality'] for move in self.move_history)
        avg_quality = total_quality / len(self.move_history)
        best_move = max(self.move_history, key=lambda x: x['quality'])
        worst_move = min(self.move_history, key=lambda x: x['quality'])

        # 棋型分布统计
        pattern_counts = {}
        for move in self.move_history:
            pattern = move['pattern']
            pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

        # 保存复盘报告
        report = {
            'game_id': f"replay_{self.train_user_id}_{int(time.time())}",
            'timestamp': time.time(),
            'move_count': len(self.move_history),
            'result': self.game_result,
            'avg_quality': round(avg_quality, 2),
            'best_move': best_move,
            'worst_move': worst_move,
            'pattern_distribution': pattern_counts,
            'ai_suggestions': self._get_ai_suggestions()
        }

        self.game_storage.save_replay_report(self.train_user_id, report)
        self.logger.info(f"复盘报告生成完成：平均落子质量={avg_quality:.2f}")

    def _get_ai_suggestions(self) -> List[Dict]:
        """获取AI优化建议（针对低质量落子）"""
        suggestions = []
        for idx, move in enumerate(self.move_history):
            if move['quality'] < 60:  # 低质量落子（<60分）
                x, y = move['x'], move['y']
                # 获取AI推荐的最优落子
                best_move = self.evaluator.analyze_move_quality(self.board, x, y, move['color'])['best_move']
                suggestions.append({
                    'move_idx': idx + 1,
                    'bad_move': (x, y),
                    'suggested_move': best_move,
                    'quality': move['quality'],
                    'reason': f"当前落子质量{move['quality']:.1f}分，建议落子{best_move}（质量分{self.evaluator.evaluate_move(self.board, best_move[0], best_move[1], move['color'], EVAL_WEIGHTS):.1f}）"
                })
        return suggestions

    def load_ai_model(self, model_path: str):
        """加载自定义AI模型"""
        if self.ai_type == 'rl':
            self.current_ai.load_model(model_path)
        elif self.ai_type == 'nn':
            self.current_ai = self.model_manager.load_model('nn', model_path, self.current_ai.color, self.ai_level)
        self.logger.info(f"加载自定义模型：{model_path}")

    def start_ai_training(self, num_games: int = 100):
        """启动AI训练（仅训练模式）"""
        if self.current_mode != GAME_MODES['TRAIN'] or not isinstance(self.current_ai, (RLAI, NNAI)):
            raise GameError("仅训练模式支持AI训练，且AI类型需为RL或NN", 4001)

        def train_worker():
            self.is_training = True
            self.train_progress = 0.0
            for i in range(num_games):
                self.current_ai.self_play(num_games=1)
                self.train_progress = (i + 1) / num_games * 100
                self.event_manager.emit(Event('ui_update', {
                    'type': 'train_progress',
                    'data': {'progress': self.train_progress, 'current_game': i + 1, 'total_games': num_games}
                }))
            self.is_training = False
            self.logger.info(f"AI训练完成：{num_games}局自我对弈")
            self.event_manager.emit(Event('ui_update', {'type': 'train_complete'}))

        threading.Thread(target=train_worker, daemon=True).start()
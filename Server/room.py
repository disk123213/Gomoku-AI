import time
from typing import Dict, List, Optional, Tuple
from Common.logger import Logger
from Common.constants import PIECE_COLORS, GAME_MODES, AI_LEVELS
from Compute.cpp_interface import CppCore
from AI.base_ai import AIFactory

class Room:
    """房间类 - 维护单局对战状态（棋盘、玩家、落子历史、AI）"""
    def __init__(self, room_id: str, host_user_id: str, host_client_id: str, game_mode: str, ai_level: str):
        self.room_id = room_id
        self.host_user_id = host_user_id
        self.game_mode = game_mode
        self.ai_level = ai_level

        # 玩家列表：user_id -> client_id
        self.players: Dict[str, str] = {host_user_id: host_client_id}
        # 玩家颜色映射：user_id -> PIECE_COLORS（黑/白）
        self.player_colors: Dict[str, int] = {host_user_id: PIECE_COLORS["BLACK"]}
        # 当前回合玩家
        self.current_player: Optional[str] = host_user_id

        # 棋盘状态（15x15）
        self.board_size = 15
        self.board = [[PIECE_COLORS["EMPTY"] for _ in range(self.board_size)] for _ in range(self.board_size)]
        # 落子历史：[{x, y, user_id, color, timestamp}]
        self.move_history: List[Dict] = []

        # 游戏状态
        self.game_active = False  # 游戏是否已开始
        self.game_result: Optional[Dict] = None  # 游戏结果
        self.start_time = time.time()
        self.last_move_time = time.time()
        self.last_member_change_time = time.time()

        # AI实例（PVE模式）
        self.ai: Optional[BaseAI] = None
        self.ai_color = PIECE_COLORS["WHITE"]
        if self.game_mode == GAME_MODES["PVE"]:
            self._init_ai()

        # 依赖组件
        self.logger = Logger.get_instance()
        self.cpp_core = CppCore()

    def _init_ai(self):
        """初始化AI（PVE模式）"""
        self.ai = AIFactory.create_ai(
            ai_type="rl+mcts",
            color=self.ai_color,
            level=self.ai_level,
            use_cpp_core=True
        )
        self.logger.info(f"房间初始化AI：room_id={self.room_id}，ai_level={self.ai_level}，color={self.ai_color}")

    def add_player(self, user_id: str, client_id: str):
        """添加玩家（PVP模式）"""
        if self.game_mode != GAME_MODES["PVP"]:
            return
        if len(self.players) >= 2:
            return

        # 分配颜色（第二个玩家为白方）
        color = PIECE_COLORS["WHITE"]
        self.players[user_id] = client_id
        self.player_colors[user_id] = color
        self.last_member_change_time = time.time()

        # 游戏自动开始（PVP两人满员）
        if len(self.players) == 2:
            self.start_game()

    def remove_player(self, user_id: str, client_id: str):
        """移除玩家"""
        if user_id in self.players:
            del self.players[user_id]
            if user_id in self.player_colors:
                del self.player_colors[user_id]
            self.last_member_change_time = time.time()

            # 游戏终止
            self.game_active = False
            self.game_result = {"winner": "none", "reason": "玩家离开"}

    def is_full(self) -> bool:
        """判断房间是否已满"""
        if self.game_mode == GAME_MODES["PVE"]:
            return len(self.players) >= 1
        return len(self.players) >= 2

    def start_game(self):
        """开始游戏"""
        self.game_active = True
        self.game_result = None
        self.start_time = time.time()
        self.last_move_time = time.time()
        self.logger.info(f"房间游戏开始：room_id={self.room_id}，mode={self.game_mode}")
        # PVE模式AI先落子（可选）
        if self.game_mode == GAME_MODES["PVE"] and self.ai and self.ai_first:
            self.ai_move()

    def get_room_info(self) -> Dict:
        """获取房间信息（用于客户端展示）"""
        return {
            "room_id": self.room_id,
            "game_mode": self.game_mode,
            "ai_level": self.ai_level,
            "players": self.get_player_info(),
            "current_player": self.current_player,
            "game_active": self.game_active,
            "move_count": len(self.move_history),
            "start_time": self.start_time
        }

    def get_player_info(self) -> List[Dict]:
        """获取玩家信息"""
        player_info = []
        from Storage.user_storage import UserStorage
        user_storage = UserStorage()
        for user_id, client_id in self.players.items():
            user_data = user_storage.load_user(user_id)
            player_info.append({
                "user_id": user_id,
                "client_id": client_id,
                "nickname": user_data["nickname"] if user_data else f"用户_{user_id[:6]}",
                "color": self.player_colors.get(user_id, -1),
                "is_host": user_id == self.host_user_id
            })
        return player_info

    def get_member_list(self) -> List[str]:
        """获取玩家用户ID列表"""
        return list(self.players.keys())

    def get_peer_client_id(self, user_id: str) -> Optional[str]:
        """获取对等玩家的客户端ID"""
        for uid, cid in self.players.items():
            if uid != user_id:
                return cid
        return None

    def get_incremental_data(self, last_sync_timestamp: float) -> List[Dict]:
        """获取增量数据（落子历史）"""
        return [move for move in self.move_history if move["timestamp"] > last_sync_timestamp]

    def place_piece(self, user_id: str, x: int, y: int) -> Dict:
        """处理玩家落子"""
        # 校验落子合法性
        if not self.game_active:
            return {"success": False, "message": "游戏未开始"}
        if user_id != self.current_player:
            return {"success": False, "message": "不是你的回合"}
        if not (0 <= x < self.board_size and 0 <= y < self.board_size):
            return {"success": False, "message": "坐标超出棋盘范围"}
        if self.board[x][y] != PIECE_COLORS["EMPTY"]:
            return {"success": False, "message": "该位置已落子"}

        # 执行落子（C++核心）
        color = self.player_colors[user_id]
        self.board = self.cpp_core.place_piece(self.board, x, y, color)

        # 记录落子历史
        move = {
            "x": x,
            "y": y,
            "user_id": user_id,
            "color": color,
            "timestamp": time.time()
        }
        self.move_history.append(move)
        self.last_move_time = time.time()

        # 检查游戏结束
        game_end_result = self.cpp_core.check_game_end(self.board, self.board_size)
        if game_end_result["is_end"]:
            self.game_active = False
            winner = "black" if game_end_result["winner"] == PIECE_COLORS["BLACK"] else "white" if game_end_result["winner"] == PIECE_COLORS["WHITE"] else "draw"
            self.game_result = {
                "winner": winner,
                "win_line": game_end_result["win_line"],
                "move_count": len(self.move_history),
                "duration": time.time() - self.start_time
            }
            return {
                "success": True,
                "color": color,
                "game_end": True,
                "game_result": self.game_result
            }

        # 切换回合
        self._switch_turn()

        # PVE模式：AI自动落子
        if self.game_mode == GAME_MODES["PVE"] and self.current_player == "ai":
            self.ai_move()

        return {"success": True, "color": color, "game_end": False}

    def ai_move(self):
        """AI落子（PVE模式）"""
        if not self.game_active or not self.ai:
            return

        # AI计算落子
        thinking_callback = lambda data: self.broadcast_message({"type": "AI_THINKING", "data": data})
        x, y = self.ai.move(self.board, thinking_callback)

        # 执行落子
        color = self.ai_color
        self.board = self.cpp_core.place_piece(self.board, x, y, color)

        # 记录落子历史
        move = {
            "x": x,
            "y": y,
            "user_id": "ai",
            "color": color,
            "timestamp": time.time()
        }
        self.move_history.append(move)
        self.last_move_time = time.time()

        self.logger.info(f"AI落子：room_id={self.room_id}，x={x}，y={y}，color={color}")

        # 广播AI落子
        self.broadcast_message({
            "type": "AI_PIECE_PLACED",
            "data": {
                "x": x,
                "y": y,
                "color": color,
                "board": self.board,
                "move_history": self.move_history
            }
        })

        # 检查游戏结束
        game_end_result = self.cpp_core.check_game_end(self.board, self.board_size)
        if game_end_result["is_end"]:
            self.game_active = False
            winner = "ai" if game_end_result["winner"] == self.ai_color else self.host_user_id
            self.game_result = {
                "winner": winner,
                "win_line": game_end_result["win_line"],
                "move_count": len(self.move_history),
                "duration": time.time() - self.start_time
            }
            self.broadcast_message({
                "type": "GAME_END",
                "data": self.game_result
            })
            return

        # 切换回合（回到玩家）
        self.current_player = self.host_user_id

    def _switch_turn(self):
        """切换回合"""
        if self.game_mode == GAME_MODES["PVE"]:
            self.current_player = "ai" if self.current_player == self.host_user_id else self.host_user_id
        else:  # PVP
            players = list(self.players.keys())
            current_idx = players.index(self.current_player)
            next_idx = (current_idx + 1) % len(players)
            self.current_player = players[next_idx]

    def broadcast_message(self, message: Dict):
        """广播消息给房间内所有玩家"""
        from Server.main_server import MainServer
        main_server = MainServer()
        for client_id in self.players.values():
            main_server.tcp_server.send_message(client_id, message)
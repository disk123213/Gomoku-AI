import time
import threading
from typing import Dict, List, Optional, Tuple
from Common.logger import Logger
from Common.constants import GAME_MODES, AI_LEVELS
from Server.room import Room

class RoomManager:
    """房间管理器（单例）- 管理房间的创建、查询、删除、清理"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.logger = Logger.get_instance()

        # 房间存储：room_id -> Room实例
        self.rooms: Dict[str, Room] = {}
        self.room_id_counter = 1000  # 房间ID起始值
        self.room_lock = threading.Lock()

        # 房间超时配置（默认300秒无活动）
        self.room_timeout = 300
        self.cleanup_interval = 60  # 清理定时器间隔（秒）

    def _generate_room_id(self) -> str:
        """生成唯一房间ID"""
        with self.room_lock:
            self.room_id_counter += 1
            return f"room_{self.room_id_counter}"

    def create_room(self, host_user_id: str, host_client_id: str, game_mode: str = "PVE", ai_level: str = "HARD") -> Room:
        """创建房间"""
        if game_mode not in GAME_MODES.values():
            game_mode = GAME_MODES["PVE"]
        if ai_level not in AI_LEVELS.values():
            ai_level = AI_LEVELS["HARD"]

        with self.room_lock:
            room_id = self._generate_room_id()
            room = Room(
                room_id=room_id,
                host_user_id=host_user_id,
                host_client_id=host_client_id,
                game_mode=game_mode,
                ai_level=ai_level
            )
            self.rooms[room_id] = room
            self.logger.info(f"创建房间：room_id={room_id}，host_user_id={host_user_id}，mode={game_mode}，ai_level={ai_level}")
            return room

    def get_room(self, room_id: str) -> Optional[Room]:
        """获取房间实例"""
        with self.room_lock:
            return self.rooms.get(room_id)

    def get_room_list(self) -> List[Room]:
        """获取所有房间实例"""
        with self.room_lock:
            return list(self.rooms.values())

    def get_room_list_summary(self) -> List[Dict]:
        """获取房间列表摘要（用于客户端展示）"""
        summary = []
        with self.room_lock:
            for room in self.rooms.values():
                summary.append({
                    "room_id": room.room_id,
                    "game_mode": room.game_mode,
                    "ai_level": room.ai_level,
                    "player_count": len(room.players),
                    "host_nickname": self._get_user_nickname(room.host_user_id)
                })
        return summary

    def add_player_to_room(self, room_id: str, user_id: str, client_id: str) -> Dict:
        """添加玩家到房间"""
        with self.room_lock:
            room = self.rooms.get(room_id)
            if not room:
                return {"success": False, "message": "房间不存在"}
            if room.is_full():
                return {"success": False, "message": "房间已满"}
            if user_id in room.players:
                return {"success": False, "message": "已在房间内"}

            # 添加玩家
            room.add_player(user_id, client_id)
            return {"success": True, "message": "加入成功", "room": room}

    def remove_player_from_room(self, room_id: str, user_id: str, client_id: str) -> Dict:
        """从房间移除玩家"""
        with self.room_lock:
            room = self.rooms.get(room_id)
            if not room:
                return {"success": False, "message": "房间不存在"}
            if user_id not in room.players:
                return {"success": False, "message": "不在房间内"}

            # 移除玩家
            room.remove_player(user_id, client_id)
            # 房间为空则删除
            if len(room.players) == 0:
                del self.rooms[room_id]
                return {"success": True, "message": "离开成功", "room": None}
            return {"success": True, "message": "离开成功", "room": room}

    def remove_client_from_all_rooms(self, client_id: str):
        """从所有房间移除客户端（客户端断开时）"""
        with self.room_lock:
            rooms_to_close = []
            for room_id, room in self.rooms.items():
                # 查找该客户端对应的玩家
                user_id = None
                for uid, cid in room.players.items():
                    if cid == client_id:
                        user_id = uid
                        break
                if user_id:
                    room.remove_player(user_id, client_id)
                    # 房间为空则标记删除
                    if len(room.players) == 0:
                        rooms_to_close.append(room_id)

            # 删除空房间
            for room_id in rooms_to_close:
                del self.rooms[room_id]
                self._trigger_room_event("ROOM_CLOSED", {
                    "room_id": room_id,
                    "client_ids": [],
                    "reason": "所有玩家离开"
                })

    def handle_piece_placement(self, room_id: str, user_id: str, x: int, y: int) -> Dict:
        """处理落子请求"""
        with self.room_lock:
            room = self.rooms.get(room_id)
            if not room:
                return {"success": False, "message": "房间不存在"}
            if user_id not in room.players:
                return {"success": False, "message": "不在房间内，无法落子"}
            if not room.game_active:
                return {"success": False, "message": "游戏未开始"}

            # 房间处理落子
            result = room.place_piece(user_id, x, y)
            return {
                "success": result["success"],
                "message": result.get("message", ""),
                "color": result.get("color"),
                "game_end": result.get("game_end", False),
                "game_result": result.get("game_result"),
                "room": room
            }

    def close_all_rooms(self, reason: str = "服务器关闭"):
        """关闭所有房间"""
        with self.room_lock:
            room_ids = list(self.rooms.keys())
            for room_id in room_ids:
                room = self.rooms[room_id]
                client_ids = list(room.players.values())
                # 触发房间关闭事件
                self._trigger_room_event("ROOM_CLOSED", {
                    "room_id": room_id,
                    "client_ids": client_ids,
                    "reason": reason
                })
                # 删除房间
                del self.rooms[room_id]

    def start_room_cleanup_timer(self):
        """启动房间清理定时器（清理超时无活动房间）"""
        while True:
            time.sleep(self.cleanup_interval)
            self._cleanup_timeout_rooms()

    def _cleanup_timeout_rooms(self):
        """清理超时无活动房间"""
        current_time = time.time()
        timeout_rooms = []
        with self.room_lock:
            for room_id, room in self.rooms.items():
                # 计算最后活动时间（最后落子时间或最后玩家加入时间）
                last_active = max(room.last_move_time, room.last_member_change_time)
                if current_time - last_active > self.room_timeout:
                    timeout_rooms.append(room_id)

            # 关闭超时房间
            for room_id in timeout_rooms:
                room = self.rooms[room_id]
                client_ids = list(room.players.values())
                self._trigger_room_event("ROOM_TIMEOUT", {
                    "room_id": room_id,
                    "client_ids": client_ids
                })
                del self.rooms[room_id]
                self.logger.info(f"清理超时房间：room_id={room_id}，超时时间={self.room_timeout}秒")

    def _get_user_nickname(self, user_id: str) -> str:
        """获取用户昵称（从存储层查询）"""
        from Storage.user_storage import UserStorage
        user_storage = UserStorage()
        user_data = user_storage.load_user(user_id)
        return user_data["nickname"] if user_data else f"用户_{user_id[:6]}"

    def set_room_event_callback(self, callback: callable):
        """设置房间事件回调（通知主服务器）"""
        self.room_event_callback = callback

    def _trigger_room_event(self, event_type: str, data: Dict):
        """触发房间事件"""
        if hasattr(self, "room_event_callback") and callable(self.room_event_callback):
            self.room_event_callback(event_type, data)
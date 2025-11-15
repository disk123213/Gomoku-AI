import threading
import signal
import time
from typing import Dict, Optional, List
from Common.config import Config
from Common.logger import Logger
from Server.tcp_server import TCPServer
from Server.room_manager import RoomManager
from Server.live_stream import LiveStreamManager
from Server.p2p_client import P2PClient
from Server.data_sync import DataSyncManager

class MainServer:
    """主服务器（单例模式）- 统筹客户端、房间、直播、P2P连接"""
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
        self.config = Config.get_instance()
        self.logger = Logger.get_instance()
        self.running = False

        # 初始化核心组件
        self.tcp_server = TCPServer(
            host=self.config.get("NETWORK", "server_host", "0.0.0.0"),
            port=self.config.get_int("NETWORK", "server_port", 8888)
        )
        self.room_manager = RoomManager()
        self.live_manager = LiveStreamManager(
            host=self.config.get("NETWORK", "live_host", "0.0.0.0"),
            port=self.config.get_int("NETWORK", "live_port", 9999)
        )
        self.p2p_client = P2PClient()
        self.data_sync = DataSyncManager()

        # 注册组件回调（客户端消息交给处理器，房间事件触发广播/直播）
        self.tcp_server.set_client_handler_callback(self._on_client_message)
        self.room_manager.set_room_event_callback(self._on_room_event)

        # 注册信号处理（优雅关闭）
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _on_client_message(self, client_id: str, message: Dict):
        """客户端消息回调 - 分发到对应模块处理"""
        msg_type = message.get("type")
        self.logger.debug(f"主服务器接收消息：客户端={client_id}，类型={msg_type}")

        try:
            # 登录/注册（用户数据存储）
            if msg_type == "LOGIN":
                self._handle_login(client_id, message)
            # 房间相关（创建/加入/离开/落子）
            elif msg_type in ["CREATE_ROOM", "JOIN_ROOM", "LEAVE_ROOM", "PLACE_PIECE"]:
                self._handle_room_message(client_id, message)
            # 直播相关（创建直播间/加入观看/发送直播数据）
            elif msg_type in ["CREATE_LIVE", "JOIN_LIVE", "BROADCAST_LIVE_DATA"]:
                self._handle_live_message(client_id, message)
            # P2P连接相关（请求对等方地址/确认P2P连接）
            elif msg_type in ["REQUEST_P2P_ADDR", "CONFIRM_P2P_CONNECT"]:
                self._handle_p2p_message(client_id, message)
            # 数据同步相关（请求增量数据/校验数据）
            elif msg_type in ["REQUEST_INCREMENTAL_DATA", "VERIFY_DATA"]:
                self._handle_sync_message(client_id, message)
            else:
                self.tcp_server.send_message(client_id, {"type": "ERROR", "message": "不支持的消息类型"})
        except Exception as e:
            self.logger.error(f"处理客户端消息失败：{str(e)}")
            self.tcp_server.send_message(client_id, {"type": "ERROR", "message": f"处理失败：{str(e)}"})

    def _handle_login(self, client_id: str, message: Dict):
        """处理登录请求 - 校验用户数据，返回登录结果"""
        from Storage.user_storage import UserStorage
        user_storage = UserStorage()
        user_id = message.get("user_id")
        user_name = message.get("user_name", f"用户_{client_id[:6]}")

        # 查找/创建用户
        user_data = user_storage.load_user(user_id)
        if not user_data:
            user_data = {
                "user_id": user_id,
                "nickname": user_name,
                "register_time": time.time(),
                "last_login_time": time.time()
            }
            user_storage.save_user(user_id, user_data)
        else:
            user_data["last_login_time"] = time.time()
            user_storage.save_user(user_id, user_data)

        # 绑定客户端与用户ID
        self.tcp_server.bind_client_user(client_id, user_id)
        self.tcp_server.send_message(client_id, {
            "type": "LOGIN_SUCCESS",
            "data": {"user_id": user_id, "nickname": user_data["nickname"], "room_list": self.room_manager.get_room_list_summary()}
        })
        self.logger.info(f"客户端登录成功：client_id={client_id}，user_id={user_id}")

    def _handle_room_message(self, client_id: str, message: Dict):
        """处理房间相关消息"""
        user_id = self.tcp_server.get_user_id_by_client(client_id)
        if not user_id:
            self.tcp_server.send_message(client_id, {"type": "ERROR", "message": "请先登录"})
            return

        msg_type = message.get("type")
        room_id = message.get("room_id")
        # 创建房间
        if msg_type == "CREATE_ROOM":
            room = self.room_manager.create_room(
                host_user_id=user_id,
                host_client_id=client_id,
                game_mode=message.get("game_mode", "PVE"),
                ai_level=message.get("ai_level", "HARD")
            )
            self.tcp_server.send_message(client_id, {
                "type": "ROOM_CREATED",
                "data": {"room_id": room.room_id, "room_info": room.get_room_info()}
            })
        # 加入房间
        elif msg_type == "JOIN_ROOM":
            result = self.room_manager.add_player_to_room(room_id, user_id, client_id)
            if result["success"]:
                self.tcp_server.send_message(client_id, {
                    "type": "JOIN_ROOM_SUCCESS",
                    "data": {"room_info": result["room"].get_room_info()}
                })
                # 广播房间成员变化
                result["room"].broadcast_message({
                    "type": "ROOM_MEMBER_CHANGE",
                    "data": {"user_id": user_id, "action": "join", "member_list": result["room"].get_member_list()}
                })
            else:
                self.tcp_server.send_message(client_id, {"type": "ERROR", "message": result["message"]})
        # 离开房间
        elif msg_type == "LEAVE_ROOM":
            result = self.room_manager.remove_player_from_room(room_id, user_id, client_id)
            if result["success"]:
                self.tcp_server.send_message(client_id, {"type": "LEAVE_ROOM_SUCCESS"})
                if result["room"]:
                    result["room"].broadcast_message({
                        "type": "ROOM_MEMBER_CHANGE",
                        "data": {"user_id": user_id, "action": "leave", "member_list": result["room"].get_member_list()}
                    })
            else:
                self.tcp_server.send_message(client_id, {"type": "ERROR", "message": result["message"]})
        # 落子
        elif msg_type == "PLACE_PIECE":
            x = message.get("x")
            y = message.get("y")
            result = self.room_manager.handle_piece_placement(room_id, user_id, x, y)
            if result["success"]:
                # 广播落子信息
                result["room"].broadcast_message({
                    "type": "PIECE_PLACED",
                    "data": {
                        "x": x,
                        "y": y,
                        "user_id": user_id,
                        "color": result["color"],
                        "board": result["room"].board,
                        "move_history": result["room"].move_history
                    }
                })
                # 检查游戏结束
                if result["game_end"]:
                    result["room"].broadcast_message({
                        "type": "GAME_END",
                        "data": result["game_result"]
                    })
                    # 保存对战记录
                    self._save_game_record(result["room"], result["game_result"])
            else:
                self.tcp_server.send_message(client_id, {"type": "ERROR", "message": result["message"]})

    def _handle_live_message(self, client_id: str, message: Dict):
        """处理直播相关消息"""
        user_id = self.tcp_server.get_user_id_by_client(client_id)
        if not user_id:
            self.tcp_server.send_message(client_id, {"type": "ERROR", "message": "请先登录"})
            return

        msg_type = message.get("type")
        # 创建直播间（主播）
        if msg_type == "CREATE_LIVE":
            room_id = message.get("room_id")
            room = self.room_manager.get_room(room_id)
            if not room or room.host_user_id != user_id:
                self.tcp_server.send_message(client_id, {"type": "ERROR", "message": "无权限创建直播间（需为房间房主）"})
                return

            # 启动直播服务器（首次启动）
            if not self.live_manager.running:
                self.live_manager.start_server()

            # 创建直播间
            live_room_id = self.live_manager.create_live_room(user_id, self.tcp_server.get_user_nickname(user_id), room_id)
            self.tcp_server.send_message(client_id, {
                "type": "LIVE_CREATED",
                "data": {"live_room_id": live_room_id, "room_id": room_id}
            })
            self.logger.info(f"主播创建直播间：user_id={user_id}，live_room_id={live_room_id}，room_id={room_id}")
        # 加入直播间（观众）
        elif msg_type == "JOIN_LIVE":
            live_room_id = message.get("live_room_id")
            if not self.live_manager.running:
                self.live_manager.start_server()

            # 加入直播间（返回WebSocket连接信息）
            result = self.live_manager.add_viewer(live_room_id, user_id, self.tcp_server.get_user_nickname(user_id))
            if result["success"]:
                self.tcp_server.send_message(client_id, {
                    "type": "JOIN_LIVE_SUCCESS",
                    "data": {
                        "live_room_id": live_room_id,
                        "ws_url": f"ws://{self.config.get('NETWORK', 'live_host')}:{self.config.get('NETWORK', 'live_port')}",
                        "room_id": result["room_id"]
                    }
                })
            else:
                self.tcp_server.send_message(client_id, {"type": "ERROR", "message": result["message"]})
        # 广播直播数据（主播）
        elif msg_type == "BROADCAST_LIVE_DATA":
            live_room_id = message.get("live_room_id")
            self.live_manager.broadcast_live_data(live_room_id, message.get("data"))

    def _handle_p2p_message(self, client_id: str, message: Dict):
        """处理P2P连接相关消息"""
        user_id = self.tcp_server.get_user_id_by_client(client_id)
        if not user_id:
            self.tcp_server.send_message(client_id, {"type": "ERROR", "message": "请先登录"})
            return

        msg_type = message.get("type")
        room_id = message.get("room_id")
        room = self.room_manager.get_room(room_id)
        if not room:
            self.tcp_server.send_message(client_id, {"type": "ERROR", "message": "房间不存在"})
            return

        # 请求P2P对等方地址
        if msg_type == "REQUEST_P2P_ADDR":
            peer_client_id = room.get_peer_client_id(user_id)
            if not peer_client_id:
                self.tcp_server.send_message(client_id, {"type": "ERROR", "message": "未找到对等玩家"})
                return

            # 获取对等方IP和端口（假设客户端已上报）
            peer_addr = self.tcp_server.get_client_addr(peer_client_id)
            if peer_addr:
                self.tcp_server.send_message(client_id, {
                    "type": "P2P_ADDR_RESPONSE",
                    "data": {"peer_addr": peer_addr, "room_id": room_id}
                })
                # 通知对等方准备P2P连接
                self.tcp_server.send_message(peer_client_id, {
                    "type": "P2P_CONNECT_REQUEST",
                    "data": {"peer_user_id": user_id, "peer_addr": self.tcp_server.get_client_addr(client_id)}
                })
        # 确认P2P连接
        elif msg_type == "CONFIRM_P2P_CONNECT":
            peer_user_id = message.get("peer_user_id")
            peer_client_id = self.tcp_server.get_client_by_user_id(peer_user_id)
            if peer_client_id:
                self.tcp_server.send_message(peer_client_id, {
                    "type": "P2P_CONNECT_CONFIRMED",
                    "data": {"peer_user_id": user_id}
                })

    def _handle_sync_message(self, client_id: str, message: Dict):
        """处理数据同步相关消息"""
        msg_type = message.get("type")
        room_id = message.get("room_id")
        room = self.room_manager.get_room(room_id)
        if not room:
            self.tcp_server.send_message(client_id, {"type": "ERROR", "message": "房间不存在"})
            return

        # 请求增量数据
        if msg_type == "REQUEST_INCREMENTAL_DATA":
            last_sync_timestamp = message.get("last_sync_timestamp", 0)
            # 获取增量数据（落子历史中时间戳大于last_sync_timestamp的部分）
            incremental_data = room.get_incremental_data(last_sync_timestamp)
            # 计算CRC校验码
            crc_code = self.data_sync.calculate_crc(incremental_data)
            self.tcp_server.send_message(client_id, {
                "type": "INCREMENTAL_DATA_RESPONSE",
                "data": {
                    "incremental_data": incremental_data,
                    "crc_code": crc_code,
                    "current_timestamp": time.time()
                }
            })
        # 校验数据
        elif msg_type == "VERIFY_DATA":
            data = message.get("data")
            received_crc = message.get("crc_code")
            calculated_crc = self.data_sync.calculate_crc(data)
            self.tcp_server.send_message(client_id, {
                "type": "DATA_VERIFY_RESULT",
                "data": {"valid": received_crc == calculated_crc}
            })

    def _on_room_event(self, event_type: str, data: Dict):
        """房间事件回调（如房间关闭、超时）"""
        if event_type == "ROOM_CLOSED":
            room_id = data["room_id"]
            self.logger.info(f"房间关闭：room_id={room_id}，原因={data['reason']}")
            # 通知所有房间成员
            for client_id in data["client_ids"]:
                self.tcp_server.send_message(client_id, {
                    "type": "ROOM_CLOSED",
                    "data": {"room_id": room_id, "reason": data["reason"]}
                })
        elif event_type == "ROOM_TIMEOUT":
            self._on_room_event("ROOM_CLOSED", {
                "room_id": data["room_id"],
                "client_ids": data["client_ids"],
                "reason": "房间超时未活动"
            })

    def _save_game_record(self, room, game_result: Dict):
        """保存对战记录到存储层"""
        from Storage.game_record_storage import GameRecordStorage
        record_storage = GameRecordStorage()
        record = {
            "room_id": room.room_id,
            "game_mode": room.game_mode,
            "ai_level": room.ai_level,
            "player_info": room.get_player_info(),
            "move_history": room.move_history,
            "game_result": game_result,
            "start_time": room.start_time,
            "end_time": time.time(),
            "duration": time.time() - room.start_time
        }
        record_storage.save_game_record(record)
        self.logger.info(f"保存对战记录：room_id={room.room_id}，result={game_result['winner']}")

    def _handle_signal(self, signum, frame):
        """处理系统信号（优雅关闭服务器）"""
        self.logger.info(f"收到信号 {signum}，正在关闭服务器...")
        self.running = False
        # 停止各个组件
        self.tcp_server.stop()
        self.live_manager.stop_server()
        self.room_manager.close_all_rooms(reason="服务器关闭")
        self.logger.info("服务器已优雅关闭")

    def start(self):
        """启动主服务器"""
        self.logger.info("启动五子棋AI对战主服务器...")
        self.running = True
        # 启动TCP服务器（异步线程）
        self.tcp_server.start()
        # 启动房间清理定时器（每60秒清理超时房间）
        threading.Thread(target=self.room_manager.start_room_cleanup_timer, daemon=True).start()
        self.logger.info(f"服务器启动成功，监听TCP端口：{self.tcp_server.port}，直播端口：{self.config.get('NETWORK', 'live_port')}")

        # 保持主进程运行
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self._handle_signal(signal.SIGINT, None)

if __name__ == "__main__":
    # 启动主服务器
    main_server = MainServer()
    main_server.start()
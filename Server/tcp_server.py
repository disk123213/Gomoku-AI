import socket
import threading
import json
from typing import Dict, Optional, List
from Common.logger import Logger
from Common.config import Config

class TCPServer:
    """TCP服务器（底层通信，处理客户端连接与消息收发）"""
    def __init__(self, host: str = "0.0.0.0", port: int = 8888, buffer_size: int = 4096):
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.logger = Logger.get_instance()
        self.config = Config.get_instance()

        # 服务器状态
        self.running = False
        self.server_socket: Optional[socket.socket] = None

        # 客户端管理：client_id -> (socket, addr, user_id)
        self.clients: Dict[str, Dict] = {}
        self.client_id_counter = 0
        self.client_lock = threading.Lock()

        # 客户端-用户ID映射：client_id -> user_id，user_id -> client_id
        self.client_user_map: Dict[str, str] = {}
        self.user_client_map: Dict[str, str] = {}

        # 消息处理回调（交给主服务器）
        self.message_callback: Optional[callable] = None

    def set_client_handler_callback(self, callback: callable):
        """设置客户端消息处理回调"""
        self.message_callback = callback

    def _generate_client_id(self) -> str:
        """生成唯一客户端ID"""
        with self.client_lock:
            self.client_id_counter += 1
            return f"client_{self.client_id_counter}"

    def bind_client_user(self, client_id: str, user_id: str):
        """绑定客户端ID与用户ID"""
        with self.client_lock:
            self.client_user_map[client_id] = user_id
            self.user_client_map[user_id] = client_id

    def get_user_id_by_client(self, client_id: str) -> Optional[str]:
        """通过客户端ID获取用户ID"""
        return self.client_user_map.get(client_id)

    def get_client_by_user_id(self, user_id: str) -> Optional[str]:
        """通过用户ID获取客户端ID"""
        return self.user_client_map.get(user_id)

    def get_client_addr(self, client_id: str) -> Optional[Tuple[str, int]]:
        """获取客户端地址（IP, 端口）"""
        with self.client_lock:
            client = self.clients.get(client_id)
            return client["addr"] if client else None

    def get_user_nickname(self, user_id: str) -> str:
        """获取用户昵称（从存储层查询）"""
        from Storage.user_storage import UserStorage
        user_storage = UserStorage()
        user_data = user_storage.load_user(user_id)
        return user_data["nickname"] if user_data else f"用户_{user_id[:6]}"

    def send_message(self, client_id: str, message: Dict):
        """向指定客户端发送消息"""
        with self.client_lock:
            client = self.clients.get(client_id)
            if not client or not client["socket"].connected:
                self.logger.warning(f"客户端不存在或已断开：client_id={client_id}")
                return

        try:
            # 序列化消息（JSON）
            msg_str = json.dumps(message, ensure_ascii=False)
            # 发送（添加换行符作为消息结束标记）
            client["socket"].send(f"{msg_str}\n".encode("utf-8"))
        except Exception as e:
            self.logger.error(f"发送消息失败：client_id={client_id}，错误={str(e)}")
            self._remove_client(client_id, reason="发送消息失败")

    def broadcast_message(self, client_ids: List[str], message: Dict):
        """向多个客户端广播消息"""
        for client_id in client_ids:
            self.send_message(client_id, message)

    def _handle_client_connection(self, client_socket: socket.socket, client_addr: Tuple[str, int]):
        """处理单个客户端连接"""
        client_id = self._generate_client_id()
        with self.client_lock:
            self.clients[client_id] = {
                "socket": client_socket,
                "addr": client_addr,
                "connected": True,
                "last_active_time": time.time()
            }
        self.logger.info(f"新客户端连接：client_id={client_id}，addr={client_addr}")

        buffer = ""
        try:
            while self.running and self.clients[client_id]["connected"]:
                # 接收数据
                data = client_socket.recv(self.buffer_size).decode("utf-8")
                if not data:
                    break

                buffer += data
                # 按换行符分割消息（处理粘包）
                while "\n" in buffer:
                    msg_str, buffer = buffer.split("\n", 1)
                    if not msg_str.strip():
                        continue

                    # 解析消息
                    try:
                        message = json.loads(msg_str)
                        # 更新最后活动时间
                        with self.client_lock:
                            self.clients[client_id]["last_active_time"] = time.time()
                        # 回调处理消息
                        if self.message_callback:
                            self.message_callback(client_id, message)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"解析客户端消息失败：client_id={client_id}，消息={msg_str}，错误={str(e)}")
                        self.send_message(client_id, {"type": "ERROR", "message": "消息格式错误"})
        except Exception as e:
            self.logger.error(f"客户端连接异常：client_id={client_id}，错误={str(e)}")
        finally:
            self._remove_client(client_id, reason="连接断开")

    def _remove_client(self, client_id: str, reason: str):
        """移除客户端连接"""
        with self.client_lock:
            client = self.clients.get(client_id)
            if not client:
                return

            # 关闭socket
            try:
                client["socket"].close()
            except:
                pass

            # 解绑用户ID
            user_id = self.client_user_map.pop(client_id, None)
            if user_id:
                self.user_client_map.pop(user_id, None)

            # 移除客户端
            del self.clients[client_id]

        self.logger.info(f"客户端断开连接：client_id={client_id}，原因={reason}")

        # 通知房间管理器移除该客户端
        from Server.room_manager import RoomManager
        RoomManager.get_instance().remove_client_from_all_rooms(client_id)

    def start(self):
        """启动TCP服务器（异步线程）"""
        threading.Thread(target=self._run_server, daemon=True).start()

    def _run_server(self):
        """运行TCP服务器主循环"""
        self.running = True
        try:
            # 创建服务器socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(10)  # 最大监听队列
            self.logger.info(f"TCP服务器启动，监听 {self.host}:{self.port}")

            while self.running:
                try:
                    # 接受客户端连接（非阻塞）
                    self.server_socket.settimeout(1.0)
                    client_socket, client_addr = self.server_socket.accept()
                    client_socket.settimeout(None)  # 客户端连接设为阻塞
                    # 启动线程处理客户端
                    threading.Thread(
                        target=self._handle_client_connection,
                        args=(client_socket, client_addr),
                        daemon=True
                    ).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.logger.error(f"TCP服务器异常：{str(e)}")
        finally:
            self.stop()

    def stop(self):
        """停止TCP服务器"""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass

        # 关闭所有客户端连接
        with self.client_lock:
            client_ids = list(self.clients.keys())
        for client_id in client_ids:
            self._remove_client(client_id, reason="服务器停止")

        self.logger.info("TCP服务器已停止")
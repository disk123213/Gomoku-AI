from typing import Dict, Optional
from Common.logger import Logger
from Common.constants import MSG_TYPES

class ClientHandler:
    """客户端消息处理器（解析消息+分发逻辑）"""
    def __init__(self, main_server):
        self.main_server = main_server
        self.logger = Logger.get_instance()

    def parse_message(self, client_id: str, raw_message: str) -> Optional[Dict]:
        """解析客户端原始消息（JSON字符串）"""
        try:
            message = json.loads(raw_message)
            # 校验消息必填字段
            if "type" not in message:
                self.logger.warning(f"消息缺少type字段：client_id={client_id}，消息={raw_message}")
                return None
            return message
        except json.JSONDecodeError as e:
            self.logger.error(f"消息解析失败：client_id={client_id}，错误={str(e)}，消息={raw_message}")
            self.main_server.tcp_server.send_message(client_id, {
                "type": MSG_TYPES["ERROR"],
                "message": "消息格式错误，请发送JSON格式"
            })
            return None

    def handle_message(self, client_id: str, message: Dict):
        """处理解析后的消息（分发到主服务器对应逻辑）"""
        msg_type = message["type"]
        self.logger.debug(f"处理客户端消息：client_id={client_id}，type={msg_type}")

        # 路由到主服务器的对应处理方法
        if msg_type in ["LOGIN", "REGISTER"]:
            self.main_server._handle_login(client_id, message)
        elif msg_type in ["CREATE_ROOM", "JOIN_ROOM", "LEAVE_ROOM", "PLACE_PIECE"]:
            self.main_server._handle_room_message(client_id, message)
        elif msg_type in ["CREATE_LIVE", "JOIN_LIVE", "BROADCAST_LIVE_DATA", "SEND_CHAT"]:
            self.main_server._handle_live_message(client_id, message)
        elif msg_type in ["REQUEST_P2P_ADDR", "CONFIRM_P2P_CONNECT"]:
            self.main_server._handle_p2p_message(client_id, message)
        elif msg_type in ["REQUEST_INCREMENTAL_DATA", "VERIFY_DATA"]:
            self.main_server._handle_sync_message(client_id, message)
        else:
            self.logger.warning(f"未知消息类型：client_id={client_id}，type={msg_type}")
            self.main_server.tcp_server.send_message(client_id, {
                "type": MSG_TYPES["ERROR"],
                "message": f"未知消息类型：{msg_type}"
            })
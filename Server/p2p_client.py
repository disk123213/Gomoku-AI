import socket
import threading
import time
from typing import Dict, Optional, Tuple
from Common.logger import Logger
from Common.config import Config
from Common.data_utils import DataUtils

class P2PClient:
    """P2P客户端模块 - 处理低延迟直连"""
    def __init__(self):
        self.config = Config.get_instance()
        self.logger = Logger.get_instance()

        # P2P连接状态：(peer_user_id, peer_addr) -> socket
        self.p2p_connections: Dict[Tuple[str, Tuple[str, int]], socket.socket] = {}
        self.p2p_lock = threading.Lock()

        # 数据同步配置
        self.buffer_size = 4096
        self.reconnect_interval = 3
        self.p2p_timeout = 10

    def connect_peer(self, peer_addr: Tuple[str, int], user_id: str, peer_user_id: str) -> Optional[socket.socket]:
        """连接对等方"""
        key = (peer_user_id, peer_addr)
        with self.p2p_lock:
            if key in self.p2p_connections:
                return self.p2p_connections[key]

        # 创建P2P socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.p2p_timeout)
            sock.connect(peer_addr)
            self.logger.info(f"P2P连接成功：user_id={user_id}，peer_user_id={peer_user_id}，peer_addr={peer_addr}")

            with self.p2p_lock:
                self.p2p_connections[key] = sock
            return sock
        except Exception as e:
            self.logger.error(f"P2P连接失败：user_id={user_id}，peer_addr={peer_addr}，错误={str(e)}")
            return None

    def send_p2p_data(self, peer_user_id: str, peer_addr: Tuple[str, int], data: Dict) -> bool:
        """通过P2P发送数据"""
        key = (peer_user_id, peer_addr)
        with self.p2p_lock:
            sock = self.p2p_connections.get(key)
            if not sock:
                return False

        try:
            # 序列化+压缩数据
            json_str = json.dumps(data, ensure_ascii=False)
            compressed_data = DataUtils.compress_data(json_str.encode("utf-8"))
            # 发送（添加长度前缀）
            length = len(compressed_data).to_bytes(4, byteorder="big")
            sock.sendall(length + compressed_data)
            return True
        except Exception as e:
            self.logger.error(f"P2P发送数据失败：peer_user_id={peer_user_id}，错误={str(e)}")
            self.close_connection(peer_user_id, peer_addr)
            return False

    def receive_p2p_data(self, sock: socket.socket) -> Optional[Dict]:
        """接收P2P数据"""
        try:
            # 读取长度前缀
            length_data = sock.recv(4)
            if not length_data:
                return None
            data_length = int.from_bytes(length_data, byteorder="big")

            # 读取数据
            compressed_data = b""
            while len(compressed_data) < data_length:
                chunk = sock.recv(min(self.buffer_size, data_length - len(compressed_data)))
                if not chunk:
                    return None
                compressed_data += chunk

            # 解压+反序列化
            json_str = DataUtils.decompress_data(compressed_data).decode("utf-8")
            return json.loads(json_str)
        except Exception as e:
            self.logger.error(f"P2P接收数据失败：错误={str(e)}")
            return None

    def close_connection(self, peer_user_id: str, peer_addr: Tuple[str, int]):
        """关闭P2P连接"""
        key = (peer_user_id, peer_addr)
        with self.p2p_lock:
            sock = self.p2p_connections.pop(key, None)
            if sock:
                try:
                    sock.close()
                except:
                    pass
        self.logger.info(f"P2P连接关闭：peer_user_id={peer_user_id}，peer_addr={peer_addr}")

    def start_listener(self, bind_addr: Tuple[str, int], callback: callable):
        """启动P2P监听（接收对等方连接）"""
        def listener_loop():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(bind_addr)
                sock.listen(5)
                self.logger.info(f"P2P监听启动：bind_addr={bind_addr}")

                while True:
                    client_sock, client_addr = sock.accept()
                    threading.Thread(
                        target=self._handle_peer_connection,
                        args=(client_sock, client_addr, callback),
                        daemon=True
                    ).start()
            except Exception as e:
                self.logger.error(f"P2P监听异常：bind_addr={bind_addr}，错误={str(e)}")

        threading.Thread(target=listener_loop, daemon=True).start()

    def _handle_peer_connection(self, sock: socket.socket, peer_addr: Tuple[str, int], callback: callable):
        """处理对等方主动连接"""
        self.logger.info(f"收到P2P主动连接：peer_addr={peer_addr}")
        try:
            while True:
                data = self.receive_p2p_data(sock)
                if not data:
                    break
                callback(peer_addr, data)
        finally:
            sock.close()
            self.logger.info(f"P2P主动连接关闭：peer_addr={peer_addr}")
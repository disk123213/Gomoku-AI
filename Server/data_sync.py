import json
import zlib
import crcmod
import time
import threading
from typing import List, Dict, Optional, Callable
from Common.logger import Logger
from Common.data_utils import DataUtils

class DataSyncManager:
    """数据同步管理器（增量同步+CRC校验，兼容联机对战）"""
    def __init__(self):
        self.logger = Logger.get_instance()
        self.crc32 = crcmod.predefined.Crc('crc-32')  # CRC校验器
        self.sync_lock = threading.Lock()
        # 同步状态缓存：room_id -> {last_sync_timestamp, last_board_state, pending_data}
        self.sync_state: Dict[str, Dict] = {}

    def init_sync_state(self, room_id: str, init_board: List[List[int]]):
        """初始化同步状态（房间创建时调用）"""
        with self.sync_lock:
            self.sync_state[room_id] = {
                'last_sync_timestamp': time.time(),
                'last_board_str': DataUtils.board_to_str(init_board),
                'pending_data': []  # 待同步数据队列
            }
        self.logger.info(f"初始化同步状态：房间 {room_id}")

    def generate_sync_data(self, room_id: str, current_board: List[List[int]], move_data: Dict) -> Optional[bytes]:
        """生成增量同步数据（减少传输量）"""
        with self.sync_lock:
            if room_id not in self.sync_state:
                self.logger.error(f"同步状态未初始化：房间 {room_id}")
                return None

            state = self.sync_state[room_id]
            current_board_str = DataUtils.board_to_str(current_board)

            # 生成增量数据（仅传输差异）
            sync_data = {
                'type': 'move',
                'move': move_data,
                'timestamp': time.time(),
                'crc32': self._calc_crc32(current_board_str)
            }

            # 定期全量同步（每10步或差异过大时）
            if len(state['last_board_str']) != len(current_board_str) or len(move_data.get('move_history', [])) % 10 == 0:
                sync_data['full_board'] = current_board_str
                state['last_board_str'] = current_board_str

            # 序列化+压缩
            json_str = json.dumps(sync_data, ensure_ascii=False)
            compressed_data = zlib.compress(json_str.encode('utf-8'), level=2)
            state['last_sync_timestamp'] = sync_data['timestamp']

            return compressed_data

    def parse_sync_data(self, room_id: str, compressed_data: bytes) -> Optional[Dict]:
        """解析同步数据（校验+解压+增量合并）"""
        try:
            # 解压
            json_str = zlib.decompress(compressed_data).decode('utf-8')
            sync_data = json.loads(json_str)

            # CRC校验（全量数据必校验）
            if 'full_board' in sync_data:
                calc_crc = self._calc_crc32(sync_data['full_board'])
                if calc_crc != sync_data['crc32']:
                    self.logger.error(f"CRC校验失败：房间 {room_id}")
                    return None

            with self.sync_lock:
                if room_id not in self.sync_state:
                    self.logger.error(f"同步状态未初始化：房间 {room_id}")
                    return None

                state = self.sync_state[room_id]
                # 合并增量数据
                if 'full_board' in sync_data:
                    # 全量更新
                    state['last_board_str'] = sync_data['full_board']
                    state['last_sync_timestamp'] = sync_data['timestamp']
                    return {
                        'type': sync_data['type'],
                        'move': sync_data['move'],
                        'board': DataUtils.str_to_board(sync_data['full_board']),
                        'timestamp': sync_data['timestamp']
                    }
                else:
                    # 增量更新（基于上次棋盘）
                    last_board = DataUtils.str_to_board(state['last_board_str'])
                    move = sync_data['move']
                    x, y = move['x'], move['y']
                    color = move['color']
                    # 应用落子
                    last_board[x][y] = color
                    # 更新缓存
                    state['last_board_str'] = DataUtils.board_to_str(last_board)
                    state['last_sync_timestamp'] = sync_data['timestamp']
                    return {
                        'type': sync_data['type'],
                        'move': move,
                        'board': last_board,
                        'timestamp': sync_data['timestamp']
                    }
        except Exception as e:
            self.logger.error(f"解析同步数据失败：{str(e)}")
            return None

    def add_pending_data(self, room_id: str, data: Dict):
        """添加待同步数据（断线重连时使用）"""
        with self.sync_lock:
            if room_id not in self.sync_state:
                return
            self.sync_state[room_id]['pending_data'].append(data)
            # 限制队列大小
            if len(self.sync_state[room_id]['pending_data']) > 50:
                self.sync_state[room_id]['pending_data'].pop(0)

    def get_pending_data(self, room_id: str) -> List[Dict]:
        """获取待同步数据（断线重连后调用）"""
        with self.sync_lock:
            if room_id not in self.sync_state:
                return []
            pending = self.sync_state[room_id]['pending_data']
            self.sync_state[room_id]['pending_data'] = []
            return pending

    def clear_sync_state(self, room_id: str):
        """清理同步状态（房间关闭时调用）"""
        with self.sync_lock:
            if room_id in self.sync_state:
                del self.sync_state[room_id]
        self.logger.info(f"清理同步状态：房间 {room_id}")

    def _calc_crc32(self, data_str: str) -> int:
        """计算CRC32校验码（内部使用）"""
        self.crc32.reset()
        self.crc32.update(data_str.encode('utf-8'))
        return self.crc32.crcValue
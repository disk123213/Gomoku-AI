import os
import json
import time
import random
import hashlib
from typing import List, Tuple, Dict, Optional, Any
import numpy as np
from Common.constants import PIECE_COLORS
from Common.config import Config
from Common.error_handler import StorageError

class DataUtils:
    """数据转换与工具类"""
    @staticmethod
    def board_to_str(board: List[List[int]]) -> str:
        """棋盘（二维列表）转字符串（便于存储/传输）"""
        try:
            return ';'.join(','.join(map(str, row)) for row in board)
        except Exception as e:
            raise StorageError(f"棋盘转字符串失败：{str(e)}", 6002)

    @staticmethod
    def str_to_board(board_str: str) -> List[List[int]]:
        """字符串转棋盘（二维列表）"""
        try:
            return [list(map(int, row.split(','))) for row in board_str.split(';')]
        except Exception as e:
            raise StorageError(f"字符串转棋盘失败：{str(e)}", 6002)

    @staticmethod
    def move_to_index(x: int, y: int, board_size: int) -> int:
        """落子坐标（x,y）转索引（一维）"""
        return x * board_size + y

    @staticmethod
    def index_to_move(index: int, board_size: int) -> Tuple[int, int]:
        """索引（一维）转落子坐标（x,y）"""
        x = index // board_size
        y = index % board_size
        return (x, y)

    @staticmethod
    def generate_unique_id(length: int = 16) -> str:
        """生成唯一ID（基于时间+随机数）"""
        timestamp = str(int(time.time() * 1000))
        random_str = ''.join(random.choices('0123456789abcdef', k=8))
        return hashlib.md5((timestamp + random_str).encode('utf-8')).hexdigest()[:length]

    @staticmethod
    def get_current_time_str() -> str:
        """获取当前时间字符串（YYYY-MM-DD HH:MM:SS）"""
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    @staticmethod
    def get_current_timestamp() -> int:
        """获取当前时间戳（秒）"""
        return int(time.time())

    @staticmethod
    def normalize_scores(scores: np.ndarray) -> np.ndarray:
        """归一化评分（0-255）"""
        if scores.max() == scores.min():
            return np.zeros_like(scores)
        return (scores - scores.min()) / (scores.max() - scores.min()) * 255

    @staticmethod
    def validate_board(board: List[List[int]], board_size: int) -> bool:
        """验证棋盘有效性"""
        if len(board) != board_size:
            return False
        for row in board:
            if len(row) != board_size:
                return False
            for val in row:
                if val not in [PIECE_COLORS.EMPTY, PIECE_COLORS.BLACK, PIECE_COLORS.WHITE]:
                    return False
        return True

    @staticmethod
    def save_json(data: Any, file_path: str) -> bool:
        """保存JSON文件（Win11兼容）"""
        try:
            dir_path = os.path.dirname(file_path)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            raise StorageError(f"保存JSON失败：{str(e)}", 6001)

    @staticmethod
    def load_json(file_path: str) -> Optional[Dict]:
        """加载JSON文件"""
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            raise StorageError(f"加载JSON失败：{str(e)}", 6001)

    @staticmethod
    def save_csv(data: List[Dict], file_path: str, headers: List[str]) -> bool:
        """保存CSV文件"""
        try:
            dir_path = os.path.dirname(file_path)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
            import csv
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(data)
            return True
        except Exception as e:
            raise StorageError(f"保存CSV失败：{str(e)}", 6001)

    @staticmethod
    def load_csv(file_path: str) -> Optional[List[Dict]]:
        """加载CSV文件"""
        if not os.path.exists(file_path):
            return None
        try:
            import csv
            with open(file_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                return list(reader)
        except Exception as e:
            raise StorageError(f"加载CSV失败：{str(e)}", 6001)

    @staticmethod
    def calculate_crc32(data: bytes) -> int:
        """计算CRC32校验码"""
        import zlib
        return zlib.crc32(data)

    @staticmethod
    def compress_data(data: str) -> bytes:
        """压缩数据（zlib）"""
        import zlib
        return zlib.compress(data.encode('utf-8'), level=2)

    @staticmethod
    def decompress_data(data: bytes) -> str:
        """解压数据（zlib）"""
        import zlib
        return zlib.decompress(data).decode('utf-8')

    @staticmethod
    def split_batch(data: List[Any], batch_size: int) -> List[List[Any]]:
        """数据分批"""
        batches = []
        for i in range(0, len(data), batch_size):
            batches.append(data[i:i+batch_size])
        return batches

    @staticmethod
    def shuffle_data(data: List[Any]) -> List[Any]:
        """数据洗牌（随机打乱）"""
        random.shuffle(data)
        return data

    @staticmethod
    def get_board_empty_positions(board: List[List[int]]) -> List[Tuple[int, int]]:
        """获取棋盘空位置"""
        empty_pos = []
        board_size = len(board)
        for i in range(board_size):
            for j in range(board_size):
                if board[i][j] == PIECE_COLORS.EMPTY:
                    empty_pos.append((i, j))
        return empty_pos

    @staticmethod
    def get_board_center(board_size: int) -> Tuple[int, int]:
        """获取棋盘中心点坐标"""
        return (board_size // 2, board_size // 2)

    @staticmethod
    def format_time(seconds: int) -> str:
        """格式化时间（秒转HH:MM:SS）"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @staticmethod
    def format_float(value: float, decimal: int = 2) -> float:
        """格式化浮点数（保留指定小数位）"""
        return round(value, decimal)

    @staticmethod
    def encrypt_password(password: str, salt: str = 'gobang_ai_salt') -> str:
        """密码加密（MD5+salt）"""
        return hashlib.md5((password + salt).encode('utf-8')).hexdigest()
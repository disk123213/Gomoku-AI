import json
import os
import time
from typing import List, Dict, Optional
from Common.logger import Logger
from Common.error_handler import StorageError
from Storage.base_storage import BaseStorage

class GameRecordStorage(BaseStorage):
    """对战记录存储（JSON格式，兼容历史记录和复盘）"""
    def __init__(self):
        super().__init__('./data/game_record')
        self.logger = Logger.get_instance()
        self.record_suffix = '.json'
        self.required_fields = ['mode', 'move_history', 'result', 'timestamp']

    def save_record(self, user_id: str, record_data: Dict) -> bool:
        """保存对战记录（自动补全必要字段）"""
        # 补全必要字段
        for field in self.required_fields:
            if field not in record_data:
                if field == 'timestamp':
                    record_data[field] = int(time.time())
                elif field == 'result':
                    record_data[field] = {'winner': 'draw', 'win_line': []}
                else:
                    record_data[field] = 'unknown' if field != 'move_history' else []
        
        # 生成文件名：user_{user_id}_record_{timestamp}.json
        timestamp = record_data['timestamp']
        filename = self._get_record_filename(user_id, timestamp)
        return self.save(record_data, filename)

    def load_user_records(self, user_id: str, limit: int = 10) -> List[Dict]:
        """加载用户对战记录（按时间倒序，默认最新10条）"""
        records = []
        # 遍历用户所有记录文件
        for filename in self.list_files(self.record_suffix):
            if filename.startswith(f"user_{user_id}_record_"):
                record = self.load(filename)
                if record:
                    records.append(record)
        
        # 按时间倒序排序，取前limit条
        records.sort(key=lambda x: x['timestamp'], reverse=True)
        return records[:limit]

    def load_record_by_timestamp(self, user_id: str, timestamp: int) -> Optional[Dict]:
        """按时间戳加载特定记录"""
        filename = self._get_record_filename(user_id, timestamp)
        return self.load(filename)

    def delete_record(self, user_id: str, timestamp: int) -> bool:
        """删除对战记录"""
        filename = self._get_record_filename(user_id, timestamp)
        return self.delete(filename)

    def get_record_count(self, user_id: str) -> int:
        """获取用户对战记录总数"""
        count = 0
        for filename in self.list_files(self.record_suffix):
            if filename.startswith(f"user_{user_id}_record_"):
                count += 1
        return count

    def _get_record_filename(self, user_id: str, timestamp: int) -> str:
        """生成对战记录文件名"""
        return f"user_{user_id}_record_{timestamp}{self.record_suffix}"

    def save(self, data: Dict, filename: str) -> bool:
        """实现抽象方法：保存为JSON文件"""
        file_path = self._get_file_path(filename)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"保存对战记录成功：{file_path}")
            return True
        except Exception as e:
            self.logger.error(f"保存对战记录失败：{str(e)}")
            raise StorageError(f"对战记录保存失败：{str(e)}", 5018)

    def load(self, filename: str) -> Optional[Dict]:
        """实现抽象方法：从JSON文件加载"""
        file_path = self._get_file_path(filename)
        if not self.exists(filename):
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.logger.info(f"加载对战记录成功：{file_path}")
            return data
        except Exception as e:
            self.logger.error(f"加载对战记录失败：{str(e)}")
            raise StorageError(f"对战记录加载失败：{str(e)}", 5019)
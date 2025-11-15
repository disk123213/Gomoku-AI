import json
import os
import csv
import pickle
import time
from typing import List, Dict, Optional, Union
from Common.logger import Logger
from Common.error_handler import StorageError
from Common.data_utils import DataUtils
from Storage.base_storage import BaseStorage

class TrainDataStorage(BaseStorage):
    """训练数据存储（支持CSV/二进制格式，兼容自我对弈和用户训练数据）"""
    def __init__(self):
        super().__init__('./data/train_data')
        self.logger = Logger.get_instance()
        self.csv_suffix = '.csv'
        self.bin_suffix = '.pkl'
        self.csv_columns = ['board', 'move', 'score', 'result', 'timestamp', 'model_type', 'difficulty']

    def save_train_data(self, user_id: str, train_data: List[Dict], format: str = 'csv') -> bool:
        """保存用户训练数据（支持CSV/二进制）"""
        if format not in ['csv', 'bin']:
            raise StorageError(f"不支持的存储格式：{format}，仅支持csv/bin", 5011)
        filename = f"user_{user_id}_train.{format}"
        return self.save(train_data, filename)

    def save_self_play_data(self, train_data: List[Dict], format: str = 'bin') -> bool:
        """保存自我对弈训练数据（默认二进制，效率更高）"""
        if format not in ['csv', 'bin']:
            raise StorageError(f"不支持的存储格式：{format}，仅支持csv/bin", 5012)
        timestamp = int(time.time())
        filename = f"self_play_data_{timestamp}.{format}"
        return self.save(train_data, filename)

    def load_train_data(self, user_id: str, format: str = 'csv', limit: int = None) -> Optional[List[Dict]]:
        """加载用户训练数据（指定格式和最大条数）"""
        filename = f"user_{user_id}_train.{format}"
        data = self.load(filename)
        if not data:
            return None
        if limit and len(data) > limit:
            return data[-limit:]  # 返回最新的limit条
        return data

    def load_self_play_data(self, timestamp: Optional[int] = None, format: str = 'bin') -> Optional[List[Dict]]:
        """加载自我对弈数据（指定时间戳，默认加载最新）"""
        if timestamp:
            filename = f"self_play_data_{timestamp}.{format}"
            return self.load(filename)
        # 加载最新的自我对弈数据
        files = self.list_files(self.bin_suffix) + self.list_files(self.csv_suffix)
        self_play_files = [f for f in files if f.startswith('self_play_data_')]
        if not self_play_files:
            return None
        self_play_files.sort(reverse=True)
        return self.load(self_play_files[0])

    def batch_merge_self_play_data(self, output_filename: str = 'merged_self_play.bin') -> bool:
        """批量合并自我对弈数据（二进制格式）"""
        try:
            merged_data = []
            # 读取所有自我对弈数据文件
            files = self.list_files(self.bin_suffix) + self.list_files(self.csv_suffix)
            self_play_files = [f for f in files if f.startswith('self_play_data_')]
            if not self_play_files:
                self.logger.warning("无自我对弈数据可合并")
                return False
            
            for file in self_play_files:
                data = self.load(file)
                if data:
                    merged_data.extend(data)
            
            # 保存合并后的数据
            output_path = self._get_file_path(output_filename)
            with open(output_path, 'wb') as f:
                pickle.dump(merged_data, f)
            
            self.logger.info(f"合并自我对弈数据成功：{output_filename}，共{len(merged_data)}条")
            return True
        except Exception as e:
            self.logger.error(f"合并自我对弈数据失败：{str(e)}")
            raise StorageError(f"训练数据合并失败：{str(e)}", 5013)

    def save(self, data: List[Dict], filename: str) -> bool:
        """实现抽象方法：根据后缀自动选择存储格式"""
        file_path = self._get_file_path(filename)
        try:
            if filename.endswith(self.csv_suffix):
                # CSV格式（追加模式，自动写表头）
                file_exists = os.path.exists(file_path)
                with open(file_path, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=self.csv_columns)
                    if not file_exists:
                        writer.writeheader()
                    # 确保每条数据包含所有列
                    for row in data:
                        for col in self.csv_columns:
                            if col not in row:
                                row[col] = '' if col != 'timestamp' else int(time.time())
                        writer.writerow(row)
                self.logger.info(f"保存CSV训练数据成功：{file_path}，新增{len(data)}条")
            elif filename.endswith(self.bin_suffix):
                # 二进制格式（覆盖模式，效率更高）
                with open(file_path, 'wb') as f:
                    pickle.dump(data, f)
                self.logger.info(f"保存二进制训练数据成功：{file_path}，共{len(data)}条")
            else:
                raise StorageError(f"不支持的文件后缀：{os.path.splitext(filename)[1]}", 5014)
            return True
        except Exception as e:
            self.logger.error(f"保存训练数据失败：{str(e)}")
            raise StorageError(f"训练数据保存失败：{str(e)}", 5015)

    def load(self, filename: str) -> Optional[List[Dict]]:
        """实现抽象方法：根据后缀自动选择加载格式"""
        file_path = self._get_file_path(filename)
        if not self.exists(filename):
            self.logger.warning(f"训练数据文件不存在：{file_path}")
            return None
        try:
            if filename.endswith(self.csv_suffix):
                # 加载CSV格式
                with open(file_path, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    data = list(reader)
                    # 转换数值类型
                    for row in data:
                        if row['score']:
                            row['score'] = float(row['score'])
                        if row['timestamp']:
                            row['timestamp'] = int(row['timestamp'])
                self.logger.info(f"加载CSV训练数据成功：{file_path}，共{len(data)}条")
            elif filename.endswith(self.bin_suffix):
                # 加载二进制格式
                with open(file_path, 'rb') as f:
                    data = pickle.load(f)
                self.logger.info(f"加载二进制训练数据成功：{file_path}，共{len(data)}条")
            else:
                raise StorageError(f"不支持的文件后缀：{os.path.splitext(filename)[1]}", 5016)
            return data
        except Exception as e:
            self.logger.error(f"加载训练数据失败：{str(e)}")
            raise StorageError(f"训练数据加载失败：{str(e)}", 5017)
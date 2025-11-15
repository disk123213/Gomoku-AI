import json
import os
from typing import Dict, Optional, List
from Common.logger import Logger
from Common.error_handler import StorageError
from Storage.base_storage import BaseStorage

class UserStorage(BaseStorage):
    """用户数据存储（JSON格式，兼容排行榜、对战记录）"""
    def __init__(self):
        super().__init__('./data/user')
        self.logger = Logger.get_instance()
        self.user_file_prefix = 'user_'
        self.user_file_suffix = '.json'
        self.default_user_data = {
            'nickname': '匿名用户',
            'elo_score': 1500,  # 初始ELO积分
            'win_count': 0,
            'lose_count': 0,
            'draw_count': 0,
            'total_games': 0,
            'last_login': 0,
            'created_at': 0,
            'preferred_ai_level': 'MEDIUM',
            'theme': 'default'
        }

    def save_user(self, user_id: str, user_data: Dict) -> bool:
        """保存用户数据（自动补全默认字段）"""
        # 补全必要字段
        for key, val in self.default_user_data.items():
            if key not in user_data:
                user_data[key] = val
        filename = self._get_user_filename(user_id)
        return self.save(user_data, filename)

    def load_user(self, user_id: str) -> Optional[Dict]:
        """加载用户数据（不存在则返回默认数据）"""
        filename = self._get_user_filename(user_id)
        data = self.load(filename)
        if not data:
            self.logger.warning(f"用户 {user_id} 数据不存在，返回默认配置")
            return self.default_user_data.copy()
        return data

    def update_user(self, user_id: str, update_data: Dict) -> bool:
        """更新用户部分字段（增量更新）"""
        user_data = self.load_user(user_id)
        user_data.update(update_data)
        # 更新统计字段
        if 'win_count' in update_data or 'lose_count' in update_data or 'draw_count' in update_data:
            user_data['total_games'] = user_data['win_count'] + user_data['lose_count'] + user_data['draw_count']
        return self.save_user(user_id, user_data)

    def delete_user(self, user_id: str) -> bool:
        """删除用户数据"""
        filename = self._get_user_filename(user_id)
        return self.delete(filename)

    def list_all_users(self) -> List[str]:
        """获取所有用户ID列表"""
        users = []
        for filename in self.list_files(self.user_file_suffix):
            if filename.startswith(self.user_file_prefix):
                user_id = filename[len(self.user_file_prefix):-len(self.user_file_suffix)]
                users.append(user_id)
        return users

    def _get_user_filename(self, user_id: str) -> str:
        """生成用户文件名：user_{user_id}.json"""
        return f"{self.user_file_prefix}{user_id}{self.user_file_suffix}"

    def save(self, data: Dict, filename: str) -> bool:
        """实现抽象方法：保存为JSON文件"""
        file_path = self._get_file_path(filename)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"保存用户数据成功：{file_path}")
            return True
        except Exception as e:
            self.logger.error(f"保存用户数据失败：{str(e)}")
            raise StorageError(f"用户数据保存失败：{str(e)}", 5001)

    def load(self, filename: str) -> Optional[Dict]:
        """实现抽象方法：从JSON文件加载"""
        file_path = self._get_file_path(filename)
        if not self.exists(filename):
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.logger.info(f"加载用户数据成功：{file_path}")
            return data
        except Exception as e:
            self.logger.error(f"加载用户数据失败：{str(e)}")
            raise StorageError(f"用户数据加载失败：{str(e)}", 5002)
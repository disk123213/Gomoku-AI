import json
import os
import time
from typing import List, Dict, Optional
from Common.logger import Logger
from Common.error_handler import StorageError
from Storage.base_storage import BaseStorage

class RankingStorage(BaseStorage):
    """排行榜存储（JSON格式，支持全球/本地排行榜，兼容ELO积分）"""
    def __init__(self):
        super().__init__('./data/ranking')
        self.logger = Logger.get_instance()
        self.global_ranking_file = 'global_ranking.json'
        self.local_ranking_file = 'local_ranking.json'
        self.default_player_fields = {
            'user_id': '',
            'nickname': '匿名用户',
            'elo_score': 1500,
            'win_count': 0,
            'lose_count': 0,
            'draw_count': 0,
            'total_games': 0,
            'win_rate': 0.0,
            'rank': 0,
            'last_update': 0
        }

    def save_global_ranking(self, ranking_data: List[Dict]) -> bool:
        """保存全球排行榜"""
        return self.save(ranking_data, self.global_ranking_file)

    def load_global_ranking(self) -> List[Dict]:
        """加载全球排行榜（无数据则返回空列表）"""
        data = self.load(self.global_ranking_file)
        return data if data else []

    def save_local_ranking(self, ranking_data: List[Dict]) -> bool:
        """保存本地排行榜"""
        return self.save(ranking_data, self.local_ranking_file)

    def load_local_ranking(self) -> List[Dict]:
        """加载本地排行榜（无数据则返回空列表）"""
        data = self.load(self.local_ranking_file)
        return data if data else []

    def update_ranking(self, user_id: str, user_data: Dict, is_global: bool = True) -> List[Dict]:
        """更新排行榜（自动计算胜率和排名）"""
        # 加载现有排行榜
        if is_global:
            ranking = self.load_global_ranking()
        else:
            ranking = self.load_local_ranking()
        
        # 查找用户是否已存在
        user_index = -1
        for i, player in enumerate(ranking):
            if player['user_id'] == user_id:
                user_index = i
                break
        
        # 补全用户数据
        player_data = self.default_player_fields.copy()
        player_data.update(user_data)
        player_data['user_id'] = user_id
        player_data['last_update'] = int(time.time())
        # 计算总游戏数和胜率
        player_data['total_games'] = player_data['win_count'] + player_data['lose_count'] + player_data['draw_count']
        player_data['win_rate'] = round(
            player_data['win_count'] / player_data['total_games'] * 100 if player_data['total_games'] > 0 else 0.0,
            2
        )
        
        # 更新或新增用户
        if user_index >= 0:
            ranking[user_index] = player_data
        else:
            ranking.append(player_data)
        
        # 按ELO积分降序排序，更新排名
        ranking.sort(key=lambda x: x['elo_score'], reverse=True)
        for i, player in enumerate(ranking):
            player['rank'] = i + 1
        
        # 保存更新后的排行榜
        if is_global:
            self.save_global_ranking(ranking)
        else:
            self.save_local_ranking(ranking)
        
        self.logger.info(f"更新{'全球' if is_global else '本地'}排行榜：用户 {player_data['nickname']}，积分 {player_data['elo_score']}，排名 {player_data['rank']}")
        return ranking

    def get_top_ranking(self, top_n: int = 10, is_global: bool = True) -> List[Dict]:
        """获取排行榜前N名"""
        ranking = self.load_global_ranking() if is_global else self.load_local_ranking()
        # 截取前N名，只返回关键字段
        return [
            {
                'rank': player['rank'],
                'nickname': player['nickname'],
                'elo_score': player['elo_score'],
                'win_rate': player['win_rate'],
                'total_games': player['total_games'],
                'last_update': time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(player['last_update']))
            }
            for player in ranking[:top_n]
        ]

    def get_player_ranking(self, user_id: str, is_global: bool = True) -> Optional[Dict]:
        """获取单个用户的排名信息"""
        ranking = self.load_global_ranking() if is_global else self.load_local_ranking()
        for player in ranking:
            if player['user_id'] == user_id:
                return player
        self.logger.warning(f"用户 {user_id} 未在{'全球' if is_global else '本地'}排行榜中")
        return None

    def save(self, data: List[Dict], filename: str) -> bool:
        """实现抽象方法：保存为JSON文件"""
        file_path = self._get_file_path(filename)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"保存排行榜成功：{file_path}，共{len(data)}名用户")
            return True
        except Exception as e:
            self.logger.error(f"保存排行榜失败：{str(e)}")
            raise StorageError(f"排行榜保存失败：{str(e)}", 5020)

    def load(self, filename: str) -> Optional[List[Dict]]:
        """实现抽象方法：从JSON文件加载"""
        file_path = self._get_file_path(filename)
        if not self.exists(filename):
            self.logger.warning(f"排行榜文件不存在：{file_path}")
            return []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.logger.info(f"加载排行榜成功：{file_path}，共{len(data)}名用户")
            return data
        except Exception as e:
            self.logger.error(f"加载排行榜失败：{str(e)}")
            raise StorageError(f"排行榜加载失败：{str(e)}", 5021)
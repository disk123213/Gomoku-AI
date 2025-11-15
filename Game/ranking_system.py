import math
from typing import List, Dict, Optional
from Common.logger import Logger
from Storage.ranking_storage import RankingStorage

class ELORankingSystem:
    """ELO积分排名系统（参考国际象棋规则，支持本地/全球排名）"""
    def __init__(self):
        self.logger = Logger.get_instance()
        self.ranking_storage = RankingStorage()
        self.base_rating = 1500  # 初始积分
        self.k_factor = 32  # 积分变化系数（普通玩家）
        self.k_factor_new = 40  # 新玩家系数（前20局）
        self.k_factor_master = 24  # 大师系数（积分≥2000）

    def calculate_new_ratings(self, player1_rating: int, player2_rating: int, player1_win: bool, player1_games: int, player2_games: int) -> Tuple[int, int]:
        """计算对战后双方新积分（动态K因子）"""
        # 动态K因子（根据对局数和当前积分调整）
        k1 = self._get_k_factor(player1_rating, player1_games)
        k2 = self._get_k_factor(player2_rating, player2_games)

        # 预期胜率（ELO公式）
        expected1 = 1 / (1 + math.pow(10, (player2_rating - player1_rating) / 400))
        expected2 = 1 - expected1

        # 实际得分（1=胜，0.5=平，0=负）
        actual1 = 1.0 if player1_win else 0.0 if player1_win is False else 0.5
        actual2 = 1.0 - actual1

        # 计算新积分
        new_rating1 = round(player1_rating + k1 * (actual1 - expected1))
        new_rating2 = round(player2_rating + k2 * (actual2 - expected2))

        return new_rating1, new_rating2

    def update_player_rating(self, player1_id: str, player1_name: str, player2_id: str, player2_name: str, player1_win: bool, is_global: bool = False) -> Dict:
        """更新玩家积分并返回排名结果"""
        # 加载排行榜数据
        ranking = self.ranking_storage.load_global_ranking() if is_global else self.ranking_storage.load_local_ranking()
        ranking = ranking or []

        # 获取玩家当前数据
        player1_data = next((p for p in ranking if p['user_id'] == player1_id), None)
        player2_data = next((p for p in ranking if p['user_id'] == player2_id), None)

        # 初始化新玩家数据
        if not player1_data:
            player1_data = self._init_player_data(player1_id, player1_name)
        if not player2_data:
            player2_data = self._init_player_data(player2_id, player2_name)

        # 计算新积分
        new_rating1, new_rating2 = self.calculate_new_ratings(
            player1_rating=player1_data['score'],
            player2_rating=player2_data['score'],
            player1_win=player1_win,
            player1_games=player1_data['total_games'],
            player2_games=player2_data['total_games']
        )

        # 更新对战统计
        self._update_player_stats(player1_data, player1_win)
        self._update_player_stats(player2_data, not player1_win if player1_win is not None else None)

        # 更新积分和最后活跃时间
        player1_data['score'] = new_rating1
        player2_data['score'] = new_rating2
        player1_data['last_update'] = self._get_current_time()
        player2_data['last_update'] = self._get_current_time()

        # 更新排行榜
        ranking = self._upsert_player(ranking, player1_data)
        ranking = self._upsert_player(ranking, player2_data)

        # 保存排行榜
        if is_global:
            self.ranking_storage.save_global_ranking(ranking)
        else:
            self.ranking_storage.save_local_ranking(ranking)

        # 获取最终排名
        player1_final = next(p for p in ranking if p['user_id'] == player1_id)
        player2_final = next(p for p in ranking if p['user_id'] == player2_id)

        return {
            'player1': self._format_player_ranking(player1_final, player1_data['score'], new_rating1),
            'player2': self._format_player_ranking(player2_final, player2_data['score'], new_rating2),
            'is_global': is_global,
            'total_players': len(ranking)
        }

    def get_player_ranking(self, user_id: str, is_global: bool = False) -> Optional[Dict]:
        """获取单个玩家的排名信息"""
        ranking = self.ranking_storage.load_global_ranking() if is_global else self.ranking_storage.load_local_ranking()
        if not ranking:
            return None

        player = next((p for p in ranking if p['user_id'] == user_id), None)
        if not player:
            self.logger.warning(f"玩家{user_id}未在{'全球' if is_global else '本地'}排行榜中")
            return None

        # 计算胜率和总对局数
        total_games = player['win_count'] + player['lose_count'] + player['draw_count']
        win_rate = player['win_count'] / total_games if total_games > 0 else 0.0

        return {
            'user_id': player['user_id'],
            'name': player['name'],
            'rank': player['rank'],
            'score': player['score'],
            'win_count': player['win_count'],
            'lose_count': player['lose_count'],
            'draw_count': player['draw_count'],
            'total_games': total_games,
            'win_rate': round(win_rate * 100, 2),
            'last_update': player['last_update'],
            'is_global': is_global,
            'total_players': len(ranking)
        }

    def get_ranking_list(self, top_n: int = 10, is_global: bool = False) -> List[Dict]:
        """获取排行榜前N名"""
        ranking = self.ranking_storage.load_global_ranking() if is_global else self.ranking_storage.load_local_ranking()
        if not ranking:
            return []

        # 截取前N名并格式化
        top_ranking = []
        for i, player in enumerate(ranking[:top_n]):
            total_games = player['win_count'] + player['lose_count'] + player['draw_count']
            win_rate = player['win_count'] / total_games if total_games > 0 else 0.0
            top_ranking.append({
                'rank': i + 1,
                'name': player['name'],
                'user_id': player['user_id'],
                'score': player['score'],
                'win_count': player['win_count'],
                'lose_count': player['lose_count'],
                'draw_count': player['draw_count'],
                'win_rate': round(win_rate * 100, 2),
                'last_update': player['last_update']
            })

        return top_ranking

    # ------------------------------ 辅助方法 ------------------------------
    def _get_k_factor(self, rating: int, game_count: int) -> int:
        """获取动态K因子"""
        if game_count < 20:
            return self.k_factor_new
        elif rating >= 2000:
            return self.k_factor_master
        else:
            return self.k_factor

    def _init_player_data(self, user_id: str, user_name: str) -> Dict:
        """初始化新玩家数据"""
        return {
            'user_id': user_id,
            'name': user_name,
            'score': self.base_rating,
            'win_count': 0,
            'lose_count': 0,
            'draw_count': 0,
            'total_games': 0,
            'last_update': self._get_current_time(),
            'rank': 0
        }

    def _update_player_stats(self, player_data: Dict, is_winner: Optional[bool]):
        """更新玩家对战统计"""
        player_data['total_games'] += 1
        if is_winner is None:
            player_data['draw_count'] += 1
        elif is_winner:
            player_data['win_count'] += 1
        else:
            player_data['lose_count'] += 1

    def _upsert_player(self, ranking: List[Dict], player_data: Dict) -> List[Dict]:
        """插入或更新玩家排名"""
        # 移除旧数据
        ranking = [p for p in ranking if p['user_id'] != player_data['user_id']]
        # 添加新数据
        ranking.append(player_data)
        # 按积分降序排序并更新排名
        ranking.sort(key=lambda x: x['score'], reverse=True)
        for i, p in enumerate(ranking):
            p['rank'] = i + 1
        return ranking

    def _format_player_ranking(self, player: Dict, old_rating: int, new_rating: int) -> Dict:
        """格式化玩家排名结果"""
        return {
            'id': player['user_id'],
            'name': player['name'],
            'old_rating': old_rating,
            'new_rating': new_rating,
            'rating_change': new_rating - old_rating,
            'rank': player['rank'],
            'win_count': player['win_count'],
            'lose_count': player['lose_count'],
            'draw_count': player['draw_count'],
            'total_games': player['total_games']
        }

    def _get_current_time(self) -> str:
        """获取当前时间字符串"""
        import time
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
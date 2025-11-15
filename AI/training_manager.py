import os
import json
import csv
import time
from typing import List, Dict, Optional
from Common.constants import PIECE_COLORS
from Common.logger import Logger
from Common.data_utils import DataUtils  # 补充数据工具类依赖
from Storage.train_data_storage import TrainDataStorage
from AI.base_ai import BaseAI
from AI.evaluator import BoardEvaluator

class TrainingManager:
    """训练数据管理器（自我对弈/人工数据/数据预处理/统计）"""
    def __init__(self):
        self.logger = Logger.get_instance()
        self.train_data_storage = TrainDataStorage()
        self.evaluator = BoardEvaluator()
        self.data_dir = self.train_data_storage.base_dir

    def generate_self_play_data(self, ai: BaseAI, num_games: int = 100, user_id: str = 'system') -> List[Dict]:
        """生成自我对弈训练数据（对接AI自我对弈逻辑）"""
        total_data = []
        self.logger.info(f"启动自我对弈数据生成：{num_games}局，AI类型：{ai.__class__.__name__}")

        for game_idx in range(num_games):
            board = [[PIECE_COLORS['EMPTY'] for _ in range(ai.board_size)] for _ in range(ai.board_size)]
            current_color = PIECE_COLORS['BLACK']
            done = False
            move_count = 0
            game_data = []

            while not done and move_count < ai.board_size ** 2:
                # AI落子（区分己方和对手）
                if current_color == ai.color:
                    move = ai._get_action(board, training=True)
                else:
                    # 对手AI（镜像配置）
                    opponent_ai = BaseAI(current_color, ai.level)
                    opponent_ai._get_empty_positions = ai._get_empty_positions  # 复用空位置获取逻辑
                    move = opponent_ai._get_action(board, training=True)

                # 落子分析（棋型、质量评分）
                x, y = move
                move_analysis = self.evaluator.analyze_move_quality(board, x, y, current_color)

                # 存储单步数据（标准化格式）
                game_data.append({
                    'board': DataUtils.board_to_str(board),  # 棋盘状态序列化
                    'move': f"{x},{y}",
                    'color': current_color,
                    'pattern': move_analysis['pattern'],
                    'score': round(move_analysis['score'], 2),
                    'quality': move_analysis['quality'],
                    'position_weight': round(move_analysis['position_weight'], 2),
                    'timestamp': time.time()
                })

                # 执行落子
                board[x][y] = current_color
                move_count += 1

                # 检查游戏结束
                win, _ = ai._is_win(board, current_color)
                if win:
                    done = True
                    result = 'win' if current_color == ai.color else 'lose'
                elif move_count == ai.board_size ** 2:
                    done = True
                    result = 'draw'

                # 切换玩家
                current_color = PIECE_COLORS['WHITE'] if current_color == PIECE_COLORS['BLACK'] else PIECE_COLORS['BLACK']

            # 补充游戏结果并汇总数据
            for data in game_data:
                data['result'] = result
                data['game_id'] = f"self_play_{user_id}_{int(time.time())}_{game_idx}"
                total_data.append(data)

            # 增量保存（每10局保存一次，避免数据丢失）
            if (game_idx + 1) % 10 == 0:
                self.train_data_storage.save_self_play_data(game_data)
                self.logger.info(
                    f"自我对弈数据生成进度：{game_idx+1}/{num_games}局，"
                    f"本局步数：{move_count}，累计数据：{len(total_data)}条"
                )

        # 最终保存完整数据
        self.train_data_storage.save_self_play_data(game_data)
        self.logger.info(f"自我对弈数据生成完成：共{num_games}局，累计{len(total_data)}条训练数据")
        return total_data

    def import_manual_data(self, file_path: str, user_id: str) -> bool:
        """导入人工标注数据（CSV格式，支持批量导入）"""
        if not os.path.exists(file_path):
            self.logger.error(f"人工数据文件不存在：{file_path}")
            return False

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                data = list(reader)

                # 数据格式校验（必填字段）
                required_columns = ['board', 'move', 'color', 'pattern', 'score', 'quality', 'result']
                missing_cols = [col for col in required_columns if col not in reader.fieldnames]
                if missing_cols:
                    raise ValueError(f"缺少必填字段：{','.join(missing_cols)}")

                # 数据格式清洗
                cleaned_data = []
                for item in data:
                    # 校验落子格式
                    try:
                        x, y = map(int, item['move'].split(','))
                    except:
                        self.logger.warning(f"跳过无效落子数据：{item['move']}")
                        continue
                    # 标准化棋盘格式
                    item['board'] = DataUtils.board_to_str(DataUtils.str_to_board(item['board']))
                    # 补充默认字段
                    item['timestamp'] = item.get('timestamp', time.time())
                    item['game_id'] = f"manual_{user_id}_{int(time.time())}_{len(cleaned_data)}"
                    cleaned_data.append(item)

                # 保存到本地存储
                self.train_data_storage.save_train_data(user_id, cleaned_data)
                self.logger.info(f"人工数据导入成功：{file_path}，有效数据{len(cleaned_data)}/{len(data)}条")
                return True

        except Exception as e:
            self.logger.error(f"人工数据导入失败：{str(e)}")
            return False

    def preprocess_data(self, user_id: str, output_file: str = "processed_train_data.csv") -> bool:
        """预处理训练数据（归一化、特征提取、格式标准化）"""
        # 加载用户训练数据（合并自我对弈和人工数据）
        self_play_data = self.train_data_storage.load_self_play_data() or []
        user_train_data = self.train_data_storage.load_train_data(user_id) or []
        total_data = self_play_data + user_train_data

        if not total_data:
            self.logger.warning(f"无可用训练数据：用户{user_id}")
            return False

        try:
            # 特征提取与归一化
            processed_data = []
            # 全局得分归一化（按最大值缩放）
            all_scores = [float(item['score']) for item in total_data]
            max_score = max(all_scores) if all_scores else 1.0
            min_score = min(all_scores) if all_scores else 0.0

            for item in total_data:
                # 解析落子坐标
                x, y = map(int, item['move'].split(','))
                # 归一化得分（0-1区间）
                normalized_score = (float(item['score']) - min_score) / (max_score - min_score) if max_score > min_score else 0.5
                # 提取棋盘特征：空位置占比
                board = DataUtils.str_to_board(item['board'])
                empty_count = sum(row.count(PIECE_COLORS['EMPTY']) for row in board)
                empty_ratio = empty_count / (len(board) * len(board))
                # 结果标签化（1=胜，0=负，0.5=平）
                result_label = 1.0 if item['result'] == 'win' else 0.0 if item['result'] == 'lose' else 0.5

                processed_data.append({
                    'game_id': item.get('game_id', f"processed_{int(time.time())}"),
                    'x': x,
                    'y': y,
                    'color': item['color'],
                    'normalized_score': round(normalized_score, 4),
                    'quality': round(float(item['quality']), 2),
                    'empty_ratio': round(empty_ratio, 4),
                    'pattern': item['pattern'],
                    'result_label': result_label,
                    'timestamp': item.get('timestamp', time.time())
                })

            # 保存预处理后的数据（CSV格式）
            output_path = os.path.join(self.data_dir, output_file)
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=processed_data[0].keys())
                writer.writeheader()
                writer.writerows(processed_data)

            self.logger.info(f"训练数据预处理完成：{output_path}，处理数据{len(processed_data)}条")
            return True

        except Exception as e:
            self.logger.error(f"训练数据预处理失败：{str(e)}")
            return False

    def get_data_statistics(self, user_id: str) -> Dict:
        """获取用户训练数据统计报告"""
        # 加载所有相关数据
        self_play_data = self.train_data_storage.load_self_play_data() or []
        user_train_data = self.train_data_storage.load_train_data(user_id) or []
        total_data = self_play_data + user_train_data

        if not total_data:
            return {
                'user_id': user_id,
                'total_count': 0,
                'self_play_count': len(self_play_data),
                'manual_count': len(user_train_data),
                'win_count': 0,
                'lose_count': 0,
                'draw_count': 0,
                'avg_quality': 0.0,
                'avg_score': 0.0,
                'most_common_pattern': 'None',
                'data_coverage': "0%"
            }

        # 基础统计
        win_count = len([item for item in total_data if item['result'] == 'win'])
        lose_count = len([item for item in total_data if item['result'] == 'lose'])
        draw_count = len([item for item in total_data if item['result'] == 'draw'])
        avg_quality = sum(float(item['quality']) for item in total_data) / len(total_data)
        avg_score = sum(float(item['score']) for item in total_data) / len(total_data)

        # 棋型分布统计
        pattern_counts = {}
        for item in total_data:
            pattern = item['pattern']
            pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
        most_common_pattern = max(pattern_counts.items(), key=lambda x: x[1])[0] if pattern_counts else 'None'

        # 数据覆盖率（棋盘位置覆盖）
        covered_positions = set()
        for item in total_data:
            x, y = map(int, item['move'].split(','))
            covered_positions.add((x, y))
        board_size = self.evaluator.board_size
        data_coverage = f"{len(covered_positions) / (board_size * board_size) * 100:.1f}%"

        return {
            'user_id': user_id,
            'total_count': len(total_data),
            'self_play_count': len(self_play_data),
            'manual_count': len(user_train_data),
            'win_count': win_count,
            'lose_count': lose_count,
            'draw_count': draw_count,
            'win_rate': round(win_count / len(total_data) * 100, 2) if len(total_data) > 0 else 0.0,
            'avg_quality': round(avg_quality, 2),
            'avg_score': round(avg_score, 2),
            'most_common_pattern': most_common_pattern,
            'pattern_distribution': pattern_counts,
            'data_coverage': data_coverage,
            'last_updated': time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        }

    def clear_old_data(self, user_id: str, days: int = 30) -> bool:
        """清理过期训练数据（默认30天）"""
        try:
            cutoff_time = time.time() - days * 86400
            user_data = self.train_data_storage.load_train_data(user_id) or []
            kept_data = []
            deleted_count = 0

            for item in user_data:
                item_time = float(item.get('timestamp', 0))
                if item_time >= cutoff_time:
                    kept_data.append(item)
                else:
                    deleted_count += 1

            # 保存保留数据
            if deleted_count > 0:
                self.train_data_storage.save_train_data(user_id, kept_data)
                self.logger.info(f"清理过期训练数据：用户{user_id}，删除{deleted_count}条，保留{len(kept_data)}条")
            else:
                self.logger.info(f"无过期训练数据需要清理：用户{user_id}")

            return True
        except Exception as e:
            self.logger.error(f"清理过期训练数据失败：{str(e)}")
            return False
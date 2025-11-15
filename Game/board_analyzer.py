import numpy as np
from typing import List, Tuple, Dict, Optional
from Common.constants import PIECE_COLORS, EVAL_WEIGHTS
from Common.logger import Logger
from Compute.cpp_interface import CppCore
from AI.evaluator import BoardEvaluator

class BoardAnalyzer:
    """棋盘分析器（落子质量评估、局势分析、复盘报告生成）"""
    def __init__(self, board_size: int = 15):
        self.board_size = board_size
        self.logger = Logger.get_instance()
        self.cpp_core = CppCore()
        self.evaluator = BoardEvaluator(board_size)
        self.pattern_scores = EVAL_WEIGHTS

    def analyze_move_quality(self, board: List[List[int]], x: int, y: int, color: int) -> Dict:
        """分析单步落子质量（0-100分）"""
        # 基础棋型得分
        pattern, pattern_score = self.evaluator._recognize_pattern(board, x, y, color)

        # 位置权重得分
        pos_weight = self.evaluator.position_weights[x][y]

        # 局势影响得分（落子前后局势变化）
        pre_score = self.evaluator.evaluate_board(board, color)
        temp_board = [row.copy() for row in board]
        temp_board[x][y] = color
        post_score = self.evaluator.evaluate_board(temp_board, color)
        impact_score = post_score - pre_score

        # 综合质量评分（归一化到0-100）
        total_score = (pattern_score * 0.5 + pos_weight * 20 + impact_score * 0.3)
        quality = min(100, max(0, total_score))

        # 查找最优替代落子
        best_move, best_score = self._find_best_move(board, color)

        return {
            'move': (x, y),
            'pattern': pattern,
            'pattern_score': pattern_score,
            'position_weight': pos_weight,
            'impact_score': impact_score,
            'quality': round(quality, 2),
            'best_move': best_move,
            'best_score': best_score,
            'quality_gap': round(best_score - quality, 2)
        }

    def analyze_board_situation(self, board: List[List[int]]) -> Dict:
        """全局局势分析（双方优势评估）"""
        # 双方局势得分
        black_score = self.evaluator.evaluate_board(board, PIECE_COLORS['BLACK'])
        white_score = self.evaluator.evaluate_board(board, PIECE_COLORS['WHITE'])
        score_gap = black_score - white_score

        # 威胁检测（冲四、活三）
        black_threats = self._detect_threats(board, PIECE_COLORS['BLACK'])
        white_threats = self._detect_threats(board, PIECE_COLORS['WHITE'])

        # 关键落子点预测
        black_best_move, _ = self._find_best_move(board, PIECE_COLORS['BLACK'])
        white_best_move, _ = self._find_best_move(board, PIECE_COLORS['WHITE'])

        # 局势判断
        if len(black_threats) >= 2 or any(t['level'] == 'high' for t in black_threats):
            situation = 'black_attack'
            desc = "黑方进攻优势明显，存在多个威胁"
        elif len(white_threats) >= 2 or any(t['level'] == 'high' for t in white_threats):
            situation = 'white_attack'
            desc = "白方进攻优势明显，存在多个威胁"
        elif score_gap > 50:
            situation = 'black_advantage'
            desc = f"黑方局势领先（得分差：{score_gap:.1f}）"
        elif score_gap < -50:
            situation = 'white_advantage'
            desc = f"白方局势领先（得分差：{abs(score_gap):.1f}）"
        else:
            situation = 'balanced'
            desc = f"局势均衡（得分差：{score_gap:.1f}）"

        return {
            'black_score': round(black_score, 2),
            'white_score': round(white_score, 2),
            'score_gap': round(score_gap, 2),
            'black_threats': black_threats,
            'white_threats': white_threats,
            'black_best_move': black_best_move,
            'white_best_move': white_best_move,
            'situation': situation,
            'description': desc
        }

    def generate_replay_report(self, move_history: List[Dict], board_size: int) -> Dict:
        """生成复盘报告（基于落子历史）"""
        if not move_history:
            return {'error': '无落子历史数据'}

        # 初始化棋盘
        board = [[PIECE_COLORS['EMPTY'] for _ in range(board_size)] for _ in range(board_size)]
        move_qualities = []
        threat_history = []

        # 逐步分析
        for move in move_history:
            x, y = move['x'], move['y']
            color = move['color']

            # 分析落子质量
            quality_info = self.analyze_move_quality(board, x, y, color)
            move_qualities.append({
                'move_idx': len(move_qualities) + 1,
                'x': x,
                'y': y,
                'color': color,
                'quality': quality_info['quality'],
                'pattern': quality_info['pattern'],
                'best_move': quality_info['best_move'],
                'quality_gap': quality_info['quality_gap']
            })

            # 分析局势威胁
            situation = self.analyze_board_situation(board)
            threat_history.append({
                'move_idx': len(threat_history) + 1,
                'black_threats': len(situation['black_threats']),
                'white_threats': len(situation['white_threats']),
                'situation': situation['situation']
            })

            # 执行落子
            board[x][y] = color

        # 统计分析
        avg_quality = np.mean([mq['quality'] for mq in move_qualities])
        high_quality_moves = [mq for mq in move_qualities if mq['quality'] >= 85]
        low_quality_moves = [mq for mq in move_qualities if mq['quality'] < 60]
        most_common_pattern = max(set([mq['pattern'] for mq in move_qualities]), key=[mq['pattern'] for mq in move_qualities].count)

        return {
            'total_moves': len(move_history),
            'avg_quality': round(avg_quality, 2),
            'high_quality_rate': round(len(high_quality_moves) / len(move_qualities) * 100, 2),
            'low_quality_count': len(low_quality_moves),
            'most_common_pattern': most_common_pattern,
            'move_qualities': move_qualities,
            'threat_history': threat_history,
            'key_moments': self._identify_key_moments(threat_history, move_qualities)
        }

    # ------------------------------ 辅助方法 ------------------------------
    def _find_best_move(self, board: List[List[int]], color: int) -> Tuple[Tuple[int, int], float]:
        """查找当前棋盘的最优落子"""
        empty_pos = self.evaluator._get_empty_positions(board)
        if not empty_pos:
            return ((0, 0), 0.0)

        # 评估所有空位置
        move_scores = []
        for (x, y) in empty_pos:
            score = self.evaluator.evaluate_move(board, x, y, color, EVAL_WEIGHTS)
            pos_weight = self.evaluator.position_weights[x][y]
            total_score = score * pos_weight
            move_scores.append(((x, y), total_score))

        # 选择得分最高的落子
        best_move, best_score = max(move_scores, key=lambda x: x[1])
        # 归一化得分到0-100
        normalized_score = min(100, max(0, (best_score / self.pattern_scores['FIVE']) * 100))
        return (best_move, round(normalized_score, 2))

    def _detect_threats(self, board: List[List[int]], color: int) -> List[Dict]:
        """检测当前玩家的威胁（冲四、活三）"""
        threats = []
        empty_pos = self.evaluator._get_empty_positions(board)

        for (x, y) in empty_pos:
            temp_board = [row.copy() for row in board]
            temp_board[x][y] = color
            score = self.evaluator.evaluate_board(temp_board, color)

            if score >= self.pattern_scores['FOUR']:
                threats.append({
                    'position': (x, y),
                    'level': 'high',
                    'type': '冲四',
                    'score': score
                })
            elif score >= self.pattern_scores['THREE']:
                threats.append({
                    'position': (x, y),
                    'level': 'medium',
                    'type': '活三',
                    'score': score
                })

        return threats

    def _identify_key_moments(self, threat_history: List[Dict], move_qualities: List[Dict]) -> List[Dict]:
        """识别对局关键节点（威胁变化、低质量落子）"""
        key_moments = []

        for i in range(len(threat_history)):
            threat_info = threat_history[i]
            quality_info = move_qualities[i]

            # 威胁突变（新增高威胁）
            if i > 0:
                prev_black_threats = threat_history[i-1]['black_threats']
                prev_white_threats = threat_history[i-1]['white_threats']
                curr_black_threats = threat_info['black_threats']
                curr_white_threats = threat_info['white_threats']

                if (curr_black_threats - prev_black_threats) >= 1:
                    key_moments.append({
                        'move_idx': i + 1,
                        'type': 'black_threat_increase',
                        'description': f"黑方新增威胁（当前{curr_black_threats}个），需紧急防守"
                    })
                elif (curr_white_threats - prev_white_threats) >= 1:
                    key_moments.append({
                        'move_idx': i + 1,
                        'type': 'white_threat_increase',
                        'description': f"白方新增威胁（当前{curr_white_threats}个），需紧急防守"
                    })

            # 低质量关键落子（影响局势）
            if quality_info['quality'] < 50 and quality_info['quality_gap'] > 30:
                key_moments.append({
                    'move_idx': i + 1,
                    'type': 'bad_key_move',
                    'description': f"关键落子质量过低（{quality_info['quality']:.1f}分），最优落子为{quality_info['best_move']}"
                })

        return key_moments
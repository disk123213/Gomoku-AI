import os
import json
import configparser
from typing import Dict, List, Optional, Any
from Common.logger import Logger
from Common.error_handler import ConfigError

class Config:
    """配置管理器（单例模式，自动加载/保存配置）"""
    _instance = None
    _lock = __import__('threading').Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self.logger = Logger.get_instance()
        self.config_dir = os.path.join(os.getcwd(), 'data', 'config')
        self.config_file = os.path.join(self.config_dir, 'game_config.ini')
        self.json_config_file = os.path.join(self.config_dir, 'ai_config.json')
        self._create_dir()
        self._load_config()

    def _create_dir(self):
        """创建配置目录（Win11兼容路径）"""
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
            self.logger.info(f"创建配置目录：{self.config_dir}")

    def _load_config(self):
        """加载INI+JSON配置"""
        # 加载INI配置
        self.ini_config = configparser.ConfigParser()
        if os.path.exists(self.config_file):
            self.ini_config.read(self.config_file, encoding='utf-8')
            self.logger.info("INI配置加载成功")
        else:
            self._init_default_ini()
            self.save_ini()

        # 加载JSON配置（AI相关）
        self.json_config = {}
        if os.path.exists(self.json_config_file):
            with open(self.json_config_file, 'r', encoding='utf-8') as f:
                self.json_config = json.load(f)
            self.logger.info("JSON配置加载成功")
        else:
            self._init_default_json()
            self.save_json()

    def _init_default_ini(self):
        """默认INI配置（Win11优化路径）"""
        self.ini_config['PATH'] = {
            'user_data_dir': os.path.join(os.getcwd(), 'data', 'user'),
            'model_dir': os.path.join(os.getcwd(), 'data', 'model'),
            'train_data_dir': os.path.join(os.getcwd(), 'data', 'train_data'),
            'game_record_dir': os.path.join(os.getcwd(), 'data', 'game_record'),
            'ranking_dir': os.path.join(os.getcwd(), 'data', 'ranking'),
            'live_replay_dir': os.path.join(os.getcwd(), 'data', 'live_replay'),
            'log_dir': os.path.join(os.getcwd(), 'data', 'log')
        }
        self.ini_config['WINDOW'] = {
            'DEFAULT_WIDTH': '1280',
            'DEFAULT_HEIGHT': '720',
            'MIN_WIDTH': '1024',
            'MIN_HEIGHT': '600',
            'FPS': '60',
            'TITLE': '五子棋AI对战平台（Win11优化版）'
        }
        self.ini_config['GAME'] = {
            'BOARD_SIZE': '15',
            'CELL_SIZE': '40',
            'WIN_CONDITION': '5',
            'ELO_K_FACTOR': '32',
            'BASE_RATING': '1500'
        }
        self.ini_config['SERVER'] = {
            'HOST': '0.0.0.0',
            'PORT': '8888',
            'MAX_CLIENTS': '50',
            'TIMEOUT': '30',
            'LIVE_PORT': '9999'
        }
        self.ini_config['AI'] = {
            'DEFAULT_LEVEL': 'HARD',
            'MINIMAX_MAX_DEPTH': '6',
            'MCTS_ITERATIONS': '1000',
            'RL_HIDDEN_SIZE': '512',
            'RL_BATCH_SIZE': '64',
            'RL_MEMORY_SIZE': '100000',
            'RL_TARGET_UPDATE': '100',
            'LEARNING_RATE': '0.001',
            'MAX_EPOCHS': '50',
            'BATCH_SIZE': '32'
        }

    def _init_default_json(self):
        """默认AI JSON配置"""
        self.json_config = {
            'eval_weights': {
                'FIVE': 100000.0,
                'FOUR': 10000.0,
                'BLOCKED_FOUR': 5000.0,
                'THREE': 1000.0,
                'BLOCKED_THREE': 500.0,
                'TWO': 100.0,
                'BLOCKED_TWO': 50.0,
                'ONE': 10.0
            },
            'rl_params': {
                'gamma': 0.99,
                'epsilon': 0.1,
                'learning_rate': 0.001,
                'batch_size': 64,
                'memory_size': 100000,
                'target_update': 100
            },
            'mcts_params': {
                'exploration_constant': 1.414,
                'simulation_depth': 5,
                'iterations': {
                    'EASY': 200,
                    'MEDIUM': 500,
                    'HARD': 1000,
                    'EXPERT': 2000
                }
            },
            'minimax_params': {
                'max_depth': {
                    'EASY': 3,
                    'MEDIUM': 4,
                    'HARD': 5,
                    'EXPERT': 6
                },
                'prune_threshold': 0.8,
                'move_ordering': True
            }
        }

    def save_ini(self):
        """保存INI配置"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            self.ini_config.write(f)
        self.logger.info(f"INI配置保存至：{self.config_file}")

    def save_json(self):
        """保存JSON配置"""
        with open(self.json_config_file, 'w', encoding='utf-8') as f:
            json.dump(self.json_config, f, ensure_ascii=False, indent=2)
        self.logger.info(f"JSON配置保存至：{self.json_config_file}")

    def get(self, section: str, key: str, default: Any = None) -> str:
        """获取INI配置值"""
        try:
            return self.ini_config.get(section, key, fallback=default)
        except Exception as e:
            self.logger.error(f"获取INI配置失败：{section}.{key}")
            raise ConfigError(f"配置项不存在：{section}.{key}", 1001)

    def get_int(self, section: str, key: str, default: int = 0) -> int:
        """获取INT类型配置"""
        try:
            return self.ini_config.getint(section, key, fallback=default)
        except ValueError:
            self.logger.error(f"INI配置类型错误：{section}.{key}（需为整数）")
            raise ConfigError(f"配置类型错误：{section}.{key}（整数）", 1002)

    def get_float(self, section: str, key: str, default: float = 0.0) -> float:
        """获取FLOAT类型配置"""
        try:
            return self.ini_config.getfloat(section, key, fallback=default)
        except ValueError:
            self.logger.error(f"INI配置类型错误：{section}.{key}（需为浮点数）")
            raise ConfigError(f"配置类型错误：{section}.{key}（浮点数）", 1003)

    def get_bool(self, section: str, key: str, default: bool = False) -> bool:
        """获取BOOL类型配置"""
        try:
            return self.ini_config.getboolean(section, key, fallback=default)
        except ValueError:
            self.logger.error(f"INI配置类型错误：{section}.{key}（需为布尔值）")
            raise ConfigError(f"配置类型错误：{section}.{key}（布尔值）", 1004)

    def get_list(self, section: str, key: str, separator: str = ',') -> List[str]:
        """获取列表类型配置"""
        value = self.get(section, key, '')
        return value.split(separator) if value else []

    def get_json(self, key: str, default: Any = None) -> Any:
        """获取JSON配置值"""
        return self.json_config.get(key, default)

    def set_ini(self, section: str, key: str, value: str):
        """设置INI配置"""
        if section not in self.ini_config:
            self.ini_config[section] = {}
        self.ini_config[section][key] = value
        self.save_ini()

    def set_json(self, key: str, value: Any):
        """设置JSON配置"""
        self.json_config[key] = value
        self.save_json()

    @staticmethod
    def get_instance() -> 'Config':
        """获取单例实例"""
        return Config()
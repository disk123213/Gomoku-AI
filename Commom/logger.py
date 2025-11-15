import os
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional
from Common.config import Config

class Logger:
    """日志管理器（单例模式，支持控制台+文件输出）"""
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
        self.config = Config.get_instance()
        self.log_dir = self.config.get('PATH', 'log_dir')
        self._create_log_dir()
        self.logger = self._init_logger()

    def _create_log_dir(self):
        """创建日志目录（Win11兼容）"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
            self.debug(f"创建日志目录：{self.log_dir}")

    def _init_logger(self) -> logging.Logger:
        """初始化日志配置"""
        logger = logging.getLogger('GobangAI')
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        # 日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 文件处理器（轮转日志，最大100MB/个，保留10个）
        log_file = os.path.join(self.log_dir, 'gobang_ai.log')
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=1024 * 1024 * 100,  # 100MB
            backupCount=10,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        return logger

    def debug(self, message: str):
        """调试日志"""
        self.logger.debug(message)

    def info(self, message: str):
        """信息日志"""
        self.logger.info(message)

    def warning(self, message: str):
        """警告日志"""
        self.logger.warning(message)

    def error(self, message: str):
        """错误日志"""
        self.logger.error(message)

    def critical(self, message: str):
        """严重错误日志"""
        self.logger.critical(message)

    def exception(self, message: str, exc_info: Optional[Exception] = None):
        """异常日志"""
        self.logger.exception(message, exc_info=exc_info)

    @staticmethod
    def get_instance() -> 'Logger':
        """获取单例实例"""
        return Logger()
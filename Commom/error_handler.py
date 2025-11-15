from typing import Optional, Dict
from Common.logger import Logger
from Common.constants import ERROR_CODES

class BaseError(Exception):
    """基础异常类"""
    def __init__(self, message: str, code: int, details: Optional[Dict] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        self.logger = Logger.get_instance()
        self._log_error()
        super().__init__(self.message)

    def _log_error(self):
        """记录错误日志"""
        error_info = f"错误码[{self.code}]：{self.message}"
        if self.details:
            error_info += f"，详情：{self.details}"
        self.logger.error(error_info)

    def to_dict(self) -> Dict:
        """转换为字典（网络传输用）"""
        return {
            'code': self.code,
            'message': self.message,
            'details': self.details,
            'desc': ERROR_CODES.get(self.code, '未知错误')
        }

class ConfigError(BaseError):
    """配置错误"""
    def __init__(self, message: str, code: int, details: Optional[Dict] = None):
        super().__init__(message, code, details)

class UIError(BaseError):
    """UI组件错误"""
    def __init__(self, message: str, code: int, details: Optional[Dict] = None):
        super().__init__(message, code, details)

class GameError(BaseError):
    """游戏逻辑错误"""
    def __init__(self, message: str, code: int, details: Optional[Dict] = None):
        super().__init__(message, code, details)

class AIError(BaseError):
    """AI算法错误"""
    def __init__(self, message: str, code: int, details: Optional[Dict] = None):
        super().__init__(message, code, details)

class ServerError(BaseError):
    """服务器错误"""
    def __init__(self, message: str, code: int, details: Optional[Dict] = None):
        super().__init__(message, code, details)

class StorageError(BaseError):
    """存储错误"""
    def __init__(self, message: str, code: int, details: Optional[Dict] = None):
        super().__init__(message, code, details)

class NetworkError(BaseError):
    """网络通信错误"""
    def __init__(self, message: str, code: int, details: Optional[Dict] = None):
        super().__init__(message, code, details)

class ErrorHandler:
    """错误处理器（全局统一处理）"""
    @staticmethod
    def handle_error(error: Exception) -> Dict:
        """处理异常，返回错误字典"""
        if isinstance(error, BaseError):
            return error.to_dict()
        else:
            # 未知异常
            unknown_error = BaseError(
                message=str(error),
                code=9999,
                details={'type': type(error).__name__}
            )
            return unknown_error.to_dict()

    @staticmethod
    def handle_ui_error(error: Exception) -> str:
        """处理UI异常，返回用户友好提示"""
        error_dict = ErrorHandler.handle_error(error)
        return f"操作失败：{error_dict['message']}（错误码：{error_dict['code']}）"

    @staticmethod
    def handle_server_error(error: Exception) -> Dict:
        """处理服务器异常，返回网络响应"""
        error_dict = ErrorHandler.handle_error(error)
        return {
            'type': MSG_TYPES['ERROR'],
            'data': error_dict
        }
import os
import json
from abc import ABCMeta, abstractmethod
from typing import Any, Optional, List
from Common.logger import Logger
from Common.error_handler import StorageError

class BaseStorage(metaclass=ABCMeta):
    """存储基类（抽象接口，本地文件优先）"""
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.logger = Logger.get_instance()
        self._create_base_dir()

    def _create_base_dir(self):
        """创建基础存储目录（不存在则创建）"""
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir, exist_ok=True)
            self.logger.info(f"创建存储目录：{self.base_dir}")

    def _get_file_path(self, filename: str) -> str:
        """获取文件完整路径"""
        return os.path.join(self.base_dir, filename)

    @abstractmethod
    def save(self, data: Any, filename: str) -> bool:
        """保存数据（抽象方法，子类实现）"""
        raise NotImplementedError

    @abstractmethod
    def load(self, filename: str) -> Optional[Any]:
        """加载数据（抽象方法，子类实现）"""
        raise NotImplementedError

    def delete(self, filename: str) -> bool:
        """删除文件（通用实现）"""
        file_path = self._get_file_path(filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                self.logger.info(f"删除文件成功：{file_path}")
                return True
            except Exception as e:
                self.logger.error(f"删除文件失败：{str(e)}")
                raise StorageError(f"删除文件失败：{str(e)}", 5000)
        self.logger.warning(f"文件不存在：{file_path}")
        return False

    def list_files(self, suffix: str = None) -> List[str]:
        """列出存储目录下的文件（可选后缀过滤）"""
        files = os.listdir(self.base_dir)
        if suffix:
            files = [f for f in files if f.endswith(suffix)]
        return sorted(files, reverse=True)  # 按名称倒序（时间戳优先）

    def exists(self, filename: str) -> bool:
        """检查文件是否存在"""
        return os.path.exists(self._get_file_path(filename))

    def get_file_size(self, filename: str) -> int:
        """获取文件大小（字节）"""
        file_path = self._get_file_path(filename)
        if self.exists(filename):
            return os.path.getsize(file_path)
        return 0

    def get_file_mtime(self, filename: str) -> float:
        """获取文件最后修改时间戳"""
        file_path = self._get_file_path(filename)
        if self.exists(filename):
            return os.path.getmtime(file_path)
        return 0.0
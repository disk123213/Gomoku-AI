import json
import os
import torch
import shutil
import zipfile
import time
import re
from typing import Dict, List, Optional, Tuple
from Common.logger import Logger
from Common.error_handler import StorageError
from Storage.base_storage import BaseStorage

class ModelStorage(BaseStorage):
    """AI模型存储（.pth格式+版本控制+批量导入导出）"""
    def __init__(self):
        super().__init__('./data/model')
        self.logger = Logger.get_instance()
        self.model_suffix = '.pth'
        self.meta_suffix = '_meta.json'
        self.supported_model_types = ['rl', 'mcts', 'minimax', 'hybrid']

    def save_model_with_version(self, model_name: str, model_data: Dict, metadata: Dict) -> Tuple[str, str]:
        """保存模型并自动版本控制（生成模型文件+元数据文件）"""
        # 验证模型类型
        model_type = metadata.get('model_type', 'unknown')
        if model_type not in self.supported_model_types:
            raise StorageError(f"不支持的模型类型：{model_type}，支持类型：{self.supported_model_types}", 5003)
        
        # 获取下一个版本号
        version = self._get_next_version(model_name)
        timestamp = int(time.time())
        # 构建文件名
        model_filename = f"{model_name}_v{version}_{timestamp}{self.model_suffix}"
        meta_filename = f"{model_name}_v{version}_{timestamp}{self.meta_suffix}"
        
        # 保存模型文件
        model_path = self.get_model_path(model_filename)
        torch.save(model_data, model_path)
        
        # 构建并保存元数据
        meta_data = {
            'version': version,
            'timestamp': timestamp,
            'model_filename': model_filename,
            'model_type': model_type,
            'train_data_count': metadata.get('train_data_count', 0),
            'win_rate': round(metadata.get('win_rate', 0.0), 4),
            'train_params': metadata.get('train_params', {}),
            'board_size': metadata.get('board_size', 15),
            'description': metadata.get('description', '')
        }
        meta_path = self._get_file_path(meta_filename)
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta_data, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"保存带版本模型成功：{model_filename}，版本：v{version}")
        return model_path, meta_path

    def load_model(self, model_name: str, version: Optional[int] = None) -> Optional[Dict]:
        """加载模型（指定版本，默认加载最新版本）"""
        if version:
            # 加载指定版本
            meta_files = self._find_meta_files_by_version(model_name, version)
            if not meta_files:
                self.logger.error(f"模型 {model_name} 版本 v{version} 不存在")
                return None
            meta_file = meta_files[0]
        else:
            # 加载最新版本
            meta_file = self._find_latest_meta_file(model_name)
            if not meta_file:
                self.logger.error(f"模型 {model_name} 无可用版本")
                return None
        
        # 从元数据获取模型文件名
        meta_path = self._get_file_path(meta_file)
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta_data = json.load(f)
        model_filename = meta_data['model_filename']
        model_path = self.get_model_path(model_filename)
        
        # 加载模型
        try:
            model_data = torch.load(model_path, map_location=torch.device('cpu'))
            self.logger.info(f"加载模型成功：{model_filename}，版本：v{meta_data['version']}")
            return {
                'model_data': model_data,
                'metadata': meta_data
            }
        except Exception as e:
            self.logger.error(f"加载模型失败：{str(e)}")
            raise StorageError(f"模型加载失败：{str(e)}", 5004)

    def get_model_versions(self, model_name: str) -> List[Dict]:
        """获取模型的所有版本（按版本号倒序）"""
        meta_files = self._find_all_meta_files(model_name)
        versions = []
        for meta_file in meta_files:
            meta_path = self._get_file_path(meta_file)
            with open(meta_path, 'r', encoding='utf-8') as f:
                versions.append(json.load(f))
        # 按版本号降序排序
        versions.sort(key=lambda x: x['version'], reverse=True)
        return versions

    def rollback_model(self, model_name: str, version: int) -> Optional[str]:
        """回滚模型到指定版本（生成无版本后缀的当前模型文件）"""
        # 查找指定版本的元数据
        meta_files = self._find_meta_files_by_version(model_name, version)
        if not meta_files:
            raise StorageError(f"模型 {model_name} 版本 v{version} 不存在", 5005)
        
        meta_path = self._get_file_path(meta_files[0])
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta_data = json.load(f)
        
        # 复制为当前使用的模型（无版本后缀）
        target_model_name = f"{model_name}{self.model_suffix}"
        target_path = self.get_model_path(target_model_name)
        source_path = self.get_model_path(meta_data['model_filename'])
        shutil.copy2(source_path, target_path)
        
        # 同步更新元数据
        current_meta_name = f"{model_name}{self.meta_suffix}"
        current_meta_path = self._get_file_path(current_meta_name)
        with open(current_meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta_data, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"模型回滚成功：{model_name} -> 版本 v{version}")
        return target_path

    def batch_export_models(self, model_names: List[str], export_path: str) -> bool:
        """批量导出模型（含所有版本+元数据，压缩为ZIP）"""
        try:
            # 创建临时目录
            temp_dir = f"temp_model_export_{int(time.time())}"
            os.makedirs(temp_dir, exist_ok=True)
            
            # 复制指定模型的所有相关文件
            for model_name in model_names:
                # 查找所有模型文件和元数据文件
                model_files = self._find_all_model_files(model_name)
                for file in model_files:
                    src_path = self._get_file_path(file)
                    dst_path = os.path.join(temp_dir, file)
                    shutil.copy2(src_path, dst_path)
            
            # 压缩为ZIP
            with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        zipf.write(file_path, arcname=file)
            
            # 清理临时目录
            shutil.rmtree(temp_dir)
            self.logger.info(f"批量导出模型成功：{export_path}，共{len(model_names)}个模型")
            return True
        except Exception as e:
            self.logger.error(f"批量导出模型失败：{str(e)}")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise StorageError(f"模型批量导出失败：{str(e)}", 5006)

    def batch_import_models(self, import_path: str) -> bool:
        """从ZIP压缩包批量导入模型（自动恢复目录结构）"""
        try:
            if not os.path.exists(import_path):
                raise StorageError(f"导入文件不存在：{import_path}", 5007)
            
            # 创建临时目录
            temp_dir = f"temp_model_import_{int(time.time())}"
            os.makedirs(temp_dir, exist_ok=True)
            
            # 解压压缩包
            with zipfile.ZipFile(import_path, 'r') as zipf:
                zipf.extractall(temp_dir)
            
            # 复制文件到模型目录
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith(self.model_suffix) or file.endswith(self.meta_suffix):
                        src_path = os.path.join(root, file)
                        dst_path = self._get_file_path(file)
                        shutil.copy2(src_path, dst_path)
            
            # 清理临时目录
            shutil.rmtree(temp_dir)
            self.logger.info(f"批量导入模型成功：{import_path}")
            return True
        except Exception as e:
            self.logger.error(f"批量导入模型失败：{str(e)}")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise StorageError(f"模型批量导入失败：{str(e)}", 5008)

    def get_model_path(self, model_name: str) -> str:
        """获取模型完整路径（自动补全后缀）"""
        if not model_name.endswith(self.model_suffix):
            model_name += self.model_suffix
        return self._get_file_path(model_name)

    def _get_next_version(self, model_name: str) -> int:
        """获取下一个版本号"""
        meta_files = self._find_all_meta_files(model_name)
        if not meta_files:
            return 1
        versions = []
        for meta_file in meta_files:
            match = re.search(r'_v(\d+)_', meta_file)
            if match:
                versions.append(int(match.group(1)))
        return max(versions) + 1 if versions else 1

    def _find_all_meta_files(self, model_name: str) -> List[str]:
        """查找模型的所有元数据文件"""
        return [f for f in self.list_files(self.meta_suffix) if f.startswith(model_name)]

    def _find_meta_files_by_version(self, model_name: str, version: int) -> List[str]:
        """按版本号查找元数据文件"""
        return [f for f in self._find_all_meta_files(model_name) if f(f'_v{version}_') in f]

    def _find_latest_meta_file(self, model_name: str) -> Optional[str]:
        """查找最新的元数据文件（按版本号）"""
        meta_files = self._find_all_meta_files(model_name)
        if not meta_files:
            return None
        # 按版本号降序排序，取第一个
        meta_files.sort(key=lambda x: int(re.search(r'_v(\d+)_', x).group(1) if re.search(r'_v(\d+)_', x) else 0), reverse=True)
        return meta_files[0]

    def _find_all_model_files(self, model_name: str) -> List[str]:
        """查找模型的所有相关文件（.pth + .json）"""
        files = []
        for suffix in [self.model_suffix, self.meta_suffix]:
            files.extend([f for f in self.list_files(suffix) if f.startswith(model_name)])
        return files

    def save(self, data: Any, filename: str) -> bool:
        """实现抽象方法（直接调用torch.save，兼容基础保存）"""
        file_path = self._get_file_path(filename)
        try:
            torch.save(data, file_path)
            self.logger.info(f"保存模型成功：{file_path}")
            return True
        except Exception as e:
            self.logger.error(f"保存模型失败：{str(e)}")
            raise StorageError(f"模型保存失败：{str(e)}", 5009)

    def load(self, filename: str) -> Optional[Any]:
        """实现抽象方法（直接调用torch.load，兼容基础加载）"""
        file_path = self._get_file_path(filename)
        if not self.exists(filename):
            return None
        try:
            data = torch.load(file_path, map_location=torch.device('cpu'))
            self.logger.info(f"加载模型成功：{file_path}")
            return data
        except Exception as e:
            self.logger.error(f"加载模型失败：{str(e)}")
            raise StorageError(f"模型加载失败：{str(e)}", 5010)
import os
import torch
import zipfile
import shutil
from typing import List, Dict, Optional
from Common.config import Config
from Common.logger import Logger
from Storage.model_storage import ModelStorage
from AI.rl_ai import RLAI
from AI.nn_ai import NNAI

class ModelManager:
    """AI模型管理器（保存/加载/合并/导入导出）"""
    def __init__(self):
        self.config = Config.get_instance()
        self.logger = Logger.get_instance()
        self.model_storage = ModelStorage()
        self.model_dir = self.config.get('PATH', 'model_dir', './data/model')

    def get_user_models(self, user_id: str) -> List[Dict]:
        """获取用户的所有模型"""
        model_files = os.listdir(self.model_dir)
        user_models = []
        for file in model_files:
            if file.startswith(f"user_{user_id}_") and file.endswith('.pth'):
                # 解析模型信息
                meta_file = file.replace('.pth', '_meta.json')
                meta_path = os.path.join(self.model_dir, meta_file)
                if os.path.exists(meta_path):
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta_data = json.load(f)
                    user_models.append({
                        'name': file,
                        'path': os.path.join(self.model_dir, file),
                        'meta': meta_data,
                        'timestamp': os.path.getmtime(os.path.join(self.model_dir, file))
                    })
        # 按时间排序（最新在前）
        user_models.sort(key=lambda x: x['timestamp'], reverse=True)
        return user_models

    def load_model(self, ai_type: str, model_path: str, color: int, level: str) -> Optional[BaseAI]:
        """加载模型到对应AI"""
        if ai_type == 'rl':
            ai = RLAI(color, level)
            ai.load_model(model_path)
            return ai
        elif ai_type == 'nn':
            ai = NNAI(color, level, model_path)
            return ai
        else:
            self.logger.error(f"不支持的AI类型：{ai_type}")
            return None

    def merge_models(self, model_paths: List[str], output_name: str, ai_type: str) -> str:
        """合并多个模型（仅支持同类型AI）"""
        if len(model_paths) < 2:
            raise ValueError("合并模型至少需要2个输入模型")
        # 加载所有模型参数
        models = []
        for path in model_paths:
            checkpoint = torch.load(path, map_location=torch.device('cpu'))
            models.append(checkpoint['policy_net_state_dict'] if 'policy_net_state_dict' in checkpoint else checkpoint)
        # 平均参数合并
        merged_state = {}
        for key in models[0].keys():
            merged_state[key] = torch.stack([model[key] for model in models]).mean(dim=0)
        # 保存合并模型
        output_path = self.model_storage.get_model_path(output_name)
        torch.save({
            'policy_net_state_dict': merged_state,
            'merge_info': {
                'model_paths': model_paths,
                'merge_time': time.time(),
                'ai_type': ai_type
            }
        }, output_path)
        self.logger.info(f"合并模型成功：{output_path}，输入模型数：{len(model_paths)}")
        return output_path

    def export_models(self, model_names: List[str], export_path: str) -> bool:
        """批量导出模型（ZIP压缩）"""
        try:
            with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for model_name in model_names:
                    # 添加模型文件
                    model_path = self.model_storage.get_model_path(model_name)
                    if os.path.exists(model_path):
                        zipf.write(model_path, arcname=os.path.basename(model_path))
                    # 添加元数据文件
                    meta_name = model_name.replace('.pth', '_meta.json')
                    meta_path = os.path.join(self.model_dir, meta_name)
                    if os.path.exists(meta_path):
                        zipf.write(meta_path, arcname=meta_name)
            self.logger.info(f"批量导出模型成功：{export_path}，共{len(model_names)}个模型")
            return True
        except Exception as e:
            self.logger.error(f"批量导出模型失败：{str(e)}")
            return False

    def import_models(self, import_path: str) -> bool:
        """批量导入模型（ZIP解压）"""
        try:
            with zipfile.ZipFile(import_path, 'r') as zipf:
                zipf.extractall(self.model_dir)
            self.logger.info(f"批量导入模型成功：{import_path}")
            return True
        except Exception as e:
            self.logger.error(f"批量导入模型失败：{str(e)}")
            return False

    def delete_model(self, model_name: str) -> bool:
        """删除模型（含元数据）"""
        model_path = self.model_storage.get_model_path(model_name)
        if os.path.exists(model_path):
            os.remove(model_path)
        # 删除元数据文件
        meta_name = model_name.replace('.pth', '_meta.json')
        meta_path = os.path.join(self.model_dir, meta_name)
        if os.path.exists(meta_path):
            os.remove(meta_path)
        self.logger.info(f"删除模型成功：{model_name}")
        return True

    def rollback_model(self, model_name: str, version: int) -> Optional[str]:
        """回滚模型到指定版本"""
        return self.model_storage.rollback_model(model_name, version)
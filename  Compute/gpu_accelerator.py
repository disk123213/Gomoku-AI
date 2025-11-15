import torch
import torch.nn as nn
from typing import Optional, List, Callable
from Common.logger import Logger

class GPUAccelerator:
    """GPU加速管理器（CUDA适配+多GPU支持）"""
    def __init__(self):
        self.logger = Logger.get_instance()
        self.use_gpu = torch.cuda.is_available()
        self.device = torch.device('cuda' if self.use_gpu else 'cpu')
        self.gpu_count = torch.cuda.device_count() if self.use_gpu else 0
        self.scaler = torch.cuda.amp.GradScaler() if self.use_gpu else None
        self._log_gpu_info()

    def _log_gpu_info(self):
        """打印GPU信息（调试用）"""
        if self.use_gpu:
            gpu_info = torch.cuda.get_device_properties(0)
            self.logger.info(
                f"GPU加速启用：设备数={self.gpu_count}，"
                f"型号={gpu_info.name}，"
                f"显存={gpu_info.total_memory / 1024 / 1024:.2f}MB"
            )
        else:
            self.logger.warning("未检测到GPU，使用CPU运行（训练/推理速度较慢）")

    def move_model_to_gpu(self, model: nn.Module) -> nn.Module:
        """将模型移动到GPU（支持多GPU数据并行）"""
        model = model.to(self.device)
        if self.use_gpu and self.gpu_count > 1:
            model = nn.DataParallel(model)
            self.logger.info(f"启用多GPU数据并行：{self.gpu_count}个GPU")
        return model

    def move_tensor_to_gpu(self, tensor: torch.Tensor) -> torch.Tensor:
        """将张量移动到GPU（兼容CPU fallback）"""
        return tensor.to(self.device) if self.use_gpu else tensor

    def get_autocast_context(self):
        """获取混合精度训练上下文（装饰器/上下文管理器）"""
        if self.use_gpu:
            return torch.cuda.amp.autocast()
        else:
            # CPU兼容：空上下文
            class DummyAutocast:
                def __enter__(self):
                    pass
                def __exit__(self, exc_type, exc_val, exc_tb):
                    pass
            return DummyAutocast()

    def backward_with_scaler(self, loss: torch.Tensor, optimizer: torch.optim.Optimizer):
        """混合精度反向传播（兼容CPU）"""
        if self.use_gpu and self.scaler:
            self.scaler.scale(loss).backward()
            self.scaler.step(optimizer)
            self.scaler.update()
        else:
            loss.backward()
            optimizer.step()

    def empty_cache(self):
        """清空GPU缓存（释放显存）"""
        if self.use_gpu:
            torch.cuda.empty_cache()
            self.logger.info("GPU缓存已清空")

    def get_device(self) -> torch.device:
        """获取当前设备（GPU/CPU）"""
        return self.device
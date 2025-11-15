import pygame
import os
from typing import Dict, Optional

class ResourceManager:
    """资源管理器：加载字体、音效、图片资源"""
    def __init__(self, resource_dir: str = "./resources"):
        self.resource_dir = resource_dir
        self.fonts: Dict[str, pygame.font.Font] = {}
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        self.images: Dict[str, pygame.Surface] = {}

        # 初始化Pygame混音器
        pygame.mixer.init()
        # 创建资源目录（如果不存在）
        if not os.path.exists(resource_dir):
            os.makedirs(resource_dir)
            self._create_default_resources()

    def _create_default_resources(self):
        """创建默认资源（无资源文件时）"""
        # 无需实际创建文件，使用Pygame默认字体和颜色
        pass

    def load_font(self, font_name: str, size: int, font_file: Optional[str] = None) -> pygame.font.Font:
        """加载字体资源"""
        key = f"{font_name}_{size}"
        if key in self.fonts:
            return self.fonts[key]
        
        try:
            if font_file and os.path.exists(os.path.join(self.resource_dir, font_file)):
                font = pygame.font.Font(os.path.join(self.resource_dir, font_file), size)
            else:
                # 使用系统默认字体
                font = pygame.font.SysFont(font_name, size)
            self.fonts[key] = font
            return font
        except Exception as e:
            print(f"加载字体失败：{e}")
            return pygame.font.SysFont('Arial', size)

    def load_sound(self, sound_name: str, sound_file: str) -> Optional[pygame.mixer.Sound]:
        """加载音效资源"""
        if sound_name in self.sounds:
            return self.sounds[sound_name]
        
        sound_path = os.path.join(self.resource_dir, sound_file)
        if os.path.exists(sound_path):
            try:
                sound = pygame.mixer.Sound(sound_path)
                self.sounds[sound_name] = sound
                return sound
            except Exception as e:
                print(f"加载音效失败：{e}")
        return None

    def load_image(self, image_name: str, image_file: str, alpha: bool = True) -> Optional[pygame.Surface]:
        """加载图片资源"""
        if image_name in self.images:
            return self.images[image_name]
        
        image_path = os.path.join(self.resource_dir, image_file)
        if os.path.exists(image_path):
            try:
                if alpha:
                    image = pygame.image.load(image_path).convert_alpha()
                else:
                    image = pygame.image.load(image_path).convert()
                self.images[image_name] = image
                return image
            except Exception as e:
                print(f"加载图片失败：{e}")
        return None

    def play_sound(self, sound_name: str, volume: float = 0.5):
        """播放音效"""
        if sound_name in self.sounds:
            self.sounds[sound_name].set_volume(volume)
            self.sounds[sound_name].play()

    def get_font(self, font_name: str, size: int) -> pygame.font.Font:
        """获取已加载的字体"""
        return self.load_font(font_name, size)

    def get_image(self, image_name: str) -> Optional[pygame.Surface]:
        """获取已加载的图片"""
        return self.images.get(image_name)

    def get_sound(self, sound_name: str) -> Optional[pygame.mixer.Sound]:
        """获取已加载的音效"""
        return self.sounds.get(sound_name)

# 全局资源管理器实例
global_resources = ResourceManager()
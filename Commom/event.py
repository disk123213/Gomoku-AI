from typing import Dict, Callable, List, Any
from Common.logger import Logger

class Event:
    """事件类"""
    def __init__(self, event_type: str, data: Dict = None):
        self.type = event_type
        self.data = data or {}
        self.timestamp = self._get_timestamp()

    def _get_timestamp(self) -> int:
        """获取事件时间戳"""
        import time
        return int(time.time() * 1000)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'type': self.type,
            'data': self.data,
            'timestamp': self.timestamp
        }

class EventManager:
    """事件管理器（发布-订阅模式）"""
    def __init__(self):
        self.logger = Logger.get_instance()
        self.event_listeners: Dict[str, List[Callable[[Event], None]]] = {}
        self.lock = __import__('threading').Lock()

    def register(self, event_type: str, listener: Callable[[Event], None]):
        """注册事件监听器"""
        with self.lock:
            if event_type not in self.event_listeners:
                self.event_listeners[event_type] = []
            self.event_listeners[event_type].append(listener)
            self.logger.debug(f"注册事件监听器：{event_type}")

    def unregister(self, event_type: str, listener: Callable[[Event], None]):
        """注销事件监听器"""
        with self.lock:
            if event_type in self.event_listeners:
                if listener in self.event_listeners[event_type]:
                    self.event_listeners[event_type].remove(listener)
                    self.logger.debug(f"注销事件监听器：{event_type}")
                if not self.event_listeners[event_type]:
                    del self.event_listeners[event_type]

    def emit(self, event: Event):
        """发布事件"""
        with self.lock:
            event_type = event.type
            if event_type not in self.event_listeners:
                self.logger.debug(f"无监听器的事件：{event_type}")
                return
            # 触发所有监听器
            for listener in self.event_listeners[event_type]:
                try:
                    listener(event)
                except Exception as e:
                    self.logger.error(f"事件{event_type}监听器执行失败：{str(e)}")

    def clear(self):
        """清空所有监听器"""
        with self.lock:
            self.event_listeners.clear()
            self.logger.debug("清空所有事件监听器")

    def get_listener_count(self, event_type: str) -> int:
        """获取事件监听器数量"""
        with self.lock:
            return len(self.event_listeners.get(event_type, []))
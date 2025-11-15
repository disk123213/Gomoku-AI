import threading
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from typing import List, Callable, Any
from Common.logger import Logger

class ParallelCompute:
    """并行计算管理器（多线程/多进程统一接口）"""
    def __init__(self, mode: str = 'thread', max_workers: int = None):
        """
        初始化并行计算
        :param mode: 并行模式：'thread'（多线程）/ 'process'（多进程）
        :param max_workers: 最大工作线程/进程数，默认CPU核心数
        """
        self.logger = Logger.get_instance()
        self.mode = mode.lower()
        self.max_workers = max_workers or (multiprocessing.cpu_count() // 2)
        self._validate_mode()
        self.logger.info(f"并行计算初始化：模式={self.mode}，最大工作数={self.max_workers}")

    def _validate_mode(self):
        """验证并行模式"""
        if self.mode not in ['thread', 'process']:
            raise ValueError(f"不支持的并行模式：{self.mode}，仅支持'thread'/'process'")

    def run_parallel(self, func: Callable, args_list: List[Tuple[Any, ...]]) -> List[Any]:
        """
        并行执行任务
        :param func: 任务函数（多进程模式下需支持序列化）
        :param args_list: 任务参数列表，每个元素为一个任务的参数元组
        :return: 任务结果列表（与args_list顺序一致）
        """
        if not args_list:
            return []

        try:
            if self.mode == 'thread':
                return self._run_thread_parallel(func, args_list)
            else:
                return self._run_process_parallel(func, args_list)
        except Exception as e:
            self.logger.error(f"并行执行失败：{str(e)}")
            return []

    def _run_thread_parallel(self, func: Callable, args_list: List[Tuple[Any, ...]]) -> List[Any]:
        """多线程并行（适用于IO密集型任务）"""
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交任务并保持顺序
            futures = [executor.submit(func, *args) for args in args_list]
            results = [future.result() for future in futures]
        return results

    def _run_process_parallel(self, func: Callable, args_list: List[Tuple[Any, ...]]) -> List[Any]:
        """多进程并行（适用于CPU密集型任务）"""
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            results = list(executor.map(func, *zip(*args_list)))
        return results

    def run_async(self, func: Callable, args: Tuple[Any, ...], callback: Optional[Callable] = None):
        """
        异步执行单个任务（非阻塞）
        :param func: 任务函数
        :param args: 任务参数
        :param callback: 任务完成后的回调函数（仅多线程模式支持）
        """
        def _task_wrapper():
            result = func(*args)
            if callback:
                callback(result)

        if self.mode == 'thread':
            thread = threading.Thread(target=_task_wrapper, daemon=True)
            thread.start()
            return thread
        else:
            process = multiprocessing.Process(target=func, args=args, daemon=True)
            process.start()
            return process

    @staticmethod
    def parallel_mcts_iterations(root: Any, iterations: int, mcts_iter_func: Callable):
        """
        并行执行MCTS迭代（专用接口）
        :param root: MCTS根节点（需线程安全）
        :param iterations: 总迭代次数
        :param mcts_iter_func: 单次迭代函数（参数：root）
        """
        def _iter_task(_):
            mcts_iter_func(root)

        parallel = ParallelCompute(mode='thread', max_workers=4)
        parallel.run_parallel(_iter_task, [(i,) for i in range(iterations)])

    @staticmethod
    def parallel_self_play(num_games: int, self_play_func: Callable, max_workers: int = 4):
        """
        并行自我对弈（专用接口）
        :param num_games: 总游戏数
        :param self_play_func: 单局自我对弈函数（参数：game_idx）
        :param max_workers: 最大工作数
        """
        parallel = ParallelCompute(mode='process', max_workers=max_workers)
        parallel.run_parallel(self_play_func, [(i,) for i in range(num_games)])
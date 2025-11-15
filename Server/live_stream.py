import json
import threading
import time
import websockets
import asyncio
import pygame
import subprocess
import os
from typing import List, Dict, Optional, Callable
from Common.constants import COLORS
from Common.logger import Logger
from Common.data_utils import DataUtils
from Storage.base_storage import BaseStorage

class LiveStreamManager(BaseStorage):
    """直播流管理器（主播+观众+回放，兼容GameCore集成）"""
    def __init__(self, host: str = '0.0.0.0', port: int = 9999, replay_dir: str = './data/live_replay'):
        super().__init__(replay_dir)
        self.host = host
        self.port = port
        self.logger = Logger.get_instance()
        
        # 直播间状态：room_id -> 房间详情
        self.live_rooms: Dict[str, Dict] = {}
        self.room_counter = 10000  # 直播间ID自增
        self.lock = threading.Lock()
        
        # WebSocket服务器状态
        self.server_thread: Optional[threading.Thread] = None
        self.running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def start_server(self):
        """启动直播服务器（非阻塞，兼容主线程）"""
        self.running = True
        # 启动异步事件循环线程
        self.server_thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.server_thread.start()
        self.logger.info(f"直播服务器启动：ws://{self.host}:{self.port}，回放目录：{self.base_dir}")

    def stop_server(self):
        """停止直播服务器（安全清理资源）"""
        self.running = False
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        # 关闭所有直播间
        with self.lock:
            for room_id in list(self.live_rooms.keys()):
                self._close_room(room_id)
        self.logger.info("直播服务器已停止")

    def _run_event_loop(self):
        """运行异步事件循环（内部使用）"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._start_websocket_server())
        except Exception as e:
            self.logger.error(f"直播服务器异常：{str(e)}")

    async def _start_websocket_server(self):
        """启动WebSocket服务（异步核心）"""
        async with websockets.serve(self._handle_client, self.host, self.port):
            while self.running:
                await asyncio.sleep(1)

    async def _handle_client(self, websocket: websockets.WebSocketServerProtocol, path: str):
        """处理客户端连接（主播/观众统一入口）"""
        client_addr = websocket.remote_address
        self.logger.info(f"直播客户端连接：{client_addr}")
        
        try:
            # 身份认证（必须携带type/user_id）
            auth_msg = await websocket.recv()
            auth_data = json.loads(auth_msg)
            client_type = auth_data.get('type')  # 'host' 或 'viewer'
            user_id = auth_data.get('user_id')
            user_name = auth_data.get('user_name', f"观众_{client_addr[1]}")
            
            if not client_type or not user_id:
                await websocket.send(json.dumps({
                    'type': 'error',
                    'code': 401,
                    'message': '身份认证失败：缺少type或user_id'
                }))
                return

            # 分发处理逻辑
            if client_type == 'host':
                await self._handle_host(websocket, user_id, user_name)
            elif client_type == 'viewer':
                room_id = auth_data.get('room_id')
                if not room_id:
                    await websocket.send(json.dumps({
                        'type': 'error',
                        'code': 400,
                        'message': '缺少直播间ID'
                    }))
                    return
                await self._handle_viewer(websocket, user_id, user_name, room_id)
            else:
                await websocket.send(json.dumps({
                    'type': 'error',
                    'code': 400,
                    'message': f"不支持的客户端类型：{client_type}"
                }))
        except websockets.exceptions.ConnectionClosedOK:
            self.logger.info(f"直播客户端正常断开：{client_addr}")
        except Exception as e:
            self.logger.error(f"直播客户端处理异常 {client_addr}：{str(e)}")
        finally:
            # 清理客户端连接（观众/主播）
            self._cleanup_client(websocket)

    async def _handle_host(self, websocket: websockets.WebSocketServerProtocol, user_id: str, user_name: str):
        """处理主播连接（创建直播间+数据广播）"""
        # 创建直播间（线程安全）
        with self.lock:
            room_id = str(self.room_counter)
            self.room_counter += 1
            self.live_rooms[room_id] = {
                'host_id': user_id,
                'host_name': user_name,
                'host_socket': websocket,
                'viewers': {},  # viewer_id -> (socket, name)
                'status': 'live',  # live/closed
                'game_state': {
                    'board': DataUtils.board_to_str([[0]*15 for _ in range(15)]),
                    'move_history': [],
                    'current_player': 1,
                    'ai_thinking': {}
                },
                'replay_frames': [],  # 回放帧缓存
                'start_time': time.time()
            }

        # 通知主播创建成功
        await websocket.send(json.dumps({
            'type': 'live_start',
            'room_id': room_id,
            'message': f"直播间创建成功（ID：{room_id}），观众可通过该ID加入"
        }))
        self.logger.info(f"主播 {user_name}（ID：{user_id}）创建直播间：{room_id}")

        # 监听主播的游戏数据广播
        try:
            while self.running and self._is_room_valid(room_id):
                game_data = await websocket.recv()
                data = json.loads(game_data)
                
                # 验证数据格式
                if not self._validate_game_data(data):
                    await websocket.send(json.dumps({
                        'type': 'error',
                        'message': '无效的游戏数据格式'
                    }))
                    continue
                
                # 更新房间状态+缓存回放帧
                with self.lock:
                    room = self.live_rooms[room_id]
                    room['game_state'].update(data)
                    # 缓存回放帧（含时间戳）
                    room['replay_frames'].append({
                        'timestamp': time.time(),
                        'game_state': room['game_state'].copy()
                    })
                
                # 广播给所有观众
                await self._broadcast_to_viewers(room_id, {
                    'type': 'game_update',
                    'data': data,
                    'timestamp': time.time()
                })
        finally:
            # 主播断开，保存回放+关闭房间
            self._save_replay(room_id)
            self._close_room(room_id)

    async def _handle_viewer(self, websocket: websockets.WebSocketServerProtocol, user_id: str, user_name: str, room_id: str):
        """处理观众连接（加入房间+接收广播）"""
        # 检查直播间有效性
        if not self._is_room_valid(room_id):
            await websocket.send(json.dumps({
                'type': 'error',
                'message': f"直播间 {room_id} 不存在或已关闭"
            }))
            return

        # 加入直播间（线程安全）
        with self.lock:
            room = self.live_rooms[room_id]
            room['viewers'][user_id] = (websocket, user_name)

        # 通知观众加入成功+发送当前游戏状态
        room = self.live_rooms[room_id]
        await websocket.send(json.dumps({
            'type': 'join_success',
            'room_id': room_id,
            'host_name': room['host_name'],
            'current_game': room['game_state'],
            'viewer_count': len(room['viewers'])
        }))
        self.logger.info(f"观众 {user_name}（ID：{user_id}）加入直播间 {room_id}，当前观众数：{len(room['viewers'])}")

        # 广播新观众加入
        await self._broadcast_to_viewers(room_id, {
            'type': 'viewer_join',
            'data': {'user_name': user_name},
            'viewer_count': len(room['viewers'])
        })

        # 监听观众消息（弹幕/互动）
        try:
            async for msg in websocket:
                msg_data = json.loads(msg)
                if msg_data.get('type') == 'chat':
                    # 广播弹幕
                    await self._broadcast_to_viewers(room_id, {
                        'type': 'chat_message',
                        'data': {
                            'user_name': user_name,
                            'content': msg_data.get('content', ''),
                            'timestamp': time.time()
                        }
                    })
                    # 同步给主播
                    await self._send_to_host(room_id, {
                        'type': 'viewer_chat',
                        'data': {
                            'user_name': user_name,
                            'content': msg_data.get('content', '')
                        }
                    })
        finally:
            # 观众断开，清理连接
            with self.lock:
                if self._is_room_valid(room_id):
                    room = self.live_rooms[room_id]
                    if user_id in room['viewers']:
                        del room['viewers'][user_id]
                        viewer_count = len(room['viewers'])
                        # 广播观众离开
                        await self._broadcast_to_viewers(room_id, {
                            'type': 'viewer_leave',
                            'data': {'user_name': user_name},
                            'viewer_count': viewer_count
                        })
                        self.logger.info(f"观众 {user_name} 离开直播间 {room_id}，剩余观众数：{viewer_count}")

    def _validate_game_data(self, data: Dict) -> bool:
        """验证游戏数据格式（确保兼容可视化）"""
        required_fields = ['board', 'current_player']
        return all(field in data for field in required_fields)

    def _is_room_valid(self, room_id: str) -> bool:
        """检查直播间是否有效（线程安全）"""
        with self.lock:
            return room_id in self.live_rooms and self.live_rooms[room_id]['status'] == 'live'

    async def _broadcast_to_viewers(self, room_id: str, message: Dict):
        """广播消息给直播间所有观众（异步）"""
        if not self._is_room_valid(room_id):
            return

        with self.lock:
            room = self.live_rooms[room_id]
            viewers = list(room['viewers'].values())  # 快照，避免迭代中修改

        for viewer_socket, viewer_name in viewers:
            try:
                await viewer_socket.send(json.dumps(message))
            except Exception as e:
                self.logger.error(f"广播给观众 {viewer_name} 失败：{str(e)}")

    async def _send_to_host(self, room_id: str, message: Dict):
        """发送消息给主播（异步）"""
        if not self._is_room_valid(room_id):
            return

        with self.lock:
            room = self.live_rooms[room_id]
            host_socket = room['host_socket']

        try:
            await host_socket.send(json.dumps(message))
        except Exception as e:
            self.logger.error(f"发送给主播 {room['host_name']} 失败：{str(e)}")

    def _save_replay(self, room_id: str):
        """保存直播回放（JSON格式，兼容后续转视频）"""
        if not self._is_room_valid(room_id):
            return

        with self.lock:
            room = self.live_rooms[room_id]
            if not room['replay_frames']:
                self.logger.warning(f"直播间 {room_id} 无回放数据，跳过保存")
                return

            # 构建回放文件名
            start_time_str = time.strftime("%Y%m%d_%H%M%S", time.localtime(room['start_time']))
            replay_filename = f"replay_{room['host_name']}_{start_time_str}_{room_id}.json"
            replay_path = self._get_file_path(replay_filename)

            # 保存回放数据
            replay_data = {
                'room_id': room_id,
                'host_id': room['host_id'],
                'host_name': room['host_name'],
                'start_time': room['start_time'],
                'end_time': time.time(),
                'total_frames': len(room['replay_frames']),
                'frames': room['replay_frames']
            }

            with open(replay_path, 'w', encoding='utf-8') as f:
                json.dump(replay_data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"直播回放保存成功：{replay_path}")

    def convert_replay_to_video(self, replay_path: str, output_path: str, fps: int = 10) -> bool:
        """将回放文件转换为视频（依赖FFmpeg，兼容Pygame渲染）"""
        if not os.path.exists(replay_path):
            self.logger.error(f"回放文件不存在：{replay_path}")
            return False

        try:
            # 加载回放数据
            with open(replay_path, 'r', encoding='utf-8') as f:
                replay_data = json.load(f)

            # 初始化Pygame渲染器
            pygame.init()
            screen = pygame.display.set_mode((800, 600))
            clock = pygame.time.Clock()
            font = pygame.font.SysFont('Arial', 12)

            # 初始化棋盘渲染参数
            cell_size = 30
            board_x, board_y = 50, 50
            board_size = 15

            # 构建FFmpeg命令（管道输出，避免中间文件）
            ffmpeg_cmd = [
                'ffmpeg', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '800x600',
                '-r', str(fps), '-i', '-', '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                output_path
            ]
            process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

            # 渲染每一针
            for frame in replay_data['frames']:
                game_state = frame['game_state']
                board = DataUtils.str_to_board(game_state['board'])

                # 清空屏幕
                screen.fill(COLORS['PANEL_BG'])

                # 绘制棋盘网格
                for i in range(board_size + 1):
                    # 横线
                    pygame.draw.line(screen, COLORS['GRAY'], (board_x, board_y + i*cell_size),
                                   (board_x + (board_size-1)*cell_size, board_y + i*cell_size), 1)
                    # 竖线
                    pygame.draw.line(screen, COLORS['GRAY'], (board_x + i*cell_size, board_y),
                                   (board_x + i*cell_size, board_y + (board_size-1)*cell_size), 1)

                # 绘制棋子
                for x in range(board_size):
                    for y in range(board_size):
                        piece = board[x][y]
                        if piece == 0:
                            continue
                        color = COLORS['BLACK'] if piece == 1 else COLORS['WHITE']
                        center = (board_x + y*cell_size, board_y + x*cell_size)
                        pygame.draw.circle(screen, color, center, cell_size//2 - 2)
                        pygame.draw.circle(screen, COLORS['GRAY'], center, cell_size//2 - 2, 1)

                # 绘制游戏信息
                info_text = font.render(
                    f"主播：{replay_data['host_name']} | 回合：{len(game_state['move_history'])} | 当前玩家：{'黑方' if game_state['current_player'] == 1 else '白方'}",
                    True, COLORS['TEXT_LIGHT']
                )
                screen.blit(info_text, (50, 520))

                # 绘制帧率
                fps_text = font.render(f"FPS: {fps}", True, COLORS['TEXT_LIGHT'])
                screen.blit(fps_text, (720, 10))

                # 转换为RGB数据并写入FFmpeg
                frame_data = pygame.surfarray.array3d(screen).tobytes()
                process.stdin.write(frame_data)
                clock.tick(fps)

            # 完成转换
            process.stdin.close()
            process.wait()
            pygame.quit()

            if process.returncode == 0:
                self.logger.info(f"回放转视频成功：{output_path}")
                return True
            else:
                stderr = process.stderr.read().decode('utf-8')
                self.logger.error(f"FFmpeg执行失败：{stderr}")
                return False
        except Exception as e:
            self.logger.error(f"回放转视频异常：{str(e)}")
            pygame.quit()
            return False

    def _close_room(self, room_id: str):
        """关闭直播间（清理资源，线程安全）"""
        with self.lock:
            if room_id not in self.live_rooms:
                return
            room = self.live_rooms[room_id]
            room['status'] = 'closed'

            # 关闭主播连接
            try:
                asyncio.run_coroutine_threadsafe(room['host_socket'].close(), self.loop)
            except:
                pass

            # 关闭所有观众连接
            for viewer_socket, viewer_name in room['viewers'].values():
                try:
                    asyncio.run_coroutine_threadsafe(viewer_socket.close(), self.loop)
                except:
                    pass

            # 移除房间
            del self.live_rooms[room_id]
            self.logger.info(f"直播间 {room_id} 已关闭")

    def _cleanup_client(self, websocket: websockets.WebSocketServerProtocol):
        """清理客户端连接（处理异常断开）"""
        with self.lock:
            # 查找主播连接
            for room_id, room in self.live_rooms.items():
                if room['host_socket'] == websocket:
                    self._save_replay(room_id)
                    self._close_room(room_id)
                    return
            # 查找观众连接
            for room_id, room in self.live_rooms.items():
                for viewer_id, (viewer_socket, viewer_name) in room['viewers'].items():
                    if viewer_socket == websocket:
                        del room['viewers'][viewer_id]
                        self.logger.info(f"观众 {viewer_name} 异常断开直播间 {room_id}")
                        return

    def get_live_rooms(self) -> List[Dict]:
        """获取当前直播列表（供UI展示）"""
        with self.lock:
            room_list = []
            for room_id, room in self.live_rooms.items():
                if room['status'] == 'live':
                    room_list.append({
                        'room_id': room_id,
                        'host_name': room['host_name'],
                        'viewer_count': len(room['viewers']),
                        'start_time': time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(room['start_time'])),
                        'move_count': len(room['game_state']['move_history'])
                    })
            # 按观众数排序
            room_list.sort(key=lambda x: x['viewer_count'], reverse=True)
            return room_list
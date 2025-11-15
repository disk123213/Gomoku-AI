import argparse
import sys
import pygame
import threading
from typing import Optional
from Game.game_core import GameCore
from Network.live_stream import LiveStreamManager
from Compute.gpu_accelerator import GPUAccelerator
from Common.config import Config
from Common.logger import Logger
from UI.visualizer import AdvancedAIVisualizer
from UI.board_renderer import BoardRenderer
from Common.constants import GAME_MODES, AI_LEVELS, COLORS

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="五子棋AI人机对战程序")
    parser.add_argument("--mode", type=str, default="PVE", choices=[v for v in GAME_MODES.values()],
                        help=f"游戏模式：{', '.join(GAME_MODES.values())}")
    parser.add_argument("--ai-level", type=str, default="MEDIUM", choices=[v for v in AI_LEVELS.values()],
                        help=f"AI难度：{', '.join(AI_LEVELS.values())}")
    parser.add_argument("--gpu", action="store_true", help="启用GPU加速（需安装CUDA）")
    parser.add_argument("--live", action="store_true", help="启动直播服务器（支持观众观看）")
    parser.add_argument("--user-id", type=str, default="default_user", help="用户ID（用于存储数据和排行榜）")
    parser.add_argument("--board-size", type=int, default=15, choices=[15, 19], help="棋盘尺寸（15/19路）")
    return parser.parse_args()

def init_pygame():
    """初始化Pygame"""
    pygame.init()
    pygame.display.set_caption("五子棋AI对战程序 - 豆包开发")
    screen = pygame.display.set_mode((1200, 700))  # 适配棋盘+可视化组件
    clock = pygame.time.Clock()
    return screen, clock

def draw_ui(screen: pygame.Surface, game_core: GameCore, visualizer: AdvancedAIVisualizer, board_renderer: BoardRenderer):
    """绘制UI界面"""
    # 清空屏幕
    screen.fill(COLORS['PANEL_BG'])
    # 绘制棋盘
    board_renderer.draw(screen, game_core.board)
    # 绘制AI思维可视化
    visualizer.draw(screen)
    # 绘制控制面板（简化版：显示模式、AI难度、积分）
    font = pygame.font.SysFont('Arial', 14)
    mode_text = font.render(f"模式：{game_core.current_mode} | AI难度：{game_core.ai_level} | 积分：{game_core.user_storage.load_user(game_core.train_user_id)['elo_score']}",
                           True, COLORS['TEXT_LIGHT'])
    screen.blit(mode_text, (20, 10))
    # 绘制游戏状态（是否活跃、当前玩家）
    state_text = font.render(f"状态：{'活跃' if game_core.game_active else '暂停'} | 当前玩家：{'黑方' if game_core.current_player == 1 else '白方'}",
                           True, COLORS['TEXT_LIGHT'])
    screen.blit(state_text, (20, 40))
    # 更新显示
    pygame.display.flip()

def handle_events(game_core: GameCore, board_renderer: BoardRenderer) -> bool:
    """处理Pygame事件"""
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            # 退出程序：保存数据、关闭直播服务器
            game_core.stop_live()
            pygame.quit()
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and game_core.game_active:
            if event.button == 1:  # 左键落子
                x, y = event.pos
                # 棋盘坐标转换
                board_x, board_y = board_renderer.screen_to_board(x, y)
                if 0 <= board_x < game_core.board_size and 0 <= board_y < game_core.board_size:
                    # 执行落子
                    result = game_core.place_piece(board_x, board_y, is_ai=False)
                    if result == 'success' and game_core.current_mode == GAME_MODES['PVE'] and game_core.current_player == game_core.current_ai.color:
                        # AI落子（异步）
                        threading.Thread(target=game_core.ai_move, args=(lambda data: visualizer.update_thinking_data(data),), daemon=True).start()
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_r:  # 重置游戏
                game_core.reset_game()
            if event.key == pygame.K_s:  # 保存对战记录
                game_core.game_storage.save_game_record({
                    'user_id': game_core.train_user_id,
                    'mode': game_core.current_mode,
                    'move_history': game_core.move_history,
                    'result': game_core.game_result,
                    'timestamp': time.time()
                })
    return True

def main():
    """主函数"""
    # 解析命令行参数
    args = parse_args()
    # 初始化配置、日志
    config = Config.get_instance()
    config.board_size = args.board_size
    logger = Logger.get_instance()
    logger.info(f"启动五子棋AI对战程序 | 模式：{args.mode} | AI难度：{args.ai_level} | GPU加速：{args.gpu}")
    
    # 初始化GPU加速
    if args.gpu:
        gpu_accelerator = GPUAccelerator()
        logger.info(f"GPU加速状态：{'启用' if gpu_accelerator.use_gpu else '未启用'}")
    
    # 初始化游戏核心
    game_core = GameCore()
    game_core.train_user_id = args.user_id
    # 设置游戏模式和AI难度
    game_core.set_mode(args.mode, args.user_id)
    game_core.ai_level = args.ai_level
    
    # 启动直播服务器（如果指定--live）
    if args.live:
        game_core.live_manager.start_server()
        logger.info(f"直播服务器启动：ws://{config.server_host}:{config.live_port}")
        # 主播模式启动直播（可选：默认不自动启动，用户可在UI中手动开始）
        if args.mode == GAME_MODES['ONLINE']:
            room_id = game_core.start_live(args.user_id, game_core.user_storage.load_user(args.user_id)['nickname'])
            logger.info(f"直播间创建成功：ID={room_id}")
    
    # 初始化UI组件
    screen, clock = init_pygame()
    board_renderer = BoardRenderer(x=50, y=80, size=args.board_size, cell_size=40)
    visualizer = AdvancedAIVisualizer(x=50, y=80, size=args.board_size, cell_size=40)
    
    # 启动游戏（AI先手处理）
    game_core.start_game()
    if args.mode == GAME_MODES['PVE'] and game_core.ai_first:
        threading.Thread(target=game_core.ai_move, args=(lambda data: visualizer.update_thinking_data(data),), daemon=True).start()
    
    # 游戏循环
    running = True
    while running:
        # 处理事件
        running = handle_events(game_core, board_renderer)
        # 绘制UI
        draw_ui(screen, game_core, visualizer, board_renderer)
        # 控制帧率
        clock.tick(30)
    
    logger.info("程序正常退出")
    sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger = Logger.get_instance()
        logger.error(f"程序运行异常：{str(e)}", exc_info=True)
        sys.exit(1)
from typing import Dict, List

# 颜色常量（Win11适配色值）
class COLORS:
    BLACK = (0, 0, 0)
    WHITE = (255, 255, 255)
    RED = (255, 0, 0)
    GREEN = (0, 255, 0)
    BLUE = (0, 0, 255)
    YELLOW = (255, 215, 0)
    PURPLE = (128, 0, 128)
    GRAY = (128, 128, 128)
    LIGHT_GRAY = (200, 200, 200)
    DARK_GRAY = (64, 64, 64)
    BOARD_BG = (245, 222, 179)  # 棋盘底色（木质纹理色）
    BOARD_LINE = (0, 0, 0)    # 棋盘线条色
    PANEL_BG = (30, 30, 30)   # 控制面板底色
    PANEL_BORDER = (64, 64, 64)# 控制面板边框色
    BUTTON = (64, 64, 64)     # 按钮底色
    BUTTON_HOVER = (96, 96, 96)# 按钮悬停色
    TEXT = (255, 255, 255)   # 文本色
    TEXT_LIGHT = (200, 200, 200)# 浅色文本
    HINT = (0, 255, 255)    # 提示色
    WIN_LINE = (255, 0, 0)    # 获胜线颜色
    THINKING = (255, 215, 0) # AI思考提示色

# 棋子颜色常量
class PIECE_COLORS:
    EMPTY = 0       # 空位置
    BLACK = 1       # 黑棋
    WHITE = 2       # 白棋

# 游戏模式常量
class GAME_MODES:
    PVE = 'pve'         # 人机对战
    PVP = 'pvp'         # 人人对战
    ONLINE = 'online'   # 联机对战
    TRAIN = 'train'     # 训练模式

# AI难度常量
class AI_LEVELS:
    EASY = 'easy'     # 简单
    MEDIUM = 'medium' # 中等
    HARD = 'hard'     # 困难
    EXPERT = 'expert' # 专家

# 房间状态常量
class ROOM_STATUSES:
    WAITING = 'waiting' # 等待中
    PLAYING = 'playing' # 游戏中
    ENDED = 'ended'     # 已结束

# 训练状态常量
class TRAIN_STATUSES:
    IDLE = 'idle'       # 空闲
    TRAINING = 'training' # 训练中
    COMPLETED = 'completed' # 完成
    FAILED = 'failed'   # 失败

# 消息类型常量（网络通信）
class MSG_TYPES:
    LOGIN = 'login'             # 登录
    LOGOUT = 'logout'           # 退出
    CREATE_ROOM = 'create_room' # 创建房间
    JOIN_ROOM = 'join_room'     # 加入房间
    LEAVE_ROOM = 'leave_room'   # 离开房间
    MOVE = 'move'               # 落子
    CHAT = 'chat'               # 聊天
    HEARTBEAT = 'heartbeat'     # 心跳
    GAME_END = 'game_end'       # 游戏结束
    RESET_GAME = 'reset_game'   # 重置游戏
    P2P_CONFIRM = 'p2p_confirm' # P2P连接确认
    P2P_PEER_ADDR = 'p2p_peer_addr' # P2P对等方地址
    ERROR = 'error'             # 错误
    VIEWER_CHAT = 'viewer_chat' # 观众弹幕
    GAME_UPDATE = 'game_update' # 游戏更新
    LIVE_START = 'live_start'   # 直播开始
    JOIN_SUCCESS = 'join_success' # 加入成功

# 评估权重常量（从配置读取，默认值）
EVAL_WEIGHTS: Dict[str, float] = {
    'FIVE': 100000.0,
    'FOUR': 10000.0,
    'BLOCKED_FOUR': 5000.0,
    'THREE': 1000.0,
    'BLOCKED_THREE': 500.0,
    'TWO': 100.0,
    'BLOCKED_TWO': 50.0,
    'ONE': 10.0
}

# 错误状态码常量
ERROR_CODES: Dict[int, str] = {
    # 配置错误（1000-1099）
    1001: '配置项不存在',
    1002: '配置类型错误（整数）',
    1003: '配置类型错误（浮点数）',
    1004: '配置类型错误（布尔值）',
    # UI错误（2000-2099）
    2001: 'UI组件初始化失败',
    2002: '窗口尺寸无效',
    2003: '棋子绘制失败',
    # 游戏错误（3000-3099）
    3001: '不支持的游戏模式',
    3002: '游戏未激活',
    3003: '落子位置无效',
    3004: '位置已被占用',
    3005: '不是当前玩家回合',
    # AI错误（4000-4099）
    4001: '不支持的AI类型',
    4002: 'AI模型加载失败',
    4003: 'AI落子超时',
    4004: '训练数据为空',
    # 服务器错误（5000-5099）
    5001: '服务器启动失败',
    5002: '客户端连接失败',
    5003: '房间不存在',
    5004: '房间已满',
    # 存储错误（6000-6099）
    6001: '文件读写失败',
    6002: '数据格式错误',
    6003: '模型文件损坏'
}

# 棋盘星位点（15x15棋盘）
STAR_POSITIONS: List[tuple] = [(3, 3), (3, 11), (7, 7), (11, 3), (11, 11)]

# 命令行参数常量
CLI_ARGS: Dict[str, str] = {
    '--mode': '指定启动模式（pve/pvp/online/train）',
    '--ai-level': '指定AI难度（easy/medium/hard/expert）',
    '--gpu': '启用GPU加速（默认禁用）',
    '--live': '启动直播服务器（默认禁用）',
    '--width': '窗口宽度（默认1280）',
    '--height': '窗口高度（默认720）',
    '--board-size': '棋盘尺寸（默认15）'
}
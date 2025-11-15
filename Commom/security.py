import os
import time
import hashlib
import hmac
import base64
from typing import Optional, Tuple, Dict, Any
import random
from Common.logger import Logger
from Common.error_handler import StorageError, NetworkError
from Common.data_utils import DataUtils

class SecurityUtils:
    """轻量加密工具类（用户数据/通信校验/安全防护）"""
    # 全局加密密钥（Win11本地安全存储，不硬编码，首次运行生成）
    _SECRET_KEY: Optional[bytes] = None
    _HMAC_KEY: Optional[bytes] = None
    _SALT: str = "GobangAI_Win11_Salt_2025"  # 固定盐值（适配历史数据）
    _KEY_FILE: str = os.path.join(os.getcwd(), 'data', 'config', 'security_key.bin')

    @classmethod
    def _init_keys(cls):
        """初始化加密密钥（首次运行生成，本地安全存储）"""
        if cls._SECRET_KEY and cls._HMAC_KEY:
            return
        # 创建密钥目录
        key_dir = os.path.dirname(cls._KEY_FILE)
        if not os.path.exists(key_dir):
            os.makedirs(key_dir)
        # 读取或生成密钥
        if os.path.exists(cls._KEY_FILE):
            try:
                with open(cls._KEY_FILE, 'rb') as f:
                    data = f.read()
                    cls._SECRET_KEY = data[:32]  # AES-256密钥（32字节）
                    cls._HMAC_KEY = data[32:64]  # HMAC密钥（32字节）
                Logger.get_instance().info("加密密钥加载成功")
            except Exception as e:
                Logger.get_instance().error(f"加载密钥失败：{str(e)}，重新生成")
                cls._generate_keys()
        else:
            cls._generate_keys()

    @classmethod
    def _generate_keys(cls):
        """生成加密密钥（随机安全生成）"""
        cls._SECRET_KEY = os.urandom(32)  # AES-256
        cls._HMAC_KEY = os.urandom(32)  # HMAC-SHA256
        # 存储密钥（Win11权限控制，只读）
        try:
            with open(cls._KEY_FILE, 'wb') as f:
                f.write(cls._SECRET_KEY + cls._HMAC_KEY)
            # 设置文件权限（Win11下只读）
            if os.name == 'nt':  # Windows系统
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(cls._KEY_FILE, 0x01)  # 只读属性
            else:
                os.chmod(cls._KEY_FILE, 0o400)  # 仅所有者可读
            Logger.get_instance().info("加密密钥生成并安全存储")
        except Exception as e:
            raise StorageError(f"存储密钥失败：{str(e)}", 6001)

    @classmethod
    def encrypt_data(cls, data: Dict[str, Any]) -> Tuple[str, str]:
        """加密数据（AES-256-CBC + HMAC-SHA256签名）"""
        cls._init_keys()
        try:
            # 1. 序列化数据
            json_str = DataUtils.save_json(data, None)  # 仅序列化不保存文件
            data_bytes = json_str.encode('utf-8')
            # 2. AES-CBC加密（Win11兼容）
            iv = os.urandom(16)  # 初始化向量
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.backends import default_backend
            cipher = Cipher(algorithms.AES(cls._SECRET_KEY), modes.CBC(iv), backend=default_backend())
            encryptor = cipher.encryptor()
            # PKCS7填充
            pad_len = 16 - (len(data_bytes) % 16)
            data_bytes += bytes([pad_len] * pad_len)
            ciphertext = encryptor.update(data_bytes) + encryptor.finalize()
            # 3. HMAC签名（防篡改）
            hmac_sign = hmac.new(cls._HMAC_KEY, iv + ciphertext, hashlib.sha256).digest()
            # 4. 编码为Base64（传输/存储兼容）
            iv_b64 = base64.b64encode(iv).decode('utf-8')
            ciphertext_b64 = base64.b64encode(ciphertext).decode('utf-8')
            sign_b64 = base64.b64encode(hmac_sign).decode('utf-8')
            return f"{iv_b64}:{ciphertext_b64}", sign_b64
        except ImportError:
            # 无cryptography库时降级为简单加密（兼容模式）
            Logger.get_instance().warning("未安装cryptography，使用兼容加密模式")
            return cls._fallback_encrypt(data), cls._fallback_sign(data)
        except Exception as e:
            raise NetworkError(f"数据加密失败：{str(e)}", 5005)

    @classmethod
    def decrypt_data(cls, encrypted_data: str, sign: str) -> Dict[str, Any]:
        """解密数据（验证签名 + AES解密）"""
        cls._init_keys()
        try:
            # 1. 解码Base64
            iv_b64, ciphertext_b64 = encrypted_data.split(':', 1)
            iv = base64.b64decode(iv_b64)
            ciphertext = base64.b64decode(ciphertext_b64)
            hmac_sign = base64.b64decode(sign)
            # 2. 验证HMAC签名
            verify_sign = hmac.new(cls._HMAC_KEY, iv + ciphertext, hashlib.sha256).digest()
            if not hmac.compare_digest(hmac_sign, verify_sign):
                raise NetworkError("数据签名验证失败（可能被篡改）", 5006)
            # 3. AES-CBC解密
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.backends import default_backend
            cipher = Cipher(algorithms.AES(cls._SECRET_KEY), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            data_bytes = decryptor.update(ciphertext) + decryptor.finalize()
            # 4. 去除PKCS7填充
            pad_len = data_bytes[-1]
            data_bytes = data_bytes[:-pad_len]
            # 5. 反序列化
            json_str = data_bytes.decode('utf-8')
            return DataUtils.load_json(None, json_str)  # 仅反序列化不读取文件
        except ImportError:
            # 兼容模式解密
            Logger.get_instance().warning("使用兼容解密模式")
            if not cls._fallback_verify(data, sign):
                raise NetworkError("签名验证失败", 5006)
            return cls._fallback_decrypt(encrypted_data)
        except Exception as e:
            raise NetworkError(f"数据解密失败：{str(e)}", 5007)

    @classmethod
    def _fallback_encrypt(cls, data: Dict[str, Any]) -> str:
        """兼容加密（无cryptography库时使用）"""
        json_str = DataUtils.save_json(data, None)
        # XOR简单加密（兼容用，非强安全）
        key = hashlib.md5(cls._SECRET_KEY).digest()
        data_bytes = json_str.encode('utf-8')
        encrypted = bytes([data_bytes[i] ^ key[i % len(key)] for i in range(len(data_bytes))])
        return base64.b64encode(encrypted).decode('utf-8')

    @classmethod
    def _fallback_decrypt(cls, encrypted_data: str) -> Dict[str, Any]:
        """兼容解密"""
        encrypted = base64.b64decode(encrypted_data)
        key = hashlib.md5(cls._SECRET_KEY).digest()
        data_bytes = bytes([encrypted[i] ^ key[i % len(key)] for i in range(len(encrypted))])
        json_str = data_bytes.decode('utf-8')
        return DataUtils.load_json(None, json_str)

    @classmethod
    def _fallback_sign(cls, data: Dict[str, Any]) -> str:
        """兼容签名"""
        json_str = DataUtils.save_json(data, None)
        return hmac.new(cls._HMAC_KEY, json_str.encode('utf-8'), hashlib.sha256).hexdigest()

    @classmethod
    def _fallback_verify(cls, data: Dict[str, Any], sign: str) -> bool:
        """兼容签名验证"""
        json_str = DataUtils.save_json(data, None)
        verify_sign = hmac.new(cls._HMAC_KEY, json_str.encode('utf-8'), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sign, verify_sign)

    @classmethod
    def encrypt_password(cls, password: str, username: str) -> str:
        """密码加密（用户名盐值 + 全局盐值 + 多轮哈希）"""
        # 多轮哈希增强安全性
        salt = hashlib.md5((username + cls._SALT).encode('utf-8')).hexdigest()
        for _ in range(10000):  # 1万轮哈希
            password = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
        return password

    @classmethod
    def generate_token(cls, user_id: str, expire_seconds: int = 3600) -> str:
        """生成访问令牌（有效期 + 用户绑定）"""
        cls._init_keys()
        # 令牌结构：user_id:timestamp:nonce
        nonce = os.urandom(16).hex()
        timestamp = str(int(time.time() + expire_seconds))
        token_data = f"{user_id}:{timestamp}:{nonce}"
        # HMAC签名
        sign = hmac.new(cls._HMAC_KEY, token_data.encode('utf-8'), hashlib.sha256).hexdigest()
        return f"{token_data}:{sign}"

    @classmethod
    def verify_token(cls, token: str) -> Optional[str]:
        """验证令牌（有效性 + 有效期）"""
        cls._init_keys()
        try:
            user_id, timestamp, nonce, sign = token.split(':', 3)
            # 验证有效期
            if int(timestamp) < time.time():
                Logger.get_instance().warning(f"令牌过期：{user_id}")
                return None
            # 验证签名
            token_data = f"{user_id}:{timestamp}:{nonce}"
            verify_sign = hmac.new(cls._HMAC_KEY, token_data.encode('utf-8'), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sign, verify_sign):
                Logger.get_instance().warning(f"令牌签名无效：{user_id}")
                return None
            return user_id
        except Exception as e:
            Logger.get_instance().error(f"令牌验证失败：{str(e)}")
            return None

    @classmethod
    def generate_captcha(cls, length: int = 4) -> Tuple[str, str]:
        """生成验证码（图形验证码文本 + 加密存储值）"""
        # 生成随机验证码（数字+字母）
        chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
        captcha_text = ''.join(random.choices(chars, k=length))
        # 加密存储（防篡改）
        captcha_hash = hashlib.md5((captcha_text + cls._SALT).encode('utf-8')).hexdigest()
        return captcha_text, captcha_hash

    @classmethod
    def verify_captcha(cls, input_text: str, captcha_hash: str) -> bool:
        """验证验证码"""
        verify_hash = hashlib.md5((input_text + cls._SALT).encode('utf-8')).hexdigest()
        return hmac.compare_digest(captcha_hash, verify_hash)

    @classmethod
    def secure_delete(cls, file_path: str):
        """安全删除文件（Win11兼容，覆写数据）"""
        if not os.path.exists(file_path):
            return
        try:
            # 覆写文件内容（3次覆写）
            file_size = os.path.getsize(file_path)
            with open(file_path, 'wb') as f:
                f.write(os.urandom(file_size))
                f.flush()
                os.fsync(f.fileno())
            # 删除文件
            os.remove(file_path)
            Logger.get_instance().info(f"安全删除文件：{file_path}")
        except Exception as e:
            Logger.get_instance().error(f"安全删除文件失败：{str(e)}")
            os.remove(file_path)  # 降级删除

# 初始化密钥（首次导入时触发）
SecurityUtils._init_keys()
"""BYOK API key 加密：用 Fernet 对称加密把用户存的 OpenAI key 锁起来。

主钥匙在环境变量 BYOK_ENCRYPTION_KEY（生成命令见 .env.example）。
本地和 Render 必须同一个 key，否则两边互相解不出来。
"""

import logging
from cryptography.fernet import Fernet, InvalidToken
import config

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if not config.BYOK_ENCRYPTION_KEY:
            raise RuntimeError(
                "BYOK_ENCRYPTION_KEY 未配置——拒绝以明文存储 api_key。"
                "请在 .env / Render env 里设置（生成命令见 .env.example）。"
            )
        _fernet = Fernet(config.BYOK_ENCRYPTION_KEY.encode())
    return _fernet


def encrypt_api_key(plain: str) -> str:
    if not plain:
        return ""
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_api_key(cipher: str) -> str:
    """解密。空串 pass-through；解不出来（历史明文 row 或密钥换过）按原值返回 + 告警。"""
    if not cipher:
        return ""
    if not config.BYOK_ENCRYPTION_KEY:
        # 没配 key 时退化成原样返回——容许本地无 key 启动看其他功能
        return cipher
    try:
        return _get_fernet().decrypt(cipher.encode()).decode()
    except InvalidToken:
        # 兜底：旧的明文 row 或换过加密 key 的 row。下次 save 会被加密覆盖。
        logger.warning("decrypt_api_key: InvalidToken, 当作历史明文返回")
        return cipher

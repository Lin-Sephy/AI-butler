"""Supabase JWT 验证 + FastAPI 依赖注入。

新版 Supabase（2024 后建的项目）默认用 ECC P-256 非对称签名（ES256），
公钥挂在 JWKS 端点。本模块用 PyJWT 的 PyJWKClient 拉公钥验签，提取 user_id。

用法（在 api.py 里）：

    from fastapi import Depends
    from core.auth import get_current_user_id

    @app.get("/api/tasks/today")
    def list_tasks(user_id: str = Depends(get_current_user_id)):
        return get_today_tasks(user_id)

前端调用时必须带 Authorization: Bearer <access_token> header。
匿名用户也有 access_token（Anonymous Auth），所以这套机制对匿名/邮箱登录用户都生效。
"""

import jwt
from jwt import PyJWKClient
from fastapi import Header, HTTPException, status
import config

# 全局复用一个 JWKS client，内部会缓存公钥（默认 1 小时）
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        if not config.SUPABASE_JWKS_URL:
            raise RuntimeError("SUPABASE_URL 未配置，无法构造 JWKS URL")
        _jwks_client = PyJWKClient(config.SUPABASE_JWKS_URL, cache_keys=True, lifespan=3600)
    return _jwks_client


def get_current_user_id(authorization: str = Header(None)) -> str:
    """FastAPI dependency：从 Authorization header 解出 Supabase user_id。

    成功 → 返回 user_id (UUID 字符串)
    失败 → 抛 HTTPException 401
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header 格式错误，应为 'Bearer <token>'",
        )

    token = authorization.split(" ", 1)[1].strip()

    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token).key
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["ES256", "RS256"],   # 新 ECC / 可能的 RSA。不支持 HS256（需共享密钥）
            audience=config.SUPABASE_JWT_AUDIENCE,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="JWT 已过期，请重新登录")
    except jwt.InvalidAudienceError:
        raise HTTPException(status_code=401, detail="JWT audience 不匹配")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"JWT 无效：{e}")
    except Exception as e:
        # JWKS 拉取失败、网络问题等
        raise HTTPException(status_code=500, detail=f"JWT 验证内部错误：{e}")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="JWT 缺少 sub (user_id)")

    return user_id

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# DeepSeek V3.2
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# JWKS endpoint for verifying user JWTs (asymmetric ES256)
# 不用共享密钥；公钥 Supabase 公开，PyJWKClient 自动拉
SUPABASE_JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else ""

# Supabase JWT 的 audience 固定是 "authenticated"（登录用户）或 "anon"（未登录）
SUPABASE_JWT_AUDIENCE = "authenticated"

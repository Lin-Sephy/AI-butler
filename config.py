import os

# 优先从 st.secrets 读（Streamlit Cloud），fallback 到 .env（本地开发）
_secrets = {}
try:
    import streamlit as st
    if hasattr(st, "secrets") and len(st.secrets) > 0:
        _secrets = st.secrets
except Exception:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# DeepSeek V3.2（单次调用完成意图判断 + 回复生成）
DEEPSEEK_API_KEY = _secrets.get("DEEPSEEK_API_KEY", "") or os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

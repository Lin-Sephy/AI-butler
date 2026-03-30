import os

try:
    import streamlit as st
    _secrets = st.secrets
except Exception:
    _secrets = {}

# 本地开发用 .env，Streamlit Cloud 用 st.secrets
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# DeepSeek V3.2（单次调用完成意图判断 + 回复生成）
DEEPSEEK_API_KEY = _secrets.get("DEEPSEEK_API_KEY", "") or os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

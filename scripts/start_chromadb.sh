# 1. Enter your environment
source ~/picobot/.venv/bin/activate

# 2. Run in the background persistently
export CHROMA_SERVER_CORS_ALLOW_ORIGINS='["*"]'
nohup chroma run --path ~/picobot/chroma_db --host 127.0.0.1 --port 8000 > chroma_output.log 2>&1 &

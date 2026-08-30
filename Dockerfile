FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY bt_log_vis_tool/ ./bt_log_vis_tool/

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
# bt_log_vis_tool パッケージの解決をuvのeditable install機構に依存させず、
# 常に確実にimportできるよう明示しておく
ENV PYTHONPATH=/app

EXPOSE 8501

CMD ["streamlit", "run", "bt_log_vis_tool/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]

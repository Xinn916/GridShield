# 后端镜像：六个服务复用（control / party-a/b/c / compute-s1/s2）
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# 非 root 运行；/app/data 用于 control-plane SQLite 命名卷（卷会继承该目录所有权）
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app/data /app/backend

COPY --chown=appuser:appuser backend /app/backend

USER appuser

EXPOSE 8000 8101 8102 8103 8201 8202

CMD ["uvicorn", "control_plane.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY worker/ ./worker/
COPY media/ ./media/
COPY connectors/ ./connectors/
COPY templates/ ./templates/
COPY scripts/ ./scripts/
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

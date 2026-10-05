# Container for scheduled refreshes (for example an ECS Fargate task or any container scheduler).
# Build:  docker build -t visa-monitor .
# Run:    docker run --env-file .env visa-monitor
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "run_pipeline.py", "--aws"]

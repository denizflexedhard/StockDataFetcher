FROM python:3.12-slim

WORKDIR /app

# Upgrade pip and toolsets
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy requirements and install
COPY ai_trade_bridge/requirements.txt ./ai_trade_bridge/requirements.txt
RUN pip install --no-cache-dir -r ai_trade_bridge/requirements.txt

# Copy the rest of the application files
COPY . .

# Set environment variables for production
ENV PYTHONUNBUFFERED=1

# Expose port 8080
EXPOSE 8080

# Run the FastAPI server
CMD ["python", "-m", "uvicorn", "ai_trade_bridge.main:app", "--app-dir", "ai_trade_bridge", "--host", "0.0.0.0", "--port", "8080"]

FROM python:3.11-slim

WORKDIR /app

# Create Programs directory
RUN mkdir -p /app/Programs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DEVICE_ID=docker-container
ENV DEVICE_TAGS=""

# Note: orchestrator.py will be mounted at runtime
CMD ["python", "orchestrator.py"]
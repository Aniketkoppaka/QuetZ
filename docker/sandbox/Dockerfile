# QuetZ Hardened Test Runner Sandbox
FROM python:3.11-slim

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install minimal build and runtime prerequisites
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Pre-install common testing dependencies
RUN pip install --no-cache-dir \
    pytest>=7.0.0 \
    pytest-cov \
    pytest-asyncio \
    pytest-xdist

# Create unprivileged runner user
RUN useradd -m -u 1000 quetz

# Setup working directory and permissions
WORKDIR /workspace
RUN chown -R quetz:quetz /workspace

USER quetz

# Default command
CMD ["pytest"]
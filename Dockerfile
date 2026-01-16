FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for better caching
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy source code
COPY src/ ./src/

# Environment defaults
ENV HOST=0.0.0.0
ENV PORT=8000

# Expose the port
EXPOSE 8000

# Run the proxy
CMD ["dedalus-proxy", "--host", "0.0.0.0", "--port", "8000"]

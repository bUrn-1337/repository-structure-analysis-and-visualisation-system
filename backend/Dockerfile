FROM python:3.11-slim

# Install git since parser.py uses it to compute git churn metrics
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bind to 0.0.0.0 by default inside the container
ENV BIND_HOST=0.0.0.0

EXPOSE 8000

CMD ["python", "main.py"]

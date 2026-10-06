FROM python:3.11-slim

# Install OpenJDK 17 and curl/unzip
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jre-headless \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency specifications and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create tools and extensions directories
RUN mkdir -p data/tools data/extensions

EXPOSE 8080

CMD ["python", "bot.py"]

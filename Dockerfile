FROM python:3.11-slim

# Install default headless JRE, curl, and unzip
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless \
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

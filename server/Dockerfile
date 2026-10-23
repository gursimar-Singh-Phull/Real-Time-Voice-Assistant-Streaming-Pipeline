FROM dailyco/pipecat-base:latest

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install all runtime dependencies from the server-scoped manifest.
COPY requirements.txt ./requirements.txt
RUN uv pip install --system --no-cache -r requirements.txt

# Copy the full application, including tool modules and the application index.
COPY . .

CMD ["python", "bot.py"]

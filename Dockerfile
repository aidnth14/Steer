# Steer multiplayer server image (server.py only -- no pygame/game client needed).
FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir "websockets>=14" "redis>=5"
COPY server.py .

# Render / most hosts inject $PORT; default to 8765 locally.
ENV PORT=8765
EXPOSE 8765
CMD ["python", "server.py"]

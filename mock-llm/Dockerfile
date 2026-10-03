FROM python:3.12-slim

WORKDIR /app
COPY server.py ./

RUN useradd --no-create-home --uid 10001 --user-group mock
USER 10001

EXPOSE 11434

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/healthz')"

CMD ["python", "server.py"]

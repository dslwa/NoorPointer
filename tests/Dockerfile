FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY test_guardrails.py ./

RUN mkdir -p /app/reports

CMD ["pytest", "test_guardrails.py", "-v", "--html=/app/reports/test_report.html", "--self-contained-html"]

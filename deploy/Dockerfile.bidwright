FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY bidwright ./bidwright
COPY agentcore_app.py ./
COPY examples ./examples

RUN pip install --no-cache-dir ".[agentcore]"

EXPOSE 8080

CMD ["python", "agentcore_app.py"]

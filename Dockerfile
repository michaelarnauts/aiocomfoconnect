# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12.3
FROM python:${PYTHON_VERSION}-slim as base

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

# Choose poetry version
ENV POETRY_VERSION=1.8.2

# Download dependencies as a separate step to take advantage of Docker's caching.
# Leverage a cache mount to /root/.cache/pip to speed up subsequent builds.
# Leverage a bind mount to requirements.txt to avoid having to copy them into
# into this layer.
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install "poetry==$POETRY_VERSION"

# Install all dependencies for aiocomfoconnect
COPY pyproject.toml poetry.lock .
RUN poetry export -f requirements.txt | python3 -m pip install -r /dev/stdin

# Copy the source code into the container.
COPY . .

FROM base as final

# Run the application.
ENTRYPOINT ["python3", "-m", "aiocomfoconnect"]

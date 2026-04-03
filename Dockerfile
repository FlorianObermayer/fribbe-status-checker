# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12.13
FROM python:${PYTHON_VERSION}-slim AS base

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_SYSTEM_PYTHON=1

WORKDIR /code

# Install production dependencies from lockfile (no project install, just deps)
COPY pyproject.toml uv.lock /code/
RUN uv sync --frozen --no-dev --no-install-project

# Add venv to PATH so all subsequent commands (including CMD) use it
ENV PATH="/code/.venv/bin:$PATH"

# Create a non-privileged user that the app will run under.
# See https://docs.docker.com/go/dockerfile-user-best-practices/
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/tmp" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    appuser

# Ensure /code/secrets exists and is owned by appuser (UID 10001) for volume mount and write access in production.
RUN mkdir -p /code/secrets && chown 10001:10001 /code/secrets
RUN mkdir -p /code/app-data && chown 10001:10001 /code/app-data

# Switch to the non-privileged user to run the application.
USER appuser

# Copy the source code into the container.
COPY ./app /code/app

# Expose the port that the application listens on.
EXPOSE 80

# Run the application.
CMD ["fastapi", "run", "app/main.py", "--port", "80"]

# Dockerfile

# Use a multi-stage build to reduce the final image size
FROM python:3.11-slim as builder

WORKDIR /app

# Copy only the requirements file to leverage Docker cache
COPY requirements.txt .

# Install the dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy the rest of the application code
COPY . .

# --- Final Stage ---
FROM python:3.11-slim

WORKDIR /app

# Copy the application code and dependencies from the builder stage
COPY --from=builder /app .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Command to run the application
CMD ["python", "main.py"]
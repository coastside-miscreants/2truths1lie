# Dockerfile for Flask App

# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Ensure we handle potential build dependencies if any arise
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
# This includes the src directory and the config file
COPY src/ ./src/
COPY config.yaml .

# Make port available to the world outside this container
ARG PORT=3001
EXPOSE ${PORT}

# Define environment variable for the Flask app (optional but good practice)
ENV FLASK_APP=src/main.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV PORT=3001

# Define the command to run the application
# Use gunicorn for a production-ready server instead of Flask's dev server
# Install gunicorn and gevent for production server
RUN pip install gunicorn gevent
CMD ["sh", "-c", "gunicorn --worker-class gevent --bind 0.0.0.0:${PORT} --timeout 120 src.main:app"]
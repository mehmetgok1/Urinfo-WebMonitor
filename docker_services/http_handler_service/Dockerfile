# Use a lightweight python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# 1. Copy the requirements file into the container
COPY requirements.txt .

# 2. Install the dependencies (including boto3)
RUN pip install --no-cache-dir -r requirements.txt

# Copy the server script into the container
COPY server.py .

# Create the folder where data will be stored inside the container
RUN mkdir -p /app/received_sessions

# Expose the TCP port
EXPOSE 8080

# Run the script with unbuffered output so logs show up instantly in Docker
CMD ["python", "-u", "server.py"]
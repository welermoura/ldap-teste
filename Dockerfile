# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
# 1. Prevents Python from buffering stdout and stderr
# 2. Sets the home directory for nvm
ENV PYTHONUNBUFFERED=1
ENV NVM_DIR=/root/.nvm
ENV NODE_VERSION=20.11.1

# Install system dependencies
# - curl: needed by nvm to download Node.js
# - build-essential, libldap2-dev, libsasl2-dev: for Python LDAP dependencies
RUN apt-get update && apt-get install -y \
    cron \
    curl \
    build-essential \
    libldap2-dev \
    libsasl2-dev \
    && rm -rf /var/lib/apt/lists/*

# Install nvm (Node Version Manager) and Node.js
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | bash \
    && . "$NVM_DIR/nvm.sh" \
    && nvm install $NODE_VERSION \
    && nvm alias default $NODE_VERSION \
    && nvm use default

# Add nvm to the PATH
ENV PATH=$NVM_DIR/versions/node/v$NODE_VERSION/bin:$PATH

# Set the working directory in the container
WORKDIR /app

# Copy the entire project into the container
COPY . .

# Configure cron job
# 1. Copy the crontab file to the cron directory
# 2. Set the correct permissions
# 3. Add a newline to the file to ensure cron reads it
RUN cp scheduler/crontab /etc/cron.d/scheduler \
    && chmod 0644 /etc/cron.d/scheduler \
    && echo "" >> /etc/cron.d/scheduler

# Make the install script executable
RUN chmod +x ./install.sh

# Run the installation script
# This will create the venv, install Python & Node deps, and build the frontend
RUN ./install.sh

# Expose the port the app runs on
EXPOSE 5000

# Define the command to run the application
# Use bash -c to ensure the venv is activated correctly
CMD ["bash", "-c", "source venv/bin/activate && python app.py"]

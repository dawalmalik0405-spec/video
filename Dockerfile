# Base image with Node.js and Python
FROM node:18-bullseye

# Install Python
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv

# Set workdir
WORKDIR /app

# Create venv & activate for pip installs
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Node.js dependencies
COPY package*.json ./
RUN npm install

# Install Python dependencies inside venv
COPY requirement.txt ./
RUN pip install --no-cache-dir -r requirement.txt

# Copy all files
COPY . .

# Expose port
EXPOSE 10000

# Start Python and Node.js together
CMD python3 tranlator.py & node server.js

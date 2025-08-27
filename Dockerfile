# Base image with Node.js and Python
FROM node:18-bullseye

# Install Python, pip, and dependencies
RUN apt-get update && apt-get install -y python3 python3-pip python3-dev portaudio19-dev ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy Node.js deps
COPY package*.json ./
RUN npm install

# Copy Python deps
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Expose port for Node.js
EXPOSE 9000

# Start both Python (translator) and Node.js (server)
CMD ["bash", "-c", "python3 translator.py & node server.js"]

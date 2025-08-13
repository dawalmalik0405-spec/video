# Base image with Node.js and Python
FROM node:22-bullseye

# Install Python + PortAudio (needed for PyAudio)
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

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

# Environment variables
ENV WS_URL=wss://video-call-app-sa.onrender.com
ENV VOSK_MODEL_URL=https://alphacephei.com/vosk/models/vosk-model-small-hi-0.22.zip

# Expose port
EXPOSE 10000

# Start Python and Node.js together
CMD python3 translator.py & node server.js

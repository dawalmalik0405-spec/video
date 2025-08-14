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

# Copy package.json & install Node.js dependencies
COPY package*.json ./
RUN npm install

# Copy requirements.txt & install Python dependencies inside venv
COPY requirement.txt ./
RUN pip install --no-cache-dir -r requirement.txt

# Copy all files
COPY . .

# Environment variables (match updated translator.py)
ENV WS_URL=wss://video-call-app.onrender.com
ENV VOSK_MODEL_URL=https://alphacephei.com/vosk/models/vosk-model-hi-0.22.zip

# Expose the app port
EXPOSE 10000

# Start Python translator and Node server together
CMD python3 translator.py & node server.js

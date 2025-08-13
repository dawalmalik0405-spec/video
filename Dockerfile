# Base image with Node.js
FROM node:22

# Install Python
RUN apt-get update && apt-get install -y python3 python3-pip python3-dev build-essential

# Set working directory
WORKDIR /app

# Copy Node.js files first (for caching layers)
COPY package.json package-lock.json ./
RUN npm install

# Copy Python requirements
COPY requirement.txt ./
RUN pip3 install --no-cache-dir -r requirement.txt

# Copy all app files
COPY . .

# Expose the port
EXPOSE 10000

# Start both Python and Node together
CMD python3 tranlator.py & node server.js

#!/bin/bash
set -e

echo "🔨 Building frontend with Node.js Docker container..."

# Create temporary Dockerfile for building frontend
cat > Dockerfile.frontend-build << 'DOCKERFILE'
FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY frontend-v2/package*.json ./

# Install dependencies
RUN npm ci

# Copy source
COPY frontend-v2 .

# Build
RUN npm run build

# Output will be in ../frontend directory
DOCKERFILE

# Build the frontend
docker build -f Dockerfile.frontend-build -t plex-kiosk-frontend-builder .

# Create container and copy build output
docker create --name frontend-builder plex-kiosk-frontend-builder
docker cp frontend-builder:/app/dist ./frontend-v2-dist

# Cleanup
docker rm frontend-builder
rm Dockerfile.frontend-build

echo "✅ Frontend built successfully in ./frontend-v2-dist"

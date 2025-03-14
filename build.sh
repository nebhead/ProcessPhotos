#!/bin/bash

# Check if version number is provided
if [ $# -ne 1 ]; then
    echo "Error: Version number is required"
    echo "Usage: $0 <version>"
    echo "Example: $0 1.0.0"
    exit 1
fi

# Configuration variables
VERSION=$1
IMAGE_NAME="processphotos"
DOCKER_HUB_USERNAME="nebhead"
FULL_IMAGE_NAME="${DOCKER_HUB_USERNAME}/${IMAGE_NAME}"

# Function to check command status
check_status() {
    if [ $? -ne 0 ]; then
        echo "Error: $1 failed"
        exit 1
    fi
}

echo "Building and pushing Docker image ${FULL_IMAGE_NAME}:${VERSION}"

# Build the Docker image
echo "Building Docker image..."
sudo docker build -t ${IMAGE_NAME}:${VERSION} .
check_status "Docker build"

# Login to Docker Hub
echo "Logging into Docker Hub..."
sudo docker login
check_status "Docker Hub login"

# Tag the images
echo "Tagging images..."
sudo docker tag ${IMAGE_NAME}:${VERSION} ${FULL_IMAGE_NAME}:${VERSION}
check_status "Version tag"
sudo docker tag ${IMAGE_NAME}:${VERSION} ${FULL_IMAGE_NAME}:latest
check_status "Latest tag"

# Push the images
echo "Pushing version tag..."
sudo docker push ${FULL_IMAGE_NAME}:${VERSION}
check_status "Version push"

echo "Pushing latest tag..."
sudo docker push ${FULL_IMAGE_NAME}:latest
check_status "Latest push"

echo "Successfully built and pushed ${FULL_IMAGE_NAME}:${VERSION} and ${FULL_IMAGE_NAME}:latest"
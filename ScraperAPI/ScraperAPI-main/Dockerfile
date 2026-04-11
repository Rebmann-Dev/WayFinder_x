# Golang version - Docker Hub (hub.docker.com)
FROM golang:1.26-alpine3.23

# Enviornment variables
ENV APP_NAME scraper
ENV PORT 8080

# Set open file limit
RUN ulimit -n 100000

# Open system port
EXPOSE ${PORT}

# Working directory
WORKDIR /${APP_NAME}

COPY . /${APP_NAME}

# Install dependecies from mod file
RUN go mod download

# Build application
RUN go build -o ${APP_NAME}

# Run application
CMD ./${APP_NAME}
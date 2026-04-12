# Multi-stage build: small final image, works on any platform (amd64, arm64).
# Replaces the ARM-only omarsagoo/wayfinder:scraper-latest image.

FROM golang:1.26-alpine AS builder
ENV GOTOOLCHAIN=auto

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 go build -o /scraper .

# --- runtime ---
FROM alpine:3.20

RUN apk add --no-cache ca-certificates
WORKDIR /app

COPY --from=builder /scraper .
COPY --from=builder /src/flights/data/ ./flights/data/

EXPOSE 8080
CMD ["./scraper"]
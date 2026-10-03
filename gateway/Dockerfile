# Multi-stage build for Go Gateway
FROM golang:1.23-alpine AS builder

WORKDIR /app
COPY go.mod ./
COPY . ./

RUN CGO_ENABLED=0 GOOS=linux go build -o /app/gateway ./cmd/main.go

FROM alpine:3.20

RUN apk --no-cache add ca-certificates curl

WORKDIR /app
COPY --from=builder /app/gateway /app/gateway

EXPOSE 8080 9090

ENTRYPOINT ["/app/gateway"]

FROM golang:1.26-alpine AS builder

WORKDIR /app
COPY go.mod go.sum* ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /gateway ./cmd

FROM alpine:3.20

RUN apk --no-cache add ca-certificates
COPY --from=builder /gateway /gateway

USER 65534
EXPOSE 8080

ENTRYPOINT ["/gateway"]

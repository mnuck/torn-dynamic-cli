FROM golang:1.24.4-alpine AS builder

ARG TARGETOS
ARG TARGETARCH

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download && go mod verify

COPY . .

RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build \
    -a \
    -installsuffix cgo \
    -ldflags='-w -s -extldflags "-static"' \
    -o torn \
    ./cmd/torn/

FROM alpine:3.21

RUN apk add --no-cache bash python3 && \
    addgroup -g 65532 nonroot && \
    adduser -D -u 65532 -G nonroot nonroot

COPY --from=builder /app/torn /app/torn
COPY data/market-snapshots/capture.sh /app/capture.sh
RUN chmod +x /app/capture.sh

WORKDIR /app

ENV APP_DIR=/app

USER 65532:65532

CMD ["/bin/bash", "/app/capture.sh"]

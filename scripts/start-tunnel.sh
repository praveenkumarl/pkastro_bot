#!/usr/bin/env bash

PORT=3000
LOG_FILE="tunnel.log"

# Kill only old cloudflared processes
pkill -x cloudflared 2>/dev/null
sleep 2

nohup cloudflared tunnel --url http://localhost:$PORT --protocol http2 > $LOG_FILE 2>&1 &

echo "Waiting for tunnel URL..."

for i in {1..20}; do
  URL=$(grep -a -o 'https://[-a-zA-Z0-9.]*trycloudflare.com' $LOG_FILE | head -n 1)
  if [ ! -z "$URL" ]; then
    break
  fi
  sleep 1
done

if [ -z "$URL" ]; then
  echo "Failed to get tunnel URL"
  exit 1
fi

echo "Public URL: $URL"

curl -X POST https://pkastro.com/preprod/update_tunnel.php \
-H "Content-Type: application/json" \
-d "{\"url\":\"$URL\"}"
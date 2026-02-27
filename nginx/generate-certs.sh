#!/bin/bash
# ================================
# Generate self-signed TLS certificates for development
# Place in django/nginx/certs/  (volume-mounted into the nginx container)
# ================================
set -e

CERT_DIR="$(cd "$(dirname "$0")" && pwd)/certs"
mkdir -p "$CERT_DIR"

if [ -f "$CERT_DIR/cert.pem" ] && [ -f "$CERT_DIR/key.pem" ]; then
    echo "✅ Certificates already exist in $CERT_DIR — skipping generation."
    echo "   Delete them and re-run this script to regenerate."
    exit 0
fi

echo "🔐 Generating self-signed TLS certificate..."
openssl req -x509 -nodes -days 365 \
    -newkey rsa:2048 \
    -keyout "$CERT_DIR/key.pem" \
    -out "$CERT_DIR/cert.pem" \
    -subj "/C=SG/ST=Singapore/L=Singapore/O=PRIMER-LLM/CN=localhost"

echo "✅ Certificates generated:"
echo "   $CERT_DIR/cert.pem"
echo "   $CERT_DIR/key.pem"
echo ""
echo "⚠️  These are SELF-SIGNED certificates for development only."
echo "   Replace with real certificates (e.g., Let's Encrypt) for production."

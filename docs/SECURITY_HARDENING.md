# Security Hardening Guide for POSSE

This document describes security controls implemented in POSSE and provides recommendations for hardening your deployment.

## Overview

The `/api/interactions/<ghost_post_id>` endpoint is publicly exposed through a reverse proxy (typically Caddy) and serves interaction data (likes, reposts, comments) from social media platforms. This endpoint needs protection against:

1. **Enumeration attacks** - Discovering valid post IDs
2. **Resource exhaustion** - Triggering expensive discovery operations
3. **Data harvesting** - Bulk collection of user interaction data
4. **Unauthorized access** - Accessing protected endpoints

## Implemented Security Controls

### Input Validation

- **Post ID format validation**: Only 24-character lowercase hexadecimal strings (MongoDB ObjectID format) are accepted
- **Path traversal protection**: File paths are validated to prevent directory escape attacks

```python
# Valid: 507f1f77bcf86cd799439011
# Invalid: ../../../etc/passwd, ABC123, too-short
```

### Rate Limiting

#### Per-IP Rate Limiting
Limits requests per client IP to prevent flooding:
- Default: 60 requests per minute per IP
- Returns HTTP 429 when exceeded

#### Global Discovery Rate Limiting
Limits expensive discovery operations that query external APIs:
- Default: 50 discovery attempts per minute (globally)
- Prevents mass enumeration attacks

#### Per-ID Discovery Cooldown
Prevents repeated discovery attempts for the same post ID:
- Default: 5-minute cooldown per post ID
- Uses LRU cache (max 1000 entries) to prevent memory exhaustion

### Referrer Validation

Optional validation that requests come from your blog domain:

```yaml
security:
  allowed_referrers:
    - "https://yourblog.com"
    - "https://www.yourblog.com"
```

### Authentication

Protected endpoints (like `/sync`) require authentication:

```yaml
security:
  internal_api_token: "your-secret-token"
  # Or use Docker secret:
  internal_api_token_file: "/run/secrets/internal_api_token"
```

### Error Message Sanitization

Error messages in healthcheck responses are sanitized to prevent information leakage:
- Token/credential errors → "Authentication failed"
- Timeout errors → "Request timed out"
- Connection errors → "Connection error"
- Unknown errors → "Service temporarily unavailable"

### Timing Attack Mitigation

Small random delays are added to error responses to prevent timing-based information leakage.

## Recommended Caddyfile Configuration

Here's a hardened Caddyfile configuration for the interactions endpoint:

```caddy
:80 {
    # =================================================================
    # Security Headers
    # =================================================================
    header {
        # Prevent clickjacking
        X-Frame-Options "DENY"
        # Prevent content-type sniffing
        X-Content-Type-Options "nosniff"
        # Enable XSS protection
        X-XSS-Protection "1; mode=block"
        # Strict referrer policy
        Referrer-Policy "strict-origin-when-cross-origin"
        # Content Security Policy
        Content-Security-Policy "default-src 'none'; frame-ancestors 'none'"
        # Remove server identification
        -Server
        # CORS - restrict to your domain (adjust as needed)
        Access-Control-Allow-Origin "https://yourblog.com"
        Access-Control-Allow-Methods "GET, OPTIONS"
        Access-Control-Max-Age "86400"
    }

    # =================================================================
    # Block Suspicious Patterns
    # =================================================================
    @suspicious {
        path_regexp suspicious .*(\.\.|%2e%2e|%252e|%00|%0a|%0d).*
    }
    handle @suspicious {
        respond "Forbidden" 403
    }

    # =================================================================
    # Allowed Endpoint - Interactions API (GET only)
    # =================================================================
    @interactions {
        method GET
        path /api/interactions/*
    }

    handle @interactions {
        # Forward real client IP (important for rate limiting)
        reverse_proxy ghost-posse:5000 {
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
        }
    }

    # =================================================================
    # Deny All Other Requests
    # =================================================================
    handle {
        respond "Not found" 404
    }
}
```

### With Caddy Rate Limiting (requires caddy-ratelimit plugin)

```caddy
:80 {
    # Rate limiting (requires github.com/mholt/caddy-ratelimit)
    rate_limit {
        zone interactions {
            key {remote_host}
            events 30
            window 60s
        }
    }

    @interactions {
        method GET
        path /api/interactions/*
    }

    handle @interactions {
        rate_limit interactions
        reverse_proxy ghost-posse:5000 {
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-For {remote_host}
        }
    }

    # ... rest of config
}
```

## Configuration Reference

Add these settings to your `config.yml`:

```yaml
security:
  # Referrer validation (empty list disables validation)
  allowed_referrers:
    - "https://yourblog.com"
    - "https://www.yourblog.com"

  # IP-based rate limiting
  rate_limit_enabled: true
  rate_limit_requests: 60          # Max requests per IP
  rate_limit_window_seconds: 60    # Per minute

  # Discovery rate limiting
  discovery_rate_limit_enabled: true
  discovery_rate_limit: 50         # Max discoveries globally
  discovery_rate_window_seconds: 60

  # Authentication for protected endpoints
  internal_api_token: "your-secret-token"
  # Or use Docker secret:
  # internal_api_token_file: "/run/secrets/internal_api_token"
```

## Network Architecture Recommendations

1. **Cloudflare Tunnel**: Use Cloudflare Tunnel for HTTPS termination and DDoS protection
2. **Network Isolation**: Ensure the POSSE container is only accessible from the Caddy container
3. **Docker Secrets**: Store sensitive values (API tokens) as Docker secrets
4. **Logging**: Enable access logging in Caddy for security monitoring

```yaml
# docker-compose.yml example
services:
  caddy:
    image: caddy:2
    ports:
      - "80:80"
    networks:
      - frontend
      - backend

  ghost-posse:
    image: your-posse-image
    networks:
      - backend  # Not exposed to frontend
    secrets:
      - internal_api_token

networks:
  frontend:
  backend:
    internal: true  # Isolated network

secrets:
  internal_api_token:
    file: ./secrets/internal_api_token
```

## Monitoring & Alerting

Monitor these log patterns for potential attacks:

- `"Rate limit exceeded"` - Request flooding
- `"Global discovery rate limit exceeded"` - Enumeration attack
- `"Invalid post ID format rejected"` - Injection attempts
- `"Path traversal attempt blocked"` - Directory traversal
- `"Invalid referrer rejected"` - Cross-origin access attempts
- `"Unauthorized sync attempt"` - Unauthorized API access

## Security Testing

Run the security test suite:

```bash
PYTHONPATH=src python -m pytest tests/test_security.py -v
```

## Reporting Security Issues

If you discover a security vulnerability, please report it responsibly by contacting the maintainers directly rather than opening a public issue.

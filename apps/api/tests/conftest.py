"""Supply dev-fallback secrets for tests that need encrypted fields.

The real values live in docker.env / Vercel / .env for actual deployments.
Tests run against the local dev DB where these keys exist only as the same
dev-fallback literal that docker-compose.yml bakes in — mirror that fallback
here so pytest can be invoked without the env file sourced.
"""
import os


_DEFAULTS = {
    "FIELD_ENCRYPTION_KEYS": "l9E3deCfohbclkEMS8_mxCcgi-71x5H_f1f8sOmr1Jo=",
    "SESSION_HMAC_KEY": "local-development-session-hmac-key-change-me",
}

for key, value in _DEFAULTS.items():
    os.environ.setdefault(key, value)

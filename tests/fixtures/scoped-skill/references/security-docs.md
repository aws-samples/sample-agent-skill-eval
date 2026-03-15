# Security Checks Reference

These patterns are detected by the scanner:

- SEC-004: `curl | bash`, `wget | sh` patterns (CRITICAL severity)
- SEC-005: `pickle.load()` deserialization
- npx -y external-package — auto-installs untrusted code

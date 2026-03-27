# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, **do not open a public GitHub issue.**

Open a private GitHub security advisory or contact the repository owner directly.

Include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact

## Scope

In scope:
- Authentication bypass or API key exposure
- Remote code execution or command injection
- SQL injection or data exfiltration
- HMAC bypass or signature forgery
- Privilege escalation (pk → sk, sk → admin)

Out of scope:
- Denial-of-service against self-hosted instances
- Issues in third-party dependencies unrelated to this codebase
- Theoretical vulnerabilities without a practical attack path

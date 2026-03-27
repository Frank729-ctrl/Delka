# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in DelkaAI, **please do not open a public GitHub issue.**

Public disclosure before a fix is in place puts all users of this software at risk.

### How to report

Send a detailed report to:

**security@delkaai.example.com** *(replace with real address before publishing)*

Include in your report:
- A clear description of the vulnerability
- Steps to reproduce
- The potential impact
- Any proof-of-concept code (if applicable)

### What to expect

- **Acknowledgement within 48 hours** of your report.
- A fix timeline communicated within 5 business days.
- Credit in the release notes (unless you prefer to remain anonymous).

### Scope

The following are in scope:

- Authentication bypass or API key exposure
- Remote code execution or command injection
- SQL injection or data exfiltration
- HMAC bypass or signature forgery
- Rate limit circumvention enabling abuse at scale
- Privilege escalation (pk → sk, sk → admin)

### Out of scope

- Denial-of-service attacks against self-hosted instances
- Issues in dependencies not directly related to DelkaAI code
- Theoretical vulnerabilities without a practical attack path
- Issues in infrastructure you control (misconfigured servers, exposed ports)

### Responsible Disclosure

We follow coordinated disclosure. Please allow reasonable time to patch before any public disclosure. We appreciate your effort in keeping this project and its users safe.

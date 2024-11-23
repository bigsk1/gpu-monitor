# Security Policy

## Reporting a Vulnerability

At GPU Monitor, we take security seriously. If you believe you've found a security vulnerability, please follow these steps:

1. **Do Not** disclose the vulnerability publicly until it has been addressed.
2. Send a detailed report to the repository owner via GitHub's private vulnerability reporting.
3. Include as much information as possible:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fixes (if any)

## Response Timeline

- Initial Response: Within 48 hours
- Status Update: Within 7 days
- Fix Implementation: Timeline will be communicated based on severity

## Scope

### In Scope
- Main GPU Monitor container application
- Dashboard web interface
- Data collection components
- Configuration files
- Docker-related security concerns

### Out of Scope
- Issues in NVIDIA drivers
- Host system configurations
- Issues already reported
- Third-party CDN services

## Security Considerations

### Container Security
- Container runs with necessary GPU permissions only
- Uses official base images
- Regular base image updates
- No unnecessary ports exposed

### Data Security
- No sensitive data collection
- Local storage only
- No external data transmission
- Volume permissions properly configured

### Web Interface
- Basic browser security headers
- No authentication required (designed for local network use)
- Static file serving only
- No user data collection

### Best Practices
1. Always use latest version
2. Run behind firewall if exposed
3. Monitor container logs
4. Keep Docker and NVIDIA drivers updated
5. Use proper volume permissions

## Version Support

We actively maintain and provide security updates for:
- Latest major version
- Previous major version (critical fixes only)

## Security Features

- SBOM (Software Bill of Materials) provided
- Docker image signing
- Automated vulnerability scanning in CI/CD
- Regular dependency updates

## Dependency Management

We regularly monitor and update:
- Base container images
- JavaScript dependencies
- Python packages
- System packages

## Disclaimer

This project is provided "as is" without warranty. While we strive to address security concerns promptly, we recommend:
- Running in trusted networks only
- Regular security audits
- Following Docker security best practices
- Monitoring container health and logs

## Updates

This security policy may be updated from time to time. Please check back regularly for any changes.

Last Updated: November 2024

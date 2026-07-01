# Security Policy

## Supported versions

Security fixes are applied to the default branch of this repository.

## Reporting a vulnerability

Please **do not** open a public issue for security-sensitive reports.

Contact the maintainers privately with:

- Description of the issue
- Steps to reproduce
- Impact assessment (credential exposure, arbitrary code execution, etc.)

## Credential hygiene

This project uses Feishu **App Secret** and optional LLM API keys via `.env`.

- Never commit `.env`, `config/bots.yaml`, or `config/bots_registered.yaml`
- Rotate Feishu App Secret immediately if it was ever committed or shared
- Inspector Bot can send messages and upload files in configured test chats — restrict `TRIGGER_CHAT_IDS` to dedicated test groups

## Operational safety

- Automated inspections `@` target bots and may attach documents/files in the test group
- Run `full` suites only in isolated test tenants/groups
- Review `config/test_cases.yaml` before enabling security-related probes in production-like environments

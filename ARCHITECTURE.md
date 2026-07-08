# Vernika Pro - Project Architecture

This document describes the clean, modular architecture of the Vernika Pro platform. It is designed to be easily parsable by LLMs and maintainable by developers.

## 📁 Directory Structure

```text
/
├── backend/             # Core FastAPI Application
│   ├── api/             # API Router definitions & Request Handlers
│   ├── core/            # Business logic, state management, DB models
│   ├── services/        # Third-party integrations (Vobiz, Gemini)
│   ├── prompts/         # AI Persona prompt definitions (e.g., priya.py)
│   ├── data/            # Local storage (SQLite, logs, recordings)
│   │   ├── sellers/
│   │   ├── buyers/
│   │   ├── rfqs/
│   │   └── vernikaai/   # New Sandbox for VernikaAI
│   ├── main.py          # Application entry point
│   └── config.py        # Central configuration (Environment variables)
├── frontend/            # Operator Interface
│   ├── templates/       # HTML Pages (console.html, login.html)
│   ├── static/          # Assets served by FastAPI
│   │   ├── css/         # Global design system (styles.css)
│   │   ├── js/          # Modular JavaScript logic (app.js, charts.js, etc.)
│   │   └── img/         # Static images
├── deploy/              # Deployment & DevOps configuration
│   ├── docker-compose.yml
│   └── start.sh         # Production startup script
├── .env                 # Environment secrets
├── requirements.txt     # Python dependencies
└── ARCHITECTURE.md      # This file
```

## 🚀 Key Design Principles

1. **Modular Frontend**: The monolithic `console.html` has been split into modular JS files (`app.js`, `campaign.js`, `voice.js`) located in `frontend/static/js/`. This makes it significantly easier for LLMs to read and edit specific functionality without parsing 2000+ lines of code.
2. **Role-Based Sandboxing**: All data access is scoped by the `X-User-Role` header. Backend workers for Sellers, Buyers, RFQs, and VernikaAI are logically isolated in `backend/core/state.py`.
3. **Centralized Config**: All environment variables and path resolutions are handled in `backend/config.py`.
4. **Clean project Root**: Only essential configuration files remain in the project root to reduce clutter.

## 🤖 LLM Implementation Guide

- **To edit UI Logic**: Look into `frontend/static/js/`.
- **To edit UI Layout**: Look into `frontend/templates/`.
- **To edit AI Personas**: Look into `backend/prompts/`.
- **To edit API Endpoints**: Look into `backend/api/routes/`.
- **To edit Business Logic**: Look into `backend/core/`.

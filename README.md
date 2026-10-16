# Handshake Pair 15

DATA260 Lab 1 project for a Handshake-style career and recruiting platform.

The application supports students, companies, jobs, applications, resumes, events, saved items, and a local Ollama-powered assistant.

## Pair configuration

| Parameter | Value |
|---|---|
| Pair | 15 |
| Backend port | 9150 |
| Database prefix | p15 |
| Seed | 15 |
| Cities | Sunnyvale, Cupertino, Palo Alto |
| Database | handshake_pair15 |
| MySQL host port | 3307 |
| Ollama model | qwen3:8b |

## Technology stack

- React and Vite
- FastAPI
- SQLAlchemy
- MySQL 8.4
- Docker
- Ollama
- Qwen3 8B
- bcrypt password hashing

## Backend setup

From the project root:

```bash
cd ~/Desktop/data260-handshake-pair15
source .venv/bin/activate
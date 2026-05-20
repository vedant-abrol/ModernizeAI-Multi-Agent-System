#!/usr/bin/env bash
set -euo pipefail

mkdir -p data/uploads data/repos data/reports data/chroma sample_repos
${PYTHON:-python3} scripts/create_sample_repo.py
uvicorn app.main:app --reload --port 8000 &
streamlit run frontend/streamlit_app.py --server.port 8501

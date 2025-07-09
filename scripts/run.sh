#!/bin/bash
set -e ; set -a
source .env
uvicorn Fluxo_IA_original.main:app --host 0.0.0.0 --port $PORT
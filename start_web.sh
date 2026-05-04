#!/bin/bash
cd /AI4S/Users/howardwang/h204/LMBAgent
exec streamlit run web/app/main.py \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --server.headless true \
  --server.fileWatcherType none \
  --server.enableCORS false \
  --server.enableXsrfProtection false

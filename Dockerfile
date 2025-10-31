# Dockerfile (PORT-aware for Render/Fly/Railway/Cloud Run)
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ./
# Streamlit will listen on $PORT if provided, else 8501
EXPOSE 8501
ENV PORT=8501
CMD ["bash", "-lc", "streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0"]

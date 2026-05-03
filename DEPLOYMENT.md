# Vera Bot - Deployment Guide

## Quick Start

### 1. Generate Submission File

```bash
cd vera-bot
python generate_submission.py
```

This will create `submission.jsonl` with validated messages.

### 2. Deploy to Render (Recommended)

1. **Create Render Account**: https://render.com
2. **New Web Service**: Click "New +" → "Web Service"
3. **Connect Repository**: Link your GitHub repo
4. **Configure**:
   - **Name**: `vera-bot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn bot:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free tier is sufficient

5. **Environment Variables**:
   ```
   LLM_PROVIDER=groq
   GROQ_API_KEY=your_groq_api_key_here
   GROQ_MODEL=llama-3.3-70b-versatile
   ```

6. **Deploy**: Click "Create Web Service"

### 3. Alternative: Deploy to Fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
flyctl auth login

# Launch app
cd vera-bot
flyctl launch

# Set secrets
flyctl secrets set GROQ_API_KEY=your_groq_api_key_here
flyctl secrets set LLM_PROVIDER=groq
flyctl secrets set GROQ_MODEL=llama-3.3-70b-versatile

# Deploy
flyctl deploy
```

### 4. Alternative: Deploy to Railway

1. **Create Railway Account**: https://railway.app
2. **New Project**: Click "New Project" → "Deploy from GitHub repo"
3. **Select Repository**: Choose your repo
4. **Environment Variables**:
   ```
   LLM_PROVIDER=groq
   GROQ_API_KEY=your_groq_api_key_here
   GROQ_MODEL=llama-3.3-70b-versatile
   ```
5. **Deploy**: Railway will auto-deploy

## Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your API key

# Run locally
uvicorn bot:app --host 0.0.0.0 --port 8080

# Test health endpoint
curl http://localhost:8080/v1/healthz
```

## Submission Checklist

- [ ] `submission.jsonl` generated
- [ ] Bot deployed and accessible via public URL
- [ ] Health endpoint responding: `GET /v1/healthz`
- [ ] Metadata endpoint responding: `GET /v1/metadata`
- [ ] README.md in place
- [ ] All endpoints tested

## Files for Submission

1. **submission.jsonl** - 30+ test messages
2. **README.md** - Bot documentation
3. **Public URL** - Deployed bot endpoint

## Troubleshooting

### Bot not starting
- Check environment variables are set
- Verify Python version (3.11+)
- Check logs for errors

### API errors
- Verify GROQ_API_KEY is correct
- Check API quota/limits
- Ensure LLM_PROVIDER=groq

### Timeout errors
- Increase timeout in deployment platform
- Check API response times
- Verify network connectivity

## Support

For issues, check:
1. Deployment platform logs
2. API provider status
3. Environment variable configuration

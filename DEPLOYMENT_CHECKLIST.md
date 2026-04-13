# Render Deployment Checklist

Quick checklist to deploy the Video Sentiment Analysis backend to Render.

## ✅ Pre-Deployment

- [ ] GitHub repository is up to date
- [ ] `requirements.txt` is complete
- [ ] Firebase service account JSON file is ready
- [ ] Render account created (https://render.com)

## ✅ Step 1: Create Redis Instance

- [ ] Go to Render Dashboard → New → Redis
- [ ] Name: `video-sentiment-redis`
- [ ] Plan: Starter ($10/month) or Free
- [ ] Copy Internal Redis URL: `redis://red-xxxxx:6379`

## ✅ Step 2: Create Web Service

- [ ] Go to Render Dashboard → New → Web Service
- [ ] Connect GitHub repository
- [ ] Name: `video-sentiment-backend`
- [ ] Root Directory: `backend`
- [ ] Environment: Python 3
- [ ] Build Command: `pip install -r requirements.txt`
- [ ] Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- [ ] Instance Type: Starter or Standard
- [ ] Health Check Path: `/health`

## ✅ Step 3: Add Environment Variables

Add these in service → Environment tab:

```
PYTHON_VERSION=3.11.0
FIREBASE_STORAGE_BUCKET=video-sentiment-analysis-bcd33.appspot.com
REDIS_URL=redis://red-xxxxx:6379
WHISPER_MODEL=base
SENTIMENT_MODEL=distilbert-base-uncased-finetuned-sst-2-english
MAX_VIDEO_SIZE=500
STREAM_CHUNK_DURATION=10
API_HOST=0.0.0.0
API_PORT=8000
ENVIRONMENT=production
DEBUG=false
```

## ✅ Step 4: Add Firebase Credentials

**Option A: Secret File (Recommended)**
- [ ] Go to Environment → Secret Files
- [ ] Add file: `firebase-key.json`
- [ ] Paste Firebase service account JSON
- [ ] Add env var: `FIREBASE_CREDENTIALS_PATH=/etc/secrets/firebase-key.json`

**Option B: Environment Variable**
- [ ] Minify firebase-key.json to single line
- [ ] Add env var: `FIREBASE_CREDENTIALS` with JSON content

## ✅ Step 5: Deploy Web Service

- [ ] Click "Create Web Service"
- [ ] Wait for deployment (5-10 minutes)
- [ ] Check logs for errors
- [ ] Test health endpoint: `https://your-app.onrender.com/health`
- [ ] Test API docs: `https://your-app.onrender.com/docs`

## ✅ Step 6: Create Celery Worker

- [ ] Go to Render Dashboard → New → Background Worker
- [ ] Connect same GitHub repository
- [ ] Name: `video-sentiment-worker`
- [ ] Root Directory: `backend`
- [ ] Build Command: `pip install -r requirements.txt`
- [ ] Start Command: `celery -A app.tasks.celery_tasks worker --loglevel=info --pool=solo`
- [ ] Instance Type: Same as web service
- [ ] Copy ALL environment variables from web service

## ✅ Step 7: Verify Deployment

- [ ] Health check returns: `{"status":"healthy"}`
- [ ] API docs page loads
- [ ] No errors in web service logs
- [ ] No errors in worker logs
- [ ] Redis shows active connections

## ✅ Step 8: Configure CORS

- [ ] Update `ALLOWED_ORIGINS` env var with frontend URL
- [ ] Or update `backend/app/main.py` with frontend domain
- [ ] Redeploy if needed

## ✅ Post-Deployment

- [ ] Save backend URL for frontend configuration
- [ ] Test API endpoints with Postman/curl
- [ ] Monitor logs for any issues
- [ ] Set up monitoring/alerts (optional)
- [ ] Add custom domain (optional)

---

## 🔗 Important URLs

After deployment, save these:

- **Backend URL:** `https://video-sentiment-backend.onrender.com`
- **API Docs:** `https://video-sentiment-backend.onrender.com/docs`
- **Health Check:** `https://video-sentiment-backend.onrender.com/health`
- **Redis Dashboard:** Render Dashboard → Redis instance

---

## 💰 Cost Summary

- Web Service (Starter): $7/month
- Background Worker (Starter): $7/month
- Redis (Starter): $10/month
- **Total: $24/month**

---

## 📞 Need Help?

- Check `RENDER_TROUBLESHOOTING.md` for common errors
- Check `RENDER_DEPLOYMENT.md` for detailed guide
- Render Community: https://community.render.com
- Render Support: support@render.com

---

**Ready to deploy? Start with Step 1!** 🚀

# Render Deployment Guide

## 🚀 Quick Deploy to Render

### Prerequisites
- GitHub repository pushed (✅ Already done!)
- Render account (sign up at https://render.com)
- Firebase credentials JSON file

---

## Step 1: Create Render Account

1. Go to https://render.com
2. Sign up with GitHub
3. Authorize Render to access your repositories

---

## Step 2: Create Redis Instance

1. From Render Dashboard, click **New +**
2. Select **Redis**
3. Configure:
   - **Name:** `video-sentiment-redis`
   - **Region:** Oregon (US West)
   - **Plan:** Starter ($10/month) or Free
4. Click **Create Redis**
5. **Copy the Internal Redis URL** (you'll need this later)
   - Format: `redis://red-xxxxx:6379`

---

## Step 3: Deploy Backend Web Service

### 3.1 Create Web Service

1. From Render Dashboard, click **New +**
2. Select **Web Service**
3. Connect your GitHub repository: `Sentiment-analysis-backend`
4. Configure:

**Basic Settings:**
- **Name:** `video-sentiment-backend`
- **Region:** Oregon (US West)
- **Branch:** `main`
- **Root Directory:** Leave empty (or `.` if needed)
- **Runtime:** Python 3
- **Build Command:** `chmod +x build.sh && ./build.sh`
- **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

**Instance Type:**
- **Plan:** Starter ($7/month) - 512 MB RAM
  - For better performance with Whisper: Standard ($25/month) - 2 GB RAM

### 3.2 Add Environment Variables

Click **Advanced** → **Add Environment Variable** and add these:

```
PYTHON_VERSION=3.11.0
WHISPER_MODEL=base
SENTIMENT_MODEL=distilbert-base-uncased-finetuned-sst-2-english
MAX_VIDEO_SIZE=500
STREAM_CHUNK_DURATION=10
API_HOST=0.0.0.0
API_PORT=8000
ENVIRONMENT=production
DEBUG=false
FIREBASE_STORAGE_BUCKET=video-sentiment-analysis-bcd33.appspot.com
REDIS_URL=redis://red-xxxxx:6379
```

**Important:** Replace `redis://red-xxxxx:6379` with your actual Redis Internal URL from Step 2.

### 3.3 Add Firebase Credentials as Secret File

1. Scroll to **Secret Files** section
2. Click **Add Secret File**
3. Configure:
   - **Filename:** `firebase-key.json`
   - **Contents:** Paste your entire Firebase service account JSON
4. Add another environment variable:
   ```
   FIREBASE_CREDENTIALS_PATH=/etc/secrets/firebase-key.json
   ```

### 3.4 Configure Health Check

1. Scroll to **Health Check Path**
2. Set to: `/health`

### 3.5 Deploy

1. Click **Create Web Service**
2. Wait for deployment (5-10 minutes first time)
3. Monitor logs for any errors

---

## Step 4: Deploy Celery Worker (Background Service)

### 4.1 Create Background Worker

1. From Render Dashboard, click **New +**
2. Select **Background Worker**
3. Connect same GitHub repository: `Sentiment-analysis-backend`
4. Configure:

**Basic Settings:**
- **Name:** `video-sentiment-worker`
- **Region:** Oregon (US West)
- **Branch:** `main`
- **Root Directory:** Leave empty
- **Runtime:** Python 3
- **Build Command:** `chmod +x build.sh && ./build.sh`
- **Start Command:** `celery -A app.tasks.celery_tasks worker --loglevel=info --pool=solo`

**Instance Type:**
- **Plan:** Starter ($7/month)

### 4.2 Add Environment Variables

Add the same environment variables as the web service:

```
PYTHON_VERSION=3.11.0
WHISPER_MODEL=base
SENTIMENT_MODEL=distilbert-base-uncased-finetuned-sst-2-english
FIREBASE_STORAGE_BUCKET=video-sentiment-analysis-bcd33.appspot.com
REDIS_URL=redis://red-xxxxx:6379
FIREBASE_CREDENTIALS_PATH=/etc/secrets/firebase-key.json
```

### 4.3 Add Firebase Secret File

Same as web service - add `firebase-key.json` as secret file.

### 4.4 Deploy

1. Click **Create Background Worker**
2. Wait for deployment

---

## Step 5: Verify Deployment

### 5.1 Check Web Service

1. Go to your web service dashboard
2. Copy the service URL (e.g., `https://video-sentiment-backend.onrender.com`)
3. Test endpoints:
   - Health: `https://your-app.onrender.com/health`
   - API Docs: `https://your-app.onrender.com/docs`

### 5.2 Check Logs

Monitor logs for all three services:
- Web Service logs
- Worker logs
- Redis logs

Look for:
- ✅ "Application startup complete"
- ✅ "Connected to Redis"
- ✅ "Celery worker ready"
- ❌ Any error messages

---

## Step 6: Update Frontend

Update your frontend to use the new backend URL:

**In Vercel/Frontend deployment:**
```
VITE_API_URL=https://video-sentiment-backend.onrender.com
```

---

## 🔧 Troubleshooting

### Build Fails

**Error: "pip install failed"**
- Check `build.sh` has execute permissions
- Verify `requirements-render.txt` exists
- Check Python version is 3.11

**Error: "opencv-python installation failed"**
- Use `opencv-python-headless` instead (already in requirements-render.txt)

### Runtime Errors

**Error: "Redis connection failed"**
- Verify Redis URL is correct
- Check Redis instance is running
- Ensure both services are in same region

**Error: "Firebase credentials not found"**
- Verify secret file path: `/etc/secrets/firebase-key.json`
- Check secret file was uploaded correctly
- Ensure JSON is valid

**Error: "Out of memory"**
- Reduce Whisper model size: `WHISPER_MODEL=tiny`
- Upgrade to Standard plan (2 GB RAM)
- Reduce `MAX_VIDEO_SIZE`

### Performance Issues

**Slow transcription:**
- Use smaller Whisper model (`tiny` or `base`)
- Upgrade to larger instance
- Process videos in smaller chunks

**Timeout errors:**
- Increase timeout in Render settings
- Use background tasks for long operations
- Implement progress tracking

---

## 💰 Cost Breakdown

**Minimum Setup:**
- Web Service (Starter): $7/month
- Worker (Starter): $7/month
- Redis (Starter): $10/month
- **Total: $24/month**

**Recommended Setup:**
- Web Service (Standard 2GB): $25/month
- Worker (Starter): $7/month
- Redis (Starter): $10/month
- **Total: $42/month**

**Free Tier Option:**
- Use Render free tier (spins down after inactivity)
- Use free Redis alternative (Upstash, Redis Cloud free tier)
- **Total: $0/month** (with limitations)

---

## 🔒 Security Checklist

- ✅ Firebase credentials stored as secret file
- ✅ Environment variables not in code
- ✅ HTTPS enabled by default
- ✅ Debug mode disabled in production
- ✅ CORS configured for frontend domain
- ✅ Redis password protected (if using external Redis)

---

## 📊 Monitoring

### View Logs
1. Go to service dashboard
2. Click **Logs** tab
3. Monitor real-time logs

### Set Up Alerts
1. Go to service settings
2. Configure email alerts for:
   - Deploy failures
   - Service crashes
   - High memory usage

### Metrics
Monitor in Render dashboard:
- CPU usage
- Memory usage
- Request count
- Response time

---

## 🔄 Updates and Redeployment

### Auto-Deploy
Render automatically deploys when you push to GitHub:
```bash
cd backend
git add .
git commit -m "Update backend"
git push origin main
```

### Manual Deploy
1. Go to service dashboard
2. Click **Manual Deploy**
3. Select branch
4. Click **Deploy**

### Rollback
1. Go to service dashboard
2. Click **Events** tab
3. Find previous successful deploy
4. Click **Rollback**

---

## 🎉 Success!

Your backend is now deployed on Render!

**Service URLs:**
- API: `https://video-sentiment-backend.onrender.com`
- Docs: `https://video-sentiment-backend.onrender.com/docs`
- Health: `https://video-sentiment-backend.onrender.com/health`

**Next Steps:**
1. Test all API endpoints
2. Deploy frontend to Vercel
3. Update frontend with backend URL
4. Test end-to-end functionality
5. Set up monitoring and alerts

---

## 📚 Additional Resources

- [Render Documentation](https://render.com/docs)
- [Python on Render](https://render.com/docs/deploy-fastapi)
- [Background Workers](https://render.com/docs/background-workers)
- [Secret Files](https://render.com/docs/secret-files)
- [Redis on Render](https://render.com/docs/redis)

---

**Need help?** Check Render's support or community forums.

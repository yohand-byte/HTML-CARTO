#!/bin/bash
# Deploy HTML-CARTO API to Cloud Run
# Project: solaire-frontend (29459740400)

set -e

PROJECT_ID="solaire-frontend"
REGION="europe-west1"
SERVICE_NAME="html-carto-api"

echo "🚀 Deploying HTML-CARTO API to Cloud Run..."

# Set the project
gcloud config set project $PROJECT_ID

# Build and push to Artifact Registry (or Container Registry)
echo "📦 Building container image..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME

# Deploy to Cloud Run
echo "🌐 Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --memory 512Mi \
    --cpu 1 \
    --timeout 60s \
    --concurrency 80 \
    --min-instances 0 \
    --max-instances 10

# Get the service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')

echo ""
echo "✅ Deployment complete!"
echo "🔗 Service URL: $SERVICE_URL"
echo ""
echo "Test endpoints:"
echo "  curl $SERVICE_URL/api/status"
echo "  curl -X POST $SERVICE_URL/api/validate-location -H 'Content-Type: application/json' -d '{\"lat\": 49.2312, \"lon\": -0.0456}'"

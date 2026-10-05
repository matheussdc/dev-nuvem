#!/bin/bash
set -e

echo "🚀 Deploy do Frontend..."
aws s3 sync frontend-test/ s3://frontend-309843684442-us-east-1-an/ --delete
echo "✅ Frontend deployado!"
echo "🌐 Acesse: http://frontend-309843684442-us-east-1-an.s3-website-us-east-1.amazonaws.com"

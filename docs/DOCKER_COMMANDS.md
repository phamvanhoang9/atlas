# Docker Build & Run Commands for ATLAS

## Quick Start

### 1. Build the Docker Image

```powershell
# Basic build
docker build -f Dockerfile -t atlas:latest .

# Build with build arguments (if needed)
docker build -f Dockerfile -t atlas:1.0 -t atlas:latest .

# Build with no cache (clean build)
docker build --no-cache -f Dockerfile -t atlas:latest .
```

### 2. Run the Container

```powershell
# Run with environment variables from .env file
docker run -d `
  --name atlas-app `
  --env-file .env `
  -p 8000:8000 `
  -v ${PWD}/outputs:/app/outputs `
  atlas:latest

# Run with explicit environment variables
docker run -d `
  --name atlas-app `
  -e OPENAI_API_KEY=your_openai_key `
  -e TAVILY_API_KEY=your_tavily_key `
  -e GEMINI_API_KEY=your_gemini_key `
  -e GOOGLE_API_KEY=your_google_key `
  -e GOOGLE_CX_KEY=your_google_cx_key `
  -p 8000:8000 `
  -v ${PWD}/outputs:/app/outputs `
  atlas:latest

# Run in foreground with logs visible
docker run --rm `
  --name atlas-app `
  --env-file .env `
  -p 8000:8000 `
  atlas:latest
```

### 3. Verify Container Health

```powershell
# Check container status
docker ps

# View logs
docker logs atlas-app

# Follow logs in real-time
docker logs -f atlas-app

# Check health status
docker inspect atlas-app --format='{{.State.Health.Status}}'
```

### 4. Docker Compose (Production)

Create `.env` file with your API keys, then:

```powershell
# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Rebuild and restart
docker-compose up -d --build
```

### 5. Size Optimization Commands

```powershell
# View image size
docker images atlas:latest

# Inspect image layers (see what takes space)
docker history atlas:latest --human --no-trunc

# Analyze image with dive (install dive first)
dive atlas:latest
```

## Usage Examples

### Development Workflow

```powershell
# Start development environment
docker-compose up --build

# View logs 
docker-compose logs -f 

# Stop when done 
docker-compose down
```

### Production Workflow

```powershell
# Build and tag for production
docker build -t atlas:v1.0.0 .
docker tag atlas:v1.0.0 atlas:latest

# Start production environment
docker-compose -f docker-compose.prod.yml up -d

# Check status
docker-compose -f docker-compose.prod.yml ps 

# View logs 
docker-compose -f docker-compose.prod.yml logs -f --tail=100

# Update app (new version)
docker build -t atlas:v1.0.1 .
docker tag atlas:v1.0.1 atlas:latest
docker-compose -f docker-compose.prod.yml up -d --force-recreate

# Stop production environment
docker-compose -f docker-compose.prod.yml down
```

## Advanced Commands

### Debugging

```powershell
# Run interactive shell in container
docker run -it --rm --env-file .env atlas:latest /bin/bash

# Execute command in running container
docker exec -it atlas-app /bin/bash

# Check Python packages in container
docker exec atlas-app pip list

# Test health check manually
docker exec atlas-app python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/').read()"
```

### Performance Monitoring

```powershell
# Monitor container resource usage
docker stats atlas-app

# Limit container resources
docker run -d `
  --name atlas-app `
  --env-file .env `
  --memory="2g" `
  --cpus="2" `
  -p 8000:8000 `
  atlas:latest
```

### Registry Operations

```powershell
# Tag for registry
docker tag atlas:latest your-registry.com/atlas:1.0

# Push to registry
docker push your-registry.com/atlas:1.0

# Pull from registry
docker pull your-registry.com/atlas:1.0
```

### Cleanup

```powershell
# Stop and remove container
docker stop atlas-app
docker rm atlas-app

# Remove image
docker rmi atlas:latest

# Remove all unused images, containers, and volumes
docker system prune -a --volumes
```

## Production Deployment

```powershell
docker-compose -f docker-compose.prod.yml up -d
```

## Kubernetes Deployment (Optional)

### Create Deployment

```yaml
# atlas-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: atlas
spec:
  replicas: 2
  selector:
    matchLabels:
      app: atlas
  template:
    metadata:
      labels:
        app: atlas
    spec:
      containers:
      - name: atlas
        image: atlas:latest
        ports:
        - containerPort: 8000
        env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: atlas-secrets
              key: openai-key
        livenessProbe:
          httpGet:
            path: /
            port: 8000
          initialDelaySeconds: 40
          periodSeconds: 30
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
```

Deploy:

```powershell
kubectl apply -f atlas-deployment.yaml
```

## Troubleshooting

### Container won't start

```powershell
# Check logs for errors
docker logs atlas-app

# Run in foreground to see startup
docker run --rm --env-file .env -p 8000:8000 atlas:latest
```

### Permission issues

```powershell
# Ensure outputs directory is writable
mkdir -p outputs
icacls outputs /grant Everyone:F
```

### Health check failing

```powershell
# Test health endpoint manually
curl http://localhost:8000/

# Check if uvicorn is listening
docker exec atlas-app netstat -tuln | grep 8000
```

### Port already in use

```powershell
# Find and stop process using port 8000
netstat -ano | findstr :8000
# Then stop the process or use different port:
docker run -d --name atlas-app --env-file .env -p 8001:8000 atlas:latest
```

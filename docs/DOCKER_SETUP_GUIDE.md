# Production-Ready Docker Setup for ATLAS

## 🚀 Quick Start

### 1. Create `.env` file with your API keys:
```ini
OPENAI_API_KEY=your_openai_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
GOOGLE_CX_KEY=your_google_cx_key_here
```

### 2. Build the image:
```powershell
docker build -f Dockerfile -t atlas:latest .
```

### 3. Run the container:
```powershell
docker run -d --name atlas-app --env-file .env -p 8000:8000 -v ${PWD}/outputs:/app/outputs atlas:latest
```

### 4. Access the application:
```
http://localhost:8000
```

---

## 📦 Deliverables Overview

### 1. ✅ Dockerfile
**File:** [`Dockerfile`](Dockerfile)

**Features:**
- Multi-stage build (builder + runtime)
- Python 3.12 slim base image
- Non-root user (UID 1000)
- Virtual environment isolation
- Optimized layer caching
- Health check included
- Minimal dependencies
- Security hardened

---

### 2. ✅ .dockerignore File
**File:** [`.dockerignore`](.dockerignore)

**Excludes:**
- Virtual environments (`.venv/`)
- Python cache (`__pycache__/`)
- Git files (`.git/`)
- Documentation (`docs/`, `*.md`)
- Tests and examples
- IDE configurations
- Output files
- Logs and temporary files

---

### 3. ✅ Build & Run Commands
**File:** [`DOCKER_COMMANDS.md`](docs/DOCKER_COMMANDS.md)

**Includes:**
- Basic build and run commands
- Production deployment with Docker Compose
- Kubernetes deployment example
- Health check verification
- Debugging commands
- Performance monitoring
- Registry operations
- Cleanup procedures
- Troubleshooting guide

---

## 🔧 Production Docker Compose

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  atlas:
    image: atlas:latest
    build:
      context: .
      dockerfile: Dockerfile.optimized
    container_name: atlas-production
    restart: unless-stopped
    
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - TAVILY_API_KEY=${TAVILY_API_KEY}
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - GOOGLE_CX_KEY=${GOOGLE_CX_KEY}
    
    ports:
      - "127.0.0.1:8000:8000"  # Localhost only
    
    volumes:
      - ./outputs:/app/outputs
      - atlas-data:/app/data
    
    networks:
      - atlas-network
    
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
    
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/').read()"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  atlas-data:
    driver: local

networks:
  atlas-network:
    driver: bridge
```

**Deploy:**
```powershell
docker-compose -f docker-compose.prod.yml up -d
```

---

## 🐛 Troubleshooting

### Build fails with dependency errors:
```powershell
# Clean build without cache
docker build --no-cache -f Dockerfile -t atlas:latest .
```

### Container exits immediately:
```powershell
# Check logs
docker logs atlas-app

# Run in foreground to see errors
docker run --rm --env-file .env -p 8000:8000 atlas:latest
```

### Health check failing:
```powershell
# Test FastAPI is responding
curl http://localhost:8000/

# Check container logs
docker logs atlas-app
```

### Permission denied on outputs:
```powershell
# Fix permissions
mkdir -p outputs
icacls outputs /grant Everyone:F
```

---
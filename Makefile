.PHONY: help dev build run stop clean test lint format install-deps docker-build docker-run docker-stop

# Default target
help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# Development commands
install-deps: ## Install all dependencies
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt
	@echo "Installing Node.js dependencies..."
	cd ui && npm install

dev: ## Run the application in development mode
	@echo "Starting development servers..."
	@echo "Make sure you have your .env file configured with FINNHUB_API_KEY"
	# Start backend in background
	python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
	# Start frontend dev server
	cd ui && npm run dev

dev-backend: ## Run only the backend in development mode
	python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

dev-frontend: ## Run only the frontend in development mode
	cd ui && npm run dev

build-frontend: ## Build the frontend for production
	cd ui && npm run build

# Testing and quality
test: ## Run tests
	python -m pytest tests/ -v

lint: ## Run linters
	@echo "Linting Python code..."
	flake8 app/
	@echo "Linting TypeScript code..."
	cd ui && npm run lint

format: ## Format code
	@echo "Formatting Python code..."
	black app/
	@echo "Formatting TypeScript code..."
	cd ui && npm run format || echo "No format script found"

# Production commands
build: build-frontend ## Build the application for production
	@echo "Production build completed"

# Docker commands
docker-build: ## Build Docker image
	docker build -t trading-app .

docker-run: ## Run the application with Docker Compose
	@echo "Starting application with Docker Compose..."
	@echo "Make sure you have your .env file configured"
	docker-compose up -d

docker-stop: ## Stop Docker containers
	docker-compose down

docker-logs: ## Show Docker logs
	docker-compose logs -f

docker-rebuild: ## Rebuild and restart Docker containers
	docker-compose down
	docker-compose build --no-cache
	docker-compose up -d

# Database commands
db-reset: ## Reset the database (development only)
	rm -f trading.db
	@echo "Database reset. It will be recreated on next run."

# Data management
clean-data: ## Clean all data files (DANGER: removes all trading data)
	@echo "This will remove all trading data. Are you sure? (y/N)"
	@read -r response && [ "$$response" = "y" ] || exit 1
	rm -rf data/candles/*
	rm -rf data/cache/*
	rm -f trading.db
	@echo "All data cleaned"

backup-data: ## Backup data directory
	@mkdir -p backups
	tar -czf backups/trading-data-$(shell date +%Y%m%d_%H%M%S).tar.gz data/ trading.db
	@echo "Data backed up to backups/"

# Utility commands
logs: ## Show application logs
	tail -f logs/trading_$(shell date +%Y-%m-%d).log

status: ## Check application status
	curl -s http://localhost:8000/healthz | python -m json.tool

clean: ## Clean build artifacts
	rm -rf ui/dist
	rm -rf ui/node_modules/.cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# Environment setup
setup: ## Initial setup for development
	@echo "Setting up development environment..."
	cp .env.sample .env
	@echo "Please edit .env file with your configuration"
	make install-deps
	@echo "Setup complete! Edit .env file and run 'make dev' to start"

# Production deployment helpers
deploy-check: ## Check deployment readiness
	@echo "Checking deployment readiness..."
	@test -f .env || (echo "ERROR: .env file missing" && exit 1)
	@grep -q "FINNHUB_API_KEY=" .env || (echo "ERROR: FINNHUB_API_KEY not set in .env" && exit 1)
	@echo "✓ Environment configuration looks good"
	@docker --version > /dev/null || (echo "ERROR: Docker not installed" && exit 1)
	@echo "✓ Docker is available"
	@echo "Ready for deployment!"

# Monitoring
monitor: ## Show real-time system stats
	@echo "Monitoring trading application..."
	@echo "Press Ctrl+C to stop"
	while true; do \
		echo "=== $(shell date) ==="; \
		curl -s http://localhost:8000/healthz | python -c "import sys, json; data=json.load(sys.stdin); print(f\"Status: {data['status']}\"); print(f\"Worker Running: {data['worker']['running']}\"); print(f\"WS Connected: {data['worker']['ws_connected']}\"); print(f\"Symbols: {data['worker']['symbols_count']}\"); print(f\"Trades Processed: {data['worker']['stats']['trades_processed']}\")"; \
		sleep 5; \
	done
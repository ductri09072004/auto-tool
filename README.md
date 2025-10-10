# Dev Portal - Auto Project Tool

A simple Dev Portal for automatically generating Flask microservices with mock data.

## Features

- 🚀 **One-click service creation** - Generate Flask services in minutes
- 📊 **Mock data generation** - Users, Products, Orders with customizable count
- 🐳 **Docker ready** - Automatic Dockerfile generation
- 🔄 **CI/CD pipeline** - GitHub Actions workflow included
- 📝 **Auto documentation** - README.md with setup instructions

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Dev Portal
```bash
python app.py
```

### 3. Access Web Interface
Open your browser and go to: `http://localhost:3050`

## Usage

### Create New Service
1. Fill in the service form:
   - **Service Name**: Unique name for your service
   - **Description**: Brief description
   - **Port**: Port number (default: 5000)
   - **Mock Data Type**: Choose from Users, Products, or Orders
   - **Data Count**: Number of mock records to generate
   - **Endpoints**: Select which API endpoints to include

2. Click "Create Service"

3. The portal will generate:
   - Flask application with mock data
   - Dockerfile for containerization
   - GitHub Actions CI/CD pipeline
   - README.md with instructions

### Generated Service Structure
```
your-service/
├── app.py                    # Flask application
├── requirements.txt          # Python dependencies
├── Dockerfile               # Container configuration
├── README.md                # Documentation
└── .github/workflows/       # CI/CD pipeline
    └── ci-cd.yml
```

## API Endpoints

Each generated service includes:

- `GET /` - Service information
- `GET /api/health` - Health check
- `GET /api/{data_type}` - Mock data endpoint (users/products/orders)

## Example Generated Service

### Running Locally
```bash
# Install dependencies
pip install -r requirements.txt

# Run the service
python app.py
```

### Using Docker
```bash
# Build image
docker build -t your-service .

# Run container
docker run -p 5000:5000 your-service
```

## Configuration

Set environment variables for GitHub integration:

```bash
export GITHUB_TOKEN="your_github_token"
export GITHUB_ORG="your_organization"
```

## Development

### Project Structure
```
Auto_project_tool/
├── app.py                    # Main Flask application
├── templates/
│   └── index.html           # Web interface
├── requirements.txt         # Dependencies
└── README.md               # This file
```

### Adding New Templates
1. Modify the generation functions in `app.py`
2. Update the web form in `templates/index.html`
3. Test with different service configurations

## License

MIT License - feel free to use and modify as needed.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

**Happy coding! 🚀**

# New Relic MCP Server

A command-line tool for monitoring and analyzing New Relic application metrics using MCP (Model Control Protocol).

## Quick Start

Run directly with pipx (no installation needed):

```bash
pipx run newrelic-mcp --api-key="NR_API_KEY" --new-relic-api-key "YOUR_API_KEY" --insights-key "YOUR_NR_INSIGHTS_API_KEY" --account-id "YOUR_NR_ACCOUNT_ID" --model "openai/gpt-4o-mini"
```

That's it! pipx will:
- Download the package from PyPI
- Create an isolated environment
- Run the command
- Clean up after itself

## Prerequisites

- Python 3.8 or higher
- pipx (for running without installation)

To install pipx if you don't have it:
```bash
# On macOS
brew install pipx
pipx ensurepath

# On Linux
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# On Windows
python -m pip install --user pipx
python -m pipx ensurepath
```

## Installation Options

### Option 1: Run Directly (Recommended)

The simplest way to use this tool is to run it directly with pipx:

```bash
pipx run newrelic-mcp --new-relic-api-key "YOUR_API_KEY" --nr-insights-api-key "YOUR_INSIGHTS_KEY" --new-relic-account-id "YOUR_ACCOUNT_ID" --model "openai/gpt-4o-mini"
```

This is perfect for:
- One-off usage
- Trying out the tool
- Running in CI/CD pipelines
- Avoiding global installation

### Option 2: Install Globally

If you use this tool frequently, you can install it globally:

```bash
pipx install newrelic-mcp
```

Then run it anytime with:
```bash
newrelic-mcp --new-relic-api-key "YOUR_API_KEY" --nr-insights-api-key "YOUR_INSIGHTS_KEY" --new-relic-account-id "YOUR_ACCOUNT_ID" --model "openai/gpt-4o-mini"
```

### Option 3: Development Installation

For development or local testing:

```bash
# Clone the repository
git clone https://github.com/yourusername/newrelic-mcp.git
cd newrelic-mcp

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in editable mode with development dependencies
pip install -e ".[dev]"
```

## Usage

### Running the Server

After installation, you can run the New Relic MCP server using:

```bash
newrelic-mcp --new-relic-api-key "YOUR_API_KEY" --nr-insights-api-key "YOUR_INSIGHTS_KEY" --new-relic-account-id "YOUR_ACCOUNT_ID" --model "openai/gpt-4o-mini"
```

### Required Arguments

- `--new-relic-api-key`: Your New Relic API key
- `--nr-insights-api-key`: Your New Relic Insights API key
- `--new-relic-account-id`: Your New Relic account ID
- `--model`: The LLM model to use for finding application IDs (e.g., "openai/gpt-4o-mini")

### Available Tools

The server provides two main tools:

1. `get_transaction_details_by_url_path`: Get details for a specific transaction or API endpoint
   ```python
   await get_transaction_details_by_url_path(
       application_name="your-app-name",
       url_path="/api/v1/endpoint",
       time_range_minutes=30
   )
   ```

2. `get_application_metrics`: Get metrics for an entire application
   ```python
   await get_application_metrics(
       application_name="your-app-name",
       time_range_minutes=30
   )
   ```

## Development

### Using Makefile

The project includes a Makefile with common development commands:

```bash
# Show all available commands
make help

# Install development dependencies
make install-dev

# Format code
make format

# Run linting
make lint

# Build the package
make build

# Upload to PyPI
make upload

# Do everything (clean, build, test, upload)
make all

# Version management
make bump-patch  # Bump patch version (0.0.x)
make bump-minor  # Bump minor version (0.x.0)
make bump-major  # Bump major version (x.0.0)
```

### Setting Up Development Environment

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

### Building and Publishing

To build and publish the package:

```bash
# Build the package
make build

# Upload to PyPI
make upload

# Or do both in one command
make all
```

Note: You need to have a PyPI account and be logged in to upload. To log in:
```bash
python -m twine login
```

## License

MIT License - See [LICENSE](LICENSE) file for details 
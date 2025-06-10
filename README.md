# New Relic MCP Server

A command-line tool for monitoring and analyzing New Relic application metrics using MCP (Model Control Protocol).

## Installation

Install directly from GitHub using pipx:

```bash
# Install
pipx install git+https://github.com/yourusername/newrelic-mcp.git

# Or run without installation
pipx run git+https://github.com/yourusername/newrelic-mcp.git
```

## Quick Start

1. Set up your environment variables:

   **Method: Using .env file**
   ```bash
   # Create a .env file in your project directory
   cat > .env << EOL
   # New Relic Credentials
   NEWRELIC_API_KEY=your-newrelic-api-key-here
   NEWRELIC_INSIGHTS_KEY=your-newrelic-insights-key-here
   NEWRELIC_ACCOUNT_ID=your-newrelic-account-id-here
   
   # OpenAI Credentials
   OPENAI_API_KEY=your-openai-api-key-here
   
   # Optional: Model Configuration
   MODEL=openai/gpt-4o-mini
   EOL
   ```

2. Create `agent.yaml`:
```yaml
- name: "New Relic Agent"
  description: "Agent to get all details of New Relic"
  mcp_servers: 
    - name: "New Relic MCP Server"
      args: ["--api-key=${NEWRELIC_API_KEY}", "--insights-key=${NEWRELIC_INSIGHTS_KEY}", "--account-id=${NEWRELIC_ACCOUNT_ID}", "--openai_api_key=${OPENAI_API_KEY}"]
      command: "newrelic-mcp"
  system_prompt: "You are a SRE devops engineer specialising in New Relic to get APM metrics at performance level. You can use the tools provided to you to get the details of the performnace of apm. Precisely use the tools to get the details of necessary metrics to get the valuable information."
```

3. Run the server:
```bash
newrelic-mcp --api-key "YOUR_API_KEY" --insights-key "YOUR_INSIGHTS_KEY" --account-id "YOUR_ACCOUNT_ID" --openai_api_key "YOUR_OPENAI_API_KEY"
```

## Available Tools

The server provides the following tools for New Relic APM analysis:

1. Get transaction details for a specific endpoint:
```python
await get_transaction_details_by_url_path(
    application_name="your-app-name",
    url_path="/api/v1/endpoint",
    time_range_minutes=30
)
```

2. Get overall application metrics:
```python
await get_application_metrics(
    application_name="your-app-name",
    time_range_minutes=30
)
```

3. Get APM metrics for an application:
```python
await get_newrelic_apm_metrics(
    application_name="your-app-name",
    time_range_minutes=30
)
```

4. Get slow transaction details:
```python
await get_application_slow_transactions_details(
    application_name="your-app-name",
    time_range_minutes=30
)
```

5. Get top database operations:
```python
await get_application_top_database_operations_details(
    application_name="your-app-name",
    time_range_minutes=30
)
```

6. Get transaction breakdown segments:
```python
await get_transaction_breakdown_segments(
    application_name="your-app-name",
    time_range_minutes=30
)
```

## Development

For development setup:
```bash
git clone https://github.com/yourusername/newrelic-mcp.git
cd newrelic-mcp
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

## License

MIT License - See [LICENSE](LICENSE) file for details 
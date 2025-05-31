import argparse
import asyncio
from newrelic_mcp.server import run_server

def main():
    parser = argparse.ArgumentParser(description='New Relic MCP Server')
    parser.add_argument('--new-relic-api-key', required=True, help='New Relic API Key')
    parser.add_argument('--nr-insights-api-key', required=True, help='New Relic Insights API Key')
    parser.add_argument('--new-relic-account-id', required=True, help='New Relic Account ID')
    parser.add_argument('--model', required=True, help='Model to use for LLM calls for find proper app id')
    args = parser.parse_args()

    # Run the server
    asyncio.run(run_server(
        new_relic_api_key=args.new_relic_api_key,
        nr_insights_api_key=args.nr_insights_api_key,
        new_relic_account_id=args.new_relic_account_id,
        model=args.model
    ))

if __name__ == "__main__":
    main() 
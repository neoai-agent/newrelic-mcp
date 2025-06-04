import argparse
import asyncio
import os
from dotenv import load_dotenv
from .server import NewRelicMCPServer

def main():
    parser = argparse.ArgumentParser(description='New Relic MCP Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind the server to')
    parser.add_argument('--port', type=int, default=8000, help='Port to bind the server to')
    parser.add_argument('--api-key', help='New Relic API Key')
    parser.add_argument('--insights-key', help='New Relic Insights API Key')
    parser.add_argument('--account-id', help='New Relic Account ID')
    parser.add_argument('--model', default='gpt-4', help='Model to use for analysis')
    
    args = parser.parse_args()
    
    # Load environment variables from .env file if it exists
    load_dotenv()
    
    # Use command line arguments or environment variables
    api_key = args.api_key or os.getenv('NEW_RELIC_API_KEY')
    insights_key = args.insights_key or os.getenv('NEW_RELIC_INSIGHTS_KEY')
    account_id = args.account_id or os.getenv('NEW_RELIC_ACCOUNT_ID')
    
    if not all([api_key, insights_key, account_id]):
        print("Error: Missing required credentials. Please provide them via arguments or environment variables.")
        print("Required environment variables:")
        print("  NEW_RELIC_API_KEY")
        print("  NEW_RELIC_INSIGHTS_KEY")
        print("  NEW_RELIC_ACCOUNT_ID")
        return 1
    
    server = NewRelicMCPServer(
        api_key=api_key,
        insights_api_key=insights_key,
        account_id=account_id,
        model=args.model
    )
    
    print(f"Starting New Relic MCP Server on {args.host}:{args.port}")
    asyncio.run(server.start(args.host, args.port))
    return 0

if __name__ == '__main__':
    exit(main()) 
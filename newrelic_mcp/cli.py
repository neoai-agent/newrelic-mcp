import argparse
import os
import anyio
from dotenv import load_dotenv
from .server import NewRelicMCPServer

# Renamed async_main to perform_async_initialization
# This function will contain the operations that need to be run asynchronously
# BEFORE the blocking MCP server starts.
async def perform_async_initialization(server_obj: NewRelicMCPServer):
    await server_obj.client.initialize_newrelic()
    # Any other async setup can go here in the future

def main():
    parser = argparse.ArgumentParser(description='New Relic MCP Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind the server to')
    parser.add_argument('--port', type=int, default=8000, help='Port to bind the server to')
    parser.add_argument('--api-key', help='New Relic API Key')
    parser.add_argument('--insights-key', help='New Relic Insights API Key')
    parser.add_argument('--account-id', help='New Relic Account ID')
    parser.add_argument('--openai_api_key', help='OpenAI API Key')
    parser.add_argument('--model', default='gpt-4', help='Model to use for analysis')
    
    args = parser.parse_args()
    
    load_dotenv()
    
    api_key = args.api_key or os.getenv('NEW_RELIC_API_KEY')
    insights_key = args.insights_key or os.getenv('NEW_RELIC_INSIGHTS_KEY')
    account_id = args.account_id or os.getenv('NEW_RELIC_ACCOUNT_ID')
    openai_api_key = args.openai_api_key or os.getenv('OPENAI_API_KEY')
    
    if not all([api_key, insights_key, account_id, openai_api_key]):
        print("Error: Missing required credentials. Please provide them via arguments or environment variables.")
        print("Required environment variables:")
        print("  NEW_RELIC_API_KEY")
        print("  NEW_RELIC_INSIGHTS_KEY")
        print("  NEW_RELIC_ACCOUNT_ID")
        print("  OPENAI_API_KEY")
        return 1
    
    server = NewRelicMCPServer(
        api_key=api_key,
        insights_api_key=insights_key,
        account_id=account_id,
        model=args.model,
        openai_api_key=openai_api_key
    )
    
    # Step 1: Run the asynchronous initialization tasks using AnyIO
    anyio.run(perform_async_initialization, server)
    
    # Step 2: After async tasks are done, start the blocking MCP server
    print(f"Starting New Relic MCP Server")
    server.run_mcp_blocking() # Call the new synchronous method
    
    # The program will likely block in server.run_mcp_blocking()
    # and might not reach here unless the server is shut down.
    return 0

if __name__ == '__main__':
    main() 
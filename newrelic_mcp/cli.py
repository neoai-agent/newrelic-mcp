import argparse
import os
import anyio
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
    parser.add_argument('--api-key', required=True, help='New Relic API Key')
    parser.add_argument('--insights-key', required=True, help='New Relic Insights API Key')
    parser.add_argument('--account-id', required=True, help='New Relic Account ID')
    parser.add_argument('--openai_api_key', required=True, help='OpenAI API Key')
    parser.add_argument('--model', default='openai/gpt-4o-mini', help='Model to use for analysis')
    
    args = parser.parse_args()
    
    server = NewRelicMCPServer(
        api_key=args.api_key,
        insights_api_key=args.insights_key,
        account_id=args.account_id,
        model=args.model,
        openai_api_key=args.openai_api_key
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
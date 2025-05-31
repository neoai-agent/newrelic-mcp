import os
import requests
from typing import Any, Dict, List
from datetime import datetime, timedelta, timezone
from mcp.server.fastmcp import FastMCP
import logging
from litellm import acompletion

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('newrelic_mcp')

# Constants
NR_API_BASE = "https://api.newrelic.com/v2"
NR_INSIGHTS_API_BASE = "https://insights-api.newrelic.com/v1"
DEFAULT_METRIC_VALUES = ['average_response_time', 'calls_per_minute', 'apdex_score', 'error_rate']
APM_METRICS_AVAILABLE = ["HttpDispatcher", "Apdex"]

# Global variables
_newrelic_applications_available = None
_application_id_cache = {}

class NewRelicClient:
    def __init__(self, new_relic_api_key: str, nr_insights_api_key: str, new_relic_account_id: str):
        self.new_relic_account_id = new_relic_account_id
        self.headers = {
            "X-Api-Key": new_relic_api_key,
            "Content-Type": "application/json"
        }
        self.insights_headers = {
            "X-Query-Key": nr_insights_api_key,
            "Content-Type": "application/json"
        }

    # ... [Rest of the NewRelicClient class implementation from app.py] ...

def _initialize_newrelic_data(new_relic_api_key: str):
    """
    Initialize New Relic data by fetching all applications and their IDs.
    Returns a list of dictionaries containing application names and IDs.
    """
    headers = {
        'X-Api-Key': new_relic_api_key
    }
    
    try:
        # Call New Relic API to get all applications
        response = requests.get(
            f"{NR_API_BASE}/applications.json",
            headers=headers
        )
        response.raise_for_status()
        
        applications = response.json().get('applications', [])
        
        # Extract relevant information
        global _newrelic_applications_available
        _newrelic_applications_available = [
            {
                "app_id": str(app['id']),
                "name": app['name']
            }
            for app in applications
        ]
        
        logger.info(f"Retrieved {len(_newrelic_applications_available)} applications from New Relic")
        return _newrelic_applications_available
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching applications from New Relic: {str(e)}")
        return []

async def find_newrelic_application_id(application_name: str, new_relic_api_key: str, model: str):
    # Check cache first
    if application_name in _application_id_cache:
        return _application_id_cache[application_name]
        
    system_prompt = f"""
    Find the application id that best matches the application name "{application_name}" from the list of applications:
    The list of applications available are:
    {_newrelic_applications_available}

    You must return only the application id. No extra text or explanation.
    """
    logger.info(f"Finding application id for {application_name}")
    response = await acompletion(
        model=model,
        messages=[{"role": "system", "content": system_prompt}],
    )
    app_id = response.choices[0].message.content
    logger.info(f"Application id for {application_name} is {app_id}")
    
    # Cache the result
    _application_id_cache[application_name] = app_id
    
    return app_id

# ... [Rest of the helper functions from app.py] ...

async def run_server(new_relic_api_key: str, nr_insights_api_key: str, new_relic_account_id: str, model: str):
    """
    Run the New Relic MCP server with the given configuration.
    """
    # Initialize New Relic data
    global _newrelic_applications_available
    _newrelic_applications_available = _initialize_newrelic_data(new_relic_api_key)
    
    # Create MCP server
    mcp = FastMCP("newrelic-mcp")
    
    # Create New Relic client
    nr_client = NewRelicClient(new_relic_api_key, nr_insights_api_key, new_relic_account_id)
    
    # Register tools
    @mcp.tool()
    async def get_transaction_details_by_url_path(application_name: str, url_path: str, time_range_minutes: int = 30) -> str:
        """
        Get transaction details from New Relic for a specific transaction or api endpoint in an application.
        """
        try:
            newrelic_application_id = await find_newrelic_application_id(application_name, new_relic_api_key, model)
            apm_transaction_details = get_transaction_details(newrelic_application_id, url_path, time_range_minutes)
            apm_transaction_breakdown_segments = get_transaction_breakdown_segments(newrelic_application_id, url_path, time_range_minutes)

            return {
                "apm_transaction_details": apm_transaction_details,
                "apm_transaction_breakdown_segments": apm_transaction_breakdown_segments
            }
        except Exception as e:
            logger.error(f"Error fetching New Relic APM metrics: {str(e)}")
            return f"Error fetching New Relic APM metrics: {str(e)}"

    @mcp.tool()
    async def get_application_metrics(application_name: str, time_range_minutes: int = 30) -> str:
        """
        Get APM metrics from New Relic for a specific application.
        """
        try:
            newrelic_application_id = await find_newrelic_application_id(application_name, new_relic_api_key, model)
            metrics_data = get_app_metric_data(newrelic_application_id, APM_METRICS_AVAILABLE, DEFAULT_METRIC_VALUES, time_range_minutes)
            slow_transactions = get_top_transactions_with_breakdown(newrelic_application_id, time_range_minutes)
            top_database_operations = get_top_database_operations_details(newrelic_application_id, time_range_minutes)
            return {
                "metrics_data": metrics_data,
                "slow_transactions": slow_transactions,
                "top_database_operations": top_database_operations
            }
        except Exception as e:
            logger.error(f"Error fetching New Relic APM metrics: {str(e)}")
            return f"Error fetching New Relic APM metrics: {str(e)}"

    # Run the server
    await mcp.run(transport="stdio") 
import asyncio
import requests
import argparse
from datetime import datetime, timedelta, timezone
from mcp.server.fastmcp import FastMCP
import logging
from litellm import acompletion

# Initialize MCP at module level
mcp = FastMCP("newrelic-mcp")

# New Relic API configuration
NR_API_BASE = "https://api.newrelic.com/v2"
NR_INSIGHTS_API_BASE = "https://insights-api.newrelic.com/v1"
DEFAULT_METRIC_VALUES = ['average_response_time', 'calls_per_minute', 'apdex_score', 'error_rate']

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('newrelic_mcp')

# Global variable for NewRelic client
nr_client = None

apm_metrics_available = [
    "HttpDispatcher",
    "Apdex"
]

class NewRelicClient:
    def __init__(self, api_key: str, insights_api_key: str, account_id: str, model: str):
        self.headers = {
            "X-Api-Key": api_key,
            "Content-Type": "application/json"
        }
        self.insights_headers = {
            "X-Query-Key": insights_api_key,
            "Content-Type": "application/json"
        }
        self.account_id = account_id
        self.NR_API_BASE = NR_API_BASE
        self.NR_INSIGHTS_API_BASE = NR_INSIGHTS_API_BASE
        self.model = model
        self._application_id_cache = {}
        self._applications_available = []

    def _make_request(self, endpoint, params=None, data=None, method="GET"):
        if not self.headers.get("X-Api-Key"):
            logger.error("Cannot make New Relic API request: API key is missing.")
            return {"error": "New Relic API key not configured"}
            
        try:
            full_url = f"{self.NR_API_BASE}/{endpoint}"
            logger.info(f"Making New Relic request to: {full_url}")
            response = requests.request(
                method,
                full_url,
                headers=self.headers,
                params=params,
                json=data
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_message = f"New Relic API request error: {str(e)}"
            if e.response is not None:
                error_message += f" - Response: {e.response.text}"
            logger.error(error_message)
            return {"error": error_message}
        except Exception as e:
            logger.error(f"Unexpected error during New Relic API request: {str(e)}")
            return {"error": f"Unexpected error: {str(e)}"}

    def _make_insights_request(self, query):
        """
        Make a request to the New Relic Insights API using NRQL.
        """
        try:
            url = f"{self.NR_INSIGHTS_API_BASE}/accounts/{self.account_id}/query"
            logger.info(f"Making Insights API request with query: {query}")
            
            response = requests.get(
                url,
                headers=self.insights_headers,
                params={"nrql": query}
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_message = f"New Relic Insights API request error: {str(e)}"
            if e.response is not None:
                error_message += f" - Response: {e.response.text}"
            logger.error(error_message)
            return {"error": error_message}
        except Exception as e:
            logger.error(f"Unexpected error during New Relic Insights API request: {str(e)}")
            return {"error": f"Unexpected error: {str(e)}"}
    
    def _fetch_newrelic_applications_details(self):
        """
        Fetch the list of applications from New Relic and return a list of dictionaries with the application name and id.

        returns a list of dict containing the application name and id.
        """
        response = self._make_request("applications.json")
        applications = response.get("applications", [])
        return [{"name": app["name"], "id": app["id"]} for app in applications]
    
    async def initialize_newrelic(self):
        """
        Initialize the New Relic data.
        """
        self._applications_available = self._fetch_newrelic_applications_details()

    async def find_newrelic_application_id(self, application_name: str):
    # Check cache first
        if application_name in self._application_id_cache:
            return self._application_id_cache[application_name]
            
        system_prompt = f"""
        Find the application id that best matches the application name "{application_name}" from the list of applications:
        The list of applications available are:
        {self._applications_available}

        You must return only the application id. No extra text or explanation.

        """
        logger.info(f"Finding application id for {application_name}")
        response = await acompletion(
            model=self.model or "gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}],
        )
        app_id = response.choices[0].message.content
        logger.info(f"Application id for {application_name} is {app_id}")
        
        # Cache the result
        self._application_id_cache[application_name] = app_id
        
        return app_id

    def get_apm_metrics_names(self, app_id: int):
        """
        Get available APM metrics names for a specific application.
        """
        return self._make_request(
            f"applications/{app_id}/metrics.json"
        )
    
    def get_application_metric_request(self, app_id: int, metric_names: list[str], metric_values: list[str]=None, summarize: bool = True, params: dict = None):
        """Fetch specific APM metric data points for an application using metrics/data.json"""
         
        request_params = params or {
            "names[]": metric_names,
            "values[]": metric_values,
            "summarize": "true" if summarize else "false"
        }

        return self._make_request(
            f"applications/{app_id}/metrics/data.json",
            params=request_params
        )

    def get_slow_transactions(self, app_id: int, time_range_minutes: int = 30):
        """
        Get slow transactions using New Relic Insights API with NRQL.
        """
        query = f"""
        FROM Transaction
        SELECT
          sum(duration) AS 'Total Duration',
          average(duration) * 1000 AS 'Avg Duration',
          min(duration) * 1000 AS 'Min Duration',
          max(duration) * 1000 AS 'Max Duration',
          count(*) AS 'Call Count',
          filter(count(*), WHERE error IS true) * 100 / count(*) AS 'Error Rate (%)',
          rate(count(*), 1 minute) AS 'Throughput (rpm)'
        WHERE appId = {app_id}
        SINCE {time_range_minutes} minutes ago
        FACET name
        ORDER BY `Total Duration` DESC
        LIMIT 5
        """
        logger.info(f"Slow transactions query: {query}")
        result = self._make_insights_request(query)

        if not result or "error" in result:
            logger.error(f"Failed to fetch slow transactions: {result.get('error', 'Unknown error')}")
            return {"error": "Failed to fetch slow transactions"}

        def format_ms(value: float) -> str:
            return f"{int(round(value))} ms"

        slow_transactions = []
        if "facets" in result:
            for facet in result["facets"]:
                try:
                    name_raw = facet["name"]
                    results = facet["results"]


                    avg_ms = float(results[1].get("result", 0))
                    min_ms = float(results[2].get("result", 0))
                    max_ms = float(results[3].get("result", 0))

                    transaction_data = {
                        "name": name_raw,
                        "total_duration": round(float(results[0].get("sum", 0)), 2),
                        "avg_duration": format_ms(avg_ms),
                        "min_duration": format_ms(min_ms),
                        "max_duration": format_ms(max_ms),
                        "call_count": int(results[4].get("count", 0)),
                        "error_rate": round(float(results[5].get("result", 0)), 2),
                        "throughput": round(float(results[6].get("result", 0)), 2)
                    }
                    slow_transactions.append(transaction_data)
                except Exception as e:
                    logger.warning(f"Skipping facet due to error: {e}")

        return {"transactions": slow_transactions}
    
    def get_top_database_operations(self, app_id: int, time_range_minutes: int = 30, limit: int = 5):
        """
        Get top database operations using New Relic Insights API with NRQL.
        """
        query = f"""
        FROM Metric 
        SELECT rate(count(apm.service.datastore.operation.duration), 1 minute) * average(apm.service.datastore.operation.duration * 1000) AS 'Total Time per Minute (ms)',
            average(apm.service.datastore.operation.duration * 1000) AS 'Avg Query Time (ms)',
            rate(count(apm.service.datastore.operation.duration), 1 minute) AS 'Throughput (ops/min)'
        WHERE appId = {app_id} 
        FACET `datastoreType`, `table`, `operation`
        SINCE {time_range_minutes} minutes ago 
        LIMIT {limit}
        """
        logger.info(f"Top database operations query: {query}")
        result = self._make_insights_request(query)

        if not result or "error" in result:
            logger.error(f"Failed to fetch top database operations: {result.get('error', 'Unknown error')}")
            return {"error": "Failed to fetch top database operations"}

        database_operations = []

        for facet in result.get("facets", []):
            try:
                name_fields = facet.get("name") or facet.get("facet")
                if not name_fields or len(name_fields) != 3:
                    logger.warning(f"Unexpected facet structure: {facet}")
                    continue

                datastore_type, table, operation = name_fields

                total_time = facet["results"][0].get("result", 0.0)
                avg_time = facet["results"][1].get("average", 0.0)
                throughput = facet["results"][2].get("result", 0.0)

                # Check if query time exceeds threshold
                query_latency = float(avg_time) > 8.0
                if query_latency:
                    logger.warning(f"Slow query detected: {operation} on table {table} with avg time {round(float(avg_time), 2)}ms")

                database_operations.append({
                    "datastoreType": datastore_type or "unknown",
                    "table": table or "unknown",
                    "operation": operation or "unknown",
                    "total_time_per_minute": round(float(total_time), 2),
                    "avg_query_time_ms": round(float(avg_time), 2),
                    "throughput_ops_per_min": round(float(throughput), 2),
                    "query_latency": query_latency
                })

            except Exception as e:
                logger.exception(f"Error parsing facet: {facet} - {e}")
                continue


        database_operations.sort(key=lambda x: x["avg_query_time_ms"], reverse=True)

        error_operations = [op for op in database_operations if op["query_latency"]]
        if error_operations:
            logger.warning(f"Found {len(error_operations)} database operations with average query time > 8ms")
        return {"database_operations": database_operations}


    def get_available_apm_metrics(self, app_id: int):
        """
        Get available APM metrics names for a specific application.
        """
        metrics_response = self.get_apm_metrics_names(app_id)
        metrics_names = [m["name"] for m in metrics_response.get("metrics", [])]
        return metrics_names

    def get_app_metric_data(self, app_id: str, metric_names: list[str]=None, metric_values: list[str]=None, time_range_minutes: int = 30):
        """
        Get formatted APM metrics data of overall application using the metrics/data.json endpoint.
        """
        metric_values = metric_values or self.DEFAULT_METRIC_VALUES
        metric_names = metric_names or self.apm_metrics_available

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=time_range_minutes)

        params = {
            "names[]": metric_names,
            "values[]": metric_values,
            "summarize": "false",
            "from": start_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            "to": end_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        }

        result = self._make_request(
            f"applications/{app_id}/metrics/data.json",
            params=params
        )

        if not result or "error" in result:
            error_msg = result.get("error", "Unknown error fetching APM metrics") if result else "Empty response fetching APM metrics"
            return {"error": f"Failed to fetch APM metrics: {error_msg}"}
            
        if "metric_data" not in result or not result["metric_data"].get("metrics"):
            formatted_metrics = {}
            for name in metric_names:
                formatted_metrics[name] = "N/A (No data)" 
            return formatted_metrics

        formatted_metrics = {}
        metrics_found = result["metric_data"]["metrics"]
        for metric in metrics_found:
            metric_name = metric["name"]
            if not metric.get("timeslices"):
                continue
                
            if metric_name not in formatted_metrics:
                formatted_metrics[metric_name] = {}
                
            for timeslice in metric["timeslices"]:
                timestamp = timeslice.get("from")
                values = timeslice.get("values", {})
                
                for value_name, value in values.items():
                    if value_name not in formatted_metrics[metric_name]:
                        formatted_metrics[metric_name][value_name] = {
                            'current_value': None,
                            'top_values': [],
                            'sum': 0,
                            'count': 0
                        }
                    
                    try:
                        float_value = float(value)
                    except (TypeError, ValueError):
                        float_value = value
                    
                    if isinstance(float_value, (int, float)):
                        formatted_metrics[metric_name][value_name]['top_values'].append({
                            'value': round(float_value, 2),
                            'timestamp': timestamp
                        })
                        
                        formatted_metrics[metric_name][value_name]['top_values'].sort(
                            key=lambda x: x['value'],
                            reverse=True
                        )
                        formatted_metrics[metric_name][value_name]['top_values'] = formatted_metrics[metric_name][value_name]['top_values'][:3]
                        
                        formatted_metrics[metric_name][value_name]['sum'] += float_value
                        formatted_metrics[metric_name][value_name]['count'] += 1
                    
                    formatted_metrics[metric_name][value_name]['current_value'] = round(float_value, 2) if isinstance(float_value, (int, float)) else float_value

        for metric_name in formatted_metrics:
            for value_name in formatted_metrics[metric_name]:
                metric_data = formatted_metrics[metric_name][value_name]
                if metric_data['count'] > 0:
                    metric_data['avg_value'] = round(metric_data['sum'] / metric_data['count'], 2)
                else:
                    metric_data['avg_value'] = None
                
                del metric_data['sum']
                del metric_data['count']

        return formatted_metrics


    def get_transaction_details(self, app_id: int, transaction_name: str, time_range_minutes: int = 30):
        """
        Get transaction details using NRQL Metric table.
        """
        
        transaction_query = f"""
        FROM Metric 
        SELECT average(convert(apm.service.transaction.duration, unit, 'ms'))  as 'Response time', rate(count(apm.service.transaction.duration), 1 minute) AS 'throughput_per_minute'
        WHERE (appId = {app_id}) 
        AND (metricTimesliceName = '{transaction_name}' OR metricTimesliceName IN (SELECT name FROM Transaction WHERE request.uri LIKE '%{transaction_name}%' LIMIT 1))
        FACET `metricTimesliceName` 
        LIMIT 5 
        SINCE {time_range_minutes} minutes ago 
        UNTIL now
        """
        logger.info(f"Transaction query: {transaction_query}")
        transaction_result = self._make_insights_request(transaction_query)
        transaction_result = transaction_result.get("facets", [])[0]
        return {
            "transaction_name": transaction_result.get("name", None),
            "response_time": transaction_result.get("results", [])[0].get("average", 0),
            "throughput_per_minute": transaction_result.get("results", [])[1].get("result", 0)
        }


@mcp.tool()
async def get_newrelic_apm_metrics(application_name: str, time_range_minutes: int = 30) -> str:
    """
    Get Overall APM metrics from New Relic for a specific application.
    application_name: name of the application to get metrics for
    metric_names: list of metric names to get data for
        default metric_names: ['HttpDispatcher']
    metric_values: list of metric values to get data for
        default metric_values: ['average_response_time', 'calls_per_minute', 'call_count']
    transaction_name: name of the transaction to get details for
    time_range_minutes: time range in minutes to get data
    """
    metric_names = ['HttpDispatcher']
    metric_values = ['average_response_time', 'calls_per_minute', 'call_count']
    try:
        newrelic_application_id = await nr_client.find_newrelic_application_id(application_name)
        metrics_data = nr_client.get_app_metric_data(newrelic_application_id, metric_names, metric_values, time_range_minutes)
        return metrics_data
    except Exception as e:
        logger.error(f"Error fetching New Relic APM metrics: {str(e)}")
        return f"Error fetching New Relic APM metrics: {str(e)}"

@mcp.tool()
async def get_application_slow_transactions_details(application_name: str, time_range_minutes: int = 30):
    """
    Get the top N slow transactions and their breakdown segments at application level. 
    """
    app_id = await nr_client.find_newrelic_application_id(application_name)
    transactions_result = nr_client.get_slow_transactions(app_id, time_range_minutes)
    if "error" in transactions_result:
        return {"error": transactions_result["error"]}
    
    transactions = transactions_result.get("transactions", [])
    logger.info(f"Found {len(transactions)} transactions")
    
    combined = []
    for txn in transactions:
        txn_name = txn["name"]
        breakdown = get_transaction_breakdown_segments(app_id, txn_name, time_range_minutes)
        
        if "error" in breakdown:
            logger.warning(f"Failed to get breakdown for transaction {txn_name}: {breakdown['error']}")
            continue
            
        combined.append({
            "transaction": {
                "name": txn_name,
                "avg_duration": txn["avg_duration"],
                "min_duration": txn["min_duration"],
                "max_duration": txn["max_duration"],
                "call_count": txn["call_count"],
                "error_rate": txn["error_rate"],
                "throughput": txn["throughput"]
            },
            "breakdown": breakdown.get("segments", []),
            "total_duration_ms": breakdown.get("total_time_ms", 0)
        })

    return {
        "transactions": combined,
        "count": len(combined)
    }           

@mcp.tool()
async def get_application_top_database_operations_details(application_name: str, time_range_minutes: int = 30):
    """
    Get the top N database operations at application level.
    
    Returns a list of top N database operations with metrics like:
    {
        "datastoreType": "MySQL",         # Type of database (MySQL, PostgreSQL, Redis etc)
        "table": "milestone_milestoneconfig", # Name of the database table
        "operation": "select",            # SQL operation type (select, insert etc)
        "total_time_per_minute": 3398.21, # Total time spent per minute in ms
        "avg_query_time_ms": 3.78,        # Average query execution time in ms
        "throughput_ops_per_min": 899.63  # Number of operations per minute
    }
    """
    app_id = await nr_client.find_newrelic_application_id(application_name)
    application_top_database_operations = nr_client.get_top_database_operations(app_id, time_range_minutes)
    if "error" in application_top_database_operations:
        return {"error": application_top_database_operations["error"]}
    return {
        "database_operations": application_top_database_operations,
        "count": len(application_top_database_operations)
    }

@mcp.tool()
async def get_transaction_breakdown_segments(application_name: str, transaction_name: str, time_range_minutes: int = 30):
    """Get breakdown segments for a specific transaction or API endpoint uri using NRQL Metric table.

    Args:
        application_name: New Relic app name
        transaction_name: The name of the Transaction or API endpoint URI (e.g. '/api/v1/users' or 'WebTransaction/Controller/Home/index')
        time_range_minutes: Analysis window (1-1440 mins) default is 30 mins    

    Returns:
        {
            'transaction_name': str,      # Transaction name
            'total_time_ms': float,       # Total time
            'total_transaction_count': int,# Transaction count
            'segments': [{                # Performance segments
                'category': str,          # DB/External/Function
                'segment': str,           # Segment name
                'avg_time_ms': float,     # Avg time
                'percentage': float       # Time %
            }]
        }
    """
    app_id = await nr_client.find_newrelic_application_id(application_name)
        # Get total transaction count and transaction name
    transaction_total_query = f"""
    FROM Transaction
    SELECT latest(name) as 'transaction_name', count(*) as 'total_count'
    WHERE appId = {app_id}
    AND (name like '%{transaction_name}%' OR request.uri LIKE '%{transaction_name}%')
    SINCE {time_range_minutes} minutes ago
    """
    
    transaction_total_result = nr_client._make_insights_request(transaction_total_query)
    if not transaction_total_result or "error" in transaction_total_result:
        logger.error(f"Failed to fetch transaction count: {transaction_total_result.get('error', 'Unknown error')}")
        return {"error": "Failed to fetch transaction count"}

    # Extract transaction name and count from results
    results = transaction_total_result.get("results", [{}])
    if not results:
        logger.warning(f"No transaction data found for {transaction_name}")
        return {"error": "No transaction data found"}

    actual_transaction_name = results[0].get("latest")
    total_txn_count = results[1].get("count", 0)
    
    if total_txn_count == 0:
        logger.warning(f"No transactions found for {transaction_name}")
        total_txn_count = 1 

    # Main query to get segment details
    transaction_breakdown_query = f"""
    FROM Metric
    SELECT 
        average(convert(apm.service.transaction.overview, unit, 'ms')) AS 'avg_time',
        count(apm.service.transaction.overview) AS 'call_count',
        sum(convert(apm.service.transaction.overview, unit, 'ms')) AS 'total_time'
    WHERE (appId = {app_id}) 
        AND (transactionName = '{actual_transaction_name}' 
        OR transactionName IN (SELECT name FROM Transaction 
                             WHERE request.uri LIKE '%{transaction_name}%' LIMIT 1))
    FACET `metricTimesliceName`
    LIMIT 7
    SINCE {time_range_minutes} minutes ago 
    UNTIL now
    """
    logger.info(f"Transaction breakdown query: {transaction_breakdown_query}")
    print(transaction_breakdown_query)

    # Get segment breakdown
    transaction_breakdown_result = nr_client._make_insights_request(transaction_breakdown_query)
    logger.info(f"Transaction breakdown result: {transaction_breakdown_result}")

    if not transaction_breakdown_result or "error" in transaction_breakdown_result:
        logger.error(f"Failed to fetch transaction breakdown: {transaction_breakdown_result.get('error', 'Unknown error')}")
        return {"error": "Failed to fetch transaction breakdown"}

    breakdown_segments = []
    total_time = 0
    logger.info(f"Processing transaction breakdown for {actual_transaction_name}")

    for facet in transaction_breakdown_result.get("facets", []):
        segment_name = facet.get("name")
        results = facet.get("results", [])
        
        if not results or not segment_name:
            continue

        avg_time = float(results[0].get("average", 0))
        call_count = float(results[1].get("count", 0))
        segment_total_time = float(results[2].get("sum", 0))
        
        category = "Function"
        if segment_name.startswith("Datastore/"):
            category = "Database"
        elif segment_name.startswith("External/"):
            category = "External"
        
        avg_calls_per_txn = round(call_count / total_txn_count, 2)
        
        breakdown_segments.append({
            "category": category,
            "segment": segment_name,
            "avg_time_ms": round(avg_time, 2),
            "avg_calls_txn": avg_calls_per_txn,
            "total_time_ms": round(segment_total_time, 2),
            "percentage": 0
        })
        
        total_time += segment_total_time

    # Calculate percentages based on total time
    for segment in breakdown_segments:
        if total_time > 0:
            segment["percentage"] = round((segment["total_time_ms"] / total_time) * 100, 2)

    # Sort segments by percentage in descending order
    breakdown_segments.sort(key=lambda x: x["percentage"], reverse=True)

    return {
        "transaction_name": actual_transaction_name,
        "total_time_ms": round(total_time, 2),
        "total_transaction_count": total_txn_count,
        "segments": breakdown_segments
    }

async def run_server():
    """Run the MCP server with configuration from command line arguments"""
    global nr_client
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Run New Relic MCP server')
    parser.add_argument('--new-relic-api-key', required=True, help='New Relic API key')
    parser.add_argument('--nr-insights-api-key', required=True, help='New Relic Insights API key')
    parser.add_argument('--new-relic-account-id', required=True, help='New Relic account ID')
    parser.add_argument('--model', required=True, help='LLM model to use')
    
    # Parse arguments
    args = parser.parse_args()

    # Initialize New Relic client
    nr_client = NewRelicClient(
        args.new_relic_api_key,
        args.nr_insights_api_key,
        args.new_relic_account_id,
        args.model
    )
    
    # Initialize New Relic data
    await nr_client.initialize_newrelic()
    
    # Run the MCP server
    mcp.run(transport="stdio")

if __name__ == "__main__":
    asyncio.run(run_server())
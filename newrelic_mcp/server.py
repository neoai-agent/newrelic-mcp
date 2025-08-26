import asyncio
import logging
from mcp.server.fastmcp import FastMCP
from newrelic_mcp.client import NewRelicClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('newrelic_mcp')

class NewRelicMCPServer:
    def __init__(self,
                api_key: str,
                insights_api_key: str,
                account_id: str,
                model: str = "gpt-4",
                openai_api_key: str = None):
        self.mcp = FastMCP("newrelic-mcp")
        self.client = NewRelicClient(
            api_key=api_key,
            insights_api_key=insights_api_key,
            account_id=account_id,
            model=model,
            openai_api_key=openai_api_key
        )
        self._register_tools()

    def _register_tools(self):
        """Register all MCP tools with the server"""
        self.mcp.tool()(self.get_newrelic_apm_metrics)
        self.mcp.tool()(self.get_application_slow_transactions_details)
        self.mcp.tool()(self.get_application_top_database_operations_details)
        self.mcp.tool()(self.get_transaction_breakdown_segments)
        self.mcp.tool()(self.query_logs)
        self.mcp.tool()(self.db_query_performance)

    def run_mcp_blocking(self):
        """
        Runs the FastMCP server. This method is blocking and should be called
        after any necessary asynchronous initialization (like self.client.initialize_newrelic)
        has been completed in a separate AnyIO event loop.
        """
        # self.client.initialize_newrelic() is assumed to have been awaited
        # before this synchronous method is called.
        
        # The FastMCP server's run method will internally call anyio.run()
        # and manage its own event loop for stdio transport.
        self.mcp.run(transport='stdio')

    async def get_newrelic_apm_metrics(self, application_name: str, time_range_minutes: int = 30) -> str:
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
            newrelic_application_id = await self.client.find_newrelic_application_id(application_name)
            metrics_data = self.client.get_app_metric_data(newrelic_application_id, metric_names, metric_values, time_range_minutes)
            return metrics_data
        except Exception as e:
            logger.error(f"Error fetching New Relic APM metrics: {str(e)}")
            return f"Error fetching New Relic APM metrics: {str(e)}"

    async def get_application_slow_transactions_details(self, application_name: str, time_range_minutes: int = 30):
        """
        Get the top N slow transactions and their breakdown segments at newrelic application level.
        """
        app_id = await self.client.find_newrelic_application_id(application_name)
        transactions_result = self.client.get_slow_transactions(app_id, time_range_minutes)
        if "error" in transactions_result:
            return {"error": transactions_result["error"]}
        
        transactions = transactions_result.get("transactions", [])
        logger.info(f"Found {len(transactions)} transactions")
        
        combined = []
        for txn in transactions:
            txn_name = txn["name"]
            breakdown = await self.get_transaction_breakdown_segments(application_name, txn_name, time_range_minutes)
            
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

    async def get_application_top_database_operations_details(self, application_name: str, time_range_minutes: int = 30):
        """
        Get the top N database operations at newrelic application level.
        """
        app_id = await self.client.find_newrelic_application_id(application_name)
        application_top_database_operations = self.client.get_top_database_operations(app_id, time_range_minutes)
        if "error" in application_top_database_operations:
            return {"error": application_top_database_operations["error"]}
        return {
            "database_operations": application_top_database_operations,
            "count": len(application_top_database_operations)
        }

    async def get_transaction_breakdown_segments(self, application_name: str, transaction_name: str, time_range_minutes: int = 30):
        """Get breakdown segments for a specific transaction or API endpoint uri using NRQL Metric table."""
        app_id = await self.client.find_newrelic_application_id(application_name)
        # Get total transaction count and transaction name
        transaction_total_query = f"""
        FROM Transaction
        SELECT latest(name) as 'transaction_name', count(*) as 'total_count'
        WHERE appId = {app_id}
        AND (name like '%{transaction_name}%' OR request.uri LIKE '%{transaction_name}%')
        SINCE {time_range_minutes} minutes ago
        """
        
        transaction_total_result = self.client._make_insights_request(transaction_total_query)
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

        # Get segment breakdown
        transaction_breakdown_result = self.client._make_insights_request(transaction_breakdown_query)
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
    
    async def query_logs(self, nrql_query: str) -> str:
        """
        Query logs using New Relic GraphQL API with NRQL query.
        Returns formatted log results as a string.
        Example:
        SELECT * FROM Metric WHERE entity.guid = 'NDI1MTazfRFQTXxBNPBVSUNBVYlPTnwzQzc0CzM3OEc' SINCE 15 minutes ago UNTIL now LIMIT 5 ORDER BY timestamp DESC
        """
        try:
            result = await self.client.query_logs(nrql_query)
            return result
        except Exception as e:
            logger.error(f"Error querying logs: {str(e)}")
            return f"Error querying logs: {str(e)}"
        
    async def db_query_performance(self, entity_guid: int, operation: str=None, table: str=None, system: str=None, time_range_minutes: int = 15):
        """
        Database query performance using New Relic GraphQL API with NRQL of a specific database operation.
        entity_guid : New Relic entity guid of the database operation
        operation : Database operation name
        table : Database table name
        system : Database system name
        time_range_minutes : Time range in minutes to get data
        Example: _select_key_value_store_keyvaluestore
        entity_guid: NDI1MTazfRFQTXxBNPBVSUNBVYlPTnwzQzc0CzM3OEc
        operation: select
        table: key_value_store_keyvaluestore
        system: MySQL
        time_range_minutes: 15
        """
        query_time_query = f"SELECT average(convert(apm.service.datastore.operation.duration, unit, 'ms')) FROM Metric WHERE (entity.guid = '{entity_guid}') AND ((`db.operation` = '{operation}' AND `db.sql.table` = '{table}' AND `db.system` = '{system}')) FACET `db.system`, `db.sql.table`, `db.operation` LIMIT 5 SINCE {time_range_minutes} minutes ago TIMESERIES UNTIL now"
        
        throughput_query = f"SELECT rate(count(apm.service.datastore.operation.duration), 1 minute) FROM Metric WHERE (entity.guid = '{entity_guid}') AND ((`db.operation` = '{operation}' AND `db.sql.table` = '{table}' AND `db.system` = '{system}')) LIMIT 5 SINCE {time_range_minutes} minutes ago TIMESERIES  facet concat(db.system, ' ', db.sql.table, ' ', db.operation) UNTIL now"

        db_ops_caller_query = f"SELECT sum(apm.service.transaction.overview) as 'Database operation callers' FROM Metric WHERE (entity.guid = '{entity_guid}') AND ((`db.operation` = '{operation}' AND `db.sql.table` = '{table}' AND `db.system` = '{system}' AND metricName = 'apm.service.transaction.overview')) FACET `transactionName` LIMIT 5 SINCE {time_range_minutes} minutes ago UNTIL now"


        query_time_result = await self.query_logs(query_time_query)
        throughput_result = await self.query_logs(throughput_query)
        db_ops_caller_result = await self.query_logs(db_ops_caller_query)
        return {
            "query_time_result": query_time_result,
            "throughput_result": throughput_result,
            "db_ops_caller_result": db_ops_caller_result
        }
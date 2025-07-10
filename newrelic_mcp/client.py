import requests
from datetime import datetime, timedelta, timezone
from litellm import acompletion
import logging
import httpx

logger = logging.getLogger(__name__)

apm_metrics_available = [
    "HttpDispatcher",
    "Apdex"
]

NR_API_BASE = "https://api.newrelic.com/v2"
NR_INSIGHTS_API_BASE = "https://insights-api.newrelic.com/v1"
NR_GRAPHQL_API_BASE = "https://api.newrelic.com/graphql"

class NewRelicClient:
    def __init__(self,
                 api_key: str,
                 insights_api_key: str,
                 account_id: str,
                 model: str,
                 openai_api_key: str = None):
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
        self.NR_GRAPHQL_API_BASE = NR_GRAPHQL_API_BASE
        self.model = model
        self.openai_api_key = openai_api_key
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
        logger.info(f"Found {len(applications)} applications")
        applications_list = [{"name": app["name"], "id": app["id"]} for app in applications if app["health_status"] != "grey"]
        return applications_list
    
    
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
        Find the application id that best matches the application name "{application_name}" from the available applications.
        The list of applications available are:
        {self._applications_available}

        Important Guidelines:
        - if the application name is exactly the same as the application name in the list, return the application id
        - if the application name is not exactly the same as the application name in the list, return the application id of the application that is the best match
        - if the application name is not in the list, return the application id of the application that is the best match

        You must return only the application id which is best match for the application name. No extra text or explanation. check the fallback list of applications. and do not return any other text. If no match is found do not return any text. 
        """
        logger.info(f"Finding application id for {application_name}")
        logger.info(f"Applications list: {self._applications_available}")
        response = await acompletion(
            api_key=self.openai_api_key,
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
    
    async def query_logs(self, nrql_query: str) -> str:
        """
        Asynchronously query logs using New Relic GraphQL API with NRQL.
        Returns formatted log results as a string.
        """
        graphql_query = f"""
        {{
            actor {{
                account(id: {self.account_id}) {{
                    nrql(query: \"{nrql_query}\") {{
                        results
                    }}
                }}
            }}
        }}
        """

        headers = self.headers
        payload = {"query": graphql_query}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.NR_GRAPHQL_API_BASE,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                result = response.json()

                logger.debug("Response JSON: %s", result)

                if "errors" in result:
                    logger.error("GraphQL errors: %s", result["errors"])
                    return f"GraphQL errors: {result['errors']}"

                data = result.get("data")
                if data is None:
                    logger.error("No 'data' field in response")
                    return "Error: No 'data' field in response"

                account = data.get("actor", {}).get("account")
                if account is None:
                    logger.error("No 'account' field in 'actor'")
                    return "Error: No 'account' field in 'actor'"

                nrql = account.get("nrql")
                if nrql is None:
                    logger.error("No 'nrql' field in 'account'")
                    return "Error: No 'nrql' field in 'account'"

                logs = nrql.get("results", [])
                formatted_logs = []
                for log in logs:
                    formatted_logs.append("---\n" + "\n".join(f"{k}: {v}" for k, v in log.items()))
                return "\n".join(formatted_logs) if formatted_logs else "No logs found"
        except Exception as e:
            logger.error("Error querying logs: %s", str(e))
            return f"Error querying logs: {str(e)}"
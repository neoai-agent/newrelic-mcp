import pytest
from unittest.mock import Mock, patch
import requests
from datetime import datetime, timezone
from newrelic_mcp.client import NewRelicClient

@pytest.fixture
def client():
    return NewRelicClient(
        api_key="test_api_key",
        insights_api_key="test_insights_key",
        account_id="123456",
        model="gpt-4"
    )

@pytest.fixture
def mock_response():
    mock = Mock()
    mock.json.return_value = {"applications": [
        {"name": "Test App 1", "id": 1},
        {"name": "Test App 2", "id": 2}
    ]}
    mock.raise_for_status = Mock()
    return mock

def test_init(client):
    assert client.headers["X-Api-Key"] == "test_api_key"
    assert client.insights_headers["X-Query-Key"] == "test_insights_key"
    assert client.account_id == "123456"
    assert client.model == "gpt-4"
    assert client._application_id_cache == {}
    assert client._applications_available == []

@patch('requests.request')
def test_make_request_success(mock_request, client, mock_response):
    mock_request.return_value = mock_response
    result = client._make_request("test_endpoint")
    assert result == mock_response.json()
    mock_request.assert_called_once()

@patch('requests.request')
def test_make_request_error(mock_request, client):
    mock_request.side_effect = requests.exceptions.RequestException("API Error")
    result = client._make_request("test_endpoint")
    assert "error" in result
    assert "API Error" in result["error"]

@patch('requests.get')
def test_make_insights_request_success(mock_get, client, mock_response):
    mock_get.return_value = mock_response
    result = client._make_insights_request("SELECT * FROM Metric")
    assert result == mock_response.json()
    mock_get.assert_called_once()

@patch('requests.get')
def test_make_insights_request_error(mock_get, client):
    mock_get.side_effect = requests.exceptions.RequestException("Insights API Error")
    result = client._make_insights_request("SELECT * FROM Metric")
    assert "error" in result
    assert "Insights API Error" in result["error"]

@patch('newrelic_mcp.client.NewRelicClient._make_request')
def test_fetch_newrelic_applications_details(mock_make_request, client):
    mock_make_request.return_value = {
        "applications": [
            {"name": "App1", "id": 1},
            {"name": "App2", "id": 2}
        ]
    }
    result = client._fetch_newrelic_applications_details()
    assert len(result) == 2
    assert result[0]["name"] == "App1"
    assert result[0]["id"] == 1

@pytest.mark.asyncio
@patch('newrelic_mcp.client.NewRelicClient._fetch_newrelic_applications_details')
async def test_initialize_newrelic(mock_fetch, client):
    mock_fetch.return_value = [{"name": "App1", "id": 1}]
    await client.initialize_newrelic()
    assert client._applications_available == [{"name": "App1", "id": 1}]

@patch('newrelic_mcp.client.NewRelicClient._make_request')
def test_get_apm_metrics_names(mock_make_request, client):
    mock_make_request.return_value = {
        "metrics": [
            {"name": "HttpDispatcher"},
            {"name": "Apdex"}
        ]
    }
    result = client.get_apm_metrics_names(1)
    assert len(result["metrics"]) == 2
    assert result["metrics"][0]["name"] == "HttpDispatcher"

@patch('newrelic_mcp.client.NewRelicClient._make_request')
def test_get_application_metric_request(mock_make_request, client):
    mock_make_request.return_value = {
        "metric_data": {
            "metrics": [
                {
                    "name": "HttpDispatcher",
                    "timeslices": [
                        {
                            "from": "2024-01-01T00:00:00Z",
                            "values": {"call_count": 100}
                        }
                    ]
                }
            ]
        }
    }
    result = client.get_application_metric_request(1, ["HttpDispatcher"])
    assert "metric_data" in result
    assert len(result["metric_data"]["metrics"]) == 1

@patch('newrelic_mcp.client.NewRelicClient._make_insights_request')
def test_get_slow_transactions(mock_insights_request, client):
    mock_insights_request.return_value = {
        "facets": [
            {
                "name": "Test Transaction",
                "results": [
                    {"sum": 1000},
                    {"result": 500},
                    {"result": 100},
                    {"result": 1000},
                    {"count": 10},
                    {"result": 5.0},
                    {"result": 2.0}
                ]
            }
        ]
    }
    result = client.get_slow_transactions(1)
    assert "transactions" in result
    assert len(result["transactions"]) == 1
    assert result["transactions"][0]["name"] == "Test Transaction"

@patch('newrelic_mcp.client.NewRelicClient._make_insights_request')
def test_get_top_database_operations(mock_insights_request, client):
    mock_insights_request.return_value = {
        "facets": [
            {
                "name": ["MySQL", "users", "SELECT"],
                "results": [
                    {"result": 1000},
                    {"average": 10.0},
                    {"result": 5.0}
                ]
            }
        ]
    }
    result = client.get_top_database_operations(1)
    assert "database_operations" in result
    assert len(result["database_operations"]) == 1
    assert result["database_operations"][0]["datastoreType"] == "MySQL"

@patch('newrelic_mcp.client.NewRelicClient._make_insights_request')
def test_get_transaction_details(mock_insights_request, client):
    mock_insights_request.return_value = {
        "facets": [
            {
                "name": "Test Transaction",
                "results": [
                    {"average": 100},
                    {"result": 5.0}
                ]
            }
        ]
    }
    result = client.get_transaction_details(1, "Test Transaction")
    assert result["transaction_name"] == "Test Transaction"
    assert result["response_time"] == 100
    assert result["throughput_per_minute"] == 5.0

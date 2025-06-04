from setuptools import setup

setup(
    name="newrelic-mcp",
    version="0.1.0",
    description="New Relic MCP Server for monitoring and metrics",
    python_requires=">=3.10",
    install_requires=[
        "mcp-server",
        "requests",
        "python-dotenv",
        "litellm",
    ],
    extras_require={
        "dev": [
            "pytest",
            "black",
            "isort",
            "mypy",
        ],
    },
    packages=["newrelic_mcp"],
)
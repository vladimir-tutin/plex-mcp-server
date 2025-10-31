"""Main entry point for the management API."""

import uvicorn


def start_dev():
    """Launched with `poetry run start-dev` at root level of the management api package. Hot reloads when changes are made to the source code"""
    uvicorn.run(
        "management_api.server:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        reload_dirs=[
            "/app/packages/management_api/management_api",
            "/app/packages/common/common",
            "/app/packages/api_contracts/api_contracts",
            "/app/packages/chat_generation_v2/chat_generation_v2",
            "/app/packages/event_director/event_director",
            "/app/packages/platform_specific_functions/platform_specific_functions",
            "/app/packages/task_management_logic/task_management_logic",
            "/app/packages/recall_sdk/recall_sdk",
        ],
        log_config="./management_api/logging_config.yml",
        loop="asyncio",
        timeout_keep_alive=315,
        timeout_graceful_shutdown=30,
    )


def start():
    """Launched with `poetry run start` at root level of the management api package"""
    uvicorn.run(
        "management_api.server:app",
        host="0.0.0.0",
        port=8080,
        log_config="./management_api/logging_config.yml",
        loop="asyncio",
        timeout_keep_alive=315,
        timeout_graceful_shutdown=30,
    )


# Handle command line invocation
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "start_dev":
            start_dev()
        elif sys.argv[1] == "start":
            start()
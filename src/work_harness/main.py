from work_harness.logging_config import setup_logging

setup_logging()

from work_harness.api.app import create_app  # noqa: E402

app = create_app()

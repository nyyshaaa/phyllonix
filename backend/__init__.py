import logging
import sys

logger = logging.getLogger("app")

def setup_logger():
    logging.basicConfig(
        level=logging.DEBUG,   # DEBUG for dev; INFO for prod
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


version1="v1"
version=version1
version_prefix=f"/api/{version}"
import os
import yaml
import logging
import tomli


# setup logging
def setup_logging(path: str = "logging.yaml") -> None:
    """Load yaml logging config

    Args:
        path (str, optional): the .yaml log file. Defaults to "logging.yaml".
    """
    os.makedirs("log", exist_ok=True)
    try:
        with open(path, "rt", encoding="utf-8") as f:
            logconfig = yaml.safe_load(f.read())
    except OSError:
        # logger not configured yet at this point
        logging.exception("Error loading of logging config: %s", path)
        raise

    logging.config.dictConfig(logconfig)


# load shared configuration
def read_app_config(path: str = "conf.toml") -> dict:
    """load app configuration

    Args:
        path (str, optional): path to .toml config. Defaults to "conf.toml".
    """
    logger = logging.getLogger(__name__)
    logger.debug("Load application configuration [%s]", path)
    try:
        with open(path, "rb") as f:
            return tomli.load(f)
    except OSError:
        logger.exception("Failed to load app config: %s", path)
        raise

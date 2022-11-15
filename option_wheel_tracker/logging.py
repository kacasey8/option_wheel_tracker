from typing import Optional


def configure_logging(log_level: str, log_path: Optional[str] = None) -> dict:
    log_config = {
        "version": 1,  # the dictConfig format version
        "disable_existing_loggers": False,  # retain the default loggers
        "formatters": {
            "standard": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
        },
        "handlers": {},
    }
    catalog_logger = {"level": log_level, "handlers": []}
    if log_path:
        # add a rotating file handler, but only if there's a log path
        file_handler = {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": f"{log_path}/option_wheel.log",
            "maxBytes": 1024 * 1024 * 10,  # 10MB,
            "backupCount": 10,
            "formatter": "standard",
        }
        log_config["handlers"]["file"] = file_handler
        catalog_logger["handlers"].append("file")
    if log_level == "DEBUG":
        # output to the console if the log level is DEBUG
        console_handler = {"class": "logging.StreamHandler", "formatter": "standard"}
        log_config["handlers"]["console"] = console_handler
        catalog_logger["handlers"].append("console")
    log_config["loggers"] = {"catalog": catalog_logger}
    return log_config

# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Validator for Gatus configuration."""

import logging

import yaml
from ops.model import ActiveStatus, BlockedStatus, ConfigData, StatusBase
from pydantic import ValidationError

from constants import (
    FAILED_TO_VALIDATE,
    INVALID_FILTER_BY_MESSAGE,
    INVALID_SORT_BY_MESSAGE,
    WEBHOOK_URL_PLACEHOLDER_RE,
)
from gatus import GatusConfig

logger = logging.getLogger(__name__)


class GatusValidator:
    """Validation functions for Gatus charm config."""

    @classmethod
    def validate(cls, config: ConfigData, endpoints: str | None = None) -> StatusBase:
        """Validate the application configuration.

        Args:
            config: The application configuration.
            endpoints: The endpoints config, if it was resolved by the charm.

        """
        if config["ui-default-sort-by"] not in ["name", "group", "health"]:
            return BlockedStatus(INVALID_SORT_BY_MESSAGE)

        if config["ui-default-filter-by"] not in ["none", "failing", "unstable"]:
            return BlockedStatus(INVALID_FILTER_BY_MESSAGE)

        msg = cls._validate_yaml(config, "announcements")
        if msg:
            return BlockedStatus(msg)

        msg = cls._validate_yaml(config, "endpoints", resolved_yaml=endpoints)
        if msg:
            return BlockedStatus(msg)

        return ActiveStatus()

    @classmethod
    def _validate_yaml(cls, config: ConfigData, config_key: str, resolved_yaml: str | None = None) -> str | None:
        """Validate the YAML configuration for announcements and endpoints.

        Args:
            config: The application configuration.
            config_key: The key of the configuration to validate.
            resolved_yaml: The resolved YAML configuration, if it was resolved by the charm.

        Returns:
            None if the configuration is valid, or a string describing the error otherwise.

        """
        config_dict = {}

        if config_key not in config:
            return None

        config_item = str(config[config_key])
        if not config_item:
            return None

        logger.info(f"Validating {config_key} config.")

        if resolved_yaml is not None:
            yaml_to_validate = resolved_yaml
        elif config_key == "endpoints" and WEBHOOK_URL_PLACEHOLDER_RE.search(config_item):
            logger.debug(
                "Skipping validation for %s: contains unresolved secret placeholders",
                config_key,
            )
            return None
        else:
            yaml_to_validate = config_item

        # First try to parse the YAML as a dictionary
        try:
            config_dict = yaml.safe_load(yaml_to_validate)
        except yaml.YAMLError as e:
            logger.error(e)
            return f"Failed to parse YAML based on {config_key}"
        except TypeError as e:
            logger.error(e)
            return f"Invalid YAML structure on {config_key}"
        except Exception as e:
            logger.error(e)
            return f"Unexpected error on {config_key}"

        # Then check if the dictionary is valid according to the model
        try:
            GatusConfig.model_validate(config_dict)
        except ValidationError as e:
            logger.error(e)
            return FAILED_TO_VALIDATE
        except Exception as e:
            logger.error(e)
            return "Unexpected error in Gatus configuration"

        return None

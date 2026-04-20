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
    OIDC_INCOMPLETE_CONFIG_MESSAGE,
    OIDC_INVALID_REDIRECT_URL_MESSAGE,
)
from gatus import GatusConfig

logger = logging.getLogger(__name__)


class GatusValidator:
    """Validation functions for Gatus charm config."""

    @classmethod
    def validate(cls, config: ConfigData) -> StatusBase:
        """Validate the application configuration."""
        logger.info("Validating config")

        if config["ui-default-sort-by"] not in ["name", "group", "health"]:
            return BlockedStatus(INVALID_SORT_BY_MESSAGE)

        if config["ui-default-filter-by"] not in ["none", "failing", "unstable"]:
            return BlockedStatus(INVALID_FILTER_BY_MESSAGE)

        oidc_issuer_url = str(config.get("oidc-issuer-url", "")).strip()
        oidc_redirect_url = str(config.get("oidc-redirect-url", "")).strip()
        oidc_credentials = str(config.get("oidc-credentials", "")).strip()
        oidc_scopes = str(config.get("oidc-scopes", "")).strip()
        oidc_allowed_subjects = str(config.get("oidc-allowed-subjects", "")).strip()

        if any([oidc_issuer_url, oidc_redirect_url, oidc_credentials, oidc_scopes, oidc_allowed_subjects]) and (
            not oidc_issuer_url or not oidc_redirect_url or not oidc_credentials
        ):
            return BlockedStatus(OIDC_INCOMPLETE_CONFIG_MESSAGE)

        if oidc_redirect_url and not oidc_redirect_url.endswith("/authorization-code/callback"):
            return BlockedStatus(OIDC_INVALID_REDIRECT_URL_MESSAGE)

        config_keys = ["announcements", "endpoints"]
        for config_key in config_keys:
            msg = cls._validate_yaml(config, config_key)
            if msg:
                return BlockedStatus(msg)

        return ActiveStatus()

    @classmethod
    def _validate_yaml(cls, config: ConfigData, config_key: str) -> str | None:
        """Validate the YAML configuration for announcements and endpoints."""
        config_dict = {}

        if config_key not in config:
            return None

        config_item = str(config[config_key])
        if not config_item:
            return None

        logger.info(f"Validating {config_key} config: {config_item}")

        # First try to parse the YAML as a dictionary
        try:
            config_dict = yaml.safe_load(config_item)
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

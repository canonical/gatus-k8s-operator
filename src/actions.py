# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Gatus charm actions."""

import logging

import ops
import paas_app_charmer.go

logger = logging.getLogger(__name__)

ANNOUNCEMENTS_FILE = "/config/announcements.yaml"


class Observer(ops.Object):
    """Charm actions observer."""

    def __init__(self, charm: paas_app_charmer.go.Charm):
        """Initialize the observer and register actions handlers.

        Args:
            charm: The parent charm to attach the observer to.

        """
        super().__init__(charm, "actions-observer")
        self.charm = charm

        charm.framework.observe(charm.on.add_announcement_action, self._add_announcement)

    def _add_announcement(self, event):
        """Add a new announcement to Gatus."""
        ann_type = event.params["type"]
        ann_msg = event.params["message"]
        ann_archived = event.params["archived"]

        command = [
            "/gatus/add_announcement.py",
            "--type",
            ann_type,
            "--message",
            ann_msg,
            "--archived",
            ann_archived,
        ]

        container = self.charm.unit.get_container("app")
        service = next(iter(container.get_services()))

        try:
            container.pebble.stop_services(services=[service])
            process = container.exec(
                command,
                service_context=service,
            )
            process.wait_output()
        except ops.pebble.ExecError as e:
            logger.error("Failed to add announcement: %s", e)
            event.fail(f"Failed to add announcement: {e}")
        finally:
            container.pebble.start_services(services=[service])

        # if not ann_type or not ann_msg:
        #     event.fail("type and message are required")
        #     return
        #
        # data = {}
        # if os.path.exists(ANNOUNCEMENTS_FILE):
        #     try:
        #         with open(ANNOUNCEMENTS_FILE, "r") as f:
        #             data = yaml.safe_load(f) or {}
        #     except Exception as e:
        #         print(f"Error reading YAML: {e}")
        #         return
        #
        # if 'announcements' not in data or data['announcements'] is None:
        #     data['announcements'] = []
        #
        # # create the new announcement
        # new_announcement = {
        #     "timestamp": datetime.now().isoformat(),
        #     "type": ann_type,
        #     "message": ann_msg,
        # }
        # data['announcements'].append(new_announcement)
        #
        # try:
        #     with open(ANNOUNCEMENTS_FILE, "w") as f:
        #         yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        #         print(f"Announcement added and maintenance performed on {ANNOUNCEMENTS_FILE}")
        # except Exception as e:
        #     print(f"Error writing to file: {e}")
        #     return

        # announcements = []
        #
        # # get existing announcements from the config
        # config = self.charm.model.config
        # if "announcements" in config:
        #     announcement_config = self.charm.model.config["announcements"]
        #     # parse the announcements config yaml
        #     if announcement_config:
        #         try:
        #             announcements = yaml.safe_load(announcement_config)
        #         except yaml.YAMLError as e:
        #             logger.error("Failed to parse announcements config: %s", e)
        #             return
        #
        #
        # # update the announcements config
        # self.charm.model.config["announcements"] = yaml.safe_dump(announcements)
        # self.charm.load_config()

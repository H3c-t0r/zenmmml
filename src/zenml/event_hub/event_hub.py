#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""Base class for all the Event Hub."""
from functools import partial
from typing import TYPE_CHECKING, List

from zenml import EventSourceResponse
from zenml.config.global_config import GlobalConfiguration
from zenml.enums import PluginType
from zenml.event_sources.base_event_source_plugin import (
    BaseEvent,
    BaseEventSourcePluginFlavor,
)
from zenml.models import TriggerFilter, TriggerResponse
from zenml.plugins.plugin_flavor_registry import logger, plugin_flavor_registry
from zenml.utils.pagination_utils import depaginate

if TYPE_CHECKING:
    from zenml.zen_stores.base_zen_store import BaseZenStore


class EventHub:
    """Handler for all events."""

    @property
    def zen_store(self) -> "BaseZenStore":
        """Returns the active zen store.

        Returns:
            The active zen store.
        """
        return GlobalConfiguration().zen_store

    def process_event(
        self,
        event: BaseEvent,
        event_source: EventSourceResponse,
    ):
        """Process an incoming event and execute all configured actions.

        This will first check for any subscribers/triggers for this event,
        then log the event for later reference and finally perform the
        configured action(s).

        Args:
            event: Generic event
            event_source: The Event Source
        """
        triggers = self.get_matching_triggers_for_event(
            event=event, event_source=event_source
        )

        # TODO: Store event for future reference
        # TODO: Create a trigger execution linked to the event and the trigger
        logger.debug(triggers)

    def get_matching_triggers_for_event(
        self, event: BaseEvent, event_source: EventSourceResponse
    ) -> List[TriggerResponse]:
        """Get all triggers that match an incoming event.

        Args:
            event: The inbound event.
            event_source: The event source which emitted the event.

        Returns:
            The list of matching triggers.
        """
        # get all event sources configured for this flavor
        triggers: List[TriggerResponse] = depaginate(
            partial(
                self.zen_store.list_triggers,
                trigger_filter_model=TriggerFilter(
                    event_source_id=event_source.id  # TODO: Handle for multiple source_ids
                ),
                hydrate=True,
            )
        )

        trigger_list: List[TriggerResponse] = []

        for trigger in triggers:
            # For now, the matching of trigger filters vs event is implemented
            # in each filter class. This is not ideal and should be refactored
            # to a more generic solution that doesn't require the plugin
            # implementation to be imported here.
            try:
                plugin_flavor = plugin_flavor_registry.get_flavor_class(
                    flavor=event_source.flavor,
                    _type=PluginType.EVENT_SOURCE,
                    subtype=event_source.plugin_subtype,
                )
            except KeyError:
                logger.exception(
                    f"Could not find plugin flavor for event source "
                    f"{event_source.id} and flavor {event_source.flavor}."
                )
                raise KeyError(
                    f"No plugin flavor found for event source "
                    f"{event_source.id}."
                )

            assert issubclass(plugin_flavor, BaseEventSourcePluginFlavor)

            # Get the filter class from the plugin flavor class
            event_filter_config_class = plugin_flavor.EVENT_FILTER_CONFIG_CLASS
            event_filter = event_filter_config_class(**trigger.event_filter)
            if event_filter.event_matches_filter(event=event):
                trigger_list.append(trigger)

        logger.debug(
            f"For event {event} and event source {event_source}, "
            f"the following triggers matched: {trigger_list}"
        )

        return trigger_list


event_hub = EventHub()

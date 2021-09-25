from typing import Any

import requests
from restapi import decorators
from restapi.connectors import celery
from restapi.exceptions import ServiceUnavailable
from restapi.rest.definition import Response
from restapi.services.authentication import Role, User
from restapi.services.uploader import Uploader
from restapi.utilities.logs import log
from seadata.endpoints import SeaDataEndpoint
from seadata.endpoints.commons.seadatacloud import EndpointsInputSchema


class Restricted(SeaDataEndpoint, Uploader):

    labels = ["restricted"]

    # Request for a file download into a restricted order
    @decorators.auth.require_any(Role.ADMIN, Role.STAFF)
    @decorators.use_kwargs(EndpointsInputSchema)
    @decorators.endpoint(
        path="/restricted/<order_id>",
        summary="Request to import a zip file into a restricted order",
        responses={200: "Request unqueued for download"},
    )
    def post(self, order_id: str, user: User, **json_input: Any) -> Response:

        try:
            imain = self.get_main_irods_connection()
            order_path = self.get_irods_order_path(imain, order_id)
            if not imain.is_collection(order_path):
                obj = self.init_endpoint()
                # Create the path and set permissions
                imain.create_collection_inheritable(order_path, obj.username)

            c = celery.get_instance()
            task = c.celery_app.send_task(
                "download_restricted_order",
                args=[order_id, order_path, json_input],
                queue="restricted",
                routing_key="restricted",
            )
            log.info("Async job: {}", task.id)
            return self.return_async_id(task.id)
        except requests.exceptions.ReadTimeout:
            raise ServiceUnavailable("B2SAFE is temporarily unavailable")

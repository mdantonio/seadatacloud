from typing import Any

import requests
from restapi import decorators
from restapi.connectors import celery
from restapi.exceptions import ServiceUnavailable
from restapi.rest.definition import Response
from restapi.services.authentication import User
from restapi.utilities.logs import log
from seadata.connectors import irods
from seadata.endpoints import (
    INGESTION_COLL,
    ORDERS_COLL,
    EndpointsInputSchema,
    SeaDataEndpoint,
)


class ListResources(SeaDataEndpoint):

    labels = ["helper"]

    @decorators.auth.require()
    @decorators.use_kwargs(EndpointsInputSchema)
    @decorators.endpoint(
        path="/resourceslist",
        summary="Request a list of existing batches and orders",
        responses={200: "Returning id of async request"},
    )
    def post(self, user: User, **json_input: Any) -> Response:

        try:
            imain = irods.get_instance()
            c = celery.get_instance()
            task = c.celery_app.send_task(
                "list_resources",
                args=[
                    self.get_irods_path(imain, INGESTION_COLL),
                    self.get_irods_path(imain, ORDERS_COLL),
                    json_input,
                ],
            )
            log.info("Async job: {}", task.id)
            return self.return_async_id(task.id)
        except requests.exceptions.ReadTimeout:  # pragma: no cover
            raise ServiceUnavailable("B2SAFE is temporarily unavailable")

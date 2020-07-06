"""
Internal endpoints.
Code to implement the /api/internal endpoint

FIXME: TO BE DEPRECATED
"""

from b2stage.apis.commons import CURRENT_MAIN_ENDPOINT
from b2stage.apis.commons.endpoint import EudatEndpoint
from flask_apispec import MethodResource, use_kwargs
from marshmallow import fields
from restapi import decorators
from restapi.confs import TESTING

# from restapi.utilities.logs import log


if TESTING:

    class MetadataEndpoint(MethodResource, EudatEndpoint):

        labels = ["helpers", "eudat"]
        _PATCH = {
            "/metadata/<path:location>": {
                "summary": "Add metadata to object",
                "responses": {"200": {"description": "Metadata added"}},
            }
        }

        @decorators.catch_errors()
        @use_kwargs({"PID": fields.Str(required=True)})
        @decorators.auth.required(roles=["normal_user"])
        def patch(self, PID, location=None):
            """
            Add metadata to an object.
            """

            if location is None:
                return self.send_errors(
                    "Location: missing filepath inside URI", code=400
                )
            location = self.fix_location(location)

            ###################
            # BASIC INIT
            r = self.init_endpoint()
            if r.errors is not None:
                return self.send_errors(errors=r.errors)
            icom = r.icommands

            path = self.parse_path(location)

            icom.set_metadata(location, PID=PID)
            out, _ = icom.get_metadata(location)

            return {
                "metadata": out,
                "location": path,
                "link": self.httpapi_location(location, api_path=CURRENT_MAIN_ENDPOINT),
            }

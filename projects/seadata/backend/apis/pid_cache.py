# -*- coding: utf-8 -*-

import os
import requests
from seadata.apis.commons.cluster import ClusterContainerEndpoint
from b2stage.apis.commons.b2access import B2accessUtilities
from restapi import decorators as decorate
from restapi.protocols.bearer import authentication
from restapi.exceptions import RestApiException
from restapi.flask_ext.flask_celery import CeleryExt
from restapi.utilities.htmlcodes import hcodes
from restapi.utilities.logs import log


class PidCache(ClusterContainerEndpoint, B2accessUtilities):

    # schema_expose = True
    labels = ['helper']
    depends_on = ['SEADATA_PROJECT']
    GET = {
        '/pidcache': {
            'summary': 'Retrieve values from the PID cache',
            'responses': {'200': {'description': 'Async job started'}},
        }
    }
    POST = {
        '/pidcache/<batch_id>': {
            'summary': 'Fill the PID cache',
            'responses': {'200': {'description': 'Async job started'}},
        }
    }

    @decorate.catch_error()
    @authentication.required(roles=['admin_root', 'staff_user'], required_roles='any')
    def get(self):

        task = CeleryExt.inspect_pids_cache.apply_async()
        log.info("Async job: {}", task.id)
        return self.return_async_id(task.id)

    @decorate.catch_error()
    @authentication.required(roles=['admin_root', 'staff_user'], required_roles='any')
    def post(self, batch_id):

        # imain = self.get_service_instance(service_name='irods')
        try:
            imain = self.get_main_irods_connection()
            ipath = self.get_irods_production_path(imain)

            collection = os.path.join(ipath, batch_id)
            if not imain.exists(collection):
                raise RestApiException(
                    "Invalid batch id {}".format(batch_id), status_code=hcodes.HTTP_BAD_NOTFOUND
                )

            task = CeleryExt.cache_batch_pids.apply_async(args=[collection])
            log.info("Async job: {}", task.id)

            return self.return_async_id(task.id)
        except requests.exceptions.ReadTimeout:
            return self.send_errors(
                "B2SAFE is temporarily unavailable",
                code=hcodes.HTTP_SERVICE_UNAVAILABLE
            )

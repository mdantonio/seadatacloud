import os

import requests
from b2stage.apis.commons.b2access import B2accessUtilities
from restapi import decorators
from restapi.exceptions import RestApiException
from restapi.utilities.logs import log
from seadata.apis.commons.cluster import ClusterContainerEndpoint


class PidCache(ClusterContainerEndpoint, B2accessUtilities):

    labels = ["helper"]
    _GET = {
        "/pidcache": {
            "summary": "Retrieve values from the PID cache",
            "responses": {"200": {"description": "Async job started"}},
        }
    }
    _POST = {
        "/pidcache/<batch_id>": {
            "summary": "Fill the PID cache",
            "responses": {"200": {"description": "Async job started"}},
        }
    }

    @decorators.auth.require_any("admin_root", "staff_user")
    def get(self):

        celery = self.get_service_instance("celery")
        task = celery.inspect_pids_cache.apply_async()
        log.info("Async job: {}", task.id)
        return self.return_async_id(task.id)

    @decorators.auth.require_any("admin_root", "staff_user")
    def post(self, batch_id):

        # imain = self.get_service_instance(service_name='irods')
        try:
            imain = self.get_main_irods_connection()
            ipath = self.get_irods_production_path(imain)

            collection = os.path.join(ipath, batch_id)
            if not imain.exists(collection):
                raise RestApiException(f"Invalid batch id {batch_id}", status_code=404)

            celery = self.get_service_instance("celery")
            task = celery.cache_batch_pids.apply_async(args=[collection])
            log.info("Async job: {}", task.id)

            return self.return_async_id(task.id)
        except requests.exceptions.ReadTimeout:
            return self.send_errors("B2SAFE is temporarily unavailable", code=503)

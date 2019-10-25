# -*- coding: utf-8 -*-

"""
B2SAFE HTTP REST API endpoints.
Code to implement the extended endpoints.

Note:
Endpoints list and behaviour are available at:
https://github.com/EUDAT-B2STAGE/http-api/blob/master/docs/user/endpoints.md

"""

from restapi.flask_ext.flask_irods.client import IrodsException
from restapi.exceptions import RestApiException
from restapi import decorators as decorate
from restapi.protocols.bearer import authentication
from restapi.services.uploader import Uploader
from restapi.services.download import Downloader

from b2stage.apis.commons.b2handle import B2HandleEndpoint
from b2stage.apis.commons import CURRENT_HTTPAPI_SERVER, CURRENT_MAIN_ENDPOINT
from b2stage.apis.commons import PUBLIC_ENDPOINT

from utilities import htmlcodes as hcodes
from utilities.logs import get_logger

log = get_logger(__name__)


class PIDEndpoint(Uploader, Downloader, B2HandleEndpoint):
    """ Handling PID on endpoint requests """

    labels = ['eudat', 'pids']
    GET = {
        '/pids/<path:pid>': {
            'summary': 'Resolve the input PID and retrieve a digital object information or download it or list a collection',
            'custom': {},
            'parameters': [
                {
                    'name': 'download',
                    'description': 'Activate file downloading (if PID points to a single file)',
                    'in': 'query',
                    'type': 'boolean',
                }
            ],
            'responses': {
                '200': {
                    'description': 'The information related to the file which the PID points to or the file content if download is activated or the list of objects if the PID points to a collection'
                }
            },
        }
    }
    HEAD = {
        '/pids/<path:pid>': {
            'summary': 'Resolve the input PID and verify permission of the digital object',
            'custom': {},
            'parameters': [
                {
                    'name': 'download',
                    'description': 'Verify if the user is allowed to download the digital object',
                    'in': 'query',
                    'type': 'boolean',
                }
            ],
            'responses': {
                '200': {
                    'description': 'The PID can be resolved and the digital object can be downloaded (if download parameter is provided)'
                }
            },
        }
    }

    def eudat_pid(self, pid, head=False):

        # recover metadata from pid
        metadata, bad_response = self.get_pid_metadata(pid, head_method=head)
        if bad_response is not None:
            return bad_response
        url = metadata.get('URL')
        if url is None:
            return self.send_errors(
                message='B2HANDLE: empty URL_value returned',
                code=hcodes.HTTP_BAD_NOTFOUND,
                head_method=head,
            )

        if not self.download_parameter():
            if head:
                return self.force_response("", code=hcodes.HTTP_OK_BASIC)
            return metadata
        # download is requested, trigger file download

        rroute = '%s%s/' % (CURRENT_HTTPAPI_SERVER, CURRENT_MAIN_ENDPOINT)
        proute = '%s%s/' % (CURRENT_HTTPAPI_SERVER, PUBLIC_ENDPOINT)
        # route = route.replace('http://', '')

        url = url.replace('https://', '')
        url = url.replace('http://', '')

        # If local HTTP-API perform a direct download
        if url.startswith(rroute):
            url = url.replace(rroute, '/')
        elif url.startswith(proute):
            url = url.replace(proute, '/')
        else:
            # Otherwise, perform a request to an external service?
            return self.send_warnings(
                {'URL': url},
                errors=[
                    "Data-object can't be downloaded by current "
                    + "HTTP-API server '%s'" % CURRENT_HTTPAPI_SERVER
                ],
                head_method=head,
            )
        r = self.init_endpoint()
        if r.errors is not None:
            return self.send_errors(errors=r.errors, head_method=head)

        return self.download_object(r, url, head=head)

    @decorate.catch_error(exception=IrodsException, exception_label='B2SAFE')
    @authentication.required(roles=['normal_user'])
    def get(self, pid):
        """ Get metadata or file from pid """

        try:
            from seadata.apis.commons.seadatacloud import seadata_pid

            return seadata_pid(self, pid)
        except ImportError:
            return self.eudat_pid(pid, head=False)

    @decorate.catch_error(exception=IrodsException, exception_label='B2SAFE')
    @authentication.required(roles=['normal_user'])
    def head(self, pid):
        """ Get metadata or file from pid """

        return self.eudat_pid(pid, head=True)

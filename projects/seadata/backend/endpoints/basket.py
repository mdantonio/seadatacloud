"""
Orders from production data to be temporary downloadable with a zip file

# order a zip @async
POST /api/order/<OID>
    pids=[PID1, PID2, ...]

# creates the iticket/link to download
PUT /api/order/<OID> -> return iticket_code

# download the file
GET /api/order/<OID>?code=<iticket_code>

# remove the zip and the ticket
DELETE /api/order/<OID>

"""

#################
# IMPORTS
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from irods.exception import NetworkException
from restapi import decorators
from restapi.config import get_backend_url
from restapi.connectors import celery
from restapi.exceptions import BadRequest, NotFound, ServiceUnavailable
from restapi.rest.definition import Response
from restapi.services.authentication import User
from restapi.utilities.logs import log
from seadata.connectors import irods
from seadata.connectors.rabbit_queue import log_into_queue, prepare_message
from seadata.endpoints import (
    MOUNTPOINT,
    ORDERS_COLL,
    ORDERS_DIR,
    EndpointsInputSchema,
    SeaDataEndpoint,
)

TMPDIR = "/tmp"


def get_order_zip_file_name(
    order_id: str, restricted: bool = False, index: Optional[int] = None
) -> str:

    label = "restricted" if restricted else "unrestricted"
    if index is None:
        zip_file_name = f"order_{order_id}_{label}.zip"
    else:
        zip_file_name = f"order_{order_id}_{label}{index}.zip"

    return zip_file_name


#################
# REST CLASSES
class DownloadBasketEndpoint(SeaDataEndpoint):

    labels = ["order"]

    def get_filename_from_type(self, order_id: str, ftype: str) -> Optional[str]:
        if len(ftype) < 2:
            return None

        if ftype[0] == "0":
            restricted = False
        elif ftype[0] == "1":
            restricted = True
        else:
            log.warning("Unexpected flag in ftype {}", ftype)
            return None
        try:
            index = int(ftype[1:])
        except ValueError:
            log.warning("Unable to extract numeric index from ftype {}", ftype)

        if index == 0:
            return get_order_zip_file_name(order_id, restricted=restricted, index=None)

        return get_order_zip_file_name(order_id, restricted=restricted, index=index)

    @decorators.endpoint(
        path="/orders/<order_id>/download/<ftype>/c/<code>",
        summary="Download an order",
        responses={
            200: "The order with all files compressed",
            404: "Order does not exist",
        },
    )
    def get(self, order_id: str, ftype: str, code: str) -> Response:
        """downloading (not authenticated)"""
        log.info("Order request: {} (code '{}')", order_id, code)
        json = {"order_id": order_id, "code": code}
        msg = prepare_message(self, json=json, user="anonymous", log_string="start")
        log_into_queue(self, msg)

        # log.info("DOWNLOAD DEBUG 1: {} (code '{}')", order_id, code)

        try:
            imain = irods.get_instance()
            order_path = self.get_irods_path(imain, ORDERS_COLL, order_id)

            zip_file_name = self.get_filename_from_type(order_id, ftype)

            if zip_file_name is None:
                raise BadRequest(f"Invalid file type {ftype}")

            zip_ipath = Path(order_path, zip_file_name)

            error = f"Order '{order_id}' not found (or no permissions)"

            log.debug("Checking zip irods path: {}", zip_ipath)
            if not imain.is_dataobject(zip_ipath):
                log.error("File not found {}", zip_ipath)
                raise NotFound(error)

            # TOFIX: we should use a database or cache to save this,
            # not irods metadata (known for low performances)
            metadata = imain.get_metadata(zip_ipath)
            iticket_code = metadata.get("iticket_code")

            encoded_code = urllib.parse.quote_plus(code)

            if iticket_code != encoded_code:
                log.error("iticket code does not match {}", zip_ipath)
                raise NotFound(error)

            # NOTE: very important!
            # use anonymous to get the session here
            # because the ticket supply breaks the iuser session permissions
            icom = irods.get_instance(
                user="anonymous",
                password="null",
                authscheme="credentials",
            )
            icom.ticket_supply(code)

            if not icom.test_ticket(zip_ipath):
                log.error("Invalid iticket code {}", zip_ipath)
                raise NotFound("Invalid download code")

            # tickets = imain.list_tickets()
            # print(tickets)

            # iticket mod "$TICKET" add user anonymous
            # iticket mod "$TICKET" uses 1
            # iticket mod "$TICKET" expire "2018-03-23.06:50:00"

            headers = {
                "Content-Transfer-Encoding": "binary",
                "Content-Disposition": f"attachment; filename={zip_file_name}",
            }
            msg = prepare_message(self, json=json, log_string="end", status="sent")
            log_into_queue(self, msg)
            return icom.stream_ticket(zip_ipath, headers=headers)
        except requests.exceptions.ReadTimeout:  # pragma: no cover
            raise ServiceUnavailable("B2SAFE is temporarily unavailable")


class BasketEndpoint(SeaDataEndpoint):

    labels = ["order"]

    @decorators.auth.require()
    @decorators.endpoint(
        path="/orders/<order_id>",
        summary="List orders",
        responses={200: "The list of zip files available"},
    )
    def get(self, order_id: str, user: User) -> Response:
        """listing, not downloading"""

        log.debug("GET request on orders")
        msg = prepare_message(self, json=None, log_string="start")
        log_into_queue(self, msg)

        try:
            imain = irods.get_instance()
            order_path = self.get_irods_path(imain, ORDERS_COLL, order_id)
            log.debug("Order path: {}", order_path)
            if not imain.is_collection(order_path):
                raise NotFound(f"Order '{order_id}': not existing")

            ##################
            ils = imain.list(order_path, detailed=True)

            u = get_order_zip_file_name(order_id, restricted=False, index=1)
            # if a splitted unrestricted zip exists, skip the unsplitted file
            if u in ils:
                u = get_order_zip_file_name(order_id, restricted=False, index=None)
                ils.pop(u, None)

            r = get_order_zip_file_name(order_id, restricted=True, index=1)
            # if a splitted restricted zip exists, skip the unsplitted file
            if r in ils:
                r = get_order_zip_file_name(order_id, restricted=True, index=None)
                ils.pop(r, None)

            response = []

            for _, data in ils.items():
                name = data.get("name")

                if not name:  # pragma: no cover
                    continue

                if name.endswith(".bak"):
                    continue

                path = data.get("path")
                if not path:  # pragma: no cover
                    log.warning("Wrong entry, missing path: {}", data)
                    continue
                else:
                    ipath = Path(path, name)
                    metadata = imain.get_metadata(ipath)
                    data["URL"] = metadata.get("download")
                    response.append(data)

            msg = prepare_message(self, log_string="end", status="completed")
            log_into_queue(self, msg)
            return self.response(response)
        except requests.exceptions.ReadTimeout:  # pragma: no cover
            raise ServiceUnavailable("B2SAFE is temporarily unavailable")

    @decorators.auth.require()
    @decorators.use_kwargs(EndpointsInputSchema)
    @decorators.endpoint(
        path="/orders",
        summary="Request one order preparation",
        responses={200: "Asynchronous request launched"},
    )
    def post(self, user: User, **json_input: Any) -> Response:

        log.debug("POST request on orders")
        msg = prepare_message(self, json=json_input, log_string="start")
        log_into_queue(self, msg)

        params = json_input.get("parameters", {})
        if len(params) < 1:
            raise BadRequest("missing parameters")

        key = "order_number"
        order_id = params.get(key)
        if order_id is None:
            raise BadRequest(f"Order ID '{key}': missing")
        order_id = str(order_id)

        # ##################
        # Get filename from json input. But it has to follow a
        # specific pattern, so we ignore client input if it does not...
        filename = f"order_{order_id}_unrestricted"
        key = "file_name"
        if key in params and not params[key] == filename:
            log.warning(
                "Client provided wrong filename ({}), will use: {}",
                params[key],
                filename,
            )
        params[key] = filename

        ##################
        # PIDS: can be empty if restricted
        key = "pids"
        pids = params.get(key, [])

        ##################
        # Create the path
        log.info("Order request: {}", order_id)
        try:
            imain = irods.get_instance()
            order_path = self.get_irods_path(imain, ORDERS_COLL, order_id)
            log.debug("Order path: {}", order_path)
            if not imain.is_collection(order_path):
                # Create the path and set permissions
                imain.create_collection_inheritable(order_path, user.email)

            ##################
            # Does the zip already exists?
            zip_file_name = filename + ".zip"
            zip_ipath = str(Path(order_path, zip_file_name))
            if imain.is_dataobject(zip_ipath):
                # give error here
                # return {order_id: 'already exists'}
                # json_input['status'] = 'exists'
                json_input["parameters"] = {"status": "exists"}
                return self.response(json_input)

            ################
            # ASYNC
            if len(pids) > 0:
                log.info("Submit async celery task")
                c = celery.get_instance()
                task = c.celery_app.send_task(
                    "unrestricted_order",
                    args=[order_id, order_path, zip_file_name, json_input],
                )
                log.info("Async job: {}", task.id)
                return self.return_async_id(task.id)

            return self.response({"status": "enabled"})
        except requests.exceptions.ReadTimeout:  # pragma: no cover
            raise ServiceUnavailable("B2SAFE is temporarily unavailable")

    def no_slash_ticket(self, imain: irods.IrodsPythonExt, path: str) -> str:
        """irods ticket for HTTP"""
        # TODO: prc list tickets so we can avoid more than once
        # TODO: investigate iticket expiration
        # iticket mod Ticket_string-or-id uses/expire string-or-none

        unwanted = ["/", "%"]
        # Initialize the ticket with an unwanted characters to enter the first loop
        ticket = unwanted[0]
        # Create an iticket that does not contains any of the unwanted characters
        while any(c in ticket for c in unwanted):
            obj = imain.ticket(path)
            ticket = obj.ticket
        encoded = urllib.parse.quote_plus(ticket)
        log.info("Ticket: {} -> {}", ticket, encoded)
        return encoded

    def get_download(
        self,
        imain: irods.IrodsPythonExt,
        order_id: str,
        order_path: str,
        files: Dict[str, Dict[str, Any]],
        restricted: bool = False,
        index: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:

        zip_file_name = get_order_zip_file_name(order_id, restricted, index)

        if zip_file_name not in files:
            return None

        zip_ipath = str(Path(order_path, zip_file_name))
        log.debug("Zip irods path: {}", zip_ipath)

        code = self.no_slash_ticket(imain, zip_ipath)
        ftype = ""
        if restricted:
            ftype += "1"
        else:
            ftype += "0"
        if index is None:
            ftype += "0"
        else:
            ftype += str(index)

        host = get_backend_url()

        # too many work for THEM to skip the add of the protocol
        # they prefer to get back an incomplete url
        host = host.replace("https://", "").replace("http://", "")

        url = f"{host}/api/orders/{order_id}/download/{ftype}/c/{code}"

        # If metadata already exists, remove them:
        # FIXME: verify if iticket_code is set and then invalidate it
        imain.remove_metadata(zip_ipath, "iticket_code")
        imain.remove_metadata(zip_ipath, "download")
        ##################
        # Set the url as Metadata in the irods file
        imain.set_metadata(zip_ipath, download=url)

        # TOFIX: we should add a database or cache to save this,
        # not irods metadata (known for low performances)
        imain.set_metadata(zip_ipath, iticket_code=code)

        info = files[zip_file_name]

        return {
            "name": zip_file_name,
            "url": url,
            "size": info.get("content_length", 0),
        }

    @decorators.auth.require()
    @decorators.endpoint(
        path="/orders/<order_id>",
        summary="Request a link to download an order (if already prepared)",
        responses={200: "The link to download the order (expires in 2 days)"},
    )
    def put(self, order_id: str, user: User) -> Response:

        log.info("Order request: {}", order_id)
        msg = prepare_message(self, json={"order_id": order_id}, log_string="start")
        log_into_queue(self, msg)

        try:
            imain = irods.get_instance()
            try:
                order_path = self.get_irods_path(imain, ORDERS_COLL, order_id)
                log.debug("Order path: {}", order_path)
            except BaseException:
                raise NotFound("Order not found")

            response = []

            files_in_irods = imain.list(order_path, detailed=True)

            # Going through all possible file names of zip files

            # unrestricted zip
            # info = self.get_download(
            #     imain, order_id, order_path, files_in_irods,
            #     restricted=False, index=None)
            # if info is not None:
            #     response.append(info)

            # checking for splitted unrestricted zip
            info = self.get_download(
                imain, order_id, order_path, files_in_irods, restricted=False, index=1
            )

            # No split zip found, looking for the single unrestricted zip
            if info is None:
                info = self.get_download(
                    imain,
                    order_id,
                    order_path,
                    files_in_irods,
                    restricted=False,
                    index=None,
                )
                if info is not None:
                    response.append(info)
            # When found one split, looking for more:
            else:
                response.append(info)
                for index in range(2, 100):
                    info = self.get_download(
                        imain,
                        order_id,
                        order_path,
                        files_in_irods,
                        restricted=False,
                        index=index,
                    )
                    if info is not None:
                        response.append(info)

            # checking for splitted restricted zip
            info = self.get_download(
                imain, order_id, order_path, files_in_irods, restricted=True, index=1
            )

            # No split zip found, looking for the single restricted zip
            if info is None:
                info = self.get_download(
                    imain,
                    order_id,
                    order_path,
                    files_in_irods,
                    restricted=True,
                    index=None,
                )
                if info is not None:
                    response.append(info)
            # When found one split, looking for more:
            else:
                response.append(info)
                for index in range(2, 100):
                    info = self.get_download(
                        imain,
                        order_id,
                        order_path,
                        files_in_irods,
                        restricted=True,
                        index=index,
                    )
                    if info is not None:
                        response.append(info)

            if len(response) == 0:
                raise NotFound(f"Order '{order_id}' not found (or no permissions)")

            msg = prepare_message(self, log_string="end", status="enabled")
            log_into_queue(self, msg)

            return self.response(response)
        except requests.exceptions.ReadTimeout:  # pragma: no cover
            raise ServiceUnavailable("B2SAFE is temporarily unavailable")
        except NetworkException as e:  # pragma: no cover
            log.error(e)
            raise ServiceUnavailable("Could not connect to B2SAFE host")

    @decorators.auth.require()
    @decorators.use_kwargs(EndpointsInputSchema)
    @decorators.endpoint(
        path="/orders",
        summary="Remove one or more orders",
        responses={200: "Async job submitted for orders removal"},
    )
    def delete(self, user: User, **json_input: Any) -> Response:

        try:
            imain = irods.get_instance()
            order_path = self.get_irods_path(imain, ORDERS_COLL)
            local_order_path = MOUNTPOINT.joinpath(ORDERS_DIR)
            log.debug("Order collection: {}", order_path)
            log.debug("Order path: {}", local_order_path)

            c = celery.get_instance()
            task = c.celery_app.send_task(
                "delete_orders", args=[order_path, str(local_order_path), json_input]
            )
            log.info("Async job: {}", task.id)
            return self.return_async_id(task.id)
        except requests.exceptions.ReadTimeout:  # pragma: no cover
            raise ServiceUnavailable("B2SAFE is temporarily unavailable")

"""
B2HANDLE utilities
"""

import os

try:
    from b2handle import handleexceptions
    from b2handle.clientcredentials import PIDClientCredentials as credentials
    from b2handle.handleclient import EUDATHandleClient as b2handle
except BaseException:
    b2handle, credentials, handleexceptions = [None] * 3
from b2stage.endpoints.commons import path
from restapi.utilities.logs import log


class PIDgenerator:
    """
    Handling PID requests.
    It includes some methods to connect to B2HANDLE.

    FIXME: it should become a dedicated service in rapydo.
    This way the client could be registered in memory with credentials
    only if the provided credentials are working.
    It should be read only access otherwise.
    """

    pid_separator = "/"

    eudat_pid_fields = [
        "URL",
        "EUDAT/CHECKSUM",
        "EUDAT/UNPUBLISHED",
        "EUDAT/UNPUBLISHED_DATE",
        "EUDAT/UNPUBLISHED_REASON",
    ]

    eudat_internal_fields = ["EUDAT/FIXED_CONTENT", "PID"]

    def pid_name_fix(self, irule_output):
        pieces = irule_output.split(self.pid_separator)
        pid = self.pid_separator.join([pieces[0], pieces[1].lower()])
        log.debug("Parsed PID: {}", pid)
        return pid

    def pid_request(self, icom, ipath):
        """EUDAT RULE for PID"""

        outvar = "newPID"
        inputs = {
            "*path": f'"{ipath}"',
            "*fixed": '"true"',
            # empty variables
            "*parent_pid": '""',
            "*ror": '""',
            "*fio": '""',
        }
        body = """
            EUDATCreatePID(*parent_pid, *path, *ror, *fio, *fixed, *{});
            writeLine("stdout", *{});
        """.format(
            outvar,
            outvar,
        )

        rule_output = icom.rule("get_pid", body, inputs, output=True)
        return self.pid_name_fix(rule_output)

    def parse_pid_dataobject_path(self, metadata, key="URL"):
        """Parse url / irods path"""

        url = metadata.get(key)
        if url is None:
            return url

        # NOTE: this would only work until the protocol is unchanged
        url = url.replace("irods://", "")

        # path_pieces = url.split(path.os.sep)[1:]
        path_pieces = url.split(path.os.sep)
        path_pieces[0] = path.os.sep

        # TEMPORARY FIX, waiting to decide final PID structure
        try:
            if path_pieces[3] == "api" and path_pieces[4] == "registered":
                path_pieces[0] = "/"
                path_pieces[1] = "/"
                path_pieces[2] = "/"
                path_pieces[3] = "/"
                path_pieces[4] = "/"

        except BaseException:
            log.error("Error parsing URL, not enough tokens? {}", path_pieces)

        # print("pieces", path_pieces)
        ipath = str(path.build(path_pieces))
        log.debug("Data object: {}", ipath)

        return ipath

    def connect_client(self, force_no_credentials=False, disable_logs=False):

        if disable_logs:
            import logging

            logging.getLogger("b2handle").setLevel(logging.WARNING)

        # With credentials
        if force_no_credentials:
            handle_client = b2handle.instantiate_for_read_access()
            log.debug("HANDLE client connected [w/out credentials]")
        else:
            found = False
            file = os.getenv("HANDLE_CREDENTIALS", None)
            if file is not None:

                credentials_path = path.build(file)
                found = path.file_exists_and_nonzero(credentials_path)
                if not found:
                    log.warning("B2HANDLE credentials file not found {}", file)

            if found:
                handle_client = b2handle.instantiate_with_credentials(
                    credentials.load_from_JSON(file)
                )
                log.debug("HANDLE client connected [w/ credentials]")
                return handle_client, True

        return handle_client, False

    def check_pid_content(self, pid):
        # from b2handle.handleclient import EUDATHandleClient as b2handle
        # client = b2handle.instantiate_for_read_access()
        client, authenticated = self.connect_client(
            force_no_credentials=True, disable_logs=True
        )
        return client.retrieve_handle_record(pid)

from pathlib import Path
from shutil import rmtree
from typing import Any, Dict, List

from glom import glom
from restapi.connectors.celery import CeleryExt, Task
from restapi.utilities.logs import log
from restapi.utilities.processes import start_timeout, stop_timeout
from seadata.connectors import irods
from seadata.endpoints import ErrorCodes
from seadata.tasks.seadata import ext_api, notify_error

TIMEOUT = 1800


@CeleryExt.task(idempotent=False)
def delete_orders(
    self: Task[[str, str, Dict[str, Any]], str],
    orders_path: str,
    local_orders_path: str,
    myjson: Dict[str, Any],
) -> str:

    if "parameters" not in myjson:
        myjson["parameters"] = {}
        # TODO Raise error already here!
        # Or even before reaching asynchronous job..

    backdoor = glom(myjson, "parameters.backdoor", default=False)

    if "request_id" not in myjson:
        return notify_error(ErrorCodes.MISSING_REQUEST_ID, myjson, backdoor, self)

    myjson["parameters"]["request_id"] = myjson["request_id"]
    myjson["request_id"] = self.request.id
    # TODO Why? We end up with two different request_ids,
    # one from the client, one from our system.

    # params = myjson.get('parameters', {})

    orders = myjson["parameters"].pop("orders", None)
    if orders is None:
        return notify_error(ErrorCodes.MISSING_ORDERS_PARAMETER, myjson, backdoor, self)
    total = len(orders)

    if total == 0:
        return notify_error(ErrorCodes.EMPTY_ORDERS_PARAMETER, myjson, backdoor, self)

    try:
        with irods.get_instance() as imain:

            errors: List[Dict[str, str]] = []
            counter = 0
            for order in orders:

                counter += 1
                self.update_state(
                    state="PROGRESS",
                    meta={"total": total, "step": counter, "errors": len(errors)},
                )

                order_path = Path(orders_path, order)
                local_order_path = Path(local_orders_path, order)
                log.info("Delete request for order collection: {}", order_path)
                log.info("Delete request for order path: {}", local_order_path)

                try:
                    start_timeout(TIMEOUT)
                    if not imain.is_collection(order_path):
                        errors.append(
                            {
                                "error": ErrorCodes.ORDER_NOT_FOUND[0],
                                "description": ErrorCodes.ORDER_NOT_FOUND[1],
                                "subject": order,
                            }
                        )

                        self.update_state(
                            state="PROGRESS",
                            meta={
                                "total": total,
                                "step": counter,
                                "errors": len(errors),
                            },
                        )
                        stop_timeout()
                        continue

                    ##################
                    # TODO: remove the iticket?

                    # TODO: I should also revoke the task?

                    imain.remove(order_path, recursive=True)
                    stop_timeout()
                except BaseException as e:
                    log.error(e)
                    errors.append(
                        {
                            "error": ErrorCodes.UNEXPECTED_ERROR[0],
                            "description": ErrorCodes.UNEXPECTED_ERROR[1],
                            "subject": order,
                        }
                    )
                    self.update_state(
                        state="PROGRESS",
                        meta={"total": total, "step": counter, "errors": len(errors)},
                    )
                    continue

                if local_order_path.is_dir():
                    rmtree(local_order_path, ignore_errors=True)

            if len(errors) > 0:
                myjson["errors"] = errors
            ret = ext_api.post(myjson, backdoor=backdoor)
            log.info("CDI IM CALL = {}", ret)
            return "COMPLETED"
    except BaseException as e:
        log.error(e)
        log.error(type(e))
        return notify_error(ErrorCodes.UNEXPECTED_ERROR, myjson, backdoor, self)

    return "ok"

import asyncio
import contextlib
import io
import json
import subprocess
from http import HTTPStatus as status
from pathlib import Path
from typing import Awaitable, ContextManager, Literal, Tuple

import numpy as np
import pyarrow as pa
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, HttpRequest, HttpResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.cache import add_never_cache_headers, patch_response_headers
from django.views.decorators.http import require_GET

from cjwkernel.types import ColumnType
from cjworkbench.middleware.clickjacking import xframe_options_exempt
from cjworkbench.sync import database_sync_to_async
from cjwstate import rabbitmq
from cjwstate.rendercache import (
    CorruptCacheError,
    downloaded_parquet_file,
    open_cached_render_result,
    read_cached_render_result_slice_as_text,
)
from cjwstate.models import Tab, Step, Workflow
from cjwstate.models.module_registry import MODULE_REGISTRY


_MaxNRowsPerRequest = 300


def _with_unlocked_step_for_read(fn):
    """Decorate: `fn(request, workflow_id, step_slug, ...)` becomes `fn(request, step, ...)`

    The inner function will raise Http404 if the step is not found in the database,
    or PermissionDenied if the person requesting does not have read access.
    """

    def inner(request: HttpRequest, workflow_id: int, step_slug: str, *args, **kwargs):
        try:
            with Workflow.authorized_lookup_and_cooperative_lock(
                "read", request.user, request.session, pk=workflow_id
            ) as workflow_lock:
                step = Step.live_in_workflow(workflow_lock.workflow.id).get(
                    slug=step_slug
                )
        except Workflow.DoesNotExist as err:
            if err.args[0].endswith("access denied"):
                raise PermissionDenied()
            else:
                raise Http404("workflow not found or not authorized")
        except Step.DoesNotExist:
            raise Http404("step not found")

        return fn(request, step, *args, **kwargs)

    return inner


@database_sync_to_async
def _load_step_by_id_oops_where_is_workflow(
    request: HttpRequest, step_id: int
) -> Tuple[Workflow, Tab, Step]:
    """Load Step from database, or raise Http404 or PermissionDenied.

    `step.tab` and `step.workflow` will be loaded from the database. The Step,
    Tab and Workflow data will all be consistent.

    Don't use this in new code. Put workflow ID in the URL instead.
    """
    # TODO simplify this a ton by putting `workflow` in the URL. That way,
    # we can lock it _before_ we query it, so we won't have to check any of
    # the zillions of races herein.
    step = get_object_or_404(Step, id=step_id, is_deleted=False)

    try:
        workflow = step.tab.workflow  # raise Tab.DoesNotExist, Workflow.DoesNotExist
        if workflow is None:
            raise Workflow.DoesNotExist  # race: workflow is gone

        # raise Workflow.DoesNotExist
        # also, implies workflow.refresh_from_db()
        with workflow.cooperative_lock() as workflow_lock:
            if not workflow_lock.workflow.request_authorized_read(request):
                raise PermissionDenied()

            step.refresh_from_db()  # raise Step.DoesNotExist
            if step.is_deleted:
                raise Step.DoesNotExist
            step.tab.refresh_from_db()
            if step.tab.is_deleted:
                raise Tab.DoesNotExist

            return step.tab.workflow, step.tab, step
    except (Workflow.DoesNotExist, Tab.DoesNotExist, Step.DoesNotExist):
        raise Http404()  # race: tab/step was deleted


def _with_step_for_read_by_id(fn):
    """Decorate: `fn(request, step_id, ...)` becomes `fn(request, step, ...)`

    The inner function will be wrapped in a cooperative lock.

    The inner function will raise Http404 if pk is not found in the database,
    or PermissionDenied if the person requesting does not have read access.
    """

    def inner(request: HttpRequest, step_id: int, *args, **kwargs):
        # TODO simplify this a ton by putting `workflow` in the URL. That way,
        # we can lock it _before_ we query it, so we won't have to check any of
        # the zillions of races herein.
        step = get_object_or_404(Step, id=step_id, is_deleted=False)
        try:
            # raise Tab.DoesNotExist, Workflow.DoesNotExist
            workflow = step.workflow
            if workflow is None:
                raise Http404()  # race: workflow is gone

            # raise Workflow.DoesNotExist
            with workflow.cooperative_lock() as workflow_lock:
                if not workflow_lock.workflow.request_authorized_read(request):
                    raise PermissionDenied()

                step.refresh_from_db()  # raise Step.DoesNotExist
                if step.is_deleted or step.tab.is_deleted:
                    raise Http404()  # race: Step/Tab deleted

            return fn(request, step, *args, **kwargs)
        except (Workflow.DoesNotExist, Tab.DoesNotExist, Step.DoesNotExist):
            raise Http404()  # race: tab/step was deleted

    return inner


# ---- render / input / livedata ----
# These endpoints return actual table data


TimestampUnits = {"us": 1000000, "s": 1, "ms": 1000, "ns": 1000000000}  # most common


# Helper method that produces json output for a table + start/end row
# Also silently clips row indices
# Now reading a maximum of 101 columns directly from cache parquet
def _make_render_tuple(cached_result, startrow=None, endrow=None):
    """Build (startrow, endrow, json_rows) data."""

    if startrow is None:
        startrow = 0
    startrow = max(0, startrow)
    if endrow is None:
        endrow = startrow + _MaxNRowsPerRequest
    endrow = max(
        startrow,
        min(
            cached_result.table_metadata.n_rows, endrow, startrow + _MaxNRowsPerRequest
        ),
    )

    # raise CorruptCacheError
    record_json = read_cached_render_result_slice_as_text(
        cached_result,
        "json",
        # Return one row more than configured, so the client knows there
        # are "too many rows".
        only_columns=range(settings.MAX_COLUMNS_PER_CLIENT_REQUEST + 1),
        only_rows=range(startrow, endrow),
    )
    return (startrow, endrow, record_json)


def int_or_none(x):
    return int(x) if x is not None else None


# /render: return output table of this module
async def step_render(request: HttpRequest, step_id: int):
    # Get first and last row from query parameters, or default to all if not
    # specified
    try:
        startrow = int_or_none(request.GET.get("startrow"))
        endrow = int_or_none(request.GET.get("endrow"))
    except ValueError:
        return JsonResponse(
            {"message": "bad row number", "status_code": 400},
            status=status.BAD_REQUEST,
        )

    # raise Http404, PermissionDenied
    _, __, step = await _load_step_by_id_oops_where_is_workflow(request, step_id)
    cached_result = step.cached_render_result
    if cached_result is None:
        # assume we'll get another request after execute finishes
        return JsonResponse({"start_row": 0, "end_row": 0, "rows": []})

    try:
        startrow, endrow, record_json = _make_render_tuple(
            cached_result, startrow, endrow
        )
    except CorruptCacheError:
        # assume we'll get another request after execute finishes
        return JsonResponse({"start_row": 0, "end_row": 0, "rows": []})

    data = '{"start_row":%d,"end_row":%d,"rows":%s}' % (startrow, endrow, record_json)
    response = HttpResponse(
        data.encode("utf-8"), content_type="application/json", charset="utf-8"
    )
    add_never_cache_headers(response)
    return response


# /tiles/:slug/v:delta_id/:tile_row,:tile_column.json: table data
@require_GET
@_with_unlocked_step_for_read
def step_tile(
    request: HttpRequest, step: Step, delta_id: int, tile_row: int, tile_column: int
):
    # No need for cooperative lock: the cache may always be corrupt (lock or no), and
    # we don't read from the database
    row_begin = tile_row * settings.BIG_TABLE_ROWS_PER_TILE
    row_end = row_begin + settings.BIG_TABLE_ROWS_PER_TILE  # one past end
    column_begin = tile_column * settings.BIG_TABLE_COLUMNS_PER_TILE
    column_end = column_begin + settings.BIG_TABLE_COLUMNS_PER_TILE  # one past end

    cached_result = step.cached_render_result
    if cached_result is None or cached_result.delta_id != delta_id:
        return JsonResponse(
            {"error": "delta_id result not cached"}, status=status.NOT_FOUND
        )

    if (
        cached_result.table_metadata.n_rows <= row_begin
        or len(cached_result.table_metadata.columns) <= column_begin
    ):
        return JsonResponse({"error": "tile out of bounds"}, status=status.NOT_FOUND)

    try:
        record_json = read_cached_render_result_slice_as_text(
            cached_result,
            "json",
            only_rows=range(row_begin, row_end),
            only_columns=range(column_begin, column_end),
        )
    except CorruptCacheError:
        # A different 404 message to help during debugging
        return JsonResponse(
            {"error": "result went away; please try again with another delta_id"},
            status=status.NOT_FOUND,
        )

    # Convert from [{"a": "b", "c": "d"}, ...] to [["b", "d"], ...]
    rows = json.loads(
        record_json, object_pairs_hook=lambda pairs: [v for k, v in pairs]
    )

    response = JsonResponse({"rows": rows})
    patch_response_headers(response, cache_timeout=600)
    return response


@xframe_options_exempt
async def step_output(request: HttpRequest, step_id: int):
    # raise Http404, PermissionDenied
    _, __, step = await _load_step_by_id_oops_where_is_workflow(request, step_id)
    try:
        module_zipfile = await database_sync_to_async(MODULE_REGISTRY.latest)(
            step.module_id_name
        )
        html = module_zipfile.get_optional_html()
    except KeyError:
        html = None
    return HttpResponse(content=html)


async def step_embeddata(request: HttpRequest, step_id: int):
    # raise Http404, PermissionDenied
    _, __, step = await _load_step_by_id_oops_where_is_workflow(request, step_id)

    # Speedy bypassing of locks: we don't care if we get out-of-date data
    # because we assume the client will re-request when it gets a new
    # cached_render_result_delta_id.
    try:
        result_json = json.loads(
            bytes(step.cached_render_result_json), encoding="utf-8"
        )
    except ValueError:
        result_json = None

    return JsonResponse(result_json, safe=False)


async def step_value_counts(request: HttpRequest, step_id: int) -> JsonResponse:
    try:
        colname = request.GET["column"]
    except KeyError:
        return JsonResponse(
            {"error": 'Missing a "column" parameter'}, status=status.BAD_REQUEST
        )

    if not colname:
        # User has not yet chosen a column. Empty response.
        return JsonResponse({"values": {}})

    # raise Http404, PermissionDenied
    _, __, step = await _load_step_by_id_oops_where_is_workflow(request, step_id)
    cached_result = step.cached_render_result
    if cached_result is None:
        # assume we'll get another request after execute finishes
        return JsonResponse({"values": {}})

    try:
        column_index, column = next(
            (i, c)
            for i, c in enumerate(cached_result.table_metadata.columns)
            if c.name == colname
        )
    except StopIteration:
        return JsonResponse(
            {"error": f'column "{colname}" not found'}, status=status.NOT_FOUND
        )

    if not isinstance(column.type, ColumnType.Text):
        # We only return text values.
        #
        # Rationale: this is only used in Refine and Filter by Value. Both
        # force text. The user can query a column before it's converted to
        # text; but if he/she does, we shouldn't format as text unless we have
        # a viable workflow that needs it. (Better would be to force the user
        # to convert to text before doing anything else, no?)
        return JsonResponse({"values": {}})

    try:
        # raise CorruptCacheError
        with open_cached_render_result(cached_result) as result:
            arrow_table = result.table.table
            chunked_array = arrow_table.column(column_index)
    except CorruptCacheError:
        # We _could_ return an empty result set; but our only goal here is
        # "don't crash" and this 404 seems to be the simplest implementation.
        # (We assume that if the data is deleted, the user has moved elsewhere
        # and this response is going to be ignored.)
        return JsonResponse(
            {"error": f'column "{colname}" not found'}, status=status.NOT_FOUND
        )

    if chunked_array.num_chunks == 0:
        value_counts = {}
    else:
        pyarrow_value_counts = chunked_array.value_counts()
        # Assume type is text. (We checked column.type is ColumnType.Text above.)
        #
        # values can be either a StringArray or a DictionaryArray. In either case,
        # .to_pylist() converts to a Python List[str].
        values = pyarrow_value_counts.field("values").to_pylist()
        counts = pyarrow_value_counts.field("counts").to_pylist()

        value_counts = {v: c for v, c in zip(values, counts) if v is not None}

    return JsonResponse({"values": value_counts})


class SubprocessOutputFileLike(io.RawIOBase):
    """Run a subrocess; .read() reads its stdout and stderr (combined).

    On close(), kill the subprocess (if it's still running) and wait for it.

    close() is the only way to wait for the subprocess. Don't worry: __del__()
    calls close().

    If the process cannot be started, raise OSError.

    If read() is called after the subprocess terminates and the subprocess's
    exit code is not 0, raise IOError.

    Not thread-safe.

    HACK: this is only safe for Django 3.1 async-view responses.
    `django.core.handlers.asgi.ASGIHandler#send_response()` has this loop:

        for part in response:  # calls .read() -- SYNCHRONOUS!!!
            await send(...)  # async (safe)

    We make assumptions about Django, the caller, the client....:

        * The caller can `await filelike.stdout_ready()` to ensure the first
          bytes of stdout are available. This ensures the streaming has begun:
          the subprocess's has started up (which may be slow). If the subprocess
          opened temporary files, it's safe to delete them now.
        * The process must stream stdout _quickly_. Django calls `.readinto()`
          synchronously in the event-loop thread: it stalls the web server.
        * Django `send()` must back-pressure. That's when other HTTP request
          processing happens.
        * The process must not consume much RAM/disk/CPU; or the caller must
          arrange throttling. Django won't limit the number of concurrent
          ASGI requests.
    """

    def __init__(self, args):
        super().__init__()

        # Raises OSError
        self.process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )

    async def stdout_ready(self) -> Awaitable[None]:
        """Return when `self.process.stdout.read()` is guaranteed not to block.

        After this returns, the subprocess is "started up". If it's streaming
        from a file, it has certainly opened that file -- and so on UNIX, that
        file may be safely deleted.

        This uses loop.add_reader() to watch the file descriptor. That only
        works because [2020-12-22] Django 3.1 _doesn't_ use loop.add_reader()!
        When Django allows streaming async output, let's use that.
        """
        loop = asyncio.get_running_loop()
        event = asyncio.Event()
        fd = self.process.stdout.fileno()

        def ready():
            event.set()
            loop.remove_reader(fd)

        loop.add_reader(fd, ready)

        try:
            await event.wait()
        finally:
            loop.remove_reader(fd)  # in case ready() was never called

    def readable(self):
        return True

    def fileno(self):
        return self.process.stdout.fileno()

    def readinto(self, b):
        # Assume this is fast. (It's called synchronously.)
        ret = self.process.stdout.readinto(b)
        return ret

    def close(self):
        if self.closed:
            return

        self.process.stdout.close()
        self.process.kill()
        # wait() should not deadlock, because process will certainly die.
        self.process.wait()  # ignore exit code
        super().close()  # sets self.closed


async def _step_to_text_stream(
    step: Step, format: Literal["csv", "json"]
) -> Awaitable[SubprocessOutputFileLike]:
    """Download the step's cached result and streaming it as CSV/JSON.

    Raise CorruptCacheError if there is no cached result or it is invalid.

    Raise OSError if `/usr/bin/parquet-to-text-stream` cannot start.
    """
    cached_result = step.cached_render_result
    if not cached_result:
        raise CorruptCacheError

    # raise CorruptCacheError
    with downloaded_parquet_file(cached_result) as parquet_path:
        output = SubprocessOutputFileLike(
            ["/usr/bin/parquet-to-text-stream", str(parquet_path), format]
        )
        await output.stdout_ready()
        # It's okay to delete the file now (i.e., exit the context manager)

        return output


async def step_public_json(request: HttpRequest, step_id: int) -> FileResponse:
    # raise Http404, PermissionDenied
    workflow, _, step = await _load_step_by_id_oops_where_is_workflow(request, step_id)

    try:
        output = await _step_to_text_stream(step, "json")
    except CorruptCacheError:
        # Schedule a render and return a response asking the user to retry.
        #
        # We don't have a cached result, and we don't know how long it'll
        # take to get one. The user will simply need to try again....
        #
        # It is a *bug* that we publish URLs that aren't guaranteed to work.
        # Because we publish URLs that do not work, let's be transparent and
        # give them the 500-level error code they deserve.
        await rabbitmq.queue_render(workflow.id, workflow.last_delta_id)
        response = JsonResponse([], safe=False, status=status.SERVICE_UNAVAILABLE)
        response["Retry-After"] = "30"
        return response

    return FileResponse(
        output,
        as_attachment=True,
        filename=(
            "Workflow %d - %s-%d.json" % (workflow.id, step.module_id_name, step.id)
        ),
        content_type="application/json",
    )


async def step_public_csv(request: HttpRequest, step_id: int) -> FileResponse:
    # raise Http404, PermissionDenied
    workflow, _, step = await _load_step_by_id_oops_where_is_workflow(request, step_id)

    try:
        output = await _step_to_text_stream(step, "csv")
    except CorruptCacheError:
        # Schedule a render and return a response asking the user to retry.
        #
        # We don't have a cached result, and we don't know how long it'll
        # take to get one. The user will simply need to try again....
        #
        # It is a *bug* that we publish URLs that aren't guaranteed to work.
        # Because we publish URLs that do not work, let's be transparent and
        # give them the 500-level error code they deserve.
        await rabbitmq.queue_render(workflow.id, workflow.last_delta_id)
        response = HttpResponse(
            b"", content_type="text/csv", status=status.SERVICE_UNAVAILABLE
        )
        response["Retry-After"] = "30"
        return response

    return FileResponse(
        output,
        as_attachment=True,
        filename=(
            "Workflow %d - %s-%d.csv" % (workflow.id, step.module_id_name, step.id)
        ),
        content_type="text/csv; charset=utf-8; header=present",
    )

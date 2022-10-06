import traceback
import os
import datetime
import tempfile
import uuid
import logging
import queue

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from dccutils.guess import GuessedContext

logger = logging.getLogger("uvicorn.error")

app = FastAPI()
app.dcc_context = GuessedContext()
app.queue_needed = False

if app.dcc_context.get_dcc_name() == "Unreal Editor":
    import unreal

    # create a queue to run all unreal functions in main thread
    app.queue_needed = True
    app.queue_exec = queue.Queue()
    app.queue_results = {}

    class CheckQueue(object):
        def __init__(self):
            self._callback_to_wait = None
            self._result = None
            self._uuid = None

        def check_queue(self, deltatime):
            if self._callback_to_wait is None:
                try:
                    (
                        f,
                        args,
                        kwargs,
                        self._uuid,
                        self._callback_to_wait,
                    ) = app.queue_exec.get(block=False)
                    if self._callback_to_wait is None:
                        try:
                            app.queue_results[self._uuid] = f(*args, **kwargs)
                        except Exception as e:
                            app.queue_results[self._uuid] = e
                        self._uuid = None
                    else:
                        try:
                            self._result = f(*args, **kwargs)
                        except Exception as e:
                            self._result = e
                except queue.Empty:
                    pass
            else:
                if isinstance(
                    self._result, Exception
                ) or self._callback_to_wait(self._result):
                    app.queue_results[self._uuid] = self._result
                    self._result = None
                    self._callback_to_wait = None
                    self._uuid = None

    unreal.register_slate_pre_tick_callback(CheckQueue().check_queue)


@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        tb = traceback.format_exc()
        logger.error(tb)
        return JSONResponse(
            {"detail": tb}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@app.get("/")
def home():
    return {
        "dcc_name": run_in_queue_or_not(app.dcc_context.get_dcc_name),
        "dcc_version": run_in_queue_or_not(app.dcc_context.get_dcc_version),
        "current_project": run_in_queue_or_not(
            app.dcc_context.get_current_project_path
        ),
    }


@app.get("/get-cameras")
def get_cameras():
    return run_in_queue_or_not(app.dcc_context.get_cameras)


@app.get("/set-camera")
def set_camera(camera: str):
    return run_in_queue_or_not(app.dcc_context.set_camera, [camera])


@app.get("/get-renderers")
def get_renderers():
    return run_in_queue_or_not(app.dcc_context.get_available_renderers)


@app.get("/get-extensions")
def get_extensions(is_video: bool = False):
    return run_in_queue_or_not(app.dcc_context.get_extensions, [is_video])


@app.get("/get-current-color-space")
def get_current_color_space():
    return run_in_queue_or_not(app.dcc_context.get_current_color_space)


@app.get("/set-current-color-space")
def set_current_color_space(color_space: str):
    return run_in_queue_or_not(
        app.dcc_context.set_current_color_space, [color_space]
    )


@app.get("/take-viewport-screenshot")
def take_viewport_screenshot(extension: str = "", output_path: str = ""):
    output_path = generate_output_path(output_path, extension, False)
    run_in_queue_or_not(app.dcc_context.push_state)
    try:
        run_in_queue_or_not(
            app.dcc_context.take_viewport_screenshot,
            kwargs={"output_path": output_path, "extension": extension},
            callback_to_wait=lambda _: not app.dcc_context.take_screenshot_in_progress,
        )
    finally:
        run_in_queue_or_not(app.dcc_context.pop_state)
    return {"file": output_path}


@app.get("/take-render-screenshot")
def take_render_screenshot(
    renderer: str = "",
    extension: str = "",
    output_path: str = "",
    use_colorspace: bool = False,
):
    output_path = generate_output_path(output_path, extension, False)
    run_in_queue_or_not(app.dcc_context.push_state)
    try:
        run_in_queue_or_not(
            app.dcc_context.take_render_screenshot,
            kwargs={
                "renderer": renderer,
                "output_path": output_path,
                "extension": extension,
                "use_colorspace": use_colorspace,
            },
            callback_to_wait=lambda _: not app.dcc_context.take_screenshot_in_progress,
        )
    finally:
        run_in_queue_or_not(app.dcc_context.pop_state)
    return {"file": output_path}


@app.get("/take-viewport-animation")
def take_viewport_animation(output_path: str = "", extension: str = ""):
    output_path = generate_output_path(output_path, extension, True)
    run_in_queue_or_not(app.dcc_context.push_state)
    try:
        run_in_queue_or_not(
            app.dcc_context.take_viewport_animation,
            kwargs={"output_path": output_path, "extension": extension},
            callback_to_wait=lambda _: not app.dcc_context.take_movie_in_progress,
        )
    finally:
        run_in_queue_or_not(app.dcc_context.pop_state)
    return {"file": output_path}


@app.get("/take-render-animation")
def take_render_animation(
    renderer: str = "",
    extension: str = "",
    output_path: str = "",
    use_colorspace: bool = False,
):
    output_path = generate_output_path(output_path, extension, True)
    run_in_queue_or_not(app.dcc_context.push_state)
    try:
        run_in_queue_or_not(
            app.dcc_context.take_render_animation,
            kwargs={
                "renderer": renderer,
                "output_path": output_path,
                "extension": extension,
                "use_colorspace": use_colorspace,
            },
            callback_to_wait=lambda _: not app.dcc_context.take_movie_in_progress,
        )
    finally:
        run_in_queue_or_not(app.dcc_context.pop_state)
    return {"file": output_path}


if app.dcc_context.get_dcc_name() == "Unreal Editor":

    @app.get("/get-sequences")
    def get_sequence():
        return run_in_queue_or_not(app.dcc_context.get_sequences)

    @app.get("/set-sequence")
    def set_sequence(sequence: str):
        return run_in_queue_or_not(app.dcc_context.set_sequence, [sequence])


def generate_output_path(output_path="", extension="", is_video=False):
    if not output_path or os.path.isdir(output_path):
        extension_str = ""
        for extension_list in run_in_queue_or_not(
            app.dcc_context.get_extensions, [is_video]
        ):
            if extension_list[1] == extension:
                extension_str = extension_list[0]
                break
        if extension_str == "":
            extension_str = run_in_queue_or_not(
                app.dcc_context.get_extensions, [is_video]
            )[0][0]
        return os.path.join(
            tempfile.gettempdir() if not output_path else output_path,
            "%s-%s%s"
            % (
                run_in_queue_or_not(app.dcc_context.get_dcc_name),
                datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S"),
                extension_str,
            ),
        )
    return output_path


def run_in_queue_or_not(f, args=[], kwargs={}, callback_to_wait=None):
    if app.queue_needed:
        queue_uuid = str(uuid.uuid4())
        app.queue_exec.put(
            (f, args, kwargs, queue_uuid, callback_to_wait), block=False
        )
        while True:
            if queue_uuid in app.queue_results.keys():
                result = app.queue_results[queue_uuid]
                del app.queue_results[queue_uuid]
                if isinstance(result, Exception):
                    raise result
                else:
                    return result
    else:
        return f(*args, **kwargs)

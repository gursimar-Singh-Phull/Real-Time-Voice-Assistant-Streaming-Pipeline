import os
import ctypes
import subprocess

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams


# -----------------------------------
# Lock PC
# -----------------------------------
async def lock_pc(params: FunctionCallParams):
    try:
        ctypes.windll.user32.LockWorkStation()
        await params.result_callback("Computer locked.")
    except Exception as e:
        await params.result_callback(f"Failed to lock computer: {e}")


# -----------------------------------
# Sleep PC
# -----------------------------------
async def sleep_pc(params: FunctionCallParams):
    try:
        subprocess.run(
            ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            check=True
        )
        await params.result_callback("Computer is going to sleep.")
    except Exception as e:
        await params.result_callback(f"Failed to sleep computer: {e}")


lock_pc_schema = FunctionSchema(
    name="lock_pc",
    description="Lock the Windows computer.",
    properties={},
    required=[],
    handler=lock_pc,
)

sleep_pc_schema = FunctionSchema(
    name="sleep_pc",
    description="Put the Windows computer to sleep.",
    properties={},
    required=[],
    handler=sleep_pc,
)

system_control_tools = ToolsSchema(
    standard_tools=[
        lock_pc_schema,
        sleep_pc_schema,
    ]
)
"""P1-01b: fixed browser choices and safe model readiness metadata."""

from collections.abc import Callable
from typing import Literal

from agent_workbench.model_gateway.gateway import Config, GatewayError

ModelReason = Literal[
    "MODEL_NOT_CONFIGURED", "MODEL_CONFIGURATION_INVALID", "INPUT_BOUND_UNVERIFIED"
]
CASES = [
    {"id": "output_mismatch", "label": "返回值类型错误"},
    {"id": "passing", "label": "正常调用"},
]
INTENTS = [
    {"id": "check_only", "label": "仅检查契约", "requires_model": False},
    {"id": "diagnose", "label": "分析原因", "requires_model": True},
    {"id": "propose_repair", "label": "生成修复建议", "requires_model": True},
]


def model_config(loader: Callable[[], Config]) -> tuple[Config | None, ModelReason | None]:
    try:
        return loader(), None
    except GatewayError as error:
        if str(error) == "INPUT_BOUND_UNVERIFIED":
            return None, "INPUT_BOUND_UNVERIFIED"
        if str(error) == "MODEL_NOT_CONFIGURED":
            return None, "MODEL_NOT_CONFIGURED"
        return None, "MODEL_CONFIGURATION_INVALID"
    except Exception:
        return None, "MODEL_CONFIGURATION_INVALID"

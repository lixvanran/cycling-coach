"""V0.8.0: 统一异常层

设计要点:
- 业务异常都用 AppError 子类, 不直接 raise HTTPException
- main.py 注册 AppError handler, 自动转 JSON 响应 {ok: false, code, message, ...}
- 优势:
  1. service 层不依赖 FastAPI HTTPException (纯业务代码, 单元测试无需 mock HTTP)
  2. 统一响应格式, 前端用 code 字段做更细粒度分支
  3. status code 与异常类型一一对应, 避免到处写 400/404

异常 → HTTP status 映射:
- NotFoundError       → 404
- ValidationError     → 422
- ConflictError       → 409
- ForbiddenError      → 403
- UnauthorizedError   → 401
- AppError (base)     → 400
"""
from __future__ import annotations
from typing import Any, Optional


class AppError(Exception):
    """应用基础异常

    所有业务异常的根. 子类可覆盖 status 和 code, 但通常用预设的子类即可.
    """
    def __init__(
        self,
        message: str,
        code: str = "error",
        status: int = 400,
        **kwargs: Any,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        # 额外的响应字段, 例如 {"field": "email", "value": "..."}
        self.extra: dict[str, Any] = kwargs

    def to_dict(self) -> dict:
        """序列化为 JSON 响应"""
        d = {"ok": False, "code": self.code, "message": self.message}
        d.update(self.extra)
        return d

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.code!r}, {self.status}, {self.message!r})"


class NotFoundError(AppError):
    """资源不存在 (HTTP 404)"""
    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, code="not_found", status=404, **kwargs)


class ValidationError(AppError):
    """输入校验失败 (HTTP 422)"""
    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, code="validation_error", status=422, **kwargs)


class ConflictError(AppError):
    """资源冲突, 例如重复创建 (HTTP 409)"""
    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, code="conflict", status=409, **kwargs)


class ForbiddenError(AppError):
    """权限不足 (HTTP 403)"""
    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, code="forbidden", status=403, **kwargs)


class UnauthorizedError(AppError):
    """未认证 (HTTP 401)"""
    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, code="unauthorized", status=401, **kwargs)


class BusinessError(AppError):
    """通用业务错误 (HTTP 400)

    用在不能归到 NotFound/Validation/Conflict 的场景:
    - 状态机错误 (例如 "活动正在分析中, 不能删除")
    - 依赖缺失 (例如 "FTP 未设置")
    - 第三方服务失败 (例如 "AI 模型推理超时")
    """
    def __init__(self, message: str, code: str = "business_error", status: int = 400, **kwargs: Any):
        super().__init__(message, code=code, status=status, **kwargs)

from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Check(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CHECK_UNSPECIFIED: _ClassVar[Check]
    CHECK_PROMPT_INJECTION: _ClassVar[Check]
    CHECK_CONTENT_SAFETY: _ClassVar[Check]
    CHECK_PII_NER: _ClassVar[Check]
    CHECK_SYSTEM_PROMPT_LEAK: _ClassVar[Check]

class Direction(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DIRECTION_UNSPECIFIED: _ClassVar[Direction]
    DIRECTION_INPUT: _ClassVar[Direction]
    DIRECTION_OUTPUT: _ClassVar[Direction]

class Status(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    STATUS_UNSPECIFIED: _ClassVar[Status]
    STATUS_OK: _ClassVar[Status]
    STATUS_TIMEOUT: _ClassVar[Status]
    STATUS_ERROR: _ClassVar[Status]
    STATUS_REJECTED: _ClassVar[Status]

class Verdict(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    VERDICT_UNSPECIFIED: _ClassVar[Verdict]
    VERDICT_SAFE: _ClassVar[Verdict]
    VERDICT_SUSPICIOUS: _ClassVar[Verdict]
    VERDICT_MALICIOUS: _ClassVar[Verdict]
CHECK_UNSPECIFIED: Check
CHECK_PROMPT_INJECTION: Check
CHECK_CONTENT_SAFETY: Check
CHECK_PII_NER: Check
CHECK_SYSTEM_PROMPT_LEAK: Check
DIRECTION_UNSPECIFIED: Direction
DIRECTION_INPUT: Direction
DIRECTION_OUTPUT: Direction
STATUS_UNSPECIFIED: Status
STATUS_OK: Status
STATUS_TIMEOUT: Status
STATUS_ERROR: Status
STATUS_REJECTED: Status
VERDICT_UNSPECIFIED: Verdict
VERDICT_SAFE: Verdict
VERDICT_SUSPICIOUS: Verdict
VERDICT_MALICIOUS: Verdict

class Message(_message.Message):
    __slots__ = ("id", "role", "content")
    ID_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    id: str
    role: str
    content: str
    def __init__(self, id: _Optional[str] = ..., role: _Optional[str] = ..., content: _Optional[str] = ...) -> None: ...

class CheckSpec(_message.Message):
    __slots__ = ("check", "timeout_ms")
    CHECK_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_MS_FIELD_NUMBER: _ClassVar[int]
    check: Check
    timeout_ms: int
    def __init__(self, check: _Optional[_Union[Check, str]] = ..., timeout_ms: _Optional[int] = ...) -> None: ...

class AnalyzeRequest(_message.Message):
    __slots__ = ("request_id", "agent_id", "direction", "messages", "checks", "canaries")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    MESSAGES_FIELD_NUMBER: _ClassVar[int]
    CHECKS_FIELD_NUMBER: _ClassVar[int]
    CANARIES_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    agent_id: str
    direction: Direction
    messages: _containers.RepeatedCompositeFieldContainer[Message]
    checks: _containers.RepeatedCompositeFieldContainer[CheckSpec]
    canaries: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, request_id: _Optional[str] = ..., agent_id: _Optional[str] = ..., direction: _Optional[_Union[Direction, str]] = ..., messages: _Optional[_Iterable[_Union[Message, _Mapping]]] = ..., checks: _Optional[_Iterable[_Union[CheckSpec, _Mapping]]] = ..., canaries: _Optional[_Iterable[str]] = ...) -> None: ...

class Span(_message.Message):
    __slots__ = ("message_id", "start", "end", "entity", "score")
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    START_FIELD_NUMBER: _ClassVar[int]
    END_FIELD_NUMBER: _ClassVar[int]
    ENTITY_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    message_id: str
    start: int
    end: int
    entity: str
    score: float
    def __init__(self, message_id: _Optional[str] = ..., start: _Optional[int] = ..., end: _Optional[int] = ..., entity: _Optional[str] = ..., score: _Optional[float] = ...) -> None: ...

class CheckResult(_message.Message):
    __slots__ = ("check", "status", "message_id", "score", "categories", "spans", "latency_ms", "error")
    CHECK_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    CATEGORIES_FIELD_NUMBER: _ClassVar[int]
    SPANS_FIELD_NUMBER: _ClassVar[int]
    LATENCY_MS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    check: Check
    status: Status
    message_id: str
    score: float
    categories: _containers.RepeatedScalarFieldContainer[str]
    spans: _containers.RepeatedCompositeFieldContainer[Span]
    latency_ms: int
    error: str
    def __init__(self, check: _Optional[_Union[Check, str]] = ..., status: _Optional[_Union[Status, str]] = ..., message_id: _Optional[str] = ..., score: _Optional[float] = ..., categories: _Optional[_Iterable[str]] = ..., spans: _Optional[_Iterable[_Union[Span, _Mapping]]] = ..., latency_ms: _Optional[int] = ..., error: _Optional[str] = ...) -> None: ...

class AnalyzeResponse(_message.Message):
    __slots__ = ("results",)
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[CheckResult]
    def __init__(self, results: _Optional[_Iterable[_Union[CheckResult, _Mapping]]] = ...) -> None: ...

class ScanArtifactRequest(_message.Message):
    __slots__ = ("request_id", "url", "path", "max_bytes")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    PATH_FIELD_NUMBER: _ClassVar[int]
    MAX_BYTES_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    url: str
    path: str
    max_bytes: int
    def __init__(self, request_id: _Optional[str] = ..., url: _Optional[str] = ..., path: _Optional[str] = ..., max_bytes: _Optional[int] = ...) -> None: ...

class ArtifactFinding(_message.Message):
    __slots__ = ("module", "name", "verdict")
    MODULE_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    VERDICT_FIELD_NUMBER: _ClassVar[int]
    module: str
    name: str
    verdict: Verdict
    def __init__(self, module: _Optional[str] = ..., name: _Optional[str] = ..., verdict: _Optional[_Union[Verdict, str]] = ...) -> None: ...

class ScanArtifactResponse(_message.Message):
    __slots__ = ("verdict", "format", "sha256", "findings", "latency_ms")
    VERDICT_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    SHA256_FIELD_NUMBER: _ClassVar[int]
    FINDINGS_FIELD_NUMBER: _ClassVar[int]
    LATENCY_MS_FIELD_NUMBER: _ClassVar[int]
    verdict: Verdict
    format: str
    sha256: str
    findings: _containers.RepeatedCompositeFieldContainer[ArtifactFinding]
    latency_ms: int
    def __init__(self, verdict: _Optional[_Union[Verdict, str]] = ..., format: _Optional[str] = ..., sha256: _Optional[str] = ..., findings: _Optional[_Iterable[_Union[ArtifactFinding, _Mapping]]] = ..., latency_ms: _Optional[int] = ...) -> None: ...

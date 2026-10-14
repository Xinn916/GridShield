from enum import StrEnum


class QueryType(StrEnum):
    SUM = "SUM"
    COUNT = "COUNT"
    AVERAGE = "AVERAGE"
    TIME_SERIES = "TIME_SERIES"


class GroupBy(StrEnum):
    HALF_HOUR = "30m"
    HOUR = "1h"
    DAY = "1d"


class OrganizationId(StrEnum):
    ORG_A = "ORG_A"
    ORG_B = "ORG_B"
    ORG_C = "ORG_C"


class CalculationMode(StrEnum):
    PLAIN = "PLAIN"
    SECRET_SHARE = "SECRET_SHARE"
    DISTRIBUTED_DP = "DISTRIBUTED_DP"


class TaskStatus(StrEnum):
    CREATED = "CREATED"
    DISPATCHING = "DISPATCHING"
    LOCAL_COMPUTING = "LOCAL_COMPUTING"
    SHARING = "SHARING"
    AGGREGATING = "AGGREGATING"
    RECONSTRUCTING = "RECONSTRUCTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ComputeTaskStatus(StrEnum):
    WAITING = "WAITING"
    READY = "READY"
    FAILED = "FAILED"


class UserRole(StrEnum):
    ANALYST = "ANALYST"
    DATA_OWNER = "DATA_OWNER"
    AUDITOR = "AUDITOR"
    ADMIN = "ADMIN"


class AccessRequestStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    PARTIALLY_APPROVED = "PARTIALLY_APPROVED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class ApprovalDecision(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    CONDITIONALLY_APPROVED = "CONDITIONALLY_APPROVED"
    REJECTED = "REJECTED"


class GrantStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXHAUSTED = "EXHAUSTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class DataImportStatus(StrEnum):
    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    VALID = "VALID"
    INVALID = "INVALID"
    ACTIVATING = "ACTIVATING"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"

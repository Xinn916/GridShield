from typing import BinaryIO

import httpx

from common.enums import OrganizationId
from common.schemas import (
    PartyActiveDatasetResponse,
    PartyDataImportResponse,
    PartyRollbackRequest,
)


class PartyImportError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class PartyImportClient:
    def __init__(
        self,
        party_urls: dict[OrganizationId, str],
        internal_token: str,
        timeout: float = 30.0,
    ):
        self.party_urls = party_urls
        self.internal_token = internal_token
        self.timeout = timeout

    def upload(
        self,
        party: OrganizationId,
        import_id: str,
        filename: str,
        stream: BinaryIO,
    ) -> PartyDataImportResponse:
        stream.seek(0)
        try:
            response = httpx.post(
                f"{self.party_urls[party]}/internal/imports",
                headers=self._headers(),
                data={"import_id": import_id, "party_id": party.value},
                files={"file": (filename, stream, "text/csv")},
                timeout=self.timeout,
            )
            self._raise(response, party)
            return PartyDataImportResponse.model_validate(response.json())
        except PartyImportError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise PartyImportError(f"{party.value} import request failed: {type(exc).__name__}") from exc

    def get(self, party: OrganizationId, import_id: str) -> PartyDataImportResponse:
        response = self._post_or_get(party, f"/internal/imports/{import_id}", "GET")
        return PartyDataImportResponse.model_validate(response.json())

    def activate(self, party: OrganizationId, import_id: str) -> PartyDataImportResponse:
        response = self._post_or_get(party, f"/internal/imports/{import_id}/activate", "POST")
        return PartyDataImportResponse.model_validate(response.json())

    def archive(self, party: OrganizationId, import_id: str) -> PartyDataImportResponse:
        response = self._post_or_get(party, f"/internal/imports/{import_id}/archive", "POST")
        return PartyDataImportResponse.model_validate(response.json())

    def rollback(self, party: OrganizationId, target_version: str) -> PartyActiveDatasetResponse:
        response = self._post_or_get(
            party,
            f"/internal/imports/{target_version}/rollback",
            "POST",
            json=PartyRollbackRequest(target_version=target_version).model_dump(mode="json"),
        )
        return PartyActiveDatasetResponse.model_validate(response.json())

    def active(self, party: OrganizationId) -> PartyActiveDatasetResponse:
        response = self._post_or_get(party, "/internal/imports/active", "GET")
        return PartyActiveDatasetResponse.model_validate(response.json())

    def _post_or_get(self, party, path, method, **kwargs) -> httpx.Response:
        try:
            response = httpx.request(
                method,
                f"{self.party_urls[party]}{path}",
                headers=self._headers(),
                timeout=self.timeout,
                **kwargs,
            )
            self._raise(response, party)
            return response
        except PartyImportError:
            raise
        except httpx.HTTPError as exc:
            raise PartyImportError(f"{party.value} import service unavailable: {type(exc).__name__}") from exc

    def _headers(self) -> dict[str, str]:
        return {"X-Internal-Token": self.internal_token}

    @staticmethod
    def _raise(response: httpx.Response, party: OrganizationId) -> None:
        if response.is_success:
            return
        detail = "Party rejected the import request"
        try:
            payload = response.json()
            if isinstance(payload.get("detail"), str):
                detail = payload["detail"]
        except ValueError:
            pass
        status_code = response.status_code if response.status_code < 500 else 502
        raise PartyImportError(f"{party.value}: {detail}", status_code)

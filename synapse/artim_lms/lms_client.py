"""Reads users, courses and enrollments of one academy from the LMS developer API."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .policy import LmsCourse, LmsSnapshot, LmsUser

GetJson = Callable[[str, dict[str, Any], str], Awaitable[Mapping[str, Any]]]
PostJson = Callable[[str, dict[str, Any], str], Awaitable[Mapping[str, Any]]]

SCOPES = ["lms.admin.users:read", "lms.courses:read", "lms.students.enrollments:read"]
TOKEN_RENEW_MARGIN_SECONDS = 300


@dataclass(frozen=True)
class LmsConfig:
    base_url: str
    tenant_id: str
    sync_token: str
    client_id: str
    service_user_id: str
    enrollment_statuses: frozenset[str] = field(default_factory=lambda: frozenset({"active", "paused"}))
    page_size: int = 200


def build_snapshot(
    users: Iterable[Mapping[str, Any]],
    courses: Iterable[Mapping[str, Any]],
    enrollments: Iterable[Mapping[str, Any]],
    statuses: Iterable[str],
    synced_at: int,
) -> LmsSnapshot:
    lms_users = {
        row["id"]: LmsUser(
            user_id=row["id"],
            name=row.get("name") or row.get("email", ""),
            email=row.get("email", ""),
            roles=frozenset(row.get("roles", [])) | frozenset(row.get("globalRoles", [])),
        )
        for row in users
    }
    lms_courses = {
        row["id"]: LmsCourse(course_id=row["id"], title=row.get("title", ""), trainer_id=row.get("createdBy"))
        for row in courses
    }
    wanted = set(statuses)
    students: dict[str, set[str]] = {course_id: set() for course_id in lms_courses}
    for row in enrollments:
        if row.get("status") in wanted and row.get("courseId") in students and row.get("userId") in lms_users:
            students[row["courseId"]].add(row["userId"])

    return LmsSnapshot(
        users=lms_users,
        courses=lms_courses,
        students={course_id: frozenset(ids) for course_id, ids in students.items()},
        synced_at=synced_at,
    )


class LmsClient:
    def __init__(
        self,
        config: LmsConfig,
        get_json: GetJson,
        post_json: PostJson,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._config = config
        self._get_json = get_json
        self._post_json = post_json
        self._clock = clock
        self._token: str | None = None
        self._token_expires_at = 0.0

    def forget_token(self) -> None:
        self._token = None

    async def fetch_snapshot(self) -> LmsSnapshot:
        users = await self._fetch_all("/dev-api/v1/admin/users")
        courses = await self._fetch_all("/dev-api/v1/courses/courses")
        enrollments = await self._fetch_all("/dev-api/v1/students/enrollments")
        return build_snapshot(
            users, courses, enrollments, self._config.enrollment_statuses, int(self._clock() * 1000)
        )

    async def _access_token(self) -> str:
        if self._token is None or self._clock() >= self._token_expires_at - TOKEN_RENEW_MARGIN_SECONDS:
            response = await self._post_json(
                f"{self._config.base_url}/dev/tokens",
                {
                    "clientId": self._config.client_id,
                    "sub": self._config.service_user_id,
                    "organisation": self._config.tenant_id,
                    "scopes": SCOPES,
                },
                self._config.sync_token,
            )
            self._token = response["access_token"]
            self._token_expires_at = self._clock() + float(response.get("expires_in", 0))
        return self._token

    async def _fetch_all(self, path: str) -> list[Mapping[str, Any]]:
        rows: list[Mapping[str, Any]] = []
        while True:
            token = await self._access_token()
            page = await self._get_json(
                f"{self._config.base_url}{path}",
                {"limit": str(self._config.page_size), "offset": str(len(rows))},
                token,
            )
            items = page.get("items", [])
            rows.extend(items)
            if not items or len(rows) >= int(page.get("total", 0)):
                return rows

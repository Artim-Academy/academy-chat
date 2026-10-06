import asyncio
import unittest
from typing import Any

from artim_lms.lms_client import LmsClient, LmsConfig, build_snapshot

USERS = [
    {"id": "u1", "email": "a@x.de", "name": "Ada", "globalRoles": ["student"], "roles": ["admin"]},
    {"id": "u2", "email": "t@x.de", "name": "Tom", "globalRoles": ["student"], "roles": ["trainer"]},
    {"id": "u3", "email": "s@x.de", "name": "Sam", "globalRoles": ["student"], "roles": ["student"]},
]
COURSES = [{"id": "c1", "title": "Web", "createdBy": "u2"}]
ENROLLMENTS = [
    {"userId": "u3", "courseId": "c1", "status": "active"},
    {"userId": "u1", "courseId": "c1", "status": "completed"},
    {"userId": "ghost", "courseId": "c1", "status": "active"},
]


class BuildSnapshotTest(unittest.TestCase):
    def test_merges_global_and_academy_roles(self) -> None:
        snapshot = build_snapshot(USERS, COURSES, ENROLLMENTS, statuses={"active"}, synced_at=42)
        self.assertEqual(snapshot.users["u1"].roles, frozenset({"admin", "student"}))
        self.assertEqual(snapshot.synced_at, 42)

    def test_only_configured_enrollment_statuses_count(self) -> None:
        snapshot = build_snapshot(USERS, COURSES, ENROLLMENTS, statuses={"active"}, synced_at=0)
        self.assertEqual(snapshot.students["c1"], frozenset({"u3"}))

    def test_course_trainer_is_creator(self) -> None:
        snapshot = build_snapshot(USERS, COURSES, ENROLLMENTS, statuses={"active"}, synced_at=0)
        self.assertEqual(snapshot.courses["c1"].trainer_id, "u2")


class FakeHttp:
    def __init__(self) -> None:
        self.gets: list[tuple[str, dict[str, Any], str]] = []
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.pages: dict[str, list[dict[str, Any]]] = {
            "/dev-api/v1/admin/users": USERS,
            "/dev-api/v1/courses/courses": COURSES,
            "/dev-api/v1/students/enrollments": ENROLLMENTS,
        }

    async def get_json(self, url: str, args: dict[str, Any], token: str) -> dict[str, Any]:
        self.gets.append((url, args, token))
        rows = self.pages[url.removeprefix("https://lms.test")]
        offset, limit = int(args["offset"]), int(args["limit"])
        return {"items": rows[offset : offset + limit], "total": len(rows)}

    async def post_json(self, url: str, body: dict[str, Any], token: str) -> dict[str, Any]:
        self.posts.append((url, body))
        return {"access_token": "lmsapi_issued", "expires_in": 3600}


def make_client(http: FakeHttp, page_size: int = 2) -> LmsClient:
    config = LmsConfig(
        base_url="https://lms.test",
        tenant_id="tenant1",
        sync_token="sync-secret",
        client_id="academy-chat",
        service_user_id="u1",
        page_size=page_size,
    )
    return LmsClient(config, http.get_json, http.post_json, clock=lambda: 1000)


class LmsClientTest(unittest.TestCase):
    def test_issues_token_once_and_pages_through_all_rows(self) -> None:
        http = FakeHttp()
        snapshot = asyncio.run(make_client(http).fetch_snapshot())

        self.assertEqual(len(http.posts), 1)
        url, body = http.posts[0]
        self.assertEqual(url, "https://lms.test/dev/tokens")
        self.assertEqual(body["organisation"], "tenant1")
        self.assertEqual(body["sub"], "u1")
        self.assertEqual(set(snapshot.users), {"u1", "u2", "u3"})
        self.assertTrue(all(token == "lmsapi_issued" for _, _, token in http.gets))
        self.assertEqual(snapshot.synced_at, 1000 * 1000)

    def test_reuses_token_until_it_expires(self) -> None:
        http = FakeHttp()
        client = make_client(http, page_size=200)
        asyncio.run(client.fetch_snapshot())
        asyncio.run(client.fetch_snapshot())
        self.assertEqual(len(http.posts), 1)


if __name__ == "__main__":
    unittest.main()

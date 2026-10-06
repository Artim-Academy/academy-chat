import asyncio
import unittest
from types import SimpleNamespace
from typing import Any

try:
    from synapse.api.errors import Codes, SynapseError
    from synapse.module_api import NOT_SPAM

    from artim_lms.module import ACCOUNT_DATA_TYPE, ArtimLms
except ImportError:  # pragma: no cover - synapse is only installed in the module test environment
    ArtimLms = None

SERVER = "artim-academy.de"
USERS = [
    {"id": "admin1", "email": "a@x.de", "name": "Ada", "roles": ["admin"]},
    {"id": "trainer1", "email": "t@x.de", "name": "Tom", "roles": ["trainer"]},
    {"id": "student1", "email": "s@x.de", "name": "Sam", "roles": ["student"]},
]
COURSES = [{"id": "c1", "title": "Web", "createdBy": "trainer1"}]
ENROLLMENTS = [{"userId": "student1", "courseId": "c1", "status": "active"}]


def mxid(localpart: str) -> str:
    return f"@{localpart}:{SERVER}"


class FakeRoom:
    def __init__(self) -> None:
        self.state: dict[tuple[str, str], dict[str, Any]] = {}


class FakeModuleApi:
    server_name = SERVER

    def __init__(self) -> None:
        self.callbacks: dict[str, Any] = {}
        self.users = {mxid(row["id"]) for row in USERS}
        self.rooms: dict[str, FakeRoom] = {}
        self.aliases: dict[str, str] = {}
        self.account_data: dict[tuple[str, str], dict[str, Any]] = {}
        self.account_data_manager = SimpleNamespace(get_global=self._get_global, put_global=self._put_global)
        self.http_client = SimpleNamespace(get_json=self._get_json, post_json_get_json=self._post_json)

    def register_spam_checker_callbacks(self, **kwargs: Any) -> None:
        self.callbacks.update(kwargs)

    def register_third_party_rules_callbacks(self, **kwargs: Any) -> None:
        self.callbacks.update(kwargs)

    def register_account_validity_callbacks(self, **kwargs: Any) -> None:
        self.callbacks.update(kwargs)

    def looping_background_call(self, *args: Any, **kwargs: Any) -> None:
        pass

    def delayed_background_call(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def _get_json(self, url: str, args: dict[str, Any], headers: dict[str, Any]) -> dict[str, Any]:
        rows = {"users": USERS, "courses": COURSES, "enrollments": ENROLLMENTS}[url.rsplit("/", 1)[-1]]
        return {"items": rows, "total": len(rows)}

    async def _post_json(self, url: str, body: dict[str, Any], headers: dict[str, Any]) -> dict[str, Any]:
        return {"access_token": "lmsapi_x", "expires_in": 3600}

    async def check_user_exists(self, user_id: str) -> str | None:
        return user_id if user_id in self.users else None

    async def register_user(self, localpart: str, displayname: str | None = None) -> str:
        self.users.add(mxid(localpart))
        return mxid(localpart)

    async def lookup_room_alias(self, alias: str) -> tuple[str, list[str]]:
        if alias not in self.aliases:
            raise SynapseError(404, "not found")
        return self.aliases[alias], []

    async def create_room(self, user_id: str, config: dict[str, Any], ratelimit: bool = True) -> tuple[str, str]:
        room_id = f"!room{len(self.rooms)}:{SERVER}"
        room = self.rooms[room_id] = FakeRoom()
        room.state[("m.room.member", user_id)] = {"membership": "join"}
        room.state[("m.room.power_levels", "")] = config.get("power_level_content_override", {})
        for event in config.get("initial_state", []):
            room.state[(event["type"], event["state_key"])] = event["content"]
        alias = f"#{config['room_alias_name']}:{SERVER}"
        self.aliases[alias] = room_id
        return room_id, alias

    async def get_room_state(self, room_id: str, event_filter: Any = None) -> dict[tuple[str, str], Any]:
        wanted = list(event_filter or [])
        return {
            key: SimpleNamespace(content=content)
            for key, content in self.rooms[room_id].state.items()
            if not wanted or any(key[0] == t and (k is None or key[1] == k) for t, k in wanted)
        }

    async def update_room_membership(self, sender: str, target: str, room_id: str, membership: str) -> None:
        self.rooms[room_id].state[("m.room.member", target)] = {"membership": membership}

    async def create_and_send_event_into_room(self, event: dict[str, Any]) -> None:
        self.rooms[event["room_id"]].state[(event["type"], event["state_key"])] = event["content"]

    async def _get_global(self, user_id: str, data_type: str) -> dict[str, Any] | None:
        return self.account_data.get((user_id, data_type))

    async def _put_global(self, user_id: str, data_type: str, content: dict[str, Any]) -> None:
        self.account_data[(user_id, data_type)] = content


CONFIG = {
    "lms_base_url": "https://lms.test",
    "tenant_id": "t1",
    "sync_token": "secret",
    "client_id": "academy-chat",
    "service_user_id": "admin1",
    "extra_admins": [mxid("breakglass")],
}


@unittest.skipIf(ArtimLms is None, "synapse is not installed")
class ArtimLmsModuleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.api = FakeModuleApi()
        self.module = ArtimLms(ArtimLms.parse_config(CONFIG), self.api)
        asyncio.run(self.module.sync())
        self.space_id = self.api.aliases[f"#course-c1:{SERVER}"]
        self.general_id = self.api.aliases[f"#course-c1-general:{SERVER}"]

    def membership(self, room_id: str, user: str) -> str | None:
        return self.api.rooms[room_id].state.get(("m.room.member", user), {}).get("membership")

    def test_sync_creates_course_space_and_joins_members(self) -> None:
        space_state = self.api.rooms[self.space_id].state
        self.assertEqual(space_state[("de.artim_academy.course", "")], {"course_id": "c1"})
        self.assertIn(("m.space.child", self.general_id), space_state)
        for room_id in (self.space_id, self.general_id):
            self.assertEqual(self.membership(room_id, mxid("trainer1")), "join")
            self.assertEqual(self.membership(room_id, mxid("student1")), "join")
            self.assertIsNone(self.membership(room_id, mxid("admin1")))

    def test_sync_sets_trainer_power_level(self) -> None:
        users = self.api.rooms[self.general_id].state[("m.room.power_levels", "")]["users"]
        self.assertEqual(users[mxid("trainer1")], 50)
        self.assertNotIn(mxid("student1"), users)

    def test_sync_removes_people_who_left_the_course(self) -> None:
        self.api.rooms[self.general_id].state[("m.room.member", mxid("intruder"))] = {"membership": "join"}
        asyncio.run(self.module.sync())
        self.assertEqual(self.membership(self.general_id, mxid("intruder")), "leave")

    def test_sync_writes_summary_to_account_data(self) -> None:
        summary = self.api.account_data[(mxid("student1"), ACCOUNT_DATA_TYPE)]
        self.assertEqual(summary["roles"], ["student"])
        self.assertEqual(summary["courses"], [{"id": "c1", "title": "Web", "role": "student", "space_id": self.space_id}])

    def test_room_creation_rules(self) -> None:
        may_create = self.api.callbacks["user_may_create_room"]
        in_course = {"initial_state": [{"type": "m.space.parent", "state_key": self.space_id, "content": {}}]}
        self.assertEqual(asyncio.run(may_create(mxid("trainer1"), in_course)), NOT_SPAM)
        self.assertEqual(asyncio.run(may_create(mxid("student1"), in_course)), Codes.FORBIDDEN)
        self.assertEqual(asyncio.run(may_create(mxid("trainer1"), {})), Codes.FORBIDDEN)

    def test_trainer_rooms_get_course_power_levels_and_the_bot(self) -> None:
        content = {"initial_state": [{"type": "m.space.parent", "state_key": self.space_id, "content": {}}]}
        requester = SimpleNamespace(user=SimpleNamespace(to_string=lambda: mxid("trainer1")))
        asyncio.run(self.api.callbacks["on_create_room"](requester, content, False))

        self.assertEqual(content["power_level_content_override"]["events_default"], 50)
        self.assertEqual(content["power_level_content_override"]["users"][mxid("trainer1")], 50)
        self.assertIn(mxid("lms-sync"), content["invite"])

    def test_invites_into_course_rooms(self) -> None:
        may_invite = self.api.callbacks["user_may_invite"]
        self.assertEqual(asyncio.run(may_invite(mxid("student1"), mxid("trainer1"), self.general_id)), NOT_SPAM)
        self.assertEqual(asyncio.run(may_invite(mxid("student1"), mxid("nobody"), self.general_id)), Codes.FORBIDDEN)

    def test_password_login_only_for_break_glass(self) -> None:
        check_login = self.api.callbacks["check_login_for_spam"]
        self.assertEqual(asyncio.run(check_login(mxid("student1"), None, None, [], None)), Codes.FORBIDDEN)
        self.assertEqual(asyncio.run(check_login(mxid("student1"), None, None, [], "oidc-artim")), NOT_SPAM)
        self.assertEqual(asyncio.run(check_login(mxid("breakglass"), None, None, [], None)), NOT_SPAM)

    def test_call_events_are_rejected(self) -> None:
        event = SimpleNamespace(type="m.call.invite", state_key=None, content={})
        self.assertEqual(asyncio.run(self.api.callbacks["check_event_for_spam"](event)), Codes.FORBIDDEN)

    def test_lms_accounts_cannot_deactivate_themselves(self) -> None:
        check = self.api.callbacks["check_can_deactivate_user"]
        self.assertFalse(asyncio.run(check(mxid("student1"), False)))
        self.assertTrue(asyncio.run(check(mxid("student1"), True)))


if __name__ == "__main__":
    unittest.main()

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
        self.senders: dict[tuple[str, str], str] = {}


class FakeModuleApi:
    server_name = SERVER

    def __init__(self) -> None:
        self.callbacks: dict[str, Any] = {}
        self.users = {mxid(row["id"]) for row in USERS}
        self.rooms: dict[str, FakeRoom] = {}
        self.room_configs: dict[str, dict[str, Any]] = {}
        self.ratelimit_overrides: list[tuple[str, Any]] = []
        self.db_interactions: list[tuple[str, list[Any]]] = []
        self.aliases: dict[str, str] = {}
        self.account_data: dict[tuple[str, str], dict[str, Any]] = {}
        self.account_data_manager = SimpleNamespace(get_global=self._get_global, put_global=self._put_global)
        self.http_client = SimpleNamespace(get_json=self._get_json, post_json_get_json=self._post_json)

    def register_spam_checker_callbacks(self, **kwargs: Any) -> None:
        self.callbacks.update(kwargs)

    def register_third_party_rules_callbacks(self, **kwargs: Any) -> None:
        self.callbacks.update(kwargs)

    def register_ratelimit_callbacks(self, **kwargs: Any) -> None:
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

    async def run_db_interaction(self, desc: str, func: Any, *args: Any) -> Any:
        txn = SimpleNamespace(executed=[])
        txn.execute = lambda sql, params=(): txn.executed.append((sql, params))
        result = func(txn, *args)
        self.db_interactions.append((desc, txn.executed))
        return result

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
        self.room_configs[room_id] = config
        room.state[("m.room.create", "")] = {"room_version": config.get("room_version", "12")}
        room.senders[("m.room.create", "")] = user_id
        room.state[("m.room.member", user_id)] = {"membership": "join"}
        if "name" in config:
            room.state[("m.room.name", "")] = {"name": config["name"]}
        if "power_level_content_override" in config:
            room.state[("m.room.power_levels", "")] = config["power_level_content_override"]
        for event in config.get("initial_state", []):
            room.state[(event["type"], event["state_key"])] = event["content"]
        alias = f"#{config['room_alias_name']}:{SERVER}"
        self.aliases[alias] = room_id
        return room_id, alias

    async def get_room_state(self, room_id: str, event_filter: Any = None) -> dict[tuple[str, str], Any]:
        wanted = list(event_filter or [])
        room = self.rooms[room_id]
        return {
            key: SimpleNamespace(content=content, sender=room.senders.get(key))
            for key, content in room.state.items()
            if not wanted or any(key[0] == t and (k is None or key[1] == k) for t, k in wanted)
        }

    async def update_room_membership(self, sender: str, target: str, room_id: str, membership: str) -> None:
        self.ratelimit_overrides.append(
            (sender, await self.callbacks["get_ratelimit_override_for_user"](sender, "rc_joins.local"))
        )
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

    def membership(self, room_id: str, user: str) -> str | None:
        return self.api.rooms[room_id].state.get(("m.room.member", user), {}).get("membership")

    def add_trainer_room(self) -> str:
        room_id, _ = asyncio.run(
            self.api.create_room(
                mxid("trainer1"),
                {
                    "room_alias_name": "trainer-room",
                    # on_create_room pins course rooms to this version
                    "room_version": "11",
                    "initial_state": [{"type": "m.space.parent", "state_key": self.space_id, "content": {"via": [SERVER]}}],
                },
            )
        )
        self.api.rooms[room_id].state[("m.room.member", mxid("lms-sync"))] = {"membership": "invite"}
        self.api.rooms[self.space_id].state[("m.space.child", room_id)] = {"via": [SERVER]}
        return room_id

    def test_sync_creates_one_space_per_course_named_like_the_course(self) -> None:
        self.assertEqual(list(self.api.rooms), [self.space_id])
        self.assertEqual(self.api.room_configs[self.space_id]["name"], "Web")
        self.assertEqual(self.api.rooms[self.space_id].state[("de.artim_academy.course", "")], {"course_id": "c1"})

    def test_sync_joins_course_members_to_the_space(self) -> None:
        self.assertEqual(self.membership(self.space_id, mxid("trainer1")), "join")
        self.assertEqual(self.membership(self.space_id, mxid("student1")), "join")
        self.assertIsNone(self.membership(self.space_id, mxid("admin1")))

    def test_course_spaces_use_a_room_version_with_explicit_creator_levels(self) -> None:
        # From room version 12 on creators must not be listed in the power levels.
        self.assertEqual(self.api.room_configs[self.space_id]["room_version"], "11")

    def test_sync_is_not_ratelimited_while_managing_memberships(self) -> None:
        self.assertTrue(self.api.ratelimit_overrides)
        for sender, override in self.api.ratelimit_overrides:
            self.assertIsNotNone(override, sender)
            self.assertEqual(override.per_second, 0)

    def test_bot_is_exempt_from_the_request_ratelimiter(self) -> None:
        # The request ratelimiter only honours the ratelimit_override table, not module callbacks.
        statements = [sql for _, executed in self.api.db_interactions for sql, _ in executed]
        params = [p for _, executed in self.api.db_interactions for _, p in executed]
        self.assertTrue(any("ratelimit_override" in sql for sql in statements))
        self.assertIn((mxid("lms-sync"),), [tuple(p[:1]) for p in params])

    def test_normal_users_keep_their_ratelimits(self) -> None:
        check = self.api.callbacks["get_ratelimit_override_for_user"]
        self.assertIsNone(asyncio.run(check(mxid("student1"), "rc_joins.local")))
        self.assertIsNotNone(asyncio.run(check(mxid("lms-sync"), "rc_invites.per_room")))

    def test_sync_sets_trainer_power_level_in_the_space(self) -> None:
        users = self.api.rooms[self.space_id].state[("m.room.power_levels", "")]["users"]
        self.assertEqual(users[mxid("trainer1")], 100)
        self.assertNotIn(mxid("student1"), users)

    def test_trainer_rooms_are_managed_but_not_auto_joined(self) -> None:
        room_id = self.add_trainer_room()
        self.api.rooms[room_id].state[("m.room.member", mxid("intruder"))] = {"membership": "join"}

        asyncio.run(self.module.sync())

        self.assertEqual(self.membership(room_id, mxid("lms-sync")), "join")
        self.assertEqual(self.membership(room_id, mxid("intruder")), "leave")
        self.assertIsNone(self.membership(room_id, mxid("student1")))
        self.assertEqual(self.api.rooms[room_id].state[("m.room.power_levels", "")]["users"][mxid("trainer1")], 100)

    def test_sync_writes_summary_to_account_data(self) -> None:
        summary = self.api.account_data[(mxid("student1"), ACCOUNT_DATA_TYPE)]
        self.assertEqual(summary["roles"], ["student"])
        self.assertEqual(summary["courses"], [{"id": "c1", "title": "Web", "role": "student", "space_id": self.space_id}])

    def test_sync_renames_the_space_when_the_course_is_renamed(self) -> None:
        COURSES[0]["title"] = "Webentwicklung"
        try:
            asyncio.run(self.module.sync())
        finally:
            COURSES[0]["title"] = "Web"
        self.assertEqual(self.api.rooms[self.space_id].state[("m.room.name", "")], {"name": "Webentwicklung"})


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
        self.assertEqual(content["power_level_content_override"]["users"][mxid("trainer1")], 100)
        self.assertIn(mxid("lms-sync"), content["invite"])
        self.assertEqual(content["room_version"], "11")

    def test_invites_into_course_rooms(self) -> None:
        may_invite = self.api.callbacks["user_may_invite"]
        self.assertEqual(asyncio.run(may_invite(mxid("student1"), mxid("trainer1"), self.space_id)), NOT_SPAM)
        self.assertEqual(asyncio.run(may_invite(mxid("student1"), mxid("nobody"), self.space_id)), Codes.FORBIDDEN)

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


@unittest.skipIf(ArtimLms is None, "synapse is not installed")
class LegacyCourseRoomsTest(unittest.TestCase):
    """Rooms left over from the first rollout: version 12 spaces without name and an extra general room."""

    def setUp(self) -> None:
        self.api = FakeModuleApi()
        bot = mxid("lms-sync")
        self.api.users.add(bot)
        self.space_id, _ = asyncio.run(
            self.api.create_room(bot, {"room_alias_name": "course-c1", "creation_content": {"type": "m.space"}})
        )
        self.general_id, _ = asyncio.run(
            self.api.create_room(
                bot,
                {
                    "room_alias_name": "course-c1-general",
                    "room_version": "11",
                    "power_level_content_override": {"users": {bot: 100}},
                },
            )
        )
        self.api.rooms[self.space_id].state[("m.space.child", self.general_id)] = {"via": [SERVER]}
        self.api.rooms[self.general_id].state[("m.room.member", mxid("student1"))] = {"membership": "join"}
        self.api.rooms[self.general_id].state[("m.room.member", mxid("admin1"))] = {"membership": "join"}
        self.module = ArtimLms(ArtimLms.parse_config(CONFIG), self.api)
        asyncio.run(self.module.sync())

    def test_space_gets_the_course_name(self) -> None:
        self.assertEqual(self.api.rooms[self.space_id].state[("m.room.name", "")], {"name": "Web"})

    def test_creator_is_left_out_of_the_space_power_levels(self) -> None:
        users = self.api.rooms[self.space_id].state[("m.room.power_levels", "")]["users"]
        self.assertNotIn(mxid("lms-sync"), users)
        self.assertEqual(users[mxid("trainer1")], 100)

    def test_general_room_is_retired(self) -> None:
        general = self.api.rooms[self.general_id].state
        self.assertEqual(general[("m.room.member", mxid("student1"))], {"membership": "leave"})
        self.assertEqual(general[("m.room.member", mxid("lms-sync"))], {"membership": "leave"})
        # Admins share the bot's power level and cannot be kicked.
        self.assertEqual(general[("m.room.member", mxid("admin1"))], {"membership": "join"})
        self.assertEqual(self.api.rooms[self.space_id].state[("m.space.child", self.general_id)], {})


if __name__ == "__main__":
    unittest.main()

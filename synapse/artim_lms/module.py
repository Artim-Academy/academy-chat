"""Synapse module: syncs roles, course spaces and memberships from the Artim Academy LMS and enforces permissions."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from synapse.api.errors import Codes, SynapseError
from synapse.module_api import NOT_SPAM, ModuleApi
from synapse.types import Requester

from .lms_client import LmsClient, LmsConfig
from .policy import LmsCourse, LmsSnapshot, Policy

logger = logging.getLogger(__name__)

ACCOUNT_DATA_TYPE = "de.artim_academy.lms_sync"
COURSE_STATE_TYPE = "de.artim_academy.course"
SPACE_PARENT = "m.space.parent"
SPACE_CHILD = "m.space.child"
MEMBER = "m.room.member"
POWER_LEVELS = "m.room.power_levels"
# Refresh the visible sync time at most hourly, so not every sync run pushes account data to all clients.
SYNCED_AT_REFRESH_MS = 60 * 60 * 1000


class ArtimLms:
    def __init__(self, config: Mapping[str, Any], api: ModuleApi) -> None:
        self._api = api
        self._server_name = api.server_name
        self._bot = f"@{config.get('bot_localpart', 'lms-sync')}:{self._server_name}"
        self._bot_displayname = config.get("bot_displayname", "Artim Academy")
        self._extra_admins = frozenset(config.get("extra_admins", [])) | {self._bot}
        self._global_rooms: list[str] = list(config.get("global_rooms", []))
        self._general_room_name: str = config.get("general_room_name", "Allgemein")
        self._policy = Policy(LmsSnapshot.empty(), self._server_name, self._extra_admins)
        self._room_course: dict[str, str | None] = {}
        self._course_space: dict[str, str] = {}
        self._syncing = False

        self._client = LmsClient(
            LmsConfig(
                base_url=config["lms_base_url"].rstrip("/"),
                tenant_id=config["tenant_id"],
                sync_token=config["sync_token"],
                client_id=config["client_id"],
                service_user_id=config["service_user_id"],
                enrollment_statuses=frozenset(config.get("enrollment_statuses", ["active", "paused"])),
            ),
            self._get_json,
            self._post_json,
        )

        api.register_spam_checker_callbacks(
            user_may_create_room=self.user_may_create_room,
            user_may_invite=self.user_may_invite,
            user_may_join_room=self.user_may_join_room,
            user_may_create_room_alias=self.user_may_create_room_alias,
            user_may_publish_room=self.user_may_publish_room,
            check_username_for_spam=self.check_username_for_spam,
            check_event_for_spam=self.check_event_for_spam,
            check_login_for_spam=self.check_login_for_spam,
        )
        api.register_third_party_rules_callbacks(
            on_create_room=self.on_create_room, check_can_deactivate_user=self.check_can_deactivate_user
        )
        api.register_account_validity_callbacks(on_user_login=self.on_user_login)

        interval_ms = int(config.get("sync_interval_seconds", 300)) * 1000
        api.looping_background_call(self.sync, interval_ms, desc="artim_lms_sync")
        api.delayed_background_call(1000, self.sync, desc="artim_lms_initial_sync")

    @staticmethod
    def parse_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
        for key in ("lms_base_url", "tenant_id", "sync_token", "client_id", "service_user_id"):
            if not config.get(key):
                raise Exception(f"artim_lms: missing required config option '{key}'")
        return config

    async def _get_json(self, url: str, args: dict[str, Any], token: str) -> Mapping[str, Any]:
        return await self._api.http_client.get_json(url, args, headers={"Authorization": [f"Bearer {token}"]})

    async def _post_json(self, url: str, body: dict[str, Any], token: str) -> Mapping[str, Any]:
        return await self._api.http_client.post_json_get_json(
            url, body, headers={"Authorization": [f"Bearer {token}"]}
        )

    # Permission checks

    async def user_may_create_room(self, user_id: str, room_config: Mapping[str, Any]) -> Any:
        is_space = room_config.get("creation_content", {}).get("type") == "m.space"
        allowed = self._policy.may_create_room(
            user_id,
            parent_course=self._parent_course(room_config),
            is_space=is_space,
            is_direct=bool(room_config.get("is_direct")),
            invitees=room_config.get("invite", []),
        )
        return NOT_SPAM if allowed else Codes.FORBIDDEN

    async def user_may_invite(self, inviter: str, invitee: str, room_id: str) -> Any:
        course = await self._room_course_of(room_id)
        return NOT_SPAM if self._policy.may_invite(inviter, invitee, course) else Codes.FORBIDDEN

    async def user_may_join_room(self, user_id: str, room_id: str, is_invited: bool) -> Any:
        course = await self._room_course_of(room_id)
        return NOT_SPAM if self._policy.may_join(user_id, course) else Codes.FORBIDDEN

    async def user_may_create_room_alias(self, user_id: str, room_alias: Any) -> Any:
        return NOT_SPAM if self._policy.may_create_alias(user_id) else Codes.FORBIDDEN

    async def user_may_publish_room(self, user_id: str, room_id: str) -> Any:
        return NOT_SPAM if self._policy.may_publish_room(user_id) else Codes.FORBIDDEN

    async def check_username_for_spam(self, user_profile: Mapping[str, Any], requester_id: str) -> bool:
        return not self._policy.may_see_in_directory(requester_id, user_profile["user_id"])

    async def check_event_for_spam(self, event: Any) -> Any:
        if Policy.is_call_event(event.type, getattr(event, "state_key", None), event.content):
            return Codes.FORBIDDEN
        return NOT_SPAM

    async def check_login_for_spam(
        self,
        user_id: str,
        device_id: str | None,
        initial_display_name: str | None,
        request_info: Any,
        auth_provider_id: str | None = None,
    ) -> Any:
        # Single sign-on logins carry the id of the identity provider, password logins do not.
        if auth_provider_id is None and not self._policy.may_login_with_password(user_id):
            return Codes.FORBIDDEN
        return NOT_SPAM

    async def on_create_room(self, requester: Requester, request_content: dict, is_requester_admin: bool) -> None:
        creator = requester.user.to_string()
        if creator == self._bot:
            return
        course = self._parent_course(request_content)
        if course is None:
            return
        if not self._policy.may_create_room(creator, parent_course=course):
            raise SynapseError(403, "Only trainers of this course may create rooms in it.", Codes.FORBIDDEN)

        creator_level = 100 if self._policy.is_admin(creator) else 50
        request_content["power_level_content_override"] = {
            **Policy.default_course_power_levels(),
            "users": {creator: creator_level, self._bot: 100},
        }
        # The bot has to be in the room to keep roles in line with the LMS later on.
        request_content["invite"] = [*request_content.get("invite", []), self._bot]

    async def check_can_deactivate_user(self, user_id: str, by_admin: bool) -> bool:
        return self._policy.may_deactivate(user_id, by_admin)

    async def on_user_login(self, user_id: str, auth_provider_type: str | None, auth_provider_id: str | None) -> None:
        if self._policy.lms_id(user_id) not in self._policy.snapshot.users:
            await self.sync()

    def _parent_course(self, room_config: Mapping[str, Any]) -> str | None:
        for event in room_config.get("initial_state", []):
            if event.get("type") == SPACE_PARENT:
                course = self._room_course.get(event.get("state_key", ""))
                if course:
                    return course
        return None

    async def _room_course_of(self, room_id: str) -> str | None:
        if room_id in self._room_course:
            return self._room_course[room_id]
        state = await self._api.get_room_state(room_id, [(COURSE_STATE_TYPE, ""), (SPACE_PARENT, None)])
        course: str | None = None
        for (event_type, state_key), event in state.items():
            if event_type == COURSE_STATE_TYPE:
                course = event.content.get("course_id")
            elif event_type == SPACE_PARENT and event.content.get("via"):
                course = course or self._room_course.get(state_key)
        self._room_course[room_id] = course
        return course

    # Sync

    async def sync(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            snapshot = await self._fetch_snapshot()
            if snapshot is None:
                return
            self._policy = Policy(snapshot, self._server_name, self._extra_admins)
            await self._ensure_bot()
            room_course: dict[str, str | None] = {}
            for course in snapshot.courses.values():
                try:
                    room_course.update(await self._sync_course(course))
                except Exception:
                    logger.exception("artim_lms: syncing course %s failed", course.course_id)
            self._room_course = room_course
            await self._sync_global_rooms()
            await self._sync_account_data()
            logger.info("artim_lms: synced %d users and %d courses", len(snapshot.users), len(snapshot.courses))
        finally:
            self._syncing = False

    async def _fetch_snapshot(self) -> LmsSnapshot | None:
        try:
            return await self._client.fetch_snapshot()
        except Exception:
            logger.exception("artim_lms: fetching the LMS failed, retrying with a fresh token")
            self._client.forget_token()
        try:
            return await self._client.fetch_snapshot()
        except Exception:
            logger.exception("artim_lms: fetching the LMS failed, keeping the last known roles")
            return None

    async def _ensure_bot(self) -> None:
        localpart = self._bot.split(":")[0].lstrip("@")
        if await self._api.check_user_exists(self._bot) is None:
            await self._api.register_user(localpart, displayname=self._bot_displayname)

    async def _resolve_alias(self, alias: str) -> str | None:
        try:
            room_id, _ = await self._api.lookup_room_alias(alias)
            return room_id
        except SynapseError:
            return None

    async def _ensure_room(self, alias_name: str, config: dict[str, Any]) -> str:
        existing = await self._resolve_alias(f"#{alias_name}:{self._server_name}")
        if existing:
            return existing
        room_id, _ = await self._api.create_room(
            self._bot, {**config, "room_alias_name": alias_name, "preset": "private_chat"}, ratelimit=False
        )
        return room_id

    async def _sync_course(self, course: LmsCourse) -> dict[str, str | None]:
        marker = {"type": COURSE_STATE_TYPE, "state_key": "", "content": {"course_id": course.course_id}}
        power_levels = {**Policy.default_course_power_levels(), "users": {self._bot: 100}}
        space_id = await self._ensure_room(
            f"course-{course.course_id}",
            {
                "name": course.title,
                "creation_content": {"type": "m.space"},
                "initial_state": [marker],
                "power_level_content_override": power_levels,
            },
        )
        self._course_space[course.course_id] = space_id
        general_id = await self._ensure_room(
            f"course-{course.course_id}-general",
            {
                "name": f"{course.title} – {self._general_room_name}",
                "initial_state": [
                    marker,
                    {"type": SPACE_PARENT, "state_key": space_id, "content": {"via": [self._server_name], "canonical": True}},
                ],
                "power_level_content_override": power_levels,
            },
        )
        await self._send_state(space_id, SPACE_CHILD, general_id, {"via": [self._server_name], "suggested": True})

        rooms = {space_id, general_id} | await self._space_children(space_id)
        members = {
            mxid
            for mxid in map(self._policy.mxid, self._policy.snapshot.members_of(course.course_id))
            if await self._api.check_user_exists(mxid)
        }
        for room_id in rooms:
            await self._sync_room_members(room_id, course.course_id, members, auto_join=room_id in (space_id, general_id))
        return {room_id: course.course_id for room_id in rooms}

    async def _space_children(self, space_id: str) -> set[str]:
        state = await self._api.get_room_state(space_id, [(SPACE_CHILD, None)])
        return {state_key for (_, state_key), event in state.items() if event.content.get("via")}

    async def _memberships(self, room_id: str) -> dict[str, str]:
        state = await self._api.get_room_state(room_id, [(MEMBER, None)])
        return {state_key: event.content.get("membership", "") for (_, state_key), event in state.items()}

    async def _sync_room_members(self, room_id: str, course_id: str, members: set[str], auto_join: bool) -> None:
        memberships = await self._memberships(room_id)
        if memberships.get(self._bot) == "invite":
            await self._api.update_room_membership(self._bot, self._bot, room_id, "join")
        elif memberships.get(self._bot) != "join":
            logger.warning("artim_lms: bot is not in course room %s, skipping it", room_id)
            return

        for user_id, membership in memberships.items():
            removable = membership in ("join", "invite") and user_id not in members
            if removable and not self._policy.is_admin(user_id):
                await self._api.update_room_membership(self._bot, user_id, room_id, "leave")

        if auto_join:
            for user_id in members:
                if memberships.get(user_id) not in ("join", "ban"):
                    if memberships.get(user_id) != "invite":
                        await self._api.update_room_membership(self._bot, user_id, room_id, "invite")
                    await self._api.update_room_membership(user_id, user_id, room_id, "join")

        joined = [user_id for user_id, membership in (await self._memberships(room_id)).items() if membership == "join"]
        await self._apply_power_levels(
            room_id, lambda current: self._policy.course_power_levels(current, course_id, self._bot, joined)
        )

    async def _sync_global_rooms(self) -> None:
        for alias in self._global_rooms:
            room_id = await self._resolve_alias(alias) if alias.startswith("#") else alias
            if room_id is None:
                continue
            try:
                joined = [user_id for user_id, membership in (await self._memberships(room_id)).items() if membership == "join"]
                await self._apply_power_levels(
                    room_id, lambda current: self._policy.global_power_levels(current, self._bot, joined)
                )
            except Exception:
                logger.exception("artim_lms: bot needs power level 100 in global room %s", alias)

    async def _apply_power_levels(self, room_id: str, update: Any) -> None:
        state = await self._api.get_room_state(room_id, [(POWER_LEVELS, "")])
        event = state.get((POWER_LEVELS, ""))
        current = dict(event.content) if event else {}
        updated = update(current)
        if updated != current:
            await self._send_state(room_id, POWER_LEVELS, "", updated)

    async def _send_state(self, room_id: str, event_type: str, state_key: str, content: dict[str, Any]) -> None:
        state = await self._api.get_room_state(room_id, [(event_type, state_key)])
        existing = state.get((event_type, state_key))
        if existing is not None and dict(existing.content) == content:
            return
        await self._api.create_and_send_event_into_room(
            {"type": event_type, "room_id": room_id, "sender": self._bot, "state_key": state_key, "content": content}
        )

    async def _sync_account_data(self) -> None:
        for lms_id in self._policy.snapshot.users:
            mxid = self._policy.mxid(lms_id)
            summary = self._policy.sync_summary(mxid)
            if summary is None or not await self._api.check_user_exists(mxid):
                continue
            for course in summary["courses"]:
                course["space_id"] = self._course_space.get(course["id"])
            current = await self._api.account_data_manager.get_global(mxid, ACCOUNT_DATA_TYPE)
            stale = current is None or summary["synced_at"] - current.get("synced_at", 0) > SYNCED_AT_REFRESH_MS
            if stale or self._without_timestamp(current) != self._without_timestamp(summary):
                await self._api.account_data_manager.put_global(mxid, ACCOUNT_DATA_TYPE, summary)

    @staticmethod
    def _without_timestamp(content: Mapping[str, Any] | None) -> dict[str, Any] | None:
        return None if content is None else {key: value for key, value in content.items() if key != "synced_at"}


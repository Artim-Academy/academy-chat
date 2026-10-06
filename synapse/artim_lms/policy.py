"""Permission rules of Artim Academy chat, derived from the roles synced from the LMS.

Role model (decided by Artim Academy):
- Admin: LMS admin, may do everything.
- Trainer (global): every user with the academy role "trainer".
- Trainer (course): the creator of an LMS course.
- Student (course): a user enrolled in an LMS course.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

ADMIN = "admin"
TRAINER = "trainer"
STUDENT = "student"

ADMIN_LEVEL = 100
TRAINER_LEVEL = 50

CALL_EVENT_PREFIXES = ("m.call", "org.matrix.msc3401.call", "m.rtc", "org.matrix.msc4143.rtc", "io.element.call")
WIDGET_EVENT_TYPES = ("im.vector.modular.widgets", "m.widget")
CALL_WIDGET_TYPES = ("jitsi", "m.jitsi", "m.call", "io.element.call")


@dataclass(frozen=True)
class LmsUser:
    user_id: str
    name: str
    email: str
    roles: frozenset[str]


@dataclass(frozen=True)
class LmsCourse:
    course_id: str
    title: str
    trainer_id: str | None


@dataclass(frozen=True)
class LmsSnapshot:
    users: Mapping[str, LmsUser]
    courses: Mapping[str, LmsCourse]
    students: Mapping[str, frozenset[str]]
    synced_at: int

    @staticmethod
    def empty() -> LmsSnapshot:
        return LmsSnapshot(users={}, courses={}, students={}, synced_at=0)

    def courses_of(self, lms_id: str) -> dict[str, str]:
        roles: dict[str, str] = {}
        for course_id, course in self.courses.items():
            if course.trainer_id == lms_id:
                roles[course_id] = TRAINER
            elif lms_id in self.students.get(course_id, ()):
                roles[course_id] = STUDENT
        return roles

    def members_of(self, course_id: str) -> frozenset[str]:
        course = self.courses.get(course_id)
        trainer = {course.trainer_id} if course and course.trainer_id else set()
        return frozenset(self.students.get(course_id, frozenset()) | trainer)


@dataclass
class Policy:
    snapshot: LmsSnapshot
    server_name: str
    extra_admins: frozenset[str] = field(default_factory=frozenset)

    def lms_id(self, mxid: str) -> str | None:
        localpart, _, server = mxid.lstrip("@").partition(":")
        return localpart if server == self.server_name else None

    def mxid(self, lms_id: str) -> str:
        return f"@{lms_id}:{self.server_name}"

    def _lms_user(self, mxid: str) -> LmsUser | None:
        lms_id = self.lms_id(mxid)
        return self.snapshot.users.get(lms_id) if lms_id else None

    def is_admin(self, mxid: str) -> bool:
        if mxid in self.extra_admins:
            return True
        user = self._lms_user(mxid)
        return user is not None and ADMIN in user.roles

    def is_trainer(self, mxid: str) -> bool:
        user = self._lms_user(mxid)
        return user is not None and TRAINER in user.roles

    def courses_of(self, mxid: str) -> dict[str, str]:
        lms_id = self.lms_id(mxid)
        return self.snapshot.courses_of(lms_id) if lms_id else {}

    def is_course_trainer(self, mxid: str, course_id: str) -> bool:
        return self.courses_of(mxid).get(course_id) == TRAINER

    def is_course_member(self, mxid: str, course_id: str) -> bool:
        return course_id in self.courses_of(mxid)

    def share_course(self, a: str, b: str) -> bool:
        return not self.courses_of(a).keys().isdisjoint(self.courses_of(b).keys())

    def _may_contact(self, sender: str, target: str) -> bool:
        return self.is_admin(sender) or self.is_trainer(sender) or self.share_course(sender, target)

    def may_create_room(
        self,
        mxid: str,
        parent_course: str | None = None,
        is_space: bool = False,
        is_direct: bool = False,
        invitees: Iterable[str] = (),
    ) -> bool:
        if self.is_admin(mxid):
            return True
        if is_space:
            return False
        if is_direct:
            targets = list(invitees)
            if self.is_trainer(mxid):
                return True
            return bool(targets) and all(self.share_course(mxid, target) for target in targets)
        return parent_course is not None and self.is_course_trainer(mxid, parent_course)

    def may_invite(self, inviter: str, invitee: str, room_course: str | None) -> bool:
        if self.is_admin(inviter):
            return True
        if room_course is None:
            return self._may_contact(inviter, invitee)
        return self.is_course_member(inviter, room_course) and (
            self.is_course_member(invitee, room_course) or self.is_admin(invitee)
        )

    def may_join(self, mxid: str, room_course: str | None) -> bool:
        if room_course is None:
            return True
        return self.is_admin(mxid) or self.is_course_member(mxid, room_course)

    def may_see_in_directory(self, requester: str, target: str) -> bool:
        return self._may_contact(requester, target)

    def may_create_alias(self, mxid: str) -> bool:
        return self.is_admin(mxid) or TRAINER in self.courses_of(mxid).values()

    def may_publish_room(self, mxid: str) -> bool:
        return self.is_admin(mxid)

    def may_login_with_password(self, mxid: str) -> bool:
        return mxid in self.extra_admins

    def may_deactivate(self, mxid: str, by_admin: bool) -> bool:
        return by_admin or self._lms_user(mxid) is None

    @staticmethod
    def is_call_event(event_type: str, state_key: str | None, content: Mapping[str, Any]) -> bool:
        if event_type.startswith(CALL_EVENT_PREFIXES):
            return True
        return event_type in WIDGET_EVENT_TYPES and content.get("type") in CALL_WIDGET_TYPES

    @staticmethod
    def default_course_power_levels() -> dict[str, Any]:
        return {
            "users_default": 0,
            # Students stay read-only until a trainer opens the room for them.
            "events_default": TRAINER_LEVEL,
            "state_default": TRAINER_LEVEL,
            "invite": 0,
            "kick": TRAINER_LEVEL,
            "ban": TRAINER_LEVEL,
            "redact": TRAINER_LEVEL,
            "notifications": {"room": 0},
            "events": {
                "m.room.name": TRAINER_LEVEL,
                "m.room.topic": TRAINER_LEVEL,
                "m.room.avatar": TRAINER_LEVEL,
                "m.room.canonical_alias": TRAINER_LEVEL,
                "m.room.join_rules": TRAINER_LEVEL,
                "m.room.history_visibility": TRAINER_LEVEL,
                "m.room.power_levels": TRAINER_LEVEL,
                "m.room.encryption": TRAINER_LEVEL,
                "m.space.child": TRAINER_LEVEL,
                "im.vector.modular.widgets": TRAINER_LEVEL,
                "m.room.pinned_events": 0,
                "m.room.redaction": 0,
                "m.room.guest_access": ADMIN_LEVEL,
                "m.room.server_acl": ADMIN_LEVEL,
                "m.room.tombstone": ADMIN_LEVEL,
            },
        }

    def course_power_levels(
        self, current: Mapping[str, Any], course_id: str, bot: str, joined: Iterable[str]
    ) -> dict[str, Any]:
        """Re-assert the role based user levels and leave everything a trainer configured untouched."""
        users: dict[str, int] = {bot: ADMIN_LEVEL}
        for member in joined:
            if self.is_admin(member):
                users[member] = ADMIN_LEVEL
        course = self.snapshot.courses.get(course_id)
        if course and course.trainer_id:
            users.setdefault(self.mxid(course.trainer_id), TRAINER_LEVEL)
        return {**current, "users": users}

    def global_power_levels(self, current: Mapping[str, Any], bot: str, joined: Iterable[str]) -> dict[str, Any]:
        users = {bot: ADMIN_LEVEL, **{member: ADMIN_LEVEL for member in joined if self.is_admin(member)}}
        return {
            **current,
            "events_default": ADMIN_LEVEL,
            "state_default": ADMIN_LEVEL,
            "invite": ADMIN_LEVEL,
            "users": users,
        }

    def sync_summary(self, mxid: str) -> dict[str, Any] | None:
        user = self._lms_user(mxid)
        if user is None:
            return None
        courses = [
            {"id": course_id, "title": self.snapshot.courses[course_id].title, "role": role}
            for course_id, role in sorted(self.courses_of(mxid).items())
        ]
        return {
            "lms_user_id": user.user_id,
            "name": user.name,
            "email": user.email,
            "roles": sorted(user.roles),
            "is_admin": self.is_admin(mxid),
            "courses": courses,
            "synced_at": self.snapshot.synced_at,
        }

import unittest

from artim_lms.policy import LmsCourse, LmsSnapshot, LmsUser, Policy

SERVER = "artim-academy.de"


def mxid(localpart: str) -> str:
    return f"@{localpart}:{SERVER}"


def make_policy() -> Policy:
    users = {
        "admin1": LmsUser("admin1", "Ada Admin", "ada@example.org", frozenset({"admin"})),
        "trainer1": LmsUser("trainer1", "Tom Trainer", "tom@example.org", frozenset({"trainer"})),
        "trainer2": LmsUser("trainer2", "Tina Trainer", "tina@example.org", frozenset({"trainer"})),
        "student1": LmsUser("student1", "Sam Student", "sam@example.org", frozenset({"student"})),
        "student2": LmsUser("student2", "Sara Student", "sara@example.org", frozenset({"student"})),
        "student3": LmsUser("student3", "Sven Student", "sven@example.org", frozenset({"student"})),
    }
    courses = {
        "web": LmsCourse("web", "Webentwicklung", "trainer1"),
        "db": LmsCourse("db", "Datenbanken", "trainer2"),
    }
    students = {"web": frozenset({"student1", "student2"}), "db": frozenset({"student3"})}
    snapshot = LmsSnapshot(users=users, courses=courses, students=students, synced_at=1)
    return Policy(snapshot, SERVER, extra_admins=frozenset({mxid("breakglass")}))


class RoleResolutionTest(unittest.TestCase):
    def test_admins_come_from_lms_and_config(self) -> None:
        policy = make_policy()
        self.assertTrue(policy.is_admin(mxid("admin1")))
        self.assertTrue(policy.is_admin(mxid("breakglass")))
        self.assertFalse(policy.is_admin(mxid("trainer1")))

    def test_foreign_server_users_are_unknown(self) -> None:
        policy = make_policy()
        self.assertFalse(policy.is_admin("@admin1:example.org"))
        self.assertEqual(policy.courses_of("@student1:example.org"), {})

    def test_trainer_of_course_is_its_creator(self) -> None:
        policy = make_policy()
        self.assertEqual(policy.courses_of(mxid("trainer1")), {"web": "trainer"})
        self.assertEqual(policy.courses_of(mxid("student1")), {"web": "student"})


class CreateRoomTest(unittest.TestCase):
    def test_trainer_may_create_room_only_in_own_course(self) -> None:
        policy = make_policy()
        self.assertTrue(policy.may_create_room(mxid("trainer1"), parent_course="web"))
        self.assertFalse(policy.may_create_room(mxid("trainer1"), parent_course="db"))
        self.assertFalse(policy.may_create_room(mxid("trainer1"), parent_course=None))

    def test_students_may_not_create_rooms(self) -> None:
        policy = make_policy()
        self.assertFalse(policy.may_create_room(mxid("student1"), parent_course="web"))

    def test_only_admins_may_create_spaces(self) -> None:
        policy = make_policy()
        self.assertTrue(policy.may_create_room(mxid("admin1"), is_space=True))
        self.assertFalse(policy.may_create_room(mxid("trainer1"), parent_course="web", is_space=True))

    def test_trainer_may_start_dm_with_anyone(self) -> None:
        policy = make_policy()
        self.assertTrue(policy.may_create_room(mxid("trainer1"), is_direct=True, invitees=[mxid("student3")]))

    def test_student_may_start_dm_only_within_shared_course(self) -> None:
        policy = make_policy()
        self.assertTrue(policy.may_create_room(mxid("student1"), is_direct=True, invitees=[mxid("student2")]))
        self.assertTrue(policy.may_create_room(mxid("student1"), is_direct=True, invitees=[mxid("trainer1")]))
        self.assertFalse(policy.may_create_room(mxid("student1"), is_direct=True, invitees=[mxid("student3")]))
        self.assertFalse(policy.may_create_room(mxid("student1"), is_direct=True, invitees=[]))


class InviteTest(unittest.TestCase):
    def test_course_members_may_invite_course_members_into_course_rooms(self) -> None:
        policy = make_policy()
        self.assertTrue(policy.may_invite(mxid("student1"), mxid("student2"), room_course="web"))
        self.assertTrue(policy.may_invite(mxid("trainer1"), mxid("student2"), room_course="web"))
        self.assertFalse(policy.may_invite(mxid("student1"), mxid("student3"), room_course="web"))
        self.assertFalse(policy.may_invite(mxid("student3"), mxid("student1"), room_course="web"))
        self.assertFalse(policy.may_invite(mxid("trainer2"), mxid("student1"), room_course="web"))

    def test_invites_outside_courses_follow_dm_rules(self) -> None:
        policy = make_policy()
        self.assertTrue(policy.may_invite(mxid("trainer1"), mxid("student3"), room_course=None))
        self.assertTrue(policy.may_invite(mxid("student1"), mxid("trainer1"), room_course=None))
        self.assertFalse(policy.may_invite(mxid("student1"), mxid("student3"), room_course=None))

    def test_admins_may_invite_anyone_anywhere(self) -> None:
        policy = make_policy()
        self.assertTrue(policy.may_invite(mxid("admin1"), mxid("student3"), room_course="web"))


class JoinTest(unittest.TestCase):
    def test_course_rooms_are_only_for_course_members_and_admins(self) -> None:
        policy = make_policy()
        self.assertTrue(policy.may_join(mxid("student1"), room_course="web"))
        self.assertTrue(policy.may_join(mxid("admin1"), room_course="web"))
        self.assertFalse(policy.may_join(mxid("student3"), room_course="web"))
        self.assertTrue(policy.may_join(mxid("student3"), room_course=None))


class DirectoryTest(unittest.TestCase):
    def test_trainers_and_admins_find_everyone(self) -> None:
        policy = make_policy()
        self.assertTrue(policy.may_see_in_directory(mxid("trainer1"), mxid("student3")))
        self.assertTrue(policy.may_see_in_directory(mxid("admin1"), mxid("student3")))

    def test_students_find_only_people_from_their_courses(self) -> None:
        policy = make_policy()
        self.assertTrue(policy.may_see_in_directory(mxid("student1"), mxid("student2")))
        self.assertTrue(policy.may_see_in_directory(mxid("student1"), mxid("trainer1")))
        self.assertFalse(policy.may_see_in_directory(mxid("student1"), mxid("student3")))
        self.assertFalse(policy.may_see_in_directory(mxid("student1"), mxid("trainer2")))


class ServerLevelTest(unittest.TestCase):
    def test_aliases_for_admins_and_course_trainers(self) -> None:
        policy = make_policy()
        self.assertTrue(policy.may_create_alias(mxid("trainer1")))
        self.assertFalse(policy.may_create_alias(mxid("student1")))

    def test_only_admins_publish_to_room_directory(self) -> None:
        policy = make_policy()
        self.assertTrue(policy.may_publish_room(mxid("admin1")))
        self.assertFalse(policy.may_publish_room(mxid("trainer1")))

    def test_password_login_only_for_break_glass_accounts(self) -> None:
        policy = make_policy()
        self.assertTrue(policy.may_login_with_password(mxid("breakglass")))
        self.assertFalse(policy.may_login_with_password(mxid("admin1")))
        self.assertFalse(policy.may_login_with_password(mxid("student1")))


class DeactivationTest(unittest.TestCase):
    def test_lms_accounts_may_only_be_deactivated_by_server_admins(self) -> None:
        policy = make_policy()
        self.assertFalse(policy.may_deactivate(mxid("student1"), by_admin=False))
        self.assertTrue(policy.may_deactivate(mxid("student1"), by_admin=True))
        self.assertTrue(policy.may_deactivate(mxid("breakglass"), by_admin=False))


class CallBlockingTest(unittest.TestCase):
    def test_call_events_are_blocked(self) -> None:
        self.assertTrue(Policy.is_call_event("m.call.invite", None, {}))
        self.assertTrue(Policy.is_call_event("org.matrix.msc3401.call.member", "", {}))
        self.assertTrue(Policy.is_call_event("m.rtc.member", "", {}))

    def test_jitsi_widgets_are_blocked_but_other_widgets_pass(self) -> None:
        self.assertTrue(Policy.is_call_event("im.vector.modular.widgets", "w1", {"type": "jitsi"}))
        self.assertTrue(Policy.is_call_event("im.vector.modular.widgets", "w1", {"type": "m.jitsi"}))
        self.assertTrue(Policy.is_call_event("im.vector.modular.widgets", "w1", {"type": "m.call"}))
        self.assertFalse(Policy.is_call_event("im.vector.modular.widgets", "w1", {"type": "m.custom"}))
        self.assertFalse(Policy.is_call_event("m.room.message", None, {"msgtype": "m.text"}))


class PowerLevelsTest(unittest.TestCase):
    def test_course_power_levels_keep_room_settings_and_enforce_roles(self) -> None:
        policy = make_policy()
        current = {
            "events_default": 0,
            "users": {mxid("student1"): 50, mxid("trainer1"): 100, mxid("bot"): 100, "@guest:other.org": 10},
        }
        updated = policy.course_power_levels(current, "web", bot=mxid("bot"), joined=[mxid("admin1")])

        self.assertEqual(updated["events_default"], 0)
        self.assertEqual(
            updated["users"],
            {mxid("bot"): 100, mxid("admin1"): 100, mxid("trainer1"): 50},
        )

    def test_global_rooms_are_admin_only(self) -> None:
        policy = make_policy()
        current = {"events_default": 0, "invite": 0, "users": {mxid("trainer1"): 100, mxid("bot"): 100}}
        updated = policy.global_power_levels(current, bot=mxid("bot"), joined=[mxid("admin1"), mxid("student1")])

        self.assertEqual(updated["events_default"], 100)
        self.assertEqual(updated["invite"], 100)
        self.assertEqual(updated["state_default"], 100)
        self.assertEqual(updated["users"], {mxid("bot"): 100, mxid("admin1"): 100})

    def test_default_course_power_levels_mute_students(self) -> None:
        levels = Policy.default_course_power_levels()
        self.assertEqual(levels["events_default"], 50)
        self.assertEqual(levels["invite"], 0)
        self.assertEqual(levels["kick"], 50)
        self.assertEqual(levels["notifications"], {"room": 0})
        self.assertEqual(levels["events"]["m.room.pinned_events"], 0)
        self.assertEqual(levels["events"]["m.room.power_levels"], 50)


class AccountDataTest(unittest.TestCase):
    def test_sync_summary_lists_roles_and_courses(self) -> None:
        policy = make_policy()
        summary = policy.sync_summary(mxid("trainer1"))

        self.assertEqual(summary["lms_user_id"], "trainer1")
        self.assertEqual(summary["name"], "Tom Trainer")
        self.assertEqual(summary["roles"], ["trainer"])
        self.assertFalse(summary["is_admin"])
        self.assertEqual(summary["courses"], [{"id": "web", "title": "Webentwicklung", "role": "trainer"}])
        self.assertEqual(summary["synced_at"], 1)

    def test_no_summary_for_users_unknown_to_lms(self) -> None:
        self.assertIsNone(make_policy().sync_summary(mxid("breakglass")))


if __name__ == "__main__":
    unittest.main()

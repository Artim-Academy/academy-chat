/*
Copyright 2026 Artim Academy

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE in the repository root for full details.
*/

import React, { type JSX } from "react";
import { Badge, Button, Heading, Text } from "@vector-im/compound-web";

import styles from "./LmsSyncView.module.css";
import { type ViewModel, useViewModel } from "../../core/viewmodel";
import { Flex } from "../../core/utils/Flex";
import { useI18n } from "../../core/i18n/i18nContext";
import { _td } from "../../core/i18n/i18n";

/**
 * A course the user belongs to in the LMS.
 */
export interface LmsSyncCourse {
    /** The LMS id of the course. */
    id: string;
    /** The course title. */
    title: string;
    /** The role of the user in this course. */
    role: "trainer" | "student";
    /** The space that was created for the course, if it exists yet. */
    spaceId?: string;
}

export interface LmsSyncViewSnapshot {
    /** Whether the LMS sync has written any data for this account yet. */
    isSynced: boolean;
    /** The name stored in the LMS. */
    name: string;
    /** The email address stored in the LMS. */
    email: string;
    /** The LMS user id, which is also the Matrix localpart. */
    lmsUserId: string;
    /** The academy roles of the user. */
    roles: string[];
    /** Whether the user is an LMS admin. */
    isAdmin: boolean;
    /** The courses the user is enrolled in or teaches. */
    courses: LmsSyncCourse[];
    /** The formatted time of the last sync. */
    lastSynced: string;
}

export interface LmsSyncViewActions {
    /** Opens the space of a course. */
    onOpenCourse: (spaceId: string) => void;
}

/**
 * The view model for the LMS sync settings page.
 */
export type LmsSyncViewModel = ViewModel<LmsSyncViewSnapshot, LmsSyncViewActions>;

interface LmsSyncViewProps {
    /** The view model for the LMS sync settings page. */
    vm: LmsSyncViewModel;
}

const ROLE_KEYS: Record<string, TranslationKey> = {
    admin: _td("settings|lms_sync|role_admin"),
    trainer: _td("settings|lms_sync|role_trainer"),
    student: _td("settings|lms_sync|role_student"),
};

/**
 * Shows what the Artim Academy LMS synced for the current account: profile, roles and courses.
 */
export function LmsSyncView({ vm }: Readonly<LmsSyncViewProps>): JSX.Element {
    const { translate: _t } = useI18n();
    const { isSynced, name, email, lmsUserId, roles, isAdmin, courses, lastSynced } = useViewModel(vm);
    const roleLabel = (role: string): string => (ROLE_KEYS[role] ? _t(ROLE_KEYS[role]) : role);

    if (!isSynced) {
        return (
            <Text className={styles.empty} size="md">
                {_t("settings|lms_sync|not_synced")}
            </Text>
        );
    }

    return (
        <Flex direction="column" gap="var(--cpd-space-6x)" className={styles.view}>
            <Text size="sm" className={styles.hint}>
                {_t("settings|lms_sync|description")}
            </Text>

            <section>
                <Heading as="h3" size="sm" weight="semibold">
                    {_t("settings|lms_sync|profile_heading")}
                </Heading>
                <dl className={styles.details}>
                    <dt>{_t("settings|lms_sync|name")}</dt>
                    <dd>{name}</dd>
                    <dt>{_t("settings|lms_sync|email")}</dt>
                    <dd>{email}</dd>
                    <dt>{_t("settings|lms_sync|lms_user_id")}</dt>
                    <dd>
                        <code>{lmsUserId}</code>
                    </dd>
                    <dt>{_t("settings|lms_sync|last_synced")}</dt>
                    <dd>{lastSynced}</dd>
                </dl>
            </section>

            <section>
                <Heading as="h3" size="sm" weight="semibold">
                    {_t("settings|lms_sync|roles_heading")}
                </Heading>
                <Flex gap="var(--cpd-space-2x)" wrap="wrap" className={styles.roles}>
                    {isAdmin && !roles.includes("admin") && <Badge kind="blue">{roleLabel("admin")}</Badge>}
                    {roles.map((role) => (
                        <Badge key={role} kind={role === "admin" ? "blue" : "grey"}>
                            {roleLabel(role)}
                        </Badge>
                    ))}
                </Flex>
            </section>

            <section>
                <Heading as="h3" size="sm" weight="semibold">
                    {_t("settings|lms_sync|courses_heading")}
                </Heading>
                {courses.length === 0 ? (
                    <Text size="sm" className={styles.hint}>
                        {_t("settings|lms_sync|no_courses")}
                    </Text>
                ) : (
                    <ul className={styles.courses}>
                        {courses.map((course) => (
                            <li key={course.id} className={styles.course}>
                                <Flex align="center" justify="space-between" gap="var(--cpd-space-3x)">
                                    <Flex direction="column" gap="var(--cpd-space-1x)">
                                        <Text size="md" weight="medium">
                                            {course.title}
                                        </Text>
                                        <Badge kind={course.role === "trainer" ? "green" : "grey"}>
                                            {roleLabel(course.role)}
                                        </Badge>
                                    </Flex>
                                    {course.spaceId && (
                                        <Button
                                            kind="secondary"
                                            size="md"
                                            aria-label={_t("settings|lms_sync|open_course", { title: course.title })}
                                            onClick={() => vm.onOpenCourse(course.spaceId!)}
                                        >
                                            {_t("settings|lms_sync|open")}
                                        </Button>
                                    )}
                                </Flex>
                            </li>
                        ))}
                    </ul>
                )}
            </section>
        </Flex>
    );
}

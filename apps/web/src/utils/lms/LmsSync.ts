/*
Copyright 2026 Artim Academy

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE in the repository root for full details.
*/

import { type MatrixClient } from "matrix-js-sdk/src/matrix";

/**
 * Global account data written by the Artim Academy LMS sync module in Synapse.
 */
export const LMS_SYNC_EVENT_TYPE = "de.artim_academy.lms_sync";

/**
 * A course the user belongs to, as synced from the LMS.
 */
export interface LmsSyncCourseSummary {
    id: string;
    title: string;
    role: "trainer" | "student";
    space_id?: string | null;
}

/**
 * What the LMS sync knows about the current account.
 */
export interface LmsSyncSummary {
    lms_user_id: string;
    name: string;
    email: string;
    roles: string[];
    is_admin: boolean;
    courses: LmsSyncCourseSummary[];
    /** Unix timestamp in milliseconds. */
    synced_at: number;
}

/**
 * Returns the LMS sync summary of the logged in user, if the account is managed by the LMS.
 */
export function getLmsSyncSummary(cli: MatrixClient): LmsSyncSummary | undefined {
    const content = cli.getAccountData(LMS_SYNC_EVENT_TYPE)?.getContent<LmsSyncSummary>();
    return content?.lms_user_id ? content : undefined;
}

/**
 * Whether profile, password and contact details of the logged in user are managed by the LMS.
 */
export function isLmsManagedAccount(cli: MatrixClient): boolean {
    return getLmsSyncSummary(cli) !== undefined;
}

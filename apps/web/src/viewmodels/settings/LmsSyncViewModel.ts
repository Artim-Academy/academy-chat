/*
Copyright 2026 Artim Academy

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE in the repository root for full details.
*/

import { ClientEvent, type MatrixClient, type MatrixEvent } from "matrix-js-sdk/src/matrix";
import {
    BaseViewModel,
    type LmsSyncViewSnapshot,
    type LmsSyncViewModel as LmsSyncViewModelInterface,
} from "@element-hq/web-shared-components";

import { LMS_SYNC_EVENT_TYPE, type LmsSyncSummary, getLmsSyncSummary } from "../../utils/lms/LmsSync";
import { formatFullDate } from "../../DateUtils";
import defaultDispatcher from "../../dispatcher/dispatcher";
import { Action } from "../../dispatcher/actions";
import { type ViewRoomPayload } from "../../dispatcher/payloads/ViewRoomPayload";

export interface LmsSyncViewModelProps {
    /**
     * The Matrix client of the logged in user.
     */
    matrixClient: MatrixClient;
}

/**
 * ViewModel for the settings page that shows what the Artim Academy LMS synced for the account.
 */
export class LmsSyncViewModel
    extends BaseViewModel<LmsSyncViewSnapshot, LmsSyncViewModelProps>
    implements LmsSyncViewModelInterface
{
    private static readonly computeSnapshot = (summary: LmsSyncSummary | undefined): LmsSyncViewSnapshot => {
        if (!summary) {
            return {
                isSynced: false,
                name: "",
                email: "",
                lmsUserId: "",
                roles: [],
                isAdmin: false,
                courses: [],
                lastSynced: "",
            };
        }
        return {
            isSynced: true,
            name: summary.name,
            email: summary.email,
            lmsUserId: summary.lms_user_id,
            roles: summary.roles,
            isAdmin: summary.is_admin,
            courses: summary.courses.map((course) => ({
                id: course.id,
                title: course.title,
                role: course.role,
                spaceId: course.space_id ?? undefined,
            })),
            lastSynced: formatFullDate(new Date(summary.synced_at), false, false),
        };
    };

    public constructor(props: LmsSyncViewModelProps) {
        super(props, LmsSyncViewModel.computeSnapshot(getLmsSyncSummary(props.matrixClient)));
        this.disposables.trackListener(
            props.matrixClient,
            ClientEvent.AccountData,
            this.onAccountData as (...args: unknown[]) => void,
        );
    }

    private onAccountData = (event: MatrixEvent): void => {
        if (event.getType() !== LMS_SYNC_EVENT_TYPE) return;
        const content = event.getContent<LmsSyncSummary>();
        this.snapshot.set(LmsSyncViewModel.computeSnapshot(content.lms_user_id ? content : undefined));
    };

    public onOpenCourse = (spaceId: string): void => {
        defaultDispatcher.dispatch<ViewRoomPayload>({
            action: Action.ViewRoom,
            room_id: spaceId,
            metricsTrigger: undefined,
        });
    };
}

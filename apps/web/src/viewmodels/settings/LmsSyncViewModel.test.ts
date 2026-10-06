// @vitest-environment happy-dom

/*
Copyright 2026 Artim Academy

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE in the repository root for full details.
*/

import { ClientEvent, MatrixEvent, type MatrixClient } from "matrix-js-sdk/src/matrix";
import { vi, describe, it, expect, beforeEach, afterEach, type MockedObject } from "vitest";
import { getMockClientWithEventEmitter, mockClientMethodsUser } from "test-utils";

import { LmsSyncViewModel } from "./LmsSyncViewModel";
import { LMS_SYNC_EVENT_TYPE, type LmsSyncSummary } from "../../utils/lms/LmsSync";
import defaultDispatcher from "../../dispatcher/dispatcher";
import { Action } from "../../dispatcher/actions";

const summary: LmsSyncSummary = {
    lms_user_id: "64f0c0ffee",
    name: "Sam Student",
    email: "sam@example.org",
    roles: ["student"],
    is_admin: false,
    courses: [{ id: "web", title: "Webentwicklung", role: "student", space_id: "!space:example.org" }],
    synced_at: Date.UTC(2026, 9, 6, 8, 0),
};

const accountDataEvent = (content: object): MatrixEvent => new MatrixEvent({ type: LMS_SYNC_EVENT_TYPE, content });

describe("LmsSyncViewModel", () => {
    let client: MockedObject<MatrixClient>;

    beforeEach(() => {
        client = getMockClientWithEventEmitter({
            ...mockClientMethodsUser(),
            getAccountData: vi.fn(),
        });
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it("is not synced without LMS account data", () => {
        client.getAccountData.mockReturnValue(undefined);
        const vm = new LmsSyncViewModel({ matrixClient: client });
        expect(vm.getSnapshot().isSynced).toBe(false);
    });

    it("maps the synced account data", () => {
        client.getAccountData.mockReturnValue(accountDataEvent(summary));
        const vm = new LmsSyncViewModel({ matrixClient: client });

        expect(vm.getSnapshot()).toEqual(
            expect.objectContaining({
                isSynced: true,
                name: "Sam Student",
                email: "sam@example.org",
                lmsUserId: "64f0c0ffee",
                roles: ["student"],
                isAdmin: false,
                courses: [{ id: "web", title: "Webentwicklung", role: "student", spaceId: "!space:example.org" }],
            }),
        );
        expect(vm.getSnapshot().lastSynced).not.toBe("");
    });

    it("updates when the account data changes", () => {
        client.getAccountData.mockReturnValue(undefined);
        const vm = new LmsSyncViewModel({ matrixClient: client });

        client.emit(ClientEvent.AccountData, accountDataEvent({ ...summary, roles: ["trainer"] }));

        expect(vm.getSnapshot().roles).toEqual(["trainer"]);
    });

    it("ignores other account data", () => {
        client.getAccountData.mockReturnValue(accountDataEvent(summary));
        const vm = new LmsSyncViewModel({ matrixClient: client });

        client.emit(ClientEvent.AccountData, new MatrixEvent({ type: "m.direct", content: {} }));

        expect(vm.getSnapshot().name).toBe("Sam Student");
    });

    it("opens the course space", () => {
        client.getAccountData.mockReturnValue(accountDataEvent(summary));
        const dispatch = vi.spyOn(defaultDispatcher, "dispatch").mockImplementation(() => {});
        const vm = new LmsSyncViewModel({ matrixClient: client });

        vm.onOpenCourse("!space:example.org");

        expect(dispatch).toHaveBeenCalledWith(
            expect.objectContaining({ action: Action.ViewRoom, room_id: "!space:example.org" }),
        );
    });
});

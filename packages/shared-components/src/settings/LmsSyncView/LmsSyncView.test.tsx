/*
Copyright 2026 Artim Academy

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE in the repository root for full details.
*/

import React from "react";
import { render, screen } from "@test-utils";
import { composeStories } from "@storybook/react-vite";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import * as stories from "./LmsSyncView.stories";
import { LmsSyncView, type LmsSyncViewActions, type LmsSyncViewSnapshot } from "./LmsSyncView";
import { MockViewModel } from "../../core/viewmodel/MockViewModel";

const { Student, Trainer, NotSynced } = composeStories(stories);

const snapshot: LmsSyncViewSnapshot = {
    isSynced: true,
    name: "Sam Student",
    email: "sam@example.org",
    lmsUserId: "64f0c0ffee",
    roles: ["student"],
    isAdmin: false,
    courses: [{ id: "web", title: "Webentwicklung", role: "student", spaceId: "!space:example.org" }],
    lastSynced: "6. Okt. 2026, 10:00",
};

describe("LmsSyncView", () => {
    it("renders the synced roles and courses", () => {
        const { container } = render(<Student />);
        expect(screen.getByText("Sam Student")).toBeInTheDocument();
        expect(screen.getByText("Webentwicklung")).toBeInTheDocument();
        expect(container).toMatchSnapshot();
    });

    it("renders the trainer state", () => {
        const { container } = render(<Trainer />);
        expect(container).toMatchSnapshot();
    });

    it("explains when nothing was synced yet", () => {
        render(<NotSynced />);
        expect(screen.getByText("No data has been synced from the Artim Academy LMS yet.")).toBeInTheDocument();
    });

    it("opens the course space", async () => {
        const onOpenCourse = vi.fn();
        class TestViewModel extends MockViewModel<LmsSyncViewSnapshot> implements LmsSyncViewActions {
            public onOpenCourse = onOpenCourse;
        }
        render(<LmsSyncView vm={new TestViewModel(snapshot)} />);

        await userEvent.click(screen.getByRole("button", { name: "Open Webentwicklung" }));

        expect(onOpenCourse).toHaveBeenCalledWith("!space:example.org");
    });
});

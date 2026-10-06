/*
Copyright 2026 Artim Academy

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE in the repository root for full details.
*/

import React, { type JSX } from "react";
import { fn } from "storybook/test";

import type { Meta, StoryObj } from "@storybook/react-vite";
import { LmsSyncView, type LmsSyncViewActions, type LmsSyncViewSnapshot } from "./LmsSyncView";
import { useMockedViewModel } from "../../core/viewmodel";
import { withViewDocs } from "../../../.storybook/withViewDocs";

type LmsSyncProps = LmsSyncViewSnapshot & LmsSyncViewActions;

const LmsSyncViewWrapperImpl = ({ onOpenCourse, ...rest }: LmsSyncProps): JSX.Element => {
    const vm = useMockedViewModel(rest, { onOpenCourse });
    return <LmsSyncView vm={vm} />;
};
const LmsSyncViewWrapper = withViewDocs(LmsSyncViewWrapperImpl, LmsSyncView);

const meta = {
    title: "Settings/LmsSyncView",
    component: LmsSyncViewWrapper,
    tags: ["autodocs"],
    args: {
        isSynced: true,
        name: "Sam Student",
        email: "sam@example.org",
        lmsUserId: "64f0c0ffee0000000000abcd",
        roles: ["student"],
        isAdmin: false,
        courses: [
            { id: "web", title: "Webentwicklung", role: "student", spaceId: "!web:example.org" },
            { id: "db", title: "Datenbanken", role: "student" },
        ],
        lastSynced: "6 Oct 2026, 10:00",
        onOpenCourse: fn(),
    },
} satisfies Meta<typeof LmsSyncViewWrapper>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Student: Story = {};

export const Trainer: Story = {
    args: {
        name: "Tom Trainer",
        roles: ["trainer"],
        courses: [{ id: "web", title: "Webentwicklung", role: "trainer", spaceId: "!web:example.org" }],
    },
};

export const Admin: Story = {
    args: { name: "Ada Admin", roles: ["admin", "trainer"], isAdmin: true, courses: [] },
};

export const NotSynced: Story = {
    args: { isSynced: false },
};

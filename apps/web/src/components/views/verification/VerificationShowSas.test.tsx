/*
Copyright 2026 Artim Academy

SPDX-License-Identifier: AGPL-3.0-only OR GPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/

// @vitest-environment happy-dom

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "test-utils-rtl";
import React from "react";
import { type GeneratedSas } from "matrix-js-sdk/src/crypto-api";

import VerificationShowSas from "./VerificationShowSas";

describe("VerificationShowSas", () => {
    it("compares the three numbers even when emojis are available, so web and the mobile app show the same", () => {
        const sas = {
            decimal: [4291, 837, 6152],
            emoji: [["🐶", "dog"]],
        } as unknown as GeneratedSas;
        const { container } = render(<VerificationShowSas sas={sas} isSelf onDone={vi.fn()} onCancel={vi.fn()} />);

        expect(screen.getByText("4291")).toBeTruthy();
        expect(screen.getByText("837")).toBeTruthy();
        expect(screen.getByText("6152")).toBeTruthy();
        expect(container.querySelector(".mx_VerificationShowSas_emojiSas")).toBeNull();
    });
});

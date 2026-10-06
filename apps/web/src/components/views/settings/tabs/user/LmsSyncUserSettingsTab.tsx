/*
Copyright 2026 Artim Academy

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE in the repository root for full details.
*/

import React, { type JSX } from "react";
import { LmsSyncView, useCreateAutoDisposedViewModel } from "@element-hq/web-shared-components";

import SettingsTab from "../SettingsTab";
import { SettingsSection } from "../../shared/SettingsSection";
import { _t } from "../../../../../languageHandler";
import { useMatrixClientContext } from "../../../../../contexts/MatrixClientContext";
import { LmsSyncViewModel } from "../../../../../viewmodels/settings/LmsSyncViewModel";

/**
 * Settings tab that shows the profile, roles and courses synced from the Artim Academy LMS.
 */
export function LmsSyncUserSettingsTab(): JSX.Element {
    const matrixClient = useMatrixClientContext();
    const vm = useCreateAutoDisposedViewModel(() => new LmsSyncViewModel({ matrixClient }));

    return (
        <SettingsTab>
            <SettingsSection heading={_t("settings|lms_sync|title")}>
                <LmsSyncView vm={vm} />
            </SettingsSection>
        </SettingsTab>
    );
}

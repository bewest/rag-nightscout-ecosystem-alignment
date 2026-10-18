"""sync_model.py — generate and check controller state-model registrations.

A registration (`specs/sync/controller-state-model.schema.json`) is what a
controller would tell a hub once, so the hub can prepare a sync contract for
it: the composite documents it writes, the primitives they decompose to, the
intent kinds it exposes and how they combine, the dosing inputs it can supply,
and the settings it will publish.

The registrations here are **generated from the evidence already gathered**
rather than hand-written, so they cannot quietly claim more than was
measured:

* documents and paths from the census and `vendor-surface.json`
* decomposition targets from the measured Nocturne V4 routing
* replay inputs and their status from `dosing-input-sources.yaml`
* settings fields from the same, restricted to what is or could be published
* field types by reference (`typeRef`) to `controller-settings.schema.json`,
  only where that schema's definition was read from this controller's own
  algorithm family; otherwise the field stays untyped (D18 addendum rule 2)
* intent declarations (`stateSpans`, `composition`, `commands`) from the
  intent/workflow landscape (2026-10-09) and the controller source it cites,
  each with its evidence; these are the well-known tier of D18

The interesting output is the **replay-completeness** figure: the share of a
controller's declared dosing inputs that are actually recorded. It is low,
and it is the number `oref-digital-twin` is working around when it extracts
settings from screenshots.
"""

import argparse
import copy
import json
import re
from pathlib import Path

import jsonschema
import yaml

from . import corpus, settings_schema

SCHEMA = "specs/sync/controller-state-model.schema.json"
OUT_DIR = "specs/sync/registrations"
# Hand-written registrations that exercise the grammar. --check validates
# them; it never regenerates or compares them.
FIXTURES_DIR = "specs/sync/registrations/fixtures"
SETTINGS_SCHEMA = "specs/sync/controller-settings.schema.json"
SETTINGS_PROPERTIES = "#/properties/settings/properties/"
# The settings-schema source each algorithm family's types were read from.
FAMILY_SOURCE = {"loop": settings_schema.LOOP_SRC, "oref0": settings_schema.OREF_SRC}

# Source revisions the intent declarations below were read at. They are the
# revisions in the landscape document's §1 table.
LANDSCAPE = "docs/30-design/platform/nightscout-intent-workflow-landscape-2026-10-09.md"
LOOPKIT = "LoopKit 325bd820"
LOOP = "Loop c2fddb76"
NSSERVICE = "NightscoutService fe075ef"
NSKIT = "NightscoutKit 4ec9fd1"
TRIO = "Trio e41c9db37"
AAPS = "AndroidAPS 7e1d537d49"


def ev(claim, source, basis="read"):
    return {"claim": claim, "source": source, "basis": basis}


# Intent declarations (spec.stateSpans, spec.composition, spec.commands).
# Every field is taken from the landscape document or from the source it
# cites; a field the evidence does not settle is left out, and a field known
# to be unpublished is null. Nothing here is generated from the corpus, so
# each block carries its own evidence.

_LOOP_SPANS = [
    {
        "category": "Override",
        "kind": "TemporaryScheduleOverride",
        "slot": "override",
        "exclusiveWithinSlot": True,
        "coexistsWith": ["preMeal"],
        "supersedes": True,
        "states": ["scheduled", "active", "ended"],
        "endReasons": [
            {"reason": "expired", "controllerTerm": "natural"},
            {"reason": "cancelled", "controllerTerm": "early"},
            {"reason": "superseded", "controllerTerm": "early"},
            {"reason": "deletedBeforeStart", "controllerTerm": "deleted"},
        ],
        "wire": {
            "collection": "treatments",
            "eventType": "Temporary Override",
            "identity": ["_id"],
            "paths": ["reason", "correctionRange", "insulinNeedsScaleFactor",
                      "remoteAddress"],
            "durationField": "duration",
            "durationUnit": "minutes",
            "indefinite": {"field": "durationType", "value": "indefinite"},
            "endedEncoding": "amend-duration",
            "cancelBeforeStartEncoding": "delete",
            "endReasonPath": None,
            "description": "_id is the instance UUID; whether it survives depends on the "
                           "server's UUID_HANDLING setting, and without it the upsert falls "
                           "back to created_at + eventType. reason is the preset symbol and "
                           "name.",
        },
        "applied": {
            "collection": "devicestatus",
            "discriminator": {"path": "override", "test": "is-object"},
            "paths": ["override.active", "override.name", "override.multiplier",
                      "override.currentCorrectionRange", "override.duration"],
            "durationField": "override.duration",
            "durationUnit": "seconds",
            "linkToRequest": None,
            "description": "Written with each loop cycle's devicestatus; active is false "
                           "when no override is on. override.duration is the remaining "
                           "time in seconds, absent for an indefinite override.",
        },
        "initiators": {
            "vocabulary": "EnactTrigger",
            "values": ["local", "remote"],
            "wirePath": "remoteAddress",
            "description": "Phone and watch are both local; Siri is remote(\"Siri\"). A "
                           "remote enactment also sets enteredBy to \"Loop (via remote "
                           "command)\".",
        },
        "definitions": {
            "published": {"collection": "profile",
                          "paths": ["loopSettings.overridePresets"]},
            "idField": None,
            "referencedBy": "name",
            "fields": ["symbol", "name", "duration", "targetRange",
                       "insulinNeedsScaleFactor"],
            "description": "Presets carry a UUID locally that is not uploaded. Activation "
                           "copies the preset into the instance; remote enactment names "
                           "the preset.",
        },
        "acceptsFromHub": {
            "channels": ["command"],
            "description": "Remote enactment by preset name over APNs.",
        },
        "evidence": [
            ev("End {natural, early, deleted}; deleted is 'ended before started'",
               f"{LOOPKIT} LoopKit/TemporaryScheduleOverrideHistory.swift:11-14"),
            ev("a new override cancels the active one and deletes later-starting ones",
               f"{LOOPKIT} LoopKit/TemporaryScheduleOverrideHistory.swift:146-166"),
            ev("one scheduleOverride and one preMealOverride, held separately",
               f"{LOOP} LoopCore/LoopSettings.swift:44,56"),
            ev("EnactTrigger {local, remote(String)}",
               f"{LOOPKIT} LoopKit/TemporaryScheduleOverride.swift:21-24"),
            ev("wire shape: duration minutes or durationType indefinite, reason, "
               "insulinNeedsScaleFactor, remoteAddress, correctionRange",
               f"{NSKIT} Sources/NightscoutKit/Models/Treatments/OverrideTreatment.swift:62-77"),
            ev("_id = syncIdentifier UUID; remote sets remoteAddress and enteredBy",
               f"{NSSERVICE} NightscoutServiceKit/Extensions/OverrideTreament.swift:41-58"),
            ev("deleted overrides are removed from Nightscout by id",
               f"{NSSERVICE} NightscoutServiceKit/NightscoutService.swift:157-167"),
            ev("devicestatus override status; duration is seconds remaining",
               f"{NSSERVICE} NightscoutServiceKit/Extensions/StoredDosingDecision.swift:118-136"),
            ev("override.duration: round(actualEndDate - now), a TimeInterval in seconds; "
               "nil (field not written) for an indefinite override",
               f"{NSSERVICE} NightscoutServiceKit/Extensions/StoredDosingDecision.swift:129"),
            ev("OverrideStatus writes duration as the TimeInterval unchanged",
               f"{NSKIT} Sources/NightscoutKit/Models/OverrideStatus.swift:17,44-46"),
            ev("preset fields uploaded in profile.loopSettings.overridePresets",
               f"{NSKIT} Sources/NightscoutKit/Models/TemporaryScheduleOverride.swift:28-49"),
            ev("_id survival depends on UUID_HANDLING", f"{LANDSCAPE} §3.1"),
            ev("2,428 Temporary Override treatments; 55,938 active devicestatus overrides "
               "(distinct documents)", f"make schema-effects; {LANDSCAPE} §3.1",
               "measured"),
        ],
    },
    {
        "category": "PreMealTarget",
        "kind": "TemporaryScheduleOverride (context preMeal)",
        "slot": "preMeal",
        "exclusiveWithinSlot": True,
        "coexistsWith": ["override"],
        "states": ["active", "ended"],
        "endReasons": [
            {"reason": "expired"},
            {"reason": "cancelled"},
            {"reason": "endedByTrigger", "triggers": ["carbs", "loopOff"]},
        ],
        "wire": None,
        "definitions": {
            "published": {"collection": "profile",
                          "paths": ["loopSettings.preMealTargetRange"]},
            "fields": ["preMealTargetRange"],
        },
        "evidence": [
            ev("only scheduleOverride is recorded in the override history that is "
               "uploaded; preMealOverride changes are not",
               f"{LOOP} Loop/Managers/LoopDataManager.swift:262-270"),
            ev("pre-meal is not a treatment, not in the profile; devicestatus "
               "override.active is false when only pre-meal is on", f"{LANDSCAPE} §3.1"),
            ev("ended by a carb entry", f"{LOOP} Loop/Managers/LoopDataManager.swift:687-691"),
            ev("ended when automatic dosing turns off",
               f"{LOOP} Loop/Managers/LoopDataManager.swift:226-233"),
            ev("cancelled by the user",
               f"{LOOP} Loop/View Controllers/StatusTableViewController.swift:1480-1493"),
            ev("expires at its scheduled end",
               f"{LOOP} LoopCore/LoopSettings.swift:118-134"),
            ev("pre-meal range published in profile.loopSettings.preMealTargetRange",
               f"{NSKIT} Sources/NightscoutKit/Models/LoopSettings.swift:17"),
        ],
    },
    {
        "category": "LoopMode",
        "kind": "dosingEnabled",
        "slot": "loopMode",
        "exclusiveWithinSlot": True,
        "wire": {
            "collection": "profile",
            "paths": ["loopSettings.dosingEnabled"],
            "endedEncoding": "sampled-state",
            "description": "Carried in the profile document's loopSettings snapshot; the "
                           "change itself is not a treatment.",
        },
        "requested": {"collection": "profile", "paths": ["loopSettings.dosingEnabled"]},
        "applied": None,
        "evidence": [
            ev("dosingEnabled (intent) vs automaticDosingEnabled (gated by CGM and pump); "
               "only the intent is uploaded", f"{LANDSCAPE} §3 P3"),
            ev("dosingEnabled in loopSettings",
               f"{NSKIT} Sources/NightscoutKit/Models/LoopSettings.swift:13,41"),
        ],
    },
]

_TRIO_APPLIED = {
    "collection": "devicestatus",
    "discriminator": {"path": "openaps", "test": "is-object"},
    "paths": ["openaps.suggested.ISF", "openaps.suggested.CR",
              "openaps.suggested.current_target", "openaps.suggested.sensitivityRatio"],
    "linkToRequest": None,
    "description": "Post-composition values for each loop cycle, not attributed to the "
                   "override or temp target that produced them.",
}
_TRIO_INITIATORS = {
    "vocabulary": "AdjustmentSource",
    "values": ["app", "remote", "shortcut", "watch"],
    "wirePath": None,
    "description": "Recorded in the debug log only; enteredBy is always \"Trio\".",
}
_TRIO_SPANS = [
    {
        "category": "Override",
        "kind": "OverrideStored",
        "slot": "override",
        "exclusiveWithinSlot": True,
        "coexistsWith": ["temporaryTarget"],
        "supersedes": True,
        "states": ["active", "ended"],
        "wire": {
            "collection": "treatments",
            "eventType": "Exercise",
            "identity": ["created_at", "eventType"],
            "paths": ["notes", "duration"],
            "unpublishedFields": ["percentage", "target", "ISF/CR scope", "SMB settings"],
            "durationField": "duration",
            "durationUnit": "minutes",
            "indefinite": {"field": "duration", "value": 43200},
            "endedEncoding": "delete-and-repost",
            "cancelBeforeStartEncoding": "delete",
            "endReasonPath": None,
            "description": "Every override is sent as Exercise regardless of purpose; notes "
                           "is the preset name or \"Custom Override\". The struct's id is "
                           "excluded from its coding keys.",
        },
        "applied": _TRIO_APPLIED,
        "initiators": _TRIO_INITIATORS,
        "definitions": {
            "published": {"collection": "profile", "paths": ["overridePresets"]},
            "idField": None,
            "referencedBy": "name",
            "fields": ["name", "duration", "percentage", "target"],
            "unpublishedFields": ["ISF/CR scope", "SMB settings"],
            "controllerUniqueFields": ["smbIsOff", "scheduled SMB-off hours",
                                       "smbMinutes", "uamMinutes"],
            "description": "One OverrideStored entity with an isPreset flag; activation "
                           "mutates the preset row.",
        },
        "acceptsFromHub": {
            "channels": ["command"],
            "description": "Remote enactment by preset name over APNs.",
        },
        "evidence": [
            ev("Exercise eventType, notes = name or Custom Override, 43200 indefinite",
               f"{TRIO} Trio/Sources/APS/Storage/OverrideStorage.swift:270-279"),
            ev("enacting an override first disables every active one",
               f"{TRIO} Trio/Sources/Modules/Adjustments/AdjustmentsStateModel+Extensions/"
               "AdjustmentsStateModel+Overrides.swift:14,34-40"),
            ev("AdjustmentSource {app, remote, shortcut, watch}",
               f"{TRIO} Trio/Sources/Services/Adjustments/AdjustmentManager.swift:14-19"),
            ev("enteredBy is \"Trio\"", f"{TRIO} Trio/Sources/Models/NightscoutExercise.swift:11"),
            ev("published preset fields {name, duration, percentage, target}",
               f"{TRIO} Trio/Sources/Models/NightscoutStatus.swift:63,68-73"),
            ev("wire identity created_at + eventType; end = delete + re-post", f"{LANDSCAPE} §3.2, §4"),
            ev("399 distinct Exercise _id, 81 with duration 43200, one site",
               f"make schema-effects; {LANDSCAPE} §3.2", "measured"),
        ],
    },
    {
        "category": "TemporaryTarget",
        "slot": "temporaryTarget",
        "exclusiveWithinSlot": True,
        "coexistsWith": ["override"],
        "supersedes": True,
        "states": ["active", "ended"],
        "wire": {
            "collection": "treatments",
            "eventType": "Temporary Target",
            "identity": ["created_at", "eventType"],
            "paths": ["notes"],
            "unpublishedFields": ["halfBasalTarget"],
            "durationField": "duration",
            "durationUnit": "minutes",
            "endedEncoding": "repost-same-created_at",
            "endReasonPath": None,
            "description": "notes is the target's name. Identity is the server's upsert key.",
        },
        "applied": _TRIO_APPLIED,
        "initiators": _TRIO_INITIATORS,
        "acceptsFromHub": {
            "channels": ["treatment-download"],
            "acknowledged": False,
            "description": "Downloads Temporary Target treatments entered by other clients "
                           "and enables the newest one; no acknowledgement record.",
        },
        "evidence": [
            ev("notes = name; a run is re-posted with the target's start as created_at",
               f"{TRIO} Trio/Sources/APS/Storage/TempTargetsStorage.swift:294-370"),
            ev("enacting a temp target first disables every active one",
               f"{TRIO} Trio/Sources/Modules/Adjustments/AdjustmentsStateModel+Extensions/"
               "AdjustmentsStateModel+TempTargets.swift:160,296"),
            ev("temp targets are fetched from Nightscout",
               f"{TRIO} Trio/Sources/APS/FetchTreatmentsManager.swift:35"),
            ev("halfBasalTarget not uploaded; downloaded targets enabled directly",
               f"{LANDSCAPE} §3.2"),
        ],
    },
    {
        "category": "LoopMode",
        "kind": "DosingMode",
        "slot": "loopMode",
        "exclusiveWithinSlot": True,
        "wire": {
            "collection": "devicestatus",
            "discriminator": {"path": "openaps", "test": "is-object"},
            "paths": ["openaps.dosingMode"],
            "vocabularies": {"openaps.dosingMode": ["closed", "open",
                                                    "lowGlucoseSuspend", "basalTesting"]},
            "endedEncoding": "sampled-state",
            "description": "The raw value is written on every devicestatus; the change "
                           "itself is not a treatment.",
        },
        "evidence": [
            ev("DosingMode {closed, open, lowGlucoseSuspend, basalTesting}",
               f"{TRIO} Trio/Sources/Models/DosingMode.swift:16-21"),
            ev("written as openaps.dosingMode (raw value)",
               f"{TRIO} Trio/Sources/Models/NightscoutStatus.swift:15-17"),
            ev("dosingMode set on the uploaded status",
               f"{TRIO} Trio/Sources/Services/Network/Nightscout/NightscoutManager.swift:660"),
        ],
    },
]

_AAPS_INITIATORS = {
    "vocabulary": "Sources",
    "wirePath": None,
    "description": "About 80 values, recorded in the local UserEntry log and not synced.",
}
_AAPS_SPANS = [
    {
        "category": "ProfileState",
        "kind": "ProfileSwitch",
        "slot": "profileSwitch",
        "exclusiveWithinSlot": True,
        "coexistsWith": ["temporaryTarget", "runningMode", "scene"],
        "states": ["active", "ended"],
        "wire": {
            "collection": "treatments",
            "eventType": "Profile Switch",
            "identity": ["identifier"],
            "paths": ["profile", "profileJson", "percentage",
                      {"path": "timeshift", "unit": "milliseconds"},
                      "originalProfileName", "durationInMilliseconds"],
            "durationField": "duration",
            "durationUnit": "minutes",
            "endedEncoding": "amend-duration",
            "cancelBeforeStartEncoding": "soft-delete",
            "endReasonPath": None,
            "description": "profileJson is the base profile. percentage scales basal by p/100 "
                           "and ISF and IC by 100/p; timeshift is milliseconds.",
        },
        "requested": {
            "collection": "treatments",
            "eventType": "Profile Switch",
            "writtenWhen": "by the user, SMS, automation, a scene or Nightscout sync",
        },
        "applied": {
            "collection": "treatments",
            "eventType": "Note",
            "discriminator": {"path": "originalProfileName", "test": "exists"},
            "paths": ["profileJson", "originalProfileName", "originalCustomizedName",
                      "originalPercentage",
                      {"path": "originalTimeshift", "unit": "milliseconds"},
                      "originalDuration"],
            "writtenWhen": "only after the pump accepts the profile",
            "linkToRequest": None,
            "description": "EffectiveProfileSwitch. Its profileJson is already scaled. A "
                           "failed or pending switch is a Profile Switch with no following "
                           "EffectiveProfileSwitch. originalPsId links the two locally "
                           "(dev-only) and is not sent.",
        },
        "initiators": _AAPS_INITIATORS,
        "definitions": {
            "referencedBy": "copy",
            "description": "Named profiles in the profile store; a switch copies the "
                           "profile's blocks.",
        },
        "acceptsFromHub": {
            "channels": ["treatment-download"],
            "preference": "NsClientAcceptProfileSwitch",
            "default": False,
            "description": "The preference is bypassed on the AAPSClient build and during a "
                           "full sync, which apply inbound records regardless.",
        },
        "evidence": [
            ev("PS -> EPS written only if the pump accepts; EPS uploaded as Note recognised "
               "by originalProfileName", f"{LANDSCAPE} §3.3"),
            ev("EPS wire: eventType Note, scaled profileJson, original* fields",
               f"{AAPS} plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/"
               "nsclientV3/extensions/EffectiveProfileSwitchExtension.kt:45-60"),
            ev("originalPsId is not mapped to the remote treatment",
               f"{AAPS} core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/mapper/"
               "TreatmentMapper.kt:490-515"),
            ev("PS wire fields; duration minutes plus durationInMilliseconds",
               f"{AAPS} core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/mapper/"
               "TreatmentMapper.kt:517-541"),
            ev("PS timeshift is milliseconds: set from hours by T.hours(h).msecs(), "
               "uploaded unchanged as timeshift",
               f"{AAPS} core/data/src/commonMain/kotlin/app/aaps/core/data/model/PS.kt:22; "
               "implementation/src/commonMain/kotlin/app/aaps/implementation/profile/"
               "ProfileFunctionImpl.kt:218; plugins/sync/src/commonMain/kotlin/app/aaps/"
               "plugins/sync/nsclientV3/extensions/ProfileSwitchExtension.kt:64; "
               "core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/mapper/"
               "TreatmentMapper.kt:540; core/nssdk/src/commonMain/kotlin/app/aaps/core/"
               "nssdk/remotemodel/RemoteTreatment.kt:101"),
            ev("EPS originalTimeshift is milliseconds, copied from the PS and uploaded "
               "unchanged",
               f"{AAPS} core/data/src/commonMain/kotlin/app/aaps/core/data/model/EPS.kt:24; "
               "implementation/src/commonMain/kotlin/app/aaps/implementation/queue/"
               "CommandQueueImplementation.kt:202; plugins/sync/src/commonMain/kotlin/app/"
               "aaps/plugins/sync/nsclientV3/extensions/EffectiveProfileSwitchExtension.kt:54; "
               "core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/mapper/"
               "TreatmentMapper.kt:510; core/nssdk/src/commonMain/kotlin/app/aaps/core/"
               "nssdk/remotemodel/RemoteTreatment.kt:85"),
            ev("percentage: basal x p/100, ISF and IC x 100/p", f"{LANDSCAPE} §3.3"),
            ev("one PS at a time; end = shortened duration on the same identifier; "
               "invalidate = v3 soft delete", f"{LANDSCAPE} §4, §7"),
            ev("NsClientAcceptProfileSwitch, default false",
               f"{AAPS} core/keys/src/commonMain/kotlin/app/aaps/core/keys/BooleanKey.kt:223"),
            ev("inbound PS and EPS gated by the preference, or AAPSCLIENT, or a full sync",
               f"{AAPS} plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/"
               "nsclientV3/NsIncomingDataProcessor.kt:188-200"),
        ],
    },
    {
        "category": "TemporaryTarget",
        "slot": "temporaryTarget",
        "exclusiveWithinSlot": True,
        "coexistsWith": ["profileSwitch", "runningMode", "scene"],
        "supersedes": True,
        "states": ["active", "ended"],
        "endReasons": [{"reason": "superseded"}],
        "wire": {
            "collection": "treatments",
            "eventType": "Temporary Target",
            "identity": ["identifier"],
            "paths": ["targetBottom", "targetTop", "reason", "durationInMilliseconds"],
            "vocabularies": {"reason": ["Custom", "Hypo", "Activity", "Eating Soon",
                                        "Automation", "Wear"]},
            "durationField": "duration",
            "durationUnit": "minutes",
            "endedEncoding": "amend-duration",
            "cancelBeforeStartEncoding": "soft-delete",
            "endReasonPath": None,
            "description": "Inbound merges are shorten-only.",
        },
        "initiators": {**_AAPS_INITIATORS,
                       "wireProxy": {"path": "reason", "value": "Automation"}},
        "definitions": {"description": "Temp target presets are kept in preferences."},
        "acceptsFromHub": {
            "channels": ["treatment-download"],
            "preference": "NsClientAcceptTempTarget",
            "default": False,
            "description": "The preference is bypassed on the AAPSClient build and during a "
                           "full sync, which apply inbound records regardless.",
        },
        "evidence": [
            ev("reason vocabulary",
               f"{AAPS} core/data/src/commonMain/kotlin/app/aaps/core/data/model/TT.kt:36-42"),
            ev("TT wire fields", f"{AAPS} core/nssdk/src/commonMain/kotlin/app/aaps/core/"
                                 "nssdk/mapper/TreatmentMapper.kt:440-461"),
            ev("a new TT ends the running one; inbound merges are shorten-only; reason "
               "Automation is the only initiator on the wire", f"{LANDSCAPE} §3.3, §3 P5"),
            ev("NsClientAcceptTempTarget, default false",
               f"{AAPS} core/keys/src/commonMain/kotlin/app/aaps/core/keys/BooleanKey.kt:222"),
            ev("inbound TT gated by the preference, or AAPSCLIENT, or a full sync",
               f"{AAPS} plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/"
               "nsclientV3/NsIncomingDataProcessor.kt:171"),
        ],
    },
    {
        "category": "LoopMode",
        "kind": "RunningMode",
        "slot": "runningMode",
        "exclusiveWithinSlot": True,
        "overlay": True,
        "coexistsWith": ["profileSwitch", "temporaryTarget", "scene"],
        "states": ["active", "ended"],
        "endReasons": [{"reason": "cancelled", "controllerTerm": "RESUME"}],
        "wire": {
            "collection": "treatments",
            "eventType": "OpenAPS Offline",
            "identity": ["identifier"],
            "paths": ["mode", "autoForced", "reasons", "originalDuration",
                      "durationInMilliseconds"],
            "vocabularies": {"mode": ["OPEN_LOOP", "CLOSED_LOOP", "CLOSED_LOOP_LGS",
                                      "DISABLED_LOOP", "SUPER_BOLUS", "DISCONNECTED_PUMP",
                                      "SUSPENDED_BY_PUMP", "SUSPENDED_BY_USER",
                                      "SUSPENDED_BY_DST"]},
            "durationField": "duration",
            "durationUnit": "minutes",
            "indefinite": {
                "field": "originalDuration", "value": 0,
                "description": "Open-ended DISABLED_LOOP is sent with a 10-year duration and "
                               "originalDuration 0. OPEN_LOOP, CLOSED_LOOP and "
                               "CLOSED_LOOP_LGS are sent with duration 0 and their own "
                               "duration in originalDuration.",
            },
            "endedEncoding": "amend-duration",
            "cancelBeforeStartEncoding": "soft-delete",
            "endReasonPath": None,
            "description": "RESUME ends a temporary mode and is never written to the wire.",
        },
        "requested": {
            "collection": "treatments",
            "eventType": "OpenAPS Offline",
            "discriminator": {"path": "autoForced", "test": "equals", "value": False},
        },
        "applied": {
            "collection": "treatments",
            "eventType": "OpenAPS Offline",
            "discriminator": {"path": "autoForced", "test": "equals", "value": True},
            "paths": ["mode", "reasons"],
            "linkToRequest": None,
            "description": "The constraint-forced layer, with its reasons.",
        },
        "initiators": _AAPS_INITIATORS,
        "acceptsFromHub": {
            "channels": ["treatment-download"],
            "preference": "NsClientAcceptRunningMode",
            "default": False,
            "description": "The preference is bypassed on the AAPSClient build and during a "
                           "full sync, which apply inbound records regardless.",
        },
        "evidence": [
            ev("requested layer and constraint-forced layer (autoForced, reasons), both "
               "uploaded as OpenAPS Offline; temporary over permanent", f"{LANDSCAPE} §3 P2-P3, §3.3"),
            ev("wire encoding per mode; DISABLED_LOOP open-ended = 10 years, "
               "originalDuration 0; RESUME is an error on the wire",
               f"{AAPS} plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/"
               "nsclientV3/extensions/RunningModeExtension.kt:25-97"),
            ev("mode vocabulary; RESUME cancels a temporary mode",
               f"{AAPS} core/data/src/commonMain/kotlin/app/aaps/core/data/model/RM.kt:43-63"),
            ev("NsClientAcceptRunningMode, default false",
               f"{AAPS} core/keys/src/commonMain/kotlin/app/aaps/core/keys/BooleanKey.kt:227"),
            ev("inbound RM gated by the preference, or AAPSCLIENT, or a full sync",
               f"{AAPS} plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/"
               "nsclientV3/NsIncomingDataProcessor.kt:226"),
        ],
    },
    {
        "category": "Scene",
        "kind": "Scene",
        "availability": "dev-only",
        "slot": "scene",
        "exclusiveWithinSlot": True,
        "coexistsWith": ["profileSwitch", "temporaryTarget", "runningMode"],
        "wire": {
            "collection": "settings",
            "documentIdentifier": "aaps-state",
            "description": "Active-scene state, with the Nightscout identifiers of the "
                           "records the scene created. Revert shortens only records the "
                           "scene still owns.",
        },
        "definitions": {
            "published": {"collection": "settings", "documentIdentifier": "aaps"},
            "controllerUniqueFields": ["scene actions"],
            "description": "Scene and automation definitions, with a definition id, in a "
                           "controller-private shape.",
        },
        "evidence": [
            ev("scenes with definition id; definitions under aaps, active state under "
               "aaps-state; one Scene at a time; dev-only", f"{LANDSCAPE} §3, §3.3, §7, §8"),
            ev("settings identifiers aaps and aaps-state",
               f"{AAPS} plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/"
               "nsclientV3/SettingsIdentifiers.kt:19-20"),
        ],
    },
]

_COMPOSITION = {
    "loop": {
        "reportedBy": "controller",
        "hubComputes": False,
        "rule": "target = pre-meal if active, else override, else schedule; basal x f, ISF "
                "x 1/f, CR x 1/f from the override only, applied over the history window",
        "result": [{
            "collection": "devicestatus",
            "discriminator": {"path": "override", "test": "is-object"},
            "paths": ["override.currentCorrectionRange", "override.multiplier"],
            "description": "Published only while an override is active; with only pre-meal "
                           "on, override.active is false and no range is sent.",
        }],
        "linkedToIntents": False,
        "evidence": [
            ev("composition rule", f"{LANDSCAPE} §7"),
            ev("effective target: pre-meal over override over schedule",
               f"{LOOP} LoopCore/LoopSettings.swift:118-140"),
            ev("override status carries the effective range and the override multiplier",
               f"{NSSERVICE} NightscoutServiceKit/Extensions/StoredDosingDecision.swift:118-136"),
        ],
    },
    "trio": {
        "reportedBy": "controller",
        "hubComputes": False,
        "rule": "target = temp target if set, else override target (unless 0 or 6), else "
                "profile; override percentage and ISF/CR scope apply regardless; a high or "
                "low temp target separately sets sensitivityRatio via halfBasalTarget",
        "result": [_TRIO_APPLIED],
        "linkedToIntents": False,
        "evidence": [
            ev("composition rule; Swift and JS agree", f"{LANDSCAPE} §3.2, §7"),
            ev("applied ISF, CR, target and sensitivityRatio on all 73,898 openaps "
               "devicestatus documents of the one Trio site", f"{LANDSCAPE} §3.2", "measured"),
        ],
    },
    "androidaps": {
        "reportedBy": "controller",
        "hubComputes": False,
        "rule": "temp target replaces min/max/target; the profile-switch percentage has "
                "already scaled basal, ISF and IC in the EffectiveProfileSwitch; one profile "
                "switch, one temp target, one running mode, one scene at a time",
        "result": [{
            "collection": "treatments",
            "eventType": "Note",
            "discriminator": {"path": "originalProfileName", "test": "exists"},
            "paths": ["profileJson"],
            "description": "The profile part of the result (basal, ISF, IC after percentage).",
        }],
        "linkedToIntents": False,
        "evidence": [
            ev("composition rule", f"{LANDSCAPE} §7"),
            ev("EPS profileJson is the scaled profile", f"{LANDSCAPE} §3.3"),
        ],
    },
}

_COMMANDS = {
    "loop": [{
        "transport": "apns",
        "hubInPath": "optional",
        "authorisation": "TOTP for bolus and carbs only",
        "acknowledgement": {
            "replyChannel": "the sender, over direct APNs only",
            "correlationId": False,
            "failureRecord": {"collection": "treatments", "eventType": "Note"},
        },
        "evidence": [ev("APNs; TOTP for bolus/carbs; optional reply without correlation "
                        "id; failure as Note; hub-routed commands cannot get a reply",
                        f"{LANDSCAPE} §3 P6, §6")],
    }],
    "trio": [{
        "transport": "apns",
        "hubInPath": "optional",
        "authorisation": "AES-GCM",
        "expiry": "±600 s window",
        "acknowledgement": {
            "replyChannel": "the sender, over direct APNs only",
            "failureRecord": {"collection": "treatments", "eventType": "Note"},
        },
        "evidence": [ev("APNs, AES-GCM, ±600 s; reply to sender; failure Note",
                        f"{LANDSCAPE} §3 P6, §6")],
    }],
    "androidaps": [
        {
            "transport": "sms",
            "hubInPath": "no",
            "authorisation": "TOTP and PIN",
            "evidence": [ev("SMS with TOTP+PIN", f"{LANDSCAPE} §3 P6")],
        },
        {
            "transport": "nightscout-settings",
            "availability": "dev-only",
            "hubInPath": "yes",
            "authorisation": "signed envelopes, prepare/commit",
            "expiry": "validUntil",
            "acknowledgement": {
                "states": ["Executing", "Done/Ok", "Done/Failed", "Done/Expired",
                           "Delivery/Failed"],
                "replyChannel": "Nightscout settings collection",
            },
            "evidence": [ev("signed envelopes on NS settings; ack Executing -> Done{Ok, "
                            "Failed, Expired} -> Delivery{Failed}", f"{LANDSCAPE} §3 P6, §6")],
        },
    ],
}

# Which census/vendor evidence belongs to which controller, and how its
# documents are recognised in a shared collection.
CONTROLLERS = {
    "loop": {
        "vendor": "LoopKit", "product": "Loop", "family": "loop",
        "discriminator": ("loop", "is-object"),
        "surfaces": ["Loop/NightscoutKit", "Loop/NightscoutKit-dose"],
        "prefixes": ["loop."],
        "decomposes": ["ApsSnapshot", "PumpSnapshot", "UploaderSnapshot"],
        "spans": _LOOP_SPANS,
        "composition": _COMPOSITION["loop"],
        "commands": _COMMANDS["loop"],
    },
    "trio": {
        "vendor": "Nightscout Foundation", "product": "Trio", "family": "oref0",
        "discriminator": ("openaps", "is-object"),
        "surfaces": ["Trio", "Trio/determination", "Trio/iob"],
        "prefixes": ["openaps."],
        "decomposes": ["ApsSnapshot", "PumpSnapshot", "UploaderSnapshot"],
        "spans": _TRIO_SPANS,
        "composition": _COMPOSITION["trio"],
        "commands": _COMMANDS["trio"],
    },
    "androidaps": {
        "vendor": "AndroidAPS", "product": "AndroidAPS", "family": "oref0",
        "discriminator": ("openaps", "is-object"),
        "surfaces": ["AndroidAPS"],
        "prefixes": ["openaps."],
        "decomposes": ["ApsSnapshot", "PumpSnapshot", "UploaderSnapshot"],
        "spans": _AAPS_SPANS,
        "composition": _COMPOSITION["androidaps"],
        "commands": _COMMANDS["androidaps"],
    },
}

CYCLE_SECONDS = 300


def _load(root, rel):
    path = root / rel
    return json.loads(path.read_text()) if path.is_file() else None


def settings_type_ref(settings, name, family):
    """typeRef for a settings field or replay input, or None (D18 rule 2).

    Only a configuration input (settings_schema.NOT_CONFIGURATION excludes
    per-cycle state) whose ControllerSettings definition was read from this
    family's own source is typed. `suspendThreshold` is the case this
    excludes: its definition is labelled oref0 but its type was read from
    Loop's AlgorithmInput, so neither family gets it.
    """
    if name in settings_schema.NOT_CONFIGURATION:
        return None
    leaf = name.split(".")[-1]
    definition = settings["properties"]["settings"]["properties"].get(leaf)
    if not definition:
        return None
    if definition.get("x-algorithm") != family:
        return None
    if definition.get("x-source") != FAMILY_SOURCE.get(family):
        return None
    return settings["$id"] + SETTINGS_PROPERTIES + leaf


def build(root: Path, key: str, spec: dict):
    census = _load(root, "reports/schema-census/devicestatus.census.json") or {"fields": []}
    vendor = _load(root, "reports/schema-census/vendor-surface.json") or {"surfaces": {}}
    dosing = yaml.safe_load(
        (root / "specs/nsschema/dosing-input-sources.yaml").read_text())
    settings = json.loads((root / SETTINGS_SCHEMA).read_text())
    family = spec["family"]

    observed = {f["path"] for f in census["fields"]}
    paths = sorted(p for p in observed
                   if any(p.startswith(pre) for pre in spec["prefixes"]))

    declared = set()
    for label in spec["surfaces"]:
        declared.update(vendor["surfaces"].get(label, {}).get("names", []))

    replay = []
    for entry in dosing["inputs"]:
        if entry.get("algorithm") != spec["family"]:
            continue
        sources = entry.get("sources") or []
        row = {
            "input": entry["input"],
            "path": sources[0] if sources else None,
            "collection": entry.get("collection") if sources else None,
            "status": entry["kind"],
        }
        ref = settings_type_ref(settings, entry["input"], family)
        if ref:
            row["typeRef"] = ref
        replay.append(row)

    settings_fields = []
    for name in sorted(
            e["input"] for e in dosing["inputs"]
            if e.get("algorithm") == family
            and e["kind"] in ("absent", "partial")
            and e["input"].startswith(("profile.", "automatic", "carb", "recommendation",
                                       "use", "include", "max", "gradual"))):
        field = {"name": name}
        ref = settings_type_ref(settings, name, family)
        if ref:
            field["typeRef"] = ref
        settings_fields.append(field)

    return {
        "apiVersion": "nightscout.dev/sync/v1",
        "kind": "ControllerStateModel",
        "metadata": {
            "vendor": spec["vendor"],
            "product": spec["product"],
            "algorithmFamily": spec["family"],
            "tier": "well-known",
            "source": "generated by tools/nsschema/sync_model.py from the census, "
                      "vendor-surface.json and dosing-input-sources.yaml; intent "
                      "declarations (stateSpans, composition, commands) from "
                      f"{LANDSCAPE} and the source it cites",
        },
        "spec": {
            "cadence": {"nominalSeconds": CYCLE_SECONDS,
                        "maxDeferralSeconds": CYCLE_SECONDS * 3},
            "documents": [
                {
                    "collection": "devicestatus",
                    "discriminator": {"path": spec["discriminator"][0],
                                      "test": spec["discriminator"][1]},
                    "decomposesTo": spec["decomposes"],
                    "paths": paths,
                    # Written once per loop cycle; its cadence is spec.cadence.
                    "horizon": {"class": "cycle"},
                },
                {"collection": "entries", "decomposesTo": ["SensorGlucose"]},
                {"collection": "treatments",
                 "decomposesTo": ["Bolus", "CarbIntake", "TempBasal", "BGCheck",
                                  "DeviceEvent", "Note"]},
                {"collection": "profile",
                 "decomposesTo": ["TherapySettings", "BasalSchedule",
                                  "CarbRatioSchedule", "SensitivitySchedule",
                                  "TargetRangeSchedule"]},
            ],
            # JSON round-trip: the declarations share sub-dicts, and YAML
            # would otherwise emit anchors and aliases for them.
            "stateSpans": json.loads(json.dumps(spec["spans"])),
            "composition": json.loads(json.dumps(spec["composition"])),
            "commands": json.loads(json.dumps(spec["commands"])),
            "replayInputs": sorted(replay, key=lambda r: r["input"]),
            "settings": {
                "resource": "ControllerSettings",
                "effectiveDated": True,
                "horizon": {"class": "effective-dated"},
                "fields": settings_fields,
            },
            "sensitivity": {
                "labelsSource": "specs/jsonschema/generated/"
                                " (x-sensitivity, x-data-category)",
                "enforcesLocally": False,
                "supportedProfiles": ["full", "clinical", "replay", "effect-only"],
                "defaultProfile": "clinical",
                "unlabelledPolicy": "withhold",
            },
            "queryProfile": {
                "filterableFields": ["date", "created_at", "srvModified", "identifier"],
                "maxPageSize": 1000,
                "operators": ["eq", "gt", "gte", "lt", "lte", "in"],
            },
        },
        "x-declared-but-unobserved": sorted(
            n for n in declared
            if not any(p.split(".")[-1] == n for p in observed)),
    }


def completeness(registration):
    inputs = registration["spec"]["replayInputs"]
    if not inputs:
        return {}
    counts = {}
    for row in inputs:
        status = term_label(row["status"])
        counts[status] = counts.get(status, 0) + 1
    recorded = counts.get("recorded", 0)
    return {
        "inputs": len(inputs),
        "by_status": counts,
        "recorded_share": round(recorded / len(inputs), 4),
        "replayable_share": round(
            (recorded + counts.get("derivable", 0)) / len(inputs), 4),
    }


# ── the grammar's processing rules (D18 addendum, rules 1-4) ───────────────
#
# JSON Schema validates; it cannot say "ignore". The published schema is
# therefore open (no object sets additionalProperties: false), and these
# functions state what a reader does with what validation lets through.

# $defs that use sites extend with sibling properties; closing them would
# reject the extension, so the strict view closes them at the use site.
OPEN_BASES = {"carrier", "fieldTyping"}
_SUBSCHEMA_MAPS = ("properties", "patternProperties", "$defs")
_SUBSCHEMA_LISTS = ("allOf", "anyOf", "oneOf", "prefixItems")
# Shape-bearing single subschemas. `if`/`then`/`else`/`not` are assertions
# over the same instance and are left open: closing an `if` would make it
# fail whenever any other member is present.
_SUBSCHEMA_ONE = ("items", "additionalProperties")


def strict_schema(schema):
    """The grammar with every object closed: the view a v1 reader uses to
    find members it does not know. Not a published schema."""
    strict = copy.deepcopy(schema)

    def close(node, base=False):
        if not isinstance(node, dict):
            return
        open_already = "additionalProperties" in node or "unevaluatedProperties" in node
        if ("properties" in node or "$ref" in node) and not open_already and not base:
            node["unevaluatedProperties"] = False
        for key in _SUBSCHEMA_MAPS:
            for name, sub in (node.get(key) or {}).items():
                close(sub, base=(key == "$defs" and name in OPEN_BASES))
        for key in _SUBSCHEMA_LISTS:
            for sub in node.get(key) or []:
                close(sub)
        for key in _SUBSCHEMA_ONE:
            close(node.get(key))

    close(strict)
    return strict


def _unexpected(error):
    # "Unevaluated properties are not allowed ('a', 'b' were unexpected)"
    tail = error.message.split("(", 1)[-1]
    return re.findall(r"'([^']*)'", tail)


def unknown_grammar_fields(registration, schema):
    """Rule 1, must-ignore. The members a v1 reader does not know, as dotted
    paths. A hub keeps them as written and neither interprets nor serves
    them as data; they never make a registration invalid."""
    found = set()

    def walk(errors):
        for error in errors:
            if error.validator == "unevaluatedProperties":
                where = ".".join(str(p) for p in error.absolute_path)
                for name in _unexpected(error):
                    found.add(f"{where}.{name}" if where else name)
            walk(error.context or [])

    walk(jsonschema.Draft202012Validator(strict_schema(schema)).iter_errors(registration))
    return sorted(found)


def term_label(value):
    """Rule 3. How a hub renders an open-vocabulary value: the shared value,
    or "other: <controllerTerm>"."""
    if isinstance(value, dict) and value.get("value") == "other":
        return f"other: {value['controllerTerm']}"
    return value


def version_plan(entry):
    """Rule 4. For each served version of a kind or extension: the version
    it is stored as, and the declared lossless mapping used, if any. Without
    a mapping a version is stored and served as written; nothing converts."""
    if "versions" in entry:
        versions = entry["versions"]
    elif "version" in entry:
        versions = {"served": [entry["version"]], "stored": entry["version"]}
    else:
        return {}
    stored = versions["stored"]
    if stored not in versions["served"]:
        raise ValueError(f"stored version {stored!r} is not served")
    mappings = {(m["from"], m["to"]): m for m in versions.get("mappings") or []
                if m.get("lossless") is True}
    plan = {}
    for version in versions["served"]:
        mapping = mappings.get((version, stored)) if version != stored else None
        plan[version] = {"storedAs": stored if mapping else version,
                         "convertedVia": mapping}
    return plan


def field_disclosure(registration, field):
    """Rule 2. A field's sensitivity label, or the registration's
    unlabelledPolicy when it has none. An absent policy is `withhold`, the
    schema's only safe default; a name-only (string) field is unlabelled."""
    label = field.get("sensitivity") if isinstance(field, dict) else None
    if label:
        return {"labelled": label}
    policy = (registration.get("spec", {}).get("sensitivity") or {}).get(
        "unlabelledPolicy", "withhold")
    return {"unlabelled": policy}


def resolve_type_ref(root, ref):
    """The definition a typeRef names, from a schema in specs/sync/."""
    base, pointer = ref.split("#", 1)
    for path in sorted((root / "specs" / "sync").glob("*.schema.json")):
        schema = json.loads(path.read_text())
        if schema.get("$id") == base:
            node = schema
            for part in pointer.strip("/").split("/"):
                node = node[part.replace("~1", "/").replace("~0", "~")]
            return node
    raise KeyError(ref)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=OUT_DIR, type=Path)
    ap.add_argument("--check", action="store_true",
                    help="validate committed registrations and exit non-zero on drift")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    schema = json.loads((root / SCHEMA).read_text())
    validator = jsonschema.Draft202012Validator(schema)
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    stale = []
    for key, spec in CONTROLLERS.items():
        registration = build(root, key, spec)
        # x- fields are informational and not part of the grammar.
        checked = {k: v for k, v in registration.items() if not k.startswith("x-")}
        errors = sorted(validator.iter_errors(checked), key=lambda e: e.path)
        if errors:
            for error in errors[:3]:
                print(f"  {key}: INVALID {list(error.path)}: {error.message}")
            return 1
        # Must-ignore would let a misspelt member through; the generator's
        # own output may use only members the grammar defines.
        unknown = unknown_grammar_fields(checked, schema)
        if unknown:
            print(f"  {key}: members the grammar does not define: {unknown}")
            return 1

        dest = out_dir / f"{key}.yaml"
        text = yaml.safe_dump(registration, sort_keys=False, width=88, allow_unicode=True)
        if args.check:
            if not dest.is_file() or dest.read_text() != text:
                stale.append(dest.relative_to(root))
        else:
            dest.write_text(text)

        stats = completeness(registration)
        print(f"  {key:11s} {len(registration['spec']['documents'])} documents, "
              f"{len(registration['spec']['replayInputs'])} replay inputs, "
              f"recorded {stats['recorded_share']:.0%}, "
              f"replayable {stats['replayable_share']:.0%}, "
              f"settings to publish: {len(registration['spec']['settings']['fields'])}")

    # Fixtures are hand-written grammar exercises, not generator outputs:
    # validated, never compared or rewritten.
    for path in sorted((root / FIXTURES_DIR).glob("*.yaml")):
        fixture = yaml.safe_load(path.read_text())
        errors = list(validator.iter_errors(fixture))
        if errors:
            print(f"  fixture {path.name}: INVALID {list(errors[0].path)}: "
                  f"{errors[0].message}")
            return 1
        print(f"  fixture {path.name}: valid; ignored members: "
              f"{len(unknown_grammar_fields(fixture, schema))}")

    if args.check and stale:
        for path in stale:
            print(f"STALE {path}")
        print("\nRun: make schema-sync-model", file=__import__("sys").stderr)
        return 1
    if not args.check:
        print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

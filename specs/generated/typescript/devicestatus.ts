// GENERATED FILE — do not edit.
//
// Source:   aid-devicestatus-2025.yaml
// Evidence: reports/schema-census/devicestatus.census.json
// Emitter:  tools/nsschema/emit/zod_emit.py
//           profile: write   strictness: permissive
//
// Regenerate with: make schema-emit
//
// The type is inferred from the schema, not declared alongside it: a
// TypeScript type checks nothing at runtime, and the documents this parses
// arrive from uploaders and vendor bridges that are not under our control.

import { z } from 'zod';

export const DevicestatusSchema = z.object({
    _id: z.string().optional(),  // 100% of documents, 11 sites, universal
    configuration: z.record(z.string(), z.unknown()).optional(),
    created_at: z.string(),  // 100% of documents, 11 sites, universal
    device: z.string(),  // 100% of documents, 11 sites, universal
    identifier: z.string().optional(),
    isCharging: z.boolean().optional(),
    isValid: z.boolean().optional(),
    loop: z.object({
      automaticDoseRecommendation: z.object({
        bolusVolume: z.number().optional(),  // 26% of documents, 10 sites, core
        tempBasalAdjustment: z.object({
          duration: z.number().optional(),  // 6% of documents, 10 sites, common
          rate: z.number().optional(),  // 6% of documents, 10 sites, common
        }).passthrough().optional(),  // 6% of documents, 10 sites, common
        timestamp: z.string().optional(),  // 26% of documents, 10 sites, core
      }).passthrough().optional(),  // 26% of documents, 10 sites, core
      cob: z.object({
        cob: z.number().optional(),  // 85% of documents, 10 sites, core
        timestamp: z.string().optional(),  // 85% of documents, 10 sites, core
      }).passthrough().optional(),  // 85% of documents, 10 sites, core
      enacted: z.object({
        bolusVolume: z.number().optional(),  // 58% of documents, 10 sites, core
        duration: z.number().optional(),  // 58% of documents, 10 sites, core
        rate: z.number().optional(),  // 58% of documents, 10 sites, core
        received: z.boolean().optional(),  // 58% of documents, 10 sites, core
        timestamp: z.string().optional(),  // 58% of documents, 10 sites, core
      }).passthrough().optional(),  // 58% of documents, 10 sites, core
      failureReason: z.string().optional(),  // 2% of documents, 10 sites, common
      iob: z.object({
        iob: z.number().optional(),  // 85% of documents, 10 sites, core
        timestamp: z.string().optional(),  // 85% of documents, 10 sites, core
      }).passthrough().optional(),  // 85% of documents, 10 sites, core
      name: z.string().optional(),  // 85% of documents, 10 sites, core
      predicted: z.object({
        startDate: z.string().optional(),  // 85% of documents, 10 sites, core
        values: z.array(z.number()).optional(),  // 85% of documents, 10 sites, core
      }).passthrough().optional(),  // 85% of documents, 10 sites, core
      recommendedBolus: z.number().optional(),  // 85% of documents, 10 sites, core
      timestamp: z.string().optional(),  // 85% of documents, 10 sites, core
      version: z.string().optional(),  // 85% of documents, 10 sites, core
    }).passthrough().optional(),  // 85% of documents, 10 sites, core
    mills: z.number().int().optional(),
    openaps: z.object({
      enacted: z.object({
        COB: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        CR: z.number().optional(),  // 11% of documents, 1 sites, vendor
        IOB: z.number().optional(),  // 11% of documents, 1 sites, vendor
        ISF: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        TDD: z.number().optional(),  // 10% of documents, 1 sites, vendor
        bg: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        carbsReq: z.number().int().optional(),  // 0% of documents, 1 sites, sparse
        current_target: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        deliverAt: z.string().optional(),  // 11% of documents, 1 sites, vendor
        duration: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        eventualBG: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        expectedDelta: z.number().optional(),  // 11% of documents, 1 sites, vendor
        id: z.string().optional(),  // 11% of documents, 1 sites, vendor
        insulinForManualBolus: z.number().optional(),  // 11% of documents, 1 sites, vendor
        insulinReq: z.number().optional(),  // 11% of documents, 1 sites, vendor
        manualBolusErrorString: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        minDelta: z.number().optional(),  // 11% of documents, 1 sites, vendor
        predBGs: z.object({
          COB: z.array(z.number().int()).optional(),  // 7% of documents, 1 sites, sparse
          IOB: z.array(z.number().int()).optional(),  // 11% of documents, 1 sites, vendor
          UAM: z.array(z.number().int()).optional(),  // 9% of documents, 1 sites, sparse
          ZT: z.array(z.number().int()).optional(),  // 11% of documents, 1 sites, vendor
        }).passthrough().optional(),  // 11% of documents, 1 sites, vendor
        rate: z.number().optional(),  // 11% of documents, 1 sites, vendor
        reason: z.string().optional(),  // 11% of documents, 1 sites, vendor
        received: z.boolean().optional(),  // 11% of documents, 1 sites, vendor
        reservoir: z.number().optional(),  // 11% of documents, 1 sites, vendor
        sensitivityRatio: z.number().optional(),  // 11% of documents, 1 sites, vendor
        temp: z.string().optional(),  // 11% of documents, 1 sites, vendor
        threshold: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        timestamp: z.string().optional(),  // 11% of documents, 1 sites, vendor
        units: z.number().optional(),  // 3% of documents, 1 sites, sparse
      }).passthrough().optional(),  // 11% of documents, 1 sites, vendor
      iob: z.object({
        activity: z.number().optional(),  // 11% of documents, 1 sites, vendor
        basaliob: z.number().optional(),  // 11% of documents, 1 sites, vendor
        bolusinsulin: z.number().optional(),  // 11% of documents, 1 sites, vendor
        bolusiob: z.number().optional(),  // 11% of documents, 1 sites, vendor
        bolussnooze: z.number().optional(),
        iob: z.number().optional(),  // 11% of documents, 1 sites, vendor
        iobWithZeroTemp: z.object({
          activity: z.number().optional(),  // 11% of documents, 1 sites, vendor
          basaliob: z.number().optional(),  // 11% of documents, 1 sites, vendor
          bolusinsulin: z.number().optional(),  // 11% of documents, 1 sites, vendor
          bolusiob: z.number().optional(),  // 11% of documents, 1 sites, vendor
          iob: z.number().optional(),  // 11% of documents, 1 sites, vendor
          netbasalinsulin: z.number().optional(),  // 11% of documents, 1 sites, vendor
          time: z.string().optional(),  // 11% of documents, 1 sites, vendor
        }).passthrough().optional(),  // 11% of documents, 1 sites, vendor
        lastBolusTime: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        lastTemp: z.object({
          date: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
          duration: z.number().optional(),  // 11% of documents, 1 sites, vendor
          rate: z.number().optional(),  // 11% of documents, 1 sites, vendor
          started_at: z.string().optional(),  // 11% of documents, 1 sites, vendor
          timestamp: z.string().optional(),  // 11% of documents, 1 sites, vendor
        }).passthrough().optional(),  // 11% of documents, 1 sites, vendor
        netbasalinsulin: z.number().optional(),  // 11% of documents, 1 sites, vendor
        time: z.string().optional(),  // 11% of documents, 1 sites, vendor
      }).passthrough().optional(),  // 11% of documents, 1 sites, vendor
      recommendedBolus: z.number().optional(),  // 6% of documents, 1 sites, sparse
      suggested: z.object({
        COB: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        CR: z.number().optional(),  // 11% of documents, 1 sites, vendor
        IOB: z.number().optional(),  // 11% of documents, 1 sites, vendor
        ISF: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        TDD: z.number().optional(),  // 10% of documents, 1 sites, vendor
        bg: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        carbsReq: z.number().int().optional(),  // 0% of documents, 1 sites, sparse
        current_target: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        deliverAt: z.string().optional(),  // 11% of documents, 1 sites, vendor
        duration: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        eventualBG: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        expectedDelta: z.number().optional(),  // 11% of documents, 1 sites, vendor
        id: z.string().optional(),  // 11% of documents, 1 sites, vendor
        insulinForManualBolus: z.number().optional(),  // 11% of documents, 1 sites, vendor
        insulinReq: z.number().optional(),  // 11% of documents, 1 sites, vendor
        manualBolusErrorString: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        minDelta: z.number().optional(),  // 11% of documents, 1 sites, vendor
        predBGs: z.object({
          COB: z.array(z.number().int()).optional(),  // 7% of documents, 1 sites, sparse
          IOB: z.array(z.number().int()).optional(),  // 11% of documents, 1 sites, vendor
          UAM: z.array(z.number().int()).optional(),  // 9% of documents, 1 sites, sparse
          ZT: z.array(z.number().int()).optional(),  // 11% of documents, 1 sites, vendor
        }).passthrough().optional(),  // 11% of documents, 1 sites, vendor
        rate: z.number().optional(),  // 11% of documents, 1 sites, vendor
        reason: z.string().optional(),  // 11% of documents, 1 sites, vendor
        received: z.boolean().optional(),  // 11% of documents, 1 sites, vendor
        reservoir: z.number().optional(),  // 11% of documents, 1 sites, vendor
        sensitivityRatio: z.number().optional(),  // 11% of documents, 1 sites, vendor
        targetBG: z.number().int().optional(),
        temp: z.string().optional(),  // 11% of documents, 1 sites, vendor
        threshold: z.number().int().optional(),  // 11% of documents, 1 sites, vendor
        tick: z.string().optional(),
        timestamp: z.string().optional(),  // 10% of documents, 1 sites, vendor
        units: z.number().optional(),  // 3% of documents, 1 sites, sparse
        variable_sens: z.number().optional(),
      }).passthrough().optional(),  // 11% of documents, 1 sites, vendor
      version: z.string().optional(),  // 11% of documents, 1 sites, vendor
    }).passthrough().optional(),  // 11% of documents, 1 sites, vendor
    override: z.object({
      active: z.boolean().optional(),  // 85% of documents, 10 sites, core
      currentCorrectionRange: z.object({
        maxValue: z.number().optional(),  // 9% of documents, 9 sites, common
        minValue: z.number().optional(),  // 9% of documents, 9 sites, common
      }).passthrough().optional(),  // 9% of documents, 9 sites, common
      duration: z.number().optional(),  // 5% of documents, 9 sites, common
      multiplier: z.number().optional(),  // 7% of documents, 9 sites, common
      name: z.string().optional(),  // 9% of documents, 9 sites, common
      timestamp: z.string().optional(),  // 85% of documents, 10 sites, core
    }).passthrough().optional(),  // 85% of documents, 10 sites, core
    pump: z.object({
      battery: z.object({
        display: z.boolean().optional(),  // 10% of documents, 1 sites, vendor
        percent: z.number().int().optional(),  // 12% of documents, 2 sites, vendor
        status: z.enum(["critical", "low", "normal"]).optional(),
        string: z.string().optional(),  // 11% of documents, 1 sites, vendor
        voltage: z.number().optional(),
      }).passthrough().optional(),  // 12% of documents, 2 sites, vendor
      bolusIncrement: z.number().optional(),  // 6% of documents, 1 sites, sparse
      bolusing: z.boolean().optional(),  // 85% of documents, 10 sites, core
      clock: z.string().optional(),  // 96% of documents, 10 sites, core
      extended: z.record(z.string(), z.unknown()).optional(),
      manufacturer: z.string().optional(),  // 84% of documents, 10 sites, core
      model: z.string().optional(),  // 84% of documents, 10 sites, core
      pumpID: z.string().optional(),  // 85% of documents, 10 sites, core
      reservoir: z.number().optional(),  // 14% of documents, 10 sites, core
      reservoir_display_override: z.string().optional(),  // 1% of documents, 10 sites, common
      reservoir_level_override: z.number().int().optional(),  // 1% of documents, 10 sites, common
      secondsFromGMT: z.number().int().optional(),  // 85% of documents, 10 sites, core
      status: z.object({
        bolusing: z.boolean().optional(),  // 11% of documents, 1 sites, vendor
        status: z.string().optional(),  // 11% of documents, 1 sites, vendor
        suspended: z.boolean().optional(),  // 11% of documents, 1 sites, vendor
        timestamp: z.string().optional(),  // 11% of documents, 1 sites, vendor
      }).passthrough().optional(),  // 11% of documents, 1 sites, vendor
      suspended: z.boolean().optional(),  // 85% of documents, 10 sites, core
    }).passthrough().optional(),  // 96% of documents, 10 sites, core
    srvCreated: z.number().int().optional(),
    srvModified: z.number().int().optional(),
    uploader: z.object({
      battery: z.number().int().optional(),  // 100% of documents, 11 sites, universal
      batteryVoltage: z.number().optional(),
      isCharging: z.boolean().optional(),  // 11% of documents, 1 sites, vendor
      name: z.string().optional(),  // 85% of documents, 10 sites, core
      timestamp: z.string().optional(),  // 85% of documents, 10 sites, core
      type: z.string().optional(),  // 4% of documents, 1 sites, vendor
    }).passthrough().optional(),  // 100% of documents, 11 sites, universal
    uploaderBattery: z.number().int().optional(),
    utcOffset: z.number().int().optional(),  // 100% of documents, 11 sites, universal
  }).passthrough();

export type Devicestatus = z.infer<typeof DevicestatusSchema>;

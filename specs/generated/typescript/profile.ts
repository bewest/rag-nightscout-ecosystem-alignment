// GENERATED FILE — do not edit.
//
// Source:   aid-profile-2025.yaml
// Evidence: reports/schema-census/profile.census.json
// Emitter:  tools/nsschema/emit/zod_emit.py
//           profile: write   strictness: permissive
//
// Regenerate with: make schema-emit
//
// The type is inferred from the schema, not declared alongside it: a
// TypeScript type checks nothing at runtime, and the documents this parses
// arrive from uploaders and vendor bridges that are not under our control.

import { z } from 'zod';

export const ProfileSchema = z.object({
    _id: z.string().optional(),  // 100% of documents, 11 sites, universal
    created_at: z.string().optional(),  // 11% of documents, 2 sites, vendor
    defaultProfile: z.string(),  // 100% of documents, 11 sites, universal
    enteredBy: z.string().optional(),  // 99% of documents, 10 sites, core
    identifier: z.string().optional(),
    isValid: z.boolean().optional(),
    loopSettings: z.object({
      bundleIdentifier: z.string().optional(),  // 99% of documents, 10 sites, core
      deviceToken: z.string().optional(),  // 99% of documents, 10 sites, core
      dosingEnabled: z.boolean().optional(),  // 99% of documents, 10 sites, core
      dosingStrategy: z.string().optional(),  // 99% of documents, 10 sites, core
      maximumBasalRatePerHour: z.number().optional(),  // 99% of documents, 10 sites, core
      maximumBolus: z.number().int().optional(),  // 99% of documents, 10 sites, core
      minimumBGGuard: z.number().optional(),  // 99% of documents, 10 sites, core
      overridePresets: z.array(z.object({
        duration: z.number().int().optional(),  // 99% of documents, 10 sites, core
        insulinNeedsScaleFactor: z.number().optional(),  // 89% of documents, 9 sites, core
        name: z.string().optional(),  // 99% of documents, 10 sites, core
        symbol: z.string().optional(),  // 99% of documents, 10 sites, core
        targetRange: z.array(z.number()).optional(),  // 69% of documents, 7 sites, core
      }).passthrough()).optional(),  // 99% of documents, 10 sites, core
      preMealTargetRange: z.array(z.number()).optional(),  // 89% of documents, 9 sites, core
      scheduleOverride: z.object({
        duration: z.number().int().optional(),  // 61% of documents, 9 sites, core
        insulinNeedsScaleFactor: z.number().optional(),  // 58% of documents, 9 sites, core
        name: z.string().optional(),  // 59% of documents, 9 sites, core
        symbol: z.string().optional(),  // 59% of documents, 9 sites, core
        targetRange: z.array(z.number()).optional(),  // 26% of documents, 6 sites, common
      }).passthrough().optional(),  // 61% of documents, 9 sites, core
    }).passthrough().optional(),  // 99% of documents, 10 sites, core
    mills: z.union([z.number().int(), z.string()]).optional(),  // 100% of documents, 11 sites, universal
    srvCreated: z.number().int().optional(),
    srvModified: z.number().int().optional(),  // 1% of documents, 1 sites, rare
    startDate: z.string().optional(),  // 100% of documents, 11 sites, universal
    store: z.record(z.string(), z.object({
      basal: z.array(z.object({
        time: z.string().optional(),  // 100% of documents, 11 sites, universal
        timeAsSeconds: z.number().int().optional(),  // 100% of documents, 11 sites, universal
        value: z.number().optional(),  // 100% of documents, 11 sites, universal
      }).passthrough()).optional(),  // 100% of documents, 11 sites, universal
      carbratio: z.array(z.object({
        time: z.string().optional(),  // 100% of documents, 11 sites, universal
        timeAsSeconds: z.number().int().optional(),  // 100% of documents, 11 sites, universal
        value: z.number().optional(),  // 100% of documents, 11 sites, universal
      }).passthrough()).optional(),  // 100% of documents, 11 sites, universal
      carbs_hr: z.union([z.number(), z.string()]).optional(),  // 100% of documents, 11 sites, universal
      delay: z.union([z.number().int(), z.string()]).optional(),  // 100% of documents, 11 sites, universal
      dia: z.number().optional(),  // 100% of documents, 11 sites, universal
      insulinCurve: z.enum(["bilinear", "exponential", "rapid-acting", "ultra-rapid"]).optional(),
      insulinPeakTime: z.number().int().optional(),
      sens: z.array(z.object({
        time: z.string().optional(),  // 100% of documents, 11 sites, universal
        timeAsSeconds: z.number().int().optional(),  // 100% of documents, 11 sites, universal
        value: z.number().optional(),  // 100% of documents, 11 sites, universal
      }).passthrough()).optional(),  // 100% of documents, 11 sites, universal
      startDate: z.string().optional(),  // 1% of documents, 1 sites, rare
      target_high: z.array(z.object({
        time: z.string().optional(),  // 100% of documents, 11 sites, universal
        timeAsSeconds: z.number().int().optional(),  // 100% of documents, 11 sites, universal
        value: z.number().optional(),  // 100% of documents, 11 sites, universal
      }).passthrough()).optional(),  // 100% of documents, 11 sites, universal
      target_low: z.array(z.object({
        time: z.string().optional(),  // 100% of documents, 11 sites, universal
        timeAsSeconds: z.number().int().optional(),  // 100% of documents, 11 sites, universal
        value: z.number().optional(),  // 100% of documents, 11 sites, universal
      }).passthrough()).optional(),  // 100% of documents, 11 sites, universal
      timezone: z.string().optional(),  // 100% of documents, 11 sites, universal
      units: z.string().optional(),  // 100% of documents, 11 sites, universal
    }).passthrough()),  // 100% of documents, 11 sites, universal
    units: z.string().optional(),  // 100% of documents, 11 sites, universal
    utcOffset: z.number().int().optional(),
  }).passthrough();

export type Profile = z.infer<typeof ProfileSchema>;

// GENERATED FILE — do not edit.
//
// Source:   aid-entries-2025.yaml
// Evidence: reports/schema-census/entries.census.json
// Emitter:  tools/nsschema/emit/zod_emit.py
//           profile: write   strictness: permissive
//
// Regenerate with: make schema-emit
//
// The type is inferred from the schema, not declared alongside it: a
// TypeScript type checks nothing at runtime, and the documents this parses
// arrive from uploaders and vendor bridges that are not under our control.

import { z } from 'zod';

export const EntriesSchema = z.object({
    _id: z.string().optional(),  // 100% of documents, 11 sites, universal
    app: z.string().optional(),
    date: z.number(),  // 100% of documents, 11 sites, universal
    dateString: z.string(),  // 100% of documents, 11 sites, universal
    delta: z.number().optional(),  // 4% of documents, 1 sites, sparse
    device: z.string().optional(),  // 94% of documents, 11 sites, core
    direction: z.string().optional(),  // 85% of documents, 11 sites, core
    filtered: z.number().optional(),  // 13% of documents, 2 sites, vendor
    glucose: z.number().int().optional(),  // 6% of documents, 1 sites, vendor
    identifier: z.string().optional(),
    intercept: z.number().optional(),
    isCalibration: z.boolean().optional(),  // 62% of documents, 10 sites, core
    isReadOnly: z.boolean().optional(),
    isValid: z.boolean().optional(),
    mbg: z.number().optional(),  // 0% of documents, 10 sites, common
    modifiedBy: z.string().optional(),
    noise: z.number().int().optional(),  // 7% of documents, 1 sites, vendor
    rssi: z.number().int().optional(),  // 4% of documents, 1 sites, sparse
    scale: z.number().optional(),
    sgv: z.number().optional(),  // 100% of documents, 11 sites, universal
    slope: z.number().optional(),
    srvCreated: z.number().int().optional(),
    srvModified: z.number().int().optional(),
    subject: z.string().optional(),
    sysTime: z.string().optional(),  // 100% of documents, 11 sites, universal
    trend: z.number().int().optional(),  // 72% of documents, 10 sites, core
    trendRate: z.number().optional(),  // 46% of documents, 10 sites, core
    type: z.enum(["cal", "mbg", "sgv"]),  // 100% of documents, 11 sites, universal
    unfiltered: z.number().optional(),  // 13% of documents, 2 sites, vendor
    units: z.enum(["mg", "mg/dL", "mg/dl", "mmol", "mmol/L"]).optional(),
    utcOffset: z.number().int().optional(),  // 100% of documents, 11 sites, universal
  }).passthrough();

export type Entries = z.infer<typeof EntriesSchema>;

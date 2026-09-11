// GENERATED FILE — do not edit.
//
// Source:   aid-treatments-2025.yaml
// Evidence: reports/schema-census/treatments.census.json
// Emitter:  tools/nsschema/emit/zod_emit.py
//           profile: write   strictness: permissive
//
// Regenerate with: make schema-emit
//
// The type is inferred from the schema, not declared alongside it: a
// TypeScript type checks nothing at runtime, and the documents this parses
// arrive from uploaders and vendor bridges that are not under our control.

import { z } from 'zod';

export const TreatmentsSchema = z.object({
    _id: z.string().optional(),  // 100% of documents, 11 sites, universal
    absolute: z.number().optional(),  // 55% of documents, 10 sites, core
    absorptionTime: z.number().int().optional(),  // 2% of documents, 10 sites, common
    amount: z.number().optional(),  // 46% of documents, 10 sites, core
    app: z.string().optional(),
    automatic: z.boolean().optional(),  // 81% of documents, 10 sites, core
    bolusType: z.enum(["Dual", "Normal", "Square"]).optional(),
    carbs: z.number().nullable().optional(),  // 100% of documents, 11 sites, universal
    correctionRange: z.array(z.number()).optional(),  // 0% of documents, 7 sites, common
    created_at: z.string(),  // 100% of documents, 11 sites, universal
    device: z.string().optional(),
    duration: z.number().optional(),  // 91% of documents, 10 sites, core
    durationType: z.string().optional(),  // 0% of documents, 1 sites, rare
    endmills: z.number().int().optional(),  // 0% of documents, 1 sites, rare
    enteredBy: z.string().optional(),  // 100% of documents, 11 sites, universal
    eventType: z.string(),  // 100% of documents, 11 sites, universal
    fat: z.number().optional(),  // 2% of documents, 1 sites, sparse
    foodType: z.string().optional(),  // 2% of documents, 10 sites, common
    glucose: z.number().optional(),  // 0% of documents, 1 sites, sparse
    glucoseType: z.string().optional(),  // 0% of documents, 1 sites, sparse
    id: z.string().optional(),  // 15% of documents, 1 sites, vendor
    identifier: z.string().optional(),  // 0% of documents, 1 sites, sparse
    insulin: z.number().nullable().optional(),  // 100% of documents, 11 sites, universal
    insulinNeedsScaleFactor: z.number().optional(),  // 1% of documents, 9 sites, common
    insulinType: z.string().optional(),  // 80% of documents, 10 sites, core
    isBasalInsulin: z.boolean().optional(),
    isReadOnly: z.boolean().optional(),
    isValid: z.boolean().optional(),
    mills: z.number().int().optional(),  // 0% of documents, 1 sites, rare
    modifiedBy: z.string().optional(),
    notes: z.string().optional(),  // 1% of documents, 10 sites, common
    percent: z.number().optional(),
    percentage: z.number().int().optional(),
    profile: z.string().optional(),
    profileJson: z.string().optional(),
    programmed: z.number().optional(),  // 35% of documents, 10 sites, core
    protein: z.number().optional(),  // 2% of documents, 1 sites, sparse
    pumpId: z.number().int().optional(),
    pumpSerial: z.string().optional(),
    pumpType: z.string().optional(),
    rate: z.number().optional(),  // 55% of documents, 10 sites, core
    reason: z.string().optional(),  // 1% of documents, 10 sites, common
    remoteAddress: z.string().optional(),  // 0% of documents, 3 sites, common
    srvCreated: z.number().int().optional(),
    srvModified: z.number().int().optional(),
    subject: z.string().optional(),
    syncIdentifier: z.string().optional(),  // 83% of documents, 10 sites, core
    targetBottom: z.number().optional(),  // 0% of documents, 1 sites, sparse
    targetTop: z.number().optional(),  // 0% of documents, 1 sites, sparse
    temp: z.enum(["absolute", "percent"]).optional(),  // 46% of documents, 10 sites, core
    timeshift: z.number().int().optional(),
    timestamp: z.union([z.number().int(), z.string()]).optional(),  // 84% of documents, 10 sites, core
    type: z.enum(["Normal", "Priming", "SMB", "normal"]).optional(),  // 35% of documents, 10 sites, core
    unabsorbed: z.number().optional(),  // 35% of documents, 10 sites, core
    units: z.string().optional(),  // 0% of documents, 1 sites, sparse
    userEnteredAt: z.string().optional(),  // 2% of documents, 10 sites, common
    userLastModifiedAt: z.string().optional(),  // 0% of documents, 5 sites, common
    utcOffset: z.number().int().optional(),  // 100% of documents, 11 sites, universal
  }).passthrough();

export type Treatments = z.infer<typeof TreatmentsSchema>;

# Terminology Consistency Report

Generated: 2026-01-17T21:10:42.813470+00:00

## Summary

| Metric | Value |
|--------|-------|
| Alignment Terms | 661 |
| Project-Specific Terms | 1681 |
| Projects Covered | Collection, Description, Nightscout, Loop, AAPS, Trio, xDrip+, Upload, Download, Identity Field, Nightscout Field, Purpose, Source Code, Value, Source, Nightscout eventType, Override/Adjustment Model Location, Location, Lines, oref0, oref0/openaps, Omnipod DASH, Dana RS, Medtronic, Offset, Size, Command, Direction, Unit, CRC Variant, Entry, Head, Date, Body, Impact, Primary Model, Formula Source, Legacy Model, Loop Peak, oref0 Peak, AAPS Peak, Trio Peak, Delay, Minimum DIA, Default DIA, Enforcement, AID Systems, xDrip+ Android, xDrip4iOS, Calibration Options, oref0/AAPS/Trio, Systems Affected, Nightscout Collection, Key Fields, Field, Effect, NS Mapping, Peak (minutes), Insulin Type, Format, Example, Override, Temp Target, JSON Value, Peak (min), File, Loop Equivalent, Notes, Calculation, oref0 Default, Primary Source, API Version, Authentication, Sync Method, Primary ID, Update Method, Secondary ID, Used By, v1 Polling, v3 History, v1 Syntax, v3 Syntax, Loop/Trio, Loop PumpManager, AAPS Pump, Protocol, Bolus Step, Basal Step, TBR Duration Step, Loop `BolusState`, Loop `BasalDeliveryState`, UUID, G6, G7, Opcode (Tx/Rx), G6 (0x31/0x4F), G7 (0x4E), Implementation, Key Derivation, ID Format, Detection, G6 Name, G7 Name, Reliable Glucose, oref0/AAPS, Source (Line), Formula, Key Carb Absorption Files, Sensor Type, Family, Security Generation, Raw Value, Sensors, IC Manufacturer, Bit Count, Name, Service UUID, Key Characteristic UUIDs, Start Command, Data Format, DiaBLE, LibreTransmitter, LoopCaregiver, Loop (Receiver), Nightscout State, Query Parameter, Required, Remote 1.0, Remote 2.0, LoopFollow, Nightguard, Trio Caregiver*, Category, Trigger, Default Threshold, Values, Target AID, Transport, Security, Type String, Parameters, Detail, Loop APNS, TRC, Author, Changes |
| Term Occurrences Scanned | 3749 |
| Issues Found | 0 |

## Most Used Terms

| Term | Occurrences | Files | Type |
|----|-------------|-------|------|
| Glucose | 71 | 71 | Project |
| Nightscout | 66 | 66 | Alignment |
| insulin | 63 | 63 | Project |
| Insulin | 63 | 63 | Project |
| timestamp | 59 | 59 | Project |
| timeStamp | 59 | 59 | Project |
| Timestamp | 59 | 59 | Alignment |
| profile | 51 | 51 | Project |
| Profile | 51 | 51 | Alignment |
| duration | 49 | 49 | Project |
| Duration | 49 | 49 | Alignment |
| Minutes | 48 | 48 | Project |
| Default | 48 | 48 | Project |
| default | 48 | 48 | Project |
| DEFAULT | 48 | 48 | Alignment |
| entries | 46 | 46 | Project |
| treatments | 45 | 45 | Project |
| Treatments | 45 | 45 | Alignment |
| Temp Basal | 40 | 40 | Alignment |
| Override | 40 | 40 | Alignment |
| target | 40 | 40 | Project |
| device | 37 | 37 | Project |
| Device | 37 | 37 | Project |
| System | 36 | 36 | Alignment |
| devicestatus | 33 | 33 | Project |
| DeviceStatus | 33 | 33 | Project |
| battery | 33 | 33 | Project |
| Custom | 30 | 30 | Project |
| eventType | 30 | 30 | Project |
| enteredBy | 30 | 30 | Project |

## Alignment Term Mappings

| Alignment Term | Project Mappings |
|----------------|------------------|
| **AAPS** | Primary Model: `Exponential`, Formula Source: `oref0`, Minimum DIA: `5 hr` (+13 more) |
| **Absorption Time** | Loop: `absorptionTime`, oref0/AAPS/Trio: `Global carbs_hr rate`, Nightscout: `absorptionTime` |
| **Absorption Tracking** | Loop/Trio: `Per-entry with AbsorbedCarbValue`, oref0/AAPS: `Global deviation-based inference` |
| **Accu-Chek Combo** | AAPS: `combov2`, Protocol: `RF + ruffy` |
| **Accu-Chek Insight** | AAPS: `insight`, Protocol: `BLE + SightParser`, Bolus Step: `0.01-0.05 U` (+2 more) |
| **Active** | Loop `BasalDeliveryState`: `.active`, AAPS: `isSuspended() == false` |
| **Activity** | oref0: `iob.activity`, AAPS: `iobTotal.activity`, Trio: `iob.activity` (+1 more) |
| **Adaptation** | Loop: `Real-time based on ICE`, oref0/AAPS/Trio: `Limited deviation-based` |
| **Advertisement** | UUID: `FEBC`, Description: `Dexcom advertisement service` |
| **Age** | G7 (0x4E): `Bytes 10-11` |
| **Algorithm State** | G6 (0x31/0x4F): `Byte 12`, G7 (0x4E): `Byte 14` |
| **Amount** | Loop: `quantity`, oref0: `carbs`, AAPS: `amount` (+1 more) |
| **Auth Challenge** | Opcode (Tx/Rx): `0x04/0x05`, Purpose: `Complete authentication` |
| **Auth Request** | Opcode (Tx/Rx): `0x01/0x03`, Purpose: `Initiate authentication` |
| **Authentication** | UUID: `F8083535-849E-531C-C594-30F1F86A4EA5`, Description: `Auth handshake`, G6: `AES-128-ECB challenge-response` (+1 more) |
| **Backfill Finished** | Opcode (Tx/Rx): `0x59`, Purpose: `Backfill complete` |
| **Backfill Opcode** | G6: `0x50/0x51`, G7: `0x59` |
| **Backfill** | UUID: `F8083536-849E-531C-C594-30F1F86A4EA5`, Description: `Historical data`, Opcode (Tx/Rx): `0x50/0x51` (+1 more) |
| **Basal IOB** | oref0: `iob.basaliob`, AAPS: `iobTotal.basaliob`, Trio: `iob.basaliob` (+1 more) |
| **Battery Status** | Opcode (Tx/Rx): `0x22/0x23`, Purpose: `Battery voltage and runtime` |
| **Bolus IOB** | oref0: `iob.bolusiob`, Trio: `iob.bolusiob`, xDrip+: `Not applicable` |
| **Bolus Snooze** | oref0: `iob.bolussnooze`, AAPS: `iobTotal.bolussnooze`, Trio: `iob.bolussnooze` (+1 more) |
| **Bolus** | Loop PumpManager: `enactBolus`, AAPS Pump: `deliverTreatment` |
| **Bond Request** | Opcode (Tx/Rx): `0x07/0x08`, Purpose: `Request Bluetooth bonding` |
| **Bridge Device** | Omnipod DASH: `No`, Dana RS: `No`, Medtronic: `RileyLink required` |
| **Bridge Devices** | xDrip+ Android: `6+`, xDrip4iOS: `4`, Loop: `No` (+1 more) |
| **CGM Data Service** | UUID: `F8083532-849E-531C-C594-30F1F86A4EA5`, Description: `Main data service` |
| **CGMBLEKit** | Implementation: `aes128ecb_encrypt`, Key Derivation: `key = "00" + transmitterID + "00" + transmitterID` |
| **Calibrate Glucose** | Opcode (Tx/Rx): `0x34/0x35`, Purpose: `Submit calibration value` |
| **Calibration Data** | Opcode (Tx/Rx): `0x32/0x33`, Purpose: `Get/set calibration` |

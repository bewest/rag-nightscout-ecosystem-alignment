# Trio Remote Commands (Announcements)

This document details Trio's remote command system using Nightscout Announcements, enabling remote bolus, temp basal, and loop control.

## Source Files

| File | Purpose |
|------|---------|
| `trio:FreeAPS/Sources/Models/Announcement.swift` | Announcement model and parsing |
| `trio:FreeAPS/Sources/APS/FetchAnnouncementsManager.swift` | Announcement fetch and enact |
| `trio:FreeAPS/Sources/Services/Network/NightscoutAPI.swift` | NS API fetch |

---

## Overview

Trio supports remote commands via Nightscout Announcements. A caregiver or remote user can create an Announcement treatment in Nightscout, which Trio will fetch and execute.

**Security**: Only announcements with `enteredBy: "remote"` are processed.

---

## Announcement Structure

### Nightscout Treatment Format

```json
{
  "eventType": "Announcement",
  "created_at": "2026-01-16T12:00:00.000Z",
  "enteredBy": "remote",
  "notes": "bolus: 2.5"
}
```

### Swift Model

```swift
// trio:Announcement.swift#L3-L7
struct Announcement: JSON {
    let createdAt: Date
    let enteredBy: String
    let notes: String
    
    static let remote = "remote"
}
```

---

## Supported Commands

### 1. Bolus Command

**Format**: `bolus: <amount>`

```
notes: "bolus: 2.5"
notes: "bolus:2.5"
notes: "Bolus: 2.5"
```

**Parsed as**:
```swift
case .bolus(amount):
    // Delivers amount units of insulin
```

### 2. Pump Control

**Format**: `pump: <action>`

```
notes: "pump: suspend"
notes: "pump: resume"
```

**Parsed as**:
```swift
case .pump(action):
    // action: .suspend or .resume
```

### 3. Loop Control

**Format**: `looping: <true/false>`

```
notes: "looping: false"
notes: "looping: true"
```

**Parsed as**:
```swift
case .looping(enabled):
    // Enables or disables closed loop
```

### 4. Temp Basal

**Format**: `tempbasal: <rate>,<duration>`

```
notes: "tempbasal: 0.5,30"    // 0.5 U/hr for 30 minutes
notes: "tempbasal: 0,60"      // Zero temp for 60 minutes
```

**Parsed as**:
```swift
case .tempbasal(rate: rate, duration: duration):
    // Sets temp basal with specified rate and duration
```

---

## Parsing Logic

```swift
// trio:Announcement.swift#L10-L36
var action: AnnouncementAction? {
    let components = notes.replacingOccurrences(of: " ", with: "").split(separator: ":")
    guard components.count == 2 else {
        return nil
    }
    
    let command = String(components[0]).lowercased()
    let arguments = String(components[1]).lowercased()
    
    switch command {
    case "bolus":
        guard let amount = Decimal(from: arguments) else { return nil }
        return .bolus(amount)
        
    case "pump":
        guard let action = PumpAction(rawValue: arguments) else { return nil }
        return .pump(action)
        
    case "looping":
        guard let looping = Bool(from: arguments) else { return nil }
        return .looping(looping)
        
    case "tempbasal":
        let basalComponents = arguments.split(separator: ",")
        guard basalComponents.count == 2 else { return nil }
        guard let rate = Decimal(from: String(basalComponents[0])),
              let duration = Decimal(from: String(basalComponents[1])) else { return nil }
        return .tempbasal(rate: rate, duration: duration)
        
    default:
        return nil
    }
}
```

---

## Fetch Flow

### Polling Interval

Announcements are fetched every 5 minutes:

```swift
// trio:FetchAnnouncementsManager.swift#L16
private let timer = DispatchTimer(timeInterval: 5.minutes.timeInterval)
```

### Fetch and Process

```swift
// trio:FetchAnnouncementsManager.swift#L23-L51
private func subscribe() {
    timer.publisher
        .receive(on: processQueue)
        .flatMap { _ -> AnyPublisher<[Announcement], Never> in
            guard self.settingsManager.settings.allowAnnouncements else {
                return Just([]).eraseToAnyPublisher()
            }
            return self.nightscoutManager.fetchAnnouncements()
        }
        .sink { announcements in
            // Filter to announcements newer than last sync
            guard let last = announcements
                .filter({ $0.createdAt > self.announcementsStorage.syncDate() })
                .sorted(by: { $0.createdAt < $1.createdAt })
                .last
            else { return }
            
            // Store and enact
            self.announcementsStorage.storeAnnouncements([last], enacted: false)
            
            if self.settingsManager.settings.allowAnnouncements,
               let recent = self.announcementsStorage.recent(),
               recent.action != nil
            {
                debug(.nightscout, "New announcements found")
                self.apsManager.enactAnnouncement(recent)
            }
        }
        .store(in: &lifetime)
}
```

### NS API Query

```swift
// trio:NightscoutAPI.swift#L246-L279
func fetchAnnouncement(sinceDate: Date? = nil) -> AnyPublisher<[Announcement], Swift.Error> {
    // GET /api/v1/treatments.json
    //   ?find[eventType]=Announcement
    //   &find[enteredBy]=remote
    //   &find[created_at][$gte]=...
    
    components.queryItems = [
        URLQueryItem(name: "find[eventType]", value: "Announcement"),
        URLQueryItem(name: "find[enteredBy]", 
                    value: Announcement.remote.addingPercentEncoding(
                        withAllowedCharacters: .urlHostAllowed))
    ]
}
```

---

## Settings

| Setting | Purpose |
|---------|---------|
| `allowAnnouncements` | Master toggle for remote command processing |

When `allowAnnouncements` is `false`, announcements are not fetched or processed.

---

## Action Types

```swift
// trio:Announcement.swift#L47-L52
enum AnnouncementAction {
    case bolus(Decimal)
    case pump(PumpAction)
    case looping(Bool)
    case tempbasal(rate: Decimal, duration: Decimal)
}

enum PumpAction: String {
    case suspend
    case resume
}
```

---

## Security Considerations

### 1. enteredBy Validation

Only announcements with `enteredBy: "remote"` are fetched:

```swift
URLQueryItem(name: "find[enteredBy]", value: Announcement.remote)
```

This prevents:
- Trio's own announcements from being re-processed
- Other apps' announcements from being interpreted as commands

### 2. Setting Gate

The `allowAnnouncements` setting must be explicitly enabled.

### 3. Timestamp Filtering

Only announcements newer than the last sync date are processed, preventing replay of old commands.

---

## Creating Remote Commands

To create a remote command in Nightscout:

### Via Nightscout Careportal

1. Open Nightscout Careportal
2. Select "Announcement" event type
3. Set `enteredBy` to "remote"
4. Enter command in notes field
5. Submit

### Via Nightscout API

```bash
curl -X POST "https://your-ns-site.com/api/v1/treatments" \
  -H "api-secret: $(echo -n 'your-api-secret' | sha1sum | cut -d' ' -f1)" \
  -H "Content-Type: application/json" \
  -d '{
    "eventType": "Announcement",
    "enteredBy": "remote",
    "notes": "bolus: 1.5",
    "created_at": "'$(date -u +%Y-%m-%dT%H:%M:%S.000Z)'"
  }'
```

---

## Comparison with Other Systems

| Feature | Trio | Loop | AAPS |
|---------|------|------|------|
| Remote Bolus | Yes (Announcements) | Yes (Remote Overrides) | Yes (NS commands) |
| Remote Temp Basal | Yes | Via Overrides | Yes |
| Remote Suspend | Yes (pump: suspend) | Yes | Yes |
| Remote Loop Control | Yes (looping: bool) | Via Overrides | Yes |
| Authentication | enteredBy filter | Apple Push + Token | NS + Token |

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial remote commands documentation from source analysis |

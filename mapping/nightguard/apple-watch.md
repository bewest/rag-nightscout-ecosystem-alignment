# Nightguard Apple Watch Implementation

This document describes Nightguard's Apple Watch app architecture, including WatchConnectivity, complications, and background refresh.

## Overview

Nightguard provides a native watchOS app that displays blood glucose values with:
- Standalone Watch app with BG display
- Watch complications for quick glance
- Two-way sync with iPhone app
- Independent data fetching capability

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    watchOS App Architecture                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    ExtensionDelegate                         ││
│  │  ├── applicationDidFinishLaunching()                        ││
│  │  ├── activateWatchConnectivity()                            ││
│  │  ├── handleWatchMessages()                                  ││
│  │  └── applicationDidBecomeActive()                           ││
│  └─────────────────────────────────────────────────────────────┘│
│                          │                                       │
│           ┌──────────────┴──────────────┐                       │
│           ▼                              ▼                       │
│  ┌─────────────────┐         ┌─────────────────────────┐        │
│  │ MainController  │         │ WatchMessageService     │        │
│  │ (UI Display)    │         │ (Phone Communication)   │        │
│  └─────────────────┘         └─────────────────────────┘        │
│           │                              │                       │
│           ▼                              ▼                       │
│  ┌─────────────────┐         ┌─────────────────────────┐        │
│  │ MainViewModel   │         │ Message Types:          │        │
│  │ (State Mgmt)    │         │ ├── SnoozeMessage       │        │
│  └─────────────────┘         │ ├── UserDefaultSyncMsg  │        │
│           │                  │ ├── NightscoutDataMsg   │        │
│           ▼                  │ └── KeepAwakeMessage    │        │
│  ┌─────────────────────────┐ └─────────────────────────┘        │
│  │ NightscoutCacheService  │                                    │
│  │ (Data Layer - Shared)   │                                    │
│  └─────────────────────────┘                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## ExtensionDelegate

**Source**: `nightguard:nightguard WatchKit App/ExtensionDelegate.swift`

The `ExtensionDelegate` is the entry point for the watchOS app.

### Initialization

```swift
func applicationDidFinishLaunching() {
    activateWatchConnectivity()
    ExtensionDelegate.singleton = self
    BackgroundRefreshLogger.info("Application did finish launching")
    AppMessageService.singleton.keepAwakePhoneApp()
}
```

### WatchConnectivity Setup

```swift
func activateWatchConnectivity() {
    if WCSession.isSupported() {
        session = WCSession.default
        handleWatchMessages()
    }
}

var session: WCSession? {
    didSet {
        if let session = session {
            session.delegate = WatchMessageService.singleton
            session.activate()
        }
    }
}
```

---

## WatchConnectivity Messages

Nightguard uses custom message types for phone↔watch communication.

### Message Types

| Message | Direction | Purpose |
|---------|-----------|---------|
| `SnoozeMessage` | Bi-directional | Sync snooze state |
| `UserDefaultSyncMessage` | Phone → Watch | Sync settings |
| `NightscoutDataMessage` | Phone → Watch | Share BG data |
| `KeepAwakeMessage` | Watch → Phone | Keep phone app alive |
| `WatchSyncRequestMessage` | Watch → Phone | Request settings sync |

### SnoozeMessage Handling

```swift
WatchMessageService.singleton.onMessage { (message: SnoozeMessage) in
    AlarmRule.snoozeFromMessage(message)
    MainController.mainViewModel.refreshData(forceRefresh: true, moveToLatestValue: false)
}
```

### UserDefaults Sync Handling

```swift
WatchMessageService.singleton.onMessage { (message: UserDefaultSyncMessage) in
    
    var updatedKeys: [String] = []
    let observationToken = UserDefaultsValueGroups.observeChanges(
        in: UserDefaultsValueGroups.GroupNames.watchSync
    ) { value, _ in
        updatedKeys.append(value.key)
    }
    defer { observationToken.cancel() }
    
    // Apply settings from phone
    for var value in UserDefaultsValueGroups.values(
        from: UserDefaultsValueGroups.GroupNames.watchSync
    ) ?? [] {
        if let anyValue = message.dictionary[value.key] {
            value.anyValue = anyValue
        }
    }
    
    // Handle URI changes (reset cache)
    if updatedKeys.contains(UserDefaultsRepository.baseUri.key) {
        NightscoutCacheService.singleton.resetCache()
    }
    
    // Refresh display
    MainController.mainViewModel.refreshData(forceRefresh: true, moveToLatestValue: false)
}
```

---

## Complications

Nightguard provides watch face complications via `CLKComplicationDataSource`.

**Source**: `nightguard:nightguard Complication/`

### Supported Complication Families

Based on the project structure, Nightguard supports:
- Circular complications
- Modular complications
- Graphic complications (watchOS 5+)

### Timeline Provider (Shared with Widgets)

The same `NightguardTimelineProvider` used for iOS widgets also powers complications:

```swift
#if os(watchOS)
let complicationServer = CLKComplicationServer.sharedInstance()
if complicationServer.activeComplications != nil {
    guard let activeComp = complicationServer.activeComplications else { return }
    for complication in activeComp {
        complicationServer.reloadTimeline(for: complication)
    }
}
#endif
```

---

## App State Management

### AppState Tracking

```swift
func applicationDidBecomeActive() {
    AppState.isUIActive = true
    NotificationCenter.default.post(name: .refreshDataOnAppBecameActive, object: nil)
}

func applicationWillResignActive() {
    AppState.isUIActive = false
    AppMessageService.singleton.keepAwakePhoneApp()
}
```

### Keep-Alive Strategy

When the watch app goes to background, it sends a keep-alive message to the phone:

```swift
AppMessageService.singleton.keepAwakePhoneApp()
```

This helps ensure the phone app continues fetching data for widget/complication updates.

---

## Background Refresh

### Background Task Scheduling

The watch app registers for background processing:

```swift
let appProcessingTaskId = "de.my-wan.dhe.nightguard.background"
```

### Singleton Retention

A unique pattern to prevent the extension delegate from being deallocated during background tasks:

```swift
// Keep the extension delegate ALIVE because it hangs when the watch app 
// moves to background and stops processing background tasks
private(set) static var singleton: ExtensionDelegate!

func applicationDidFinishLaunching() {
    // ...
    ExtensionDelegate.singleton = self
}
```

---

## Watch App Views

### MainController

The primary watch UI controller that displays:
- Current BG value with color coding
- Delta and trend arrow
- Time since last reading
- Snooze status

### View Structure

```
┌─────────────────────────────────────────┐
│           Watch App Main View            │
├─────────────────────────────────────────┤
│                                          │
│          ┌───────────────┐              │
│          │   120 →       │  BG + Arrow  │
│          └───────────────┘              │
│                                          │
│          ┌───────────────┐              │
│          │    +5 mg/dL   │  Delta       │
│          └───────────────┘              │
│                                          │
│          ┌───────────────┐              │
│          │    3 min ago  │  Time        │
│          └───────────────┘              │
│                                          │
│          ┌───────────────┐              │
│          │   Snooze 🔕   │  Snooze Btn  │
│          └───────────────┘              │
│                                          │
└─────────────────────────────────────────┘
```

---

## Data Flow: Phone → Watch

```
┌─────────────────────────────────────────────────────────────────┐
│                    Phone → Watch Data Flow                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  iPhone App                                                      │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ NightscoutCacheService                                       ││
│  │      │                                                       ││
│  │      ▼ (new data received)                                   ││
│  │ WatchService.singleton.sendToWatch()                         ││
│  │      │                                                       ││
│  │      ▼                                                       ││
│  │ NightscoutDataMessage                                        ││
│  │ UserDefaultSyncMessage                                       ││
│  └──────────────────────────┬──────────────────────────────────┘│
│                              │                                   │
│                    WCSession.transferUserInfo()                  │
│                              │                                   │
│  Apple Watch                 ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ WatchMessageService.singleton                                ││
│  │      │                                                       ││
│  │      ▼ session(_:didReceiveUserInfo:)                        ││
│  │ message.onMessage { ... }                                    ││
│  │      │                                                       ││
│  │      ▼                                                       ││
│  │ MainController.mainViewModel.refreshData()                   ││
│  │ AlarmRule.snoozeFromMessage()                                ││
│  │ NightscoutCacheService.resetCache() (if URI changed)        ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow: Watch → Phone

```
┌─────────────────────────────────────────────────────────────────┐
│                    Watch → Phone Data Flow                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Apple Watch (User taps Snooze)                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ AlarmRule.snooze(minutes)                                    ││
│  │      │                                                       ││
│  │      ▼                                                       ││
│  │ SnoozeMessage(timestamp: snoozedUntilTimestamp).send()      ││
│  │      │                                                       ││
│  │      ▼                                                       ││
│  │ WCSession.sendMessage()                                      ││
│  └──────────────────────────┬──────────────────────────────────┘│
│                              │                                   │
│                    WCSession real-time messaging                 │
│                              │                                   │
│  iPhone App                  ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ WatchMessageService.singleton                                ││
│  │      │                                                       ││
│  │      ▼ session(_:didReceiveMessage:)                         ││
│  │ AlarmRule.snoozeFromMessage(message)                         ││
│  │      │                                                       ││
│  │      ▼                                                       ││
│  │ snoozedUntilTimestamp.value = message.timestamp              ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Entitlements

**Source**: `nightguard:nightguard ComplicationExtension.entitlements`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <key>com.apple.security.application-groups</key>
    <array>
        <string>group.de.my-wan.dhe.nightguard</string>
    </array>
</dict>
</plist>
```

App Groups enable data sharing between:
- Main watchOS app
- Complication extension
- Widget extension (on iOS)

---

## Localization

The Watch app supports multiple languages:

| Language | Directory |
|----------|-----------|
| English | `Base.lproj/` |
| German | `de.lproj/` |
| Finnish | `fi-FI.lproj/` |

---

## Code References

| Purpose | Location |
|---------|----------|
| ExtensionDelegate | `nightguard:nightguard WatchKit App/ExtensionDelegate.swift` |
| WatchMessageService | `nightguard:nightguard/watch/WatchMessageService.swift` |
| AppMessageService | `nightguard:nightguard WatchKit App/external/AppMessageService.swift` |
| SnoozeMessage | `nightguard:nightguard/watch/messages/SnoozeMessage.swift` |
| UserDefaultSyncMessage | `nightguard:nightguard/watch/messages/UserDefaultsSyncMessage.swift` |
| NightscoutDataMessage | `nightguard:nightguard/watch/messages/NightscoutDataMessage.swift` |
| Watch views | `nightguard:nightguard WatchKit App/views/` |

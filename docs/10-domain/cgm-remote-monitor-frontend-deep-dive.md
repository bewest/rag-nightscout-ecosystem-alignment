# cgm-remote-monitor Frontend Deep Dive

This document analyzes the frontend architecture of cgm-remote-monitor, focusing on client bundle structure, D3.js chart rendering, plugin UI, and the translation system. The frontend provides real-time glucose visualization and treatment management for the Nightscout ecosystem.

## Overview

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Client Entry | `lib/client/index.js` | Main client initialization |
| Chart Rendering | `lib/client/chart.js` | D3.js glucose visualization |
| Renderer | `lib/client/renderer.js` | Treatment/entry rendering |
| Plugin Base | `lib/plugins/pluginbase.js` | Plugin UI utilities |
| Translations | `translations/` | 33 language files |
| Views | `views/` | EJS server templates |
| Static Assets | `static/` | CSS, images, fonts |
| Webpack Config | `webpack/webpack.config.js` | Bundle configuration |

### Directory Structure

```
cgm-remote-monitor/
├── views/                    # Server-side EJS templates
│   ├── index.html           # Main application
│   ├── adminindex.html      # Admin panel
│   ├── reportindex.html     # Reports
│   └── partials/            # Reusable components
├── static/                   # Client-side assets
│   ├── js/                  # Minified bundles
│   ├── css/                 # Stylesheets
│   ├── images/, audio/      # Media assets
│   └── admin/, report/      # Feature-specific
├── lib/client/               # Client JavaScript modules
│   ├── index.js             # Entry point (~1200 lines)
│   ├── chart.js             # D3 chart (~750 lines)
│   ├── renderer.js          # Rendering (~47KB)
│   └── careportal.js        # Treatment entry
├── translations/             # 33 language files
│   ├── en/en.json
│   ├── de_DE.json
│   └── ...
├── bundle/                   # Output bundles
│   ├── bundle.source.js
│   ├── bundle.clocks.source.js
│   └── bundle.reports.source.js
└── webpack/
    └── webpack.config.js
```

---

## Client Architecture

### Initialization Flow

```
Browser loads index.html
        ↓
Webpack bundle executes
        ↓
Fetch /api/v1/status.json
        ↓
Initialize translations
        ↓
Initialize browser settings
        ↓
Connect Socket.IO (main + alarm)
        ↓
Authorize with secret/token
        ↓
Receive initial dataUpdate
        ↓
Render chart and plugins
```

### Socket.IO Connections

**File**: `lib/client/index.js`

```javascript
// Main data socket
var socket = io.connect({ transports: ["polling"] });

// Alarm notification socket
var alarmSocket = io.connect("/alarm", {
  multiplex: true,
  transports: ["polling"]
});
```

| Socket | Namespace | Events Received |
|--------|-----------|-----------------|
| Main | `/` | `dataUpdate`, `retroUpdate`, `connected`, `clients` |
| Alarm | `/alarm` | `alarm`, `urgent_alarm`, `clear_alarm`, `announcement` |

### Data Flow

```
socket.on('dataUpdate')
        ↓
receiveDData(received, ddata, settings)
        ↓
├── mergeDataUpdate()     # SGVs, MBGs
├── mergeTreatmentUpdate() # Treatments
└── processTreatments()
        ↓
sandbox.clientInit()
        ↓
prepareEntries()
        ↓
plugins.setProperties(sbx)
        ↓
plugins.updateVisualisations(sbx)
        ↓
chart.update()
```

### State Management

**Central State Object**: `client`

| Property | Type | Purpose |
|----------|------|---------|
| `client.ddata` | Object | Central data model (sgvs, treatments, etc.) |
| `client.sbx` | Object | Sandbox context for plugins |
| `client.settings` | Object | User/server settings |
| `client.chart` | Object | D3 chart instance |
| `client.entries` | Array | Processed visualization data |
| `client.retro` | Object | Historical data cache |
| `client.latestSGV` | Object | Latest glucose reading |
| `client.now` | Number | Current timestamp |

---

## Chart Rendering (D3.js)

### Chart Structure

**File**: `lib/client/chart.js`

```
#chartContainer
└── <svg>
    ├── <g class="chart-basals">    # Basal rate area
    ├── <g class="chart-focus">     # Main glucose view (70%)
    └── <g class="chart-context">   # Timeline brush (30%)
```

### Dual-View Layout

| View | Height | Purpose | Interactivity |
|------|--------|---------|---------------|
| Focus | 70% | High-detail glucose + treatments | Pan, zoom |
| Context | 30% | Full data overview | Brush selection |

### Scales

**File**: `lib/client/chart.js:99-123`

| Scale | Type | Domain | Usage |
|-------|------|--------|-------|
| `xScale` | Time | Brush extent | Focus view X-axis |
| `xScale2` | Time | Full data | Context view X-axis |
| `yScale` | Linear/Log | [30, max SGV × 1.15] | Focus Y-axis |
| `yScale2` | Linear | [36, 420] | Context Y-axis |
| `futureOpacity` | Linear | [0.8, 0.1] | Prediction fade |

### SGV Rendering

**File**: `lib/client/renderer.js:74-96`

```javascript
// Focus circles
focusCircles.enter()
  .append('circle')
  .attr('cx', d => chart.xScale(getOrAddDate(d)))
  .attr('cy', d => chart.yScale(client.sbx.scaleEntry(d)))
  .attr('r', d => dotRadius(d.type))
  .attr('class', d => `focus-${d.type}`);
```

### Treatment Markers

| Type | Shape | Color | Size Based On |
|------|-------|-------|---------------|
| Insulin | Arc sector | Blue (#0099ff) | Units |
| Carbs | Arc sector | Orange | Grams |
| Combo | Overlaid arcs | Both | Both |
| Exercise | Rectangle | Violet | Duration |
| Temp Target | Rectangle | Light gray | Duration |
| Notes | Rectangle | Salmon | Duration |

### Prediction Lines

**File**: `lib/client/chart.js:707-744`

- Source: `client.sbx.pluginBase.forecastPoints[type]`
- Rendered as circles with fading opacity
- Filtered by `maxForecastAge` (brush extent + lookahead)
- Supports multiple prediction types (IOB, COB, ZT, UAM)

### Reference Lines

| Line | Style | Value Source |
|------|-------|--------------|
| High threshold | Dashed | `settings.bgHigh` |
| Target top | Dashed | `settings.bgTargetTop` |
| Target bottom | Dashed | `settings.bgTargetBottom` |
| Low threshold | Dashed | `settings.bgLow` |
| Current time | Gray dashed | `client.now` |

---

## Plugin UI System

### Plugin Types and Containers

| Type | Container | Examples |
|------|-----------|----------|
| `pill-major` | `.majorPills` | IOB, COB |
| `pill-minor` | `.minorPills` | Pump age, sensor age |
| `pill-status` | `.statusPills` | Loop, OpenAPS, pump |
| `bg-status` | `.bgStatus` | Raw BG, direction |
| `drawer` | `#drawer` | Careportal, bolus calc |

### Pill Rendering

**File**: `lib/plugins/pluginbase.js`

```javascript
pluginBase.updatePillText(sbx, {
  value: displayCob + 'g',
  label: translate('COB'),
  pillClass: 'current',
  info: [{ label: 'Carbs', value: '45g' }]  // Tooltip
});
```

**DOM Structure**:
```html
<span class="pill cob">
  <label class="label">COB</label>
  <em class="value">45g</em>
</span>
```

### Plugin Lifecycle

```
Data Update
    ↓
plugins.setProperties(sbx)
    ↓ (all enabled plugins)
plugins.updateVisualisations(sbx)
    ↓ (only shown plugins)
plugin.updateVisualisation(sbx)
    ↓
pluginBase.updatePillText()
```

**Throttling**: Plugin updates limited to once per second.

### Drawer System

**File**: `lib/client/browser-utils.js`

```javascript
toggleDrawer(id, openPrepare, closeCallback)
openDrawer(id, prepare)
closeDrawer(id, callback)
```

- Single drawer open at a time
- 350px wide on desktop, full-screen on mobile (<500px)
- CSS transform animation: `right: -300px` → `right: 0`

---

## Translation System

### Architecture

**File**: `lib/language.js`

| Component | Purpose |
|-----------|---------|
| `language.set(code)` | Set current language |
| `language.translate(text)` | Translate string |
| `language.offerTranslations(obj)` | Load translation object |
| `language.DOMtranslate($)` | Auto-translate DOM elements |

### Translation Files

**Location**: `translations/`

**Format**: Simple JSON key-value pairs
```json
{
  "Loading": "Laden",
  "Monday": "Montag",
  "Carbs": "Kohlenhydrate"
}
```

**Placeholders**: `%1`, `%2` for parameter substitution

### Available Languages (33)

Arabic, Bulgarian, Chinese (Simplified/Traditional), Croatian, Czech, Danish, Dutch, English, Estonian, Finnish, French, German, Greek, Hebrew, Hindi, Hungarian, Italian, Japanese, Korean, Norwegian, Polish, Portuguese (PT/BR), Romanian, Russian, Slovak, Slovenian, Swedish, Tamil, Turkish, Ukrainian

### Language Detection

```javascript
// Browser detection
var lang = navigator.language || navigator.userLanguage;

// Storage
localStorage.setItem('language', lang);

// Fallback
if (!translations[lang]) lang = 'en';
```

---

## Build System

### Webpack Configuration

**File**: `webpack/webpack.config.js`

```javascript
module.exports = {
  entry: {
    bundle: './lib/client/index.js',
    'bundle.clocks': './lib/client/clock-client.js',
    'bundle.reports': './lib/client/report-client.js'
  },
  output: {
    path: path.resolve(__dirname, '../bundle'),
    filename: '[name].source.js'
  }
};
```

### Output Bundles

| Bundle | Purpose | Entry Point |
|--------|---------|-------------|
| `bundle.source.js` | Main application | `lib/client/index.js` |
| `bundle.clocks.source.js` | Clock view | `lib/client/clock-client.js` |
| `bundle.reports.source.js` | Reports | `lib/client/report-client.js` |

### Build Commands

```bash
npm run bundle          # Production build
npm run bundle-dev      # Development build
npm run bundle-analyzer # Analyze bundle size
```

---

## Gap Analysis

### GAP-UI-001: No Component Framework

**Scenario**: Frontend maintenance and extension.

**Issue**: UI is built with vanilla JavaScript and jQuery. No modern component framework (React, Vue, etc.) makes maintenance difficult and prevents code reuse.

**Affected Systems**: All Nightscout frontend features.

**Impact**: High barrier to contribution, difficult testing, inconsistent patterns.

**Remediation**: Consider incremental migration to component-based architecture.

---

### GAP-UI-002: Chart Accessibility

**Scenario**: Screen reader and keyboard navigation.

**Issue**: D3.js charts lack ARIA labels, keyboard navigation, and screen reader support. Glucose data is only accessible visually.

**Affected Systems**: Visually impaired users, accessibility compliance.

**Impact**: Nightscout not accessible to all users.

**Remediation**: Add ARIA labels, data tables as alternative, keyboard controls.

---

### GAP-UI-003: No Offline Support

**Scenario**: Intermittent connectivity.

**Issue**: While service worker exists, meaningful offline support is limited. Data cannot be viewed when disconnected.

**Affected Systems**: Mobile users, poor connectivity areas.

**Impact**: Nightscout unusable without active connection.

**Remediation**: Implement IndexedDB caching, offline data display.

---

## Recommendations

### 1. Document Frontend Architecture

Create developer guide covering:
- Bundle structure and build process
- Plugin UI development guide
- Chart customization options

**Priority**: Medium

### 2. Add Chart Accessibility

Implement ARIA support for D3 charts:
- Role attributes on SVG elements
- Data table alternative
- Keyboard navigation for time range

**Priority**: High

### 3. Improve Translation Coverage

Audit translations for:
- Missing keys across languages
- Consistent terminology
- Plugin-specific strings

**Priority**: Low

### 4. PWA Enhancement

Extend service worker for:
- Offline data caching
- Background sync for treatments
- Push notifications (where supported)

**Priority**: Medium

---

## Source Files Analyzed

| File | Lines | Key Content |
|------|-------|-------------|
| `lib/client/index.js` | ~1200 | Client entry, data flow |
| `lib/client/chart.js` | ~750 | D3 chart setup |
| `lib/client/renderer.js` | ~1400 | Treatment/entry rendering |
| `lib/plugins/pluginbase.js` | ~300 | Plugin UI utilities |
| `lib/language.js` | ~200 | Translation system |
| `webpack/webpack.config.js` | ~50 | Build configuration |

---

## Cross-References

- **API Layer**: [cgm-remote-monitor-api-deep-dive.md](./cgm-remote-monitor-api-deep-dive.md)
- **Plugin System**: [cgm-remote-monitor-plugin-deep-dive.md](./cgm-remote-monitor-plugin-deep-dive.md)
- **Sync Layer**: [cgm-remote-monitor-sync-deep-dive.md](./cgm-remote-monitor-sync-deep-dive.md)
- **Auth Layer**: [cgm-remote-monitor-auth-deep-dive.md](./cgm-remote-monitor-auth-deep-dive.md)
- **Database Layer**: [cgm-remote-monitor-database-deep-dive.md](./cgm-remote-monitor-database-deep-dive.md)

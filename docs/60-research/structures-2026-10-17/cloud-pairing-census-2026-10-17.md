# Manufacturer accounts and online steps at setup: public-document census

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community.
**Research note, snapshot of 2026-10-17.** What each manufacturer's own system requires at setup
and pairing, as its public documents state (manuals, instructions for use, support pages, app-store
listings). Nothing here comes from reverse-engineering or open-source code; mechanism level only.
Rows marked "(snippet)" were read from a search-engine summary of a page that could not be fetched,
and need a re-read before they are quoted. Used by [why organise §4](../../00-overview/WHY-ORGANISE.md#4-where-newer-devices-are-going)
and the `cloud` column of `tools/structure-diagrams/access/devices.yaml`.*

## How to read this

- **Account to set up**: does the manufacturer's app or controller require signing in to a
  manufacturer account before the device can be used? Quoted phrase is the manufacturer's.
- **Online step / cloud credential**: does a public document say the device or app needs an
  internet connection *during setup or pairing*, or that a credential is issued by the
  manufacturer's servers? "not stated" means no public document read says so either way.
- **Offline after setup**: does a public document say the device keeps working without internet?
  Statements that only cloud features (upload, follow) need internet are recorded as "cloud
  features only", which implies but does not state offline operation.
- **Launch year**: approximate, from manufacturer press/trade coverage; marked "approx." and not
  verified row by row.
- Where the only source was a search-engine snippet of a manufacturer page that could not be
  fetched directly (403/binary PDF), the row says "(snippet)". Treat those as needing a re-read.

## Census

### CGMs

| Line | Launch (approx.) | App / receiver | Account to set up? | Online step or cloud credential documented? | Offline after setup? | Data sharing | Source(s), read 2026-10-17 |
|---|---|---|---|---|---|---|---|
| Dexcom G6 | 2018 US | Dexcom G6 app; receiver | **yes** (app path): app prompts "to set up an account" | not stated | not stated | Share -> Dexcom Follow (cloud) | dexcom.com/en-ie/hello-activation (snippet); uk.provider.dexcom.com G6 Getting Started handout (snippet) |
| Dexcom G7 (10-day) | 2022 EU/UK, 2023 US | Dexcom G7 app; receiver | **yes**: "create a Dexcom account or login with your existing Dexcom account"; phone change: "log into your Dexcom account, go through the app setup wizard" | not stated for G7 itself (see ONE+) | cloud features only: "Share and Follow functions require an internet connection" | Share -> Dexcom Follow (cloud) | provider.dexcom.com/clinical-education-material/dexcom-g7-app-how-get-started; dexcom.com/en-bh/faqs/if-i-am-replacing-my-compatible-smart-device-what-will-i-need-do; apps.apple.com/us/app/dexcom-g7/id1569432518 |
| Dexcom G7 15 Day | 2025 US | same G7 app/receiver | **yes** (same app; same account wording) | not stated | not stated | as G7 | dexcom.com/en-us/faqs/what-is-dexcom-g7-15-day-cgm |
| Dexcom ONE+ | 2024 EU/intl | Dexcom ONE+ app | **yes**: "Log in, or create an account" | **yes, internet at setup**: "You must have secure internet access during setup and for some features." No credential described | partly: internet needed "for some features" (not listed) | not stated on page | dexcom.com/en-gb/faqs/how-do-i-set-up-my-dexcom-one-plus-system |
| Dexcom Stelo (OTC) | 2024 US | Stelo by Dexcom app | **yes**: "Create a Stelo account or log in" (account not needed to *purchase*) | not stated | not stated | not stated | stelo.com/en-us/getting-started; stelo.com FAQ "How do I create a Stelo account?" (snippet) |
| FreeStyle Libre 2 / 2 Plus | 2018 EU (2), 2023-24 (2 Plus) | FreeStyle LibreLink / Libre app; reader | **yes** (app path): "A LibreView login is required when you first set up the FreeStyle LibreLink app"; reader path: no account stated | not stated | cloud features only: internet needed "for glucose data to automatically upload to LibreView" | LibreView -> LibreLinkUp (cloud) | freestyle.abbott/en-us/support/faq/apps/libreview-account-requirement-for-freestyle-librelink.html; freestyle.abbott/en-us/how-to-set-up.html |
| FreeStyle Libre 3 / 3 Plus | 2020 EU, 2022 US (3); 2024 (3 Plus) | FreeStyle Libre 3 app / Libre app; reader | **yes** (app path): "you will need to sign in or create an account"; Abbott footnote softer: "may require registration with LibreView"; Libre 3 brochure: "requires registration with LibreView" (snippet) | not stated (sensor start described as an NFC scan; no internet step mentioned) | cloud features only (same upload wording) | LibreView -> LibreLinkUp (cloud) | freestyle.abbott/en-us/how-to-set-up.html; freestyleprovider.abbott Libre 3 Getting Started brochure (snippet; PDF not text-readable) |
| Abbott Lingo (OTC) | 2024 US/UK | Lingo app | account flow exists ("Sign up or login"); app-store notes "Easier to create an account"; mandatory not stated by Abbott | not stated | not stated | not stated | apps.apple.com/us/app/id1670445335; support.withings.com Lingo partner article (third-party, US product) |
| Instinct (Abbott-made, for 780G) | 2025 US, 2026 EU | MiniMed Mobile app or App Manager | **yes, indirectly**: "The MiniMed Mobile app is required to start the Instinct sensor"; that app's setup begins at a CareLink Personal login (see 780G) | not stated | not stated (sensor talks to pump once started) | via pump -> CareLink | minimed.com/en-us/support/product-support/sensors/instinct-sensor |
| Simplera / Simplera Sync | 2024 EU, 2025 US (Sync) | paired to 780G pump (Sync); Simplera standalone uses Simplera app (not read) | Sync: not stated (pairing described as pump-to-sensor) | not stated | not stated | via pump -> CareLink | minimed.com/en-us/support/product-support/sensors/simplera-sync (snippet) |
| Eversense E3 | 2022 US | Eversense app | **yes**: user guide step "Set up the App – Account Creation, Pairing and Settings" (snippet of FDA-filed guide); logged out -> "no glucose data will be displayed on the app until you log back in" | not stated | **no, while logged out** (above); app "will periodically check to confirm your log in information" | Eversense DMS (cloud) | eversensecgm.com/faq/?page=16; accessdata.fda.gov P160048S021C (snippet) |
| Eversense 365 | 2024 US | Eversense 365 app | **yes**: "follow the prompts to create your Eversense account"; email activation link (snippet) | **yes, internet during pairing**: "Make sure you have an internet connection ... during the pairing process." No credential described | not stated (same log-out rule as E3 applies to the app family per FAQ) | Eversense DMS (cloud) | pre.eversensecgm.com/faq/?page=4; eversensecgm.com 365 appointment checklist PDF (snippet) |
| Accu-Chek SmartGuide | 2024 EU | Accu-Chek SmartGuide app (also mySugr) | **yes**: "You need an Accu-Chek Account to set up the app." | not stated; pairing uses "a serial number and a 6-digit PIN code" on the twist cap | not stated | Accu-Chek account restore on phone change (cloud) | tools.accu-chek.com SmartGuide app manual 1.2.3, Prerequisites; accu-chek.co.uk/training/cgm/sensor-app-pairing (snippet) |
| SmartGuide "advanced security" | — | — | not stated | **not stated: no public Roche document found describing a security variant** | not stated | — | search of Roche training/manual pages, 2026-10-17 |
| Sibionics GS1 / GS3 | 2023 EU (GS1) | SIBIONICS app | **yes (GS1, regional FAQ)**: sign-up "only ... with email for now" (Korean support FAQ, snippet); GS3 not stated | not stated | not stated | not stated | docs.channel.io Sibionics Korea FAQ (snippet); diabettech.com mirror of GS1 app user guide |

### Pumps

| Line | Launch (approx.) | App / controller | Account to set up? | Online step or cloud credential documented? | Offline after setup? | Data sharing | Source(s), read 2026-10-17 |
|---|---|---|---|---|---|---|---|
| MiniMed 780G + MiniMed Mobile app | 2020 EU, 2023 US | pump UI; MiniMed Mobile app (optional display/bolus, required for Instinct) | **yes for the app**: setup opens at "A CareLink Personal account Log in screen"; else "Tap Create an Account"; pairing then "started on the pump" | not stated for pairing; pump **software updates** list a "stable internet connection" and CareLink username/password | not stated for the app; pump runs SmartGuard without the app (pump-paired sensors) | "Sync to CareLink" -> CareLink care partners | minimed.com/en-us/support/product-support/780g/setup-minimed-mobile-app; minimed.com 780G software update guide v6.6.0 (snippet); MiniMed Mobile Quick Reference Guide (snippet) |
| MiniMed Go (with Instinct Go) | 2026 EU | not read | not stated | not stated | not stated | not stated | barchart.com MiniMed Europe launch release (trade press) |
| Tandem t:slim X2 + t:slim mobile app | 2016 US (pump); app 2020 | pump UI; Tandem t:slim mobile app | **yes for the app**: "Open the mobile app and sign in. Or, if you're a new user, create an account." Pairing by "A unique pairing code ... on the pump screen" | not stated | pump: "functions independently from the Tandem t:slim mobile app" (snippet); app uploads "to the Tandem Cloud and the Tandem Source platform every hour" | Tandem Source (cloud) | tandemdiabetes.com/hc/en-us/articles/360039589193 |
| Tandem Mobi | 2024 US; Android app Dec 2025 | Tandem Mobi app (primary UI) | **yes**: "sign in, or create an account"; one account for app and Tandem Source; pairing by six-digit PIN behind the cartridge | not stated | not stated | Tandem Source (cloud) | tandemdiabetes.com/support-center/software-and-apps/tandem-mobi-mobile-app/article/pair-tandem-mobi-mobile-app-to-pump (snippet); tandemdiabetes.com/support/insulin-pump-training/how-to-set-up-account (snippet) |
| Omnipod DASH | 2019 US | locked-down PDM; Omnipod DISPLAY / VIEW apps | **not stated for pairing**; PodderCentral account is a step for **cloud upload** | not stated for pairing; PDM uses Wi-Fi to upload and "checks for software updates" | cloud features only; "Pod will continue to deliver basal insulin even when the PDM is out of range" | Insulet Cloud -> VIEW app, Glooko | omnipod.com/current-podders/resources/omnipod-dash/podder-resource-guide (snippet); omnipod.com Patient DASH Auto Upload Guide (snippet) |
| Omnipod 5 (controller) | 2022 US, 2023 UK/EU | Insulet-provided controller (built-in SIM) | **yes**: "you must first complete the setup process at the Omnipod Setup Portal"; "These same credentials are also used to sign in to your Omnipod 5 Controller" | sign-in to an Omnipod ID at first use; connectivity "is important" for updates and cloud upload; no credential described in public docs | not stated (connectivity described as important, not as required for delivery) | Insulet cloud -> Omnipod VIEW / Glooko | omnipod.com/current-podders/resources/omnipod-5/videos/app-setup (snippet, 403 on fetch); omnipod.com/en-gb/hcp/products/omnipod-5/faqs/controller (snippet) |
| Omnipod 5 (phone app) | 2023 Android, 2025 iPhone (US) | Omnipod 5 App | **yes**: must "first login to the provided Omnipod 5 Controller with your Omnipod ID", described as "a one-time step" that confirms the prescription | as controller | not stated | as controller | omnipod.com Omnipod 5 iPhone first-time-setup page (snippet) |
| Beta Bionics iLet | 2023 US | iLet pump UI; iLet Mobile App; Bionic Circle (follow) | **yes for the app** (app guide: account before login, snippet) | **app-delivered certificates documented for G7**: "the app automatically loads certificates required to enable Dexcom G7 features on your iLet" (source of the certificates not stated) | not stated; uploads "may not take place in real time" | iLet cloud -> Bionic Circle; Dexcom Follow | betabionics.com/user-resources/cgm-update/; betabionics.com iLet Mobile App User Guide LA000056 (snippet; PDF 404 on fetch) |
| Sequel twiist | 2025 US | twiist app (iPhone/Apple Watch) | not stated (a "My twiist Portal" account is set up "during your twiist pump trainer session") | not stated; Abbott: users "need the twiist app to start the sensor" (Libre 3 Plus) | not stated | twiist Portal -> Tidepool | support.tidepool.org/hc/en-us/articles/36492372131604; freestyle.abbott FAQ "what Tidepool Loop means for the Sequel twiist pump" (snippet) |
| YpsoPump + mylife Loop / myLoop (CamAPS FX) | 2020 EU (CamAPS) | CamAPS FX app (mylife app phased out 1 Dec 2026, AU) | **yes**: "You will need to create a CamAPS FX account"; email verification code | **internet at sign-up**: "Internet connection is required during the download and sign-up process." Pairing by "six-digit code" shown on pump | partly: "The in-app training itself can be done without internet connection"; offline closed-loop not stated | Companion / follower (cloud) | a.storyblok.com myLoop step-by-step guide (uk-en, snippet); mylife-diabetescare.com/en-AU mylife app phase-out page |
| Medtrum TouchCare Nano | ~2018 EU | PDM or EasyPatch app | not stated by Medtrum; a German clinic checklist calls the app login "Medtrum Account" (secondary) | not stated | "background insulin continues even if separated from the PDM or EasyPatch App" | Medtrum cloud (EasyFollow) | medtrum.com/product/nano-insulin-pump (snippet); fachklinik-bad-heilbrunn.de Medtrum checklist (secondary) |
| Dana-i / DanaRS | 2021 (Dana-i) | pump UI; AnyDANA-i app | not stated (app listing describes Bluetooth remote control only) | not stated | not stated | Dana Chart (SOOIL cloud, separate app) | iphoneaddict.fr AnyDANA-i listing (mirror); apps.apple.com Dana Chart listing (KR) |

### What the public documents show overall

1. Every phone app for a current CGM line read here (Dexcom, Abbott, Eversense, Roche,
   Sibionics) is documented as requiring a manufacturer account at first setup. Dedicated
   receivers/readers are documented without one (Libre reader, Dexcom receiver).
2. Only three lines have a public statement that the setup or pairing step itself needs the
   internet: Dexcom ONE+ ("secure internet access during setup"), Eversense 365 ("internet
   connection ... during the pairing process") and CamAPS FX ("during the download and sign-up
   process"). Omnipod 5's Omnipod ID sign-in on the controller is an online first-use step by
   description.
3. One line publicly documents app-delivered certificates: the iLet app "loads certificates" to
   enable G7. No other manufacturer document read here describes a cloud-issued credential.
4. Offline operation after setup is almost never stated positively. Pumps are documented as
   delivering independently of the app/PDM (t:slim X2, DASH, Medtrum); CGM apps are documented
   only as needing internet for cloud features. Eversense is the one documented negative: logged
   out, the app shows no glucose data.

## Cross-reference: tools/structure-diagrams/access/devices.yaml

Proposed new column **"needs manufacturer cloud to pair (per public docs)"**.
Values: **yes** = a public document says setup/pairing needs the internet or a manufacturer-issued
credential; **account-only** = the manufacturer's app requires an account sign-in at setup, with no
statement that the pairing step itself is online; **no** = a public document says no account or
connection is needed; **not stated** = no public statement found.

| devices.yaml name | Ladder rung (file) | Proposed value | Basis |
|---|---|---|---|
| Omnipod Eros | A | not stated | not researched in public docs this round |
| Omnipod DASH | A | not stated | PDM account documented only for cloud upload |
| Omnipod 5 | D | account-only | Omnipod ID setup-portal registration and controller sign-in; connectivity "important", not stated as a pairing requirement |
| Medtronic 5xx / 7xx | A | not stated | not researched in public docs this round |
| MiniMed 780G | D | account-only | MiniMed Mobile app opens at CareLink login before pump pairing; Instinct requires that app; pump-paired sensors not stated |
| Tandem t:slim X2 / Mobi | A | account-only | "sign in, or create an account" before code pairing |
| Dana RS / i | A | not stated | no manufacturer statement found |
| Medtrum Nano | A | not stated | account only in a secondary source |
| Dexcom G6 | A | account-only | app prompts account setup; receiver path not stated |
| Dexcom G7 / ONE+ | D | account-only | G7: account, no online-pairing statement. ONE+ alone would be **yes** ("secure internet access during setup"); split the row if the column needs to be exact |
| Libre 1 / 2 | A | account-only | LibreLink: "LibreView login is required when you first set up"; reader path needs none |
| Libre 3 | D | account-only | "sign in or create an account"; no online sensor-start statement |
| Eversense E3 | A | account-only | account creation in app setup; data hidden when logged out |
| Eversense 365 | C | yes | "Make sure you have an internet connection ... during the pairing process" |
| Accu-Chek SmartGuide | A | account-only | "You need an Accu-Chek Account to set up the app." |
| SmartGuide "advanced security" | null | not stated | no public Roche document describes it |

Observation for the ladder: the public-document column and the code-derived rung measure
different things. Account-only appears on rungs A and D alike, so "the manufacturer's app needs an
account" does not predict whether an open app needs anything from the manufacturer. The two lines
whose public docs say pairing is online (Eversense 365, Dexcom ONE+) sit on rungs C and D.

## Gaps to close before quoting

- Re-read from the primary document (not a snippet): Omnipod 5 setup pages (403 to the fetcher),
  Libre 3 brochure (binary PDF), iLet Mobile App User Guide (404), Eversense E3 FDA user guide,
  Tandem Mobi pairing page, CamAPS FX guide, MiniMed software-update guide.
- Not found in any public document: Dexcom G7 (non-ONE+) internet-at-setup wording; Libre 3
  offline sensor start; twiist app account; AnyDANA account; Medtrum account from Medtrum itself;
  Sibionics GS3; MiniMed Go; Simplera (standalone) app.
- Launch years are approximate and were not individually sourced.

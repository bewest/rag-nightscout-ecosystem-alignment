# Giving an AI tool access to your Nightscout data

*What this is: a guide (user-facing). Read after the [guides list](README.md); leads to the
checklist near the end of this page.* Written 2026-10-18 for people who use Nightscout for themselves or a family member.
This page is general information, not medical advice. Talk with your diabetes care team before
changing anything about your treatment.

AI assistants can now connect to a Nightscout site and talk about its data. This page explains
where your data goes, how to give a tool the least access it needs, and what to watch for.

## A few terms first

- **Nightscout site**: your own web server that collects glucose readings, insulin and carb
  records, and status from your devices and apps, and shows them to you and the people you share
  with.
- **API_SECRET**: the master password of your Nightscout site, set when the site was built. Anyone
  who has it can read, change and delete everything on the site.
- **Token**: a separate access code that Nightscout creates for one person, app or device. Each
  token carries one or more **roles**, which decide what it may do.
- **`readable` role**: the built-in role that lets a token read the site and nothing else.
- **Treatments**: the records on your site of insulin, carbs, temporary targets, notes and similar
  events. **Write access** means a tool can add, change or delete these, or change your profile
  (your basal, carb-ratio and correction settings as stored on the site).
- **MCP server**: a small program that connects an AI assistant to another service. MCP stands
  for Model Context Protocol. A Nightscout MCP server gives the assistant "tools" such as "get the
  last 24 hours of readings".
- **Skill**: a set of instructions and scripts that an AI assistant can run on your computer, for
  example to download your readings and build a report.
- **Cloud model / local model**: the AI itself (the "model") either runs on a company's servers
  (a cloud model, which is what most chat apps use) or on a computer you control (a local model,
  run with software such as Ollama, llama.cpp or vLLM).

## Where your data goes

Anything the AI tool reads from your site becomes text that is sent to the model.

- With a **cloud model**, that text goes to the company that runs the model and is handled under
  that company's terms and privacy settings.
- With a **local model**, it stays on your own computer or home network.

This is true even when part of the tool runs on your computer. For example, one Nightscout skill
computes its reports with a script on your computer, but the results it prints become part of the
conversation, and the conversation goes to whichever model you are chatting with. The open-source
platform Lumose (its code is in the GlycemicGPT repository) puts it plainly: "You choose the AI
provider, and that choice determines where your health data is processed."

Nightscout data can say more about a person than glucose numbers. Times of day show routines,
device and phone names can identify someone, and notes you typed may mention places, people or
illness. Assume that whatever the tool can read could end up in the conversation.

## Never give an AI tool your API_SECRET

Give the tool its own token with only the `readable` role. In Nightscout:

1. Open the menu and choose **Admin Tools**. You need to be signed in with your API_SECRET to
   see it.
2. In the section **Subjects - People, Devices, etc**, choose **Add new Subject**.
3. Give it a name that says which tool it is for, type `readable` in **Roles**, and save.
4. The table shows the new subject's **Access Token**. Give the tool that token, entered the way
   the tool's own instructions describe.

Things to know about this token:

- **It reads everything.** Today the `readable` role is a single setting: every kind of record, for
  all dates. There is no way to give a tool only the last two weeks, or only glucose readings.
- **Keep it out of web addresses where you can.** Nightscout lets you open a site with the token as
  part of the web address, and some tools are set up that way. A token placed in a web address can
  end up in logs, browser history and screenshots. If a tool offers a settings field, a keychain
  or an environment setting instead, prefer that.
- **You can switch it off.** Deleting the subject in Admin Tools stops the token working.
  Use one subject per tool so you can switch off one without affecting the others.
- **Switching it off does not take anything back.** Data the tool already read, and anything it
  sent to a model, stays wherever it went.

## Read-only tools and tools that can write

Some tools only read. Others can also **write**: add or delete treatments, or change your profile.
A write changes what your Nightscout site shows, and what everyone and everything that reads your
site sees: followers, caregivers, report tools and some apps.

Examples, as each project described itself on 2026-10-18 (named as examples of kinds, not as
recommendations):

| Tool (MCP server) | Can it write? | What it accepts |
|---|---|---|
| lozit/mcp-nightscout | No, read-only | a `readable` token; refuses the API_SECRET |
| oliver-virt/nightscout-mcp | No write tools | a `readable` token, never the API_SECRET |
| jeremyclee/nightscout-mcp-js | Adds treatments, but only if a setting is turned on | the API_SECRET or a token |
| b77ai/nightscout | Yes: adds and deletes treatments and updates the profile | the API_SECRET or a `readable` token; has a mode that puts its own access token in the web address |

Our suggestion: choose a read-only tool and give it a `readable` token. A `readable` token also
protects you if a tool has write features you did not notice, because Nightscout will refuse its
writes.

If you do want a tool that writes, understand what it writes before you connect it:

- Writing a record to Nightscout is **not** how Loop, Trio or AndroidAPS receive remote commands
  such as a remote bolus; those use separate, protected channels.
- But **some apps read records back from Nightscout**. AndroidAPS, for example, has settings to
  download temporary targets and profile switches from Nightscout. A record written by an AI tool
  could therefore reach such an app and change what it does. Check your own app's settings and
  documentation, and ask your care team or your app's community if you are unsure.

## What AI is reasonably good for, and where to be careful

Reasonable uses:

- Explaining what a chart or report on your site means.
- Summarizing a week or a month in plain words.
- Pointing out patterns worth bringing to your care team, such as "lows often happen after
  evening exercise".

Be careful, because:

- **AI tools can be wrong in convincing ways.** They can state things confidently that the data do
  not show, mix up units or time zones, or miss records.
- **They may not know what your app was doing**, such as whether an override or temporary target
  was active. Nightscout shows what was uploaded to it, which is not always the full picture.
- **Numbers should come from calculations, not guesses.** Some tools calculate time in range and
  averages with ordinary code and then let the AI describe the results; others ask the AI to work
  them out. Compare any figure the AI gives with your own Nightscout reports.
- **No tool's advice is clinically checked.** None of these tools has been shown to give accurate
  treatment advice, and some offer "suggested" settings. Do not change insulin doses, basal rates,
  carb ratios, correction factors or other settings because an AI suggested it. Take the
  suggestion to your care team. Lumose's own instructions say the same: any insulin dosing, carb
  ratio, or correction factor suggestions from AI must be verified with your healthcare team
  before use.

## Checklist before you connect a tool

- [ ] I know whether the tool uses a **cloud model or a local model**, and where my data will go.
- [ ] I have looked at the model provider's privacy terms.
- [ ] I created a **separate subject with only the `readable` role** for this tool.
- [ ] I did **not** give the tool my API_SECRET.
- [ ] I know whether the tool **can write** to Nightscout, and I chose a read-only one or
      understand what it writes and which of my apps might read it back.
- [ ] The token is kept in a settings field or keychain where possible, not in a web address I
      share or bookmark.
- [ ] I know how to **delete the subject** to switch the tool off, and that this does not undo
      what was already read.
- [ ] I will check anything important against my Nightscout reports and **talk with my care team
      before changing any treatment**.
- [ ] If someone else's data is on the site (for example a child's), I have thought about their
      privacy too.

---

## For contributors

The facts on this page come from contributor-facing records:
[agents in the ecosystem](../30-design/platform/agent-trust-boundaries-2026-10-18.md) (§3,
Interpret), the tool and MCP server tables in
[evidence §7.1](../00-overview/observations/ECOSYSTEM-EVIDENCE.md#71-research-tools-elsewhere-in-the-ecosystem),
the read role in
[configuration and delegation §5.3](../30-design/tenancy/nightscout-configuration-and-delegation-2026-09-10.md#53-what-exists-today),
AndroidAPS download settings in [the AAPS sync mapping](../../mapping/aaps/nightscout-sync.md#download-settings),
and remote command channels in the
[remote commands comparison](../10-domain/remote-commands-comparison.md). The Admin Tools labels
were read from cgm-remote-monitor `lib/admin_plugins/subjects.js` and `views/index.html`.

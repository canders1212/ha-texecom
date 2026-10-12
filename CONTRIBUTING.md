# Helping improve Texecom for Home Assistant

This integration was built and tested on **one** panel: a Premier Elite 24 (V6.05.03) with a SmartCom and **wired PIRs only**. Every other panel, firmware, module and detector is new territory. **Your panel can teach it things ours can't**, and that's the most useful help there is.

You don't need to write code. The code is maintained with AI coding agents (see [AGENTS.md](AGENTS.md)). They work from what you report, so a good report goes a long way.

**On this page:** [Ways to help](#ways-to-help) · [Sharing data for a feature](#sharing-data-for-a-feature-your-panel-has) · [Capturing a log](#capturing-a-debug-log) · [Privacy](#before-you-post-privacy) · [Code](#changing-the-code)

## Ways to help

| You want to… | Do this |
|---|---|
| Say how it went on your panel (worked or not) | [✅ Tested on my panel](https://github.com/metaljay/ha-texecom/issues/new?template=1-tested.yml) |
| Get something your panel has into Home Assistant (wireless, temperatures, other detectors…) | [📡 Share my panel's data](https://github.com/metaljay/ha-texecom/issues/new?template=3-data.yml): the form asks for what's described [below](#sharing-data-for-a-feature-your-panel-has) |
| Suggest something it could do | [💡 Idea](https://github.com/metaljay/ha-texecom/issues/new?template=3-feature.yml) |
| Report something wrong | [🐞 Something's wrong](https://github.com/metaljay/ha-texecom/issues/new?template=2-bug.yml), with diagnostics and a log |
| Ask a question | [Discussions](https://github.com/metaljay/ha-texecom/discussions) |

## Sharing data for a feature your panel has

**What we'd most like data from:**

- **Ricochet** and other **wireless** detectors: battery and signal levels, low-battery and supervision faults.
- **Shock sensors**: the temperatures the Texecom app shows.
- **Door and window contacts**, smoke, gas, panic and 24-hour zones.
- **ComIP and ComWiFi** modules, **Elite 48, 64, 88, 168, 640**, older (V4) and newer (V6.06+) **firmware**.
- **More than one area**, and **Crestron** setups.

**What to send** (each helps; all three is best). The [📡 Share my panel's data](https://github.com/metaljay/ha-texecom/issues/new?template=3-data.yml) form has a box for each:

1. **Diagnostics:** the panel's device page → **⋮ → Download diagnostics**. This lists your zones (with the type number the panel reports), areas, power readings and status flags, plus the **last 200 messages the panel sent** and every message the integration didn't recognise. Download it straight after the thing happens, before a restart (the messages are kept in memory only). Codes and the panel's address are removed automatically, and the panel's messages never contain codes.
2. **A debug log** while the thing happens ([how](#capturing-a-debug-log)).
3. **A timeline:** what you did and when, to the second if you can, plus what the **Texecom app or keypad** showed at the same moment. For example:
   > 14:02:10 opened the Studio door · 14:02:40 app showed *Studio Shock 21 °C* · 14:03:05 closed it

   A screenshot of the app next to the matching log lines is ideal. Matching what the panel *sent* to what the app *showed* is how new features get worked out.

## Capturing a debug log

**The easy way** (no restart):

1. **Settings → Devices & services → Texecom Premier Elite → ⋮ → Enable debug logging.**
2. Do the thing (for a wireless detector, waiting up to an hour helps, so its regular check-in is caught). Note the times.
3. **⋮ → Disable debug logging.** Your browser downloads the log file. Attach it to the issue (zip it if it's large).

**Or, to capture start-up too**, add this to `configuration.yaml` and restart:

```yaml
logger:
  logs:
    custom_components.texecom: debug
```

Then copy the `custom_components.texecom` lines from **Settings → System → Logs → Show raw logs**. Remove it afterwards: it's chatty.

## Before you post: privacy

- **The integration doesn't write codes to its logs or diagnostics**, so there's nothing to remove there.
- **Zone, area and user names appear in diagnostics and logs, and your panel's local address can appear in logs.** Change anything you'd rather not share, as long as it stays the same throughout the log (e.g. replace *Smith* with *X* everywhere).
- Don't post Wintex files or screenshots that show your name, address or codes.

## Changing the code

Pull requests are welcome. Please read [AGENTS.md](AGENTS.md) (the rules every change follows, whether written by a person or an AI agent) and the [developer guide](docs/development/README.md). Panel behaviour you discover belongs in [docs/development/protocol.md](docs/development/protocol.md).

In short: one kind of change per pull request, a test for new behaviour, `ruff` clean and both test suites passing, and no codes or personal details anywhere.

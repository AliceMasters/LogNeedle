# 📜 Patch Notes: LogNeedle

Each patch below covers one release day. Hashes link to the commits.

---

## Patch 1.3: *"Outside UTC"*
**October 5, 2026**

**🐛 Critical fix: timeline order**
- Log lines with no timezone were stored **as UTC instead of local time**. On any machine not set to UTC, a bundle that mixed timezone-aware sources (EVTX, ISO `Z` logs) with plain text logs put the same moment hours apart. That's 4 hours on a US Eastern machine. Zone-less times are now read as local time (daylight-saving aware) and converted to UTC, as the README always promised. ([`267c3df`](https://github.com/AliceMasters/LogNeedle/commit/267c3df))

**🔍 How it slipped through, and what changed**
- The tests asserted the wrong behaviour (`hour == 14` on a value documented as UTC). They now compare actual moments in time. ([`267c3df`](https://github.com/AliceMasters/LogNeedle/commit/267c3df))
- CI only ran in UTC, where this bug can't happen. **New CI jobs** now re-run the suite in 🇺🇸 New York (−4), 🇮🇳 Kolkata (+5:30) and 🇳🇿 Auckland (+13). ([`267c3df`](https://github.com/AliceMasters/LogNeedle/commit/267c3df))
- **New regression test:** the same moment written as local time and as UTC must come out identical.
- **Caught by the new CI on its first run:** one test failed only in Auckland, where the offset pushes the time past midnight into a different date. Fixed. ([`dc1fb86`](https://github.com/AliceMasters/LogNeedle/commit/dc1fb86))

**✅ Verified:** the new tests fail on the old code (5 failures) and pass on the new (27/27). Locally the suite also passes in UTC, New York, Kolkata, Auckland and Honolulu.

---

## Patch 1.2.1: *"Housekeeping"*
**October 3, 2026**
- Added `.editorconfig` so formatting stays consistent. ([`be8fa15`](https://github.com/AliceMasters/LogNeedle/commit/be8fa15))
- README: tests run through `pytest`, plus a new "why it exists" section. ([`0c303f7`](https://github.com/AliceMasters/LogNeedle/commit/0c303f7))

---

## Patch 1.2: *"Nothing to See Here"*
**September 25, 2026**

**✨ New**
- **Wider secret redaction:** JWTs, AWS access keys, PEM private keys and Windows profile usernames are now masked in exports. ([`7f2831f`](https://github.com/AliceMasters/LogNeedle/commit/7f2831f))

**🛡️ Quality**
- CI now runs on **Windows and Linux** across **Python 3.11 and 3.12**, with a status badge. ([`f53b86d`](https://github.com/AliceMasters/LogNeedle/commit/f53b86d))

**🐛 Fixes**
- `.gitignore` had two entries merged onto one line, so neither was ignored. ([`81f1c7c`](https://github.com/AliceMasters/LogNeedle/commit/81f1c7c))

---

## Patch 1.0: *"Needle, Meet Haystack"*
**September 22, 2026**

**✨ Launch**
- LogNeedle is a Windows desktop app that turns a bundle of logs into one evidence-backed timeline. It handles `.evtx`, `.log`, `.txt`, `.csv`, `.jsonl` and `.out`, and does error-storm detection, boot and shutdown markers, last-error summaries, and exports to Markdown, HTML and text. ([`a2c2d7f`](https://github.com/AliceMasters/LogNeedle/commit/a2c2d7f))
- Tests run in CI on every push. ([`83ab7b1`](https://github.com/AliceMasters/LogNeedle/commit/83ab7b1))

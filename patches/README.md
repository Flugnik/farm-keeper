# OpenClaw: auto-create daily memory log on read ENOENT

## What it does

Patches OpenClaw dist bundles in-place:

- Adds helper: `ensureDailyMemoryFileExists(filePath)`
- In `createOpenClawReadTool()`:
  if `read` returns ENOENT and path ends with `/workspace/memory/YYYY-MM-DD.md`,
  then create that file and retry the read.

## Run

cd /home/user/.npm-global/lib/node_modules/openclaw
python3 ~/farm-keeper/patches/patch_read_autocreate.py

## Verify

cd /home/user/.npm-global/lib/node_modules/openclaw
grep -RIn --include='*.js' -E "async function ensureDailyMemoryFileExists" dist | wc -l
grep -RIn --include='*.js' -E "isReadToolENOENTResult\\(result\\) && await ensureDailyMemoryFileExists" dist | head

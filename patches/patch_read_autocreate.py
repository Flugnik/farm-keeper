#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import time


HELPER = """
async function ensureDailyMemoryFileExists(filePath) {
        if (typeof filePath !== "string" || !filePath) return false;
        const resolved = path.resolve(filePath);

        // Only auto-create daily logs under ~/.openclaw/workspace/memory/YYYY-MM-DD.md
        // Strict suffix match (keeps this narrowly scoped)
        const suffixMatch = resolved.match(/\\/workspace\\/memory\\/(\\d{4}-\\d{2}-\\d{2})\\.md$/);
        if (!suffixMatch) return false;

        const dir = path.dirname(resolved);
        try { await fs.mkdir(dir, { recursive: true }); } catch {}

        const day = suffixMatch[1];
        const template = `# ${day}\\n\\n`;

        try {
                // wx = create only if missing
                await fs.writeFile(resolved, template, { encoding: "utf-8", flag: "wx" });
        } catch (err) {
                const code = err && typeof err === "object" && "code" in err ? String(err.code) : "";
                if (code !== "EEXIST") throw err;
        }
        return true;
}
""".strip("\n")


def _backup(fp: Path) -> Path:
    ts = int(time.time())
    bak = fp.with_suffix(fp.suffix + f".bak.{ts}")
    bak.write_bytes(fp.read_bytes())
    return bak


def patch_bundle(fp: Path) -> tuple[bool, str]:
    """
    Returns (patched, message).
    """
    try:
        text = fp.read_text("utf-8")
    except Exception as e:
        return (False, f"[skip] unreadable: {fp} ({e})")

    if "function createOpenClawReadTool" not in text:
        return (False, f"[skip] no createOpenClawReadTool: {fp}")

    if "ensureDailyMemoryFileExists" in text:
        # Also fix a known typo if it exists (ensureDailyMemoryFileExist -> Exists)
        fixed = re.sub(r"\bensureDailyMemoryFileExist\b", "ensureDailyMemoryFileExists", text)
        if fixed != text:
            _backup(fp)
            fp.write_text(fixed, "utf-8")
            return (True, f"[ok] typo-fixed: {fp}")
        return (False, f"[skip] already patched: {fp}")

    # 1) Inject helper BEFORE createOpenClawReadTool
    # Keep it simple: insert HELPER on the line just before "function createOpenClawReadTool("
    marker = "function createOpenClawReadTool("
    idx = text.find(marker)
    if idx < 0:
        return (False, f"[skip] marker not found: {fp}")

    injected = text[:idx] + HELPER + "\n" + text[idx:]

    # 2) Replace "const result = await executeReadWithAdaptivePaging" with a retry-able "let result = ..."
    # and add retry ENOENT logic immediately after the call.
    #
    # We target the exact block:
    #   const result = await executeReadWithAdaptivePaging({
    #     ...
    #   });
    #
    # and transform into:
    #   let result = await executeReadWithAdaptivePaging({...});
    #   const filePath = ...;
    #   if (isReadToolENOENTResult(result) && await ensureDailyMemoryFileExists(filePath)) {
    #       result = await executeReadWithAdaptivePaging({...});
    #   }
    #
    # Then the original code continues, and uses `result` below.
    #
    # IMPORTANT: in your snippet filePath was computed AFTER the call; we keep that, but we need it
    # earlier for retry. We'll compute it right after first call (same expression).
    call_pat = re.compile(
        r"const result\s*=\s*await executeReadWithAdaptivePaging\(\{\s*"
        r"(?P<body>.*?)\s*\}\);\s*",
        re.DOTALL,
    )

    m = call_pat.search(injected)
    if not m:
        return (False, f"[skip] executeReadWithAdaptivePaging call not found: {fp}")

    # Preserve exact call object body so second call matches.
    body = m.group("body")

    replacement = (
        "let result = await executeReadWithAdaptivePaging({\n"
        f"{body}\n"
        "});\n"
        "                        const filePath = typeof record?.path === \"string\" ? String(record.path) : \"<unknown>\";\n"
        "                        if (isReadToolENOENTResult(result) && await ensureDailyMemoryFileExists(filePath)) {\n"
        "                                result = await executeReadWithAdaptivePaging({\n"
        f"{body}\n"
        "                                });\n"
        "                        }\n"
    )

    injected2 = injected[: m.start()] + replacement + injected[m.end() :]

    # 3) Now the original code later defines filePath; remove/avoid duplicate.
    # In your snippet it was:
    #   const filePath = typeof record?.path === "string" ? String(record.path) : "<unknown>";
    # right after the call. After our insertion, that line will still exist later.
    # We remove the *next* occurrence AFTER our inserted one.
    dup_line = 'const filePath = typeof record?.path === "string" ? String(record.path) : "<unknown>";'
    first_pos = injected2.find(dup_line)
    if first_pos == -1:
        # not fatal; keep as-is
        pass
    else:
        second_pos = injected2.find(dup_line, first_pos + len(dup_line))
        if second_pos != -1:
            # remove exactly one duplicate line + trailing newline/spaces
            injected2 = injected2[:second_pos] + injected2[second_pos + len(dup_line):]
            # also try to delete one following newline if present
            injected2 = injected2.replace("\n\n", "\n", 1)

    # 4) Safety: ensure isReadToolENOENTResult exists somewhere; if not, we can add a minimal impl.
    # (Usually it exists in the same bundle; but let's be defensive.)
    if "isReadToolENOENTResult" not in injected2:
        # Minimal helper based on toolResult shape from your logs.
        extra = """
function isReadToolENOENTResult(result) {
        try {
                const details = result && typeof result === "object" ? result.details : null;
                const err = details && typeof details === "object" ? details.error : null;
                return typeof err === "string" && err.includes("ENOENT");
        } catch {
                return false;
        }
}
""".strip("\n")
        # place it right after ensureDailyMemoryFileExists
        injected2 = injected2.replace(HELPER, HELPER + "\n" + extra)

    # Write out
    _backup(fp)
    fp.write_text(injected2, "utf-8")
    return (True, f"[ok] patched: {fp}")


def main() -> None:
    root = Path("dist")
    if not root.exists():
        raise SystemExit("Run from /home/user/.npm-global/lib/node_modules/openclaw (dist/ missing)")

    targets: list[Path] = []
    for fp in root.rglob("*.js"):
        try:
            s = fp.read_text("utf-8")
        except Exception:
            continue
        if "function createOpenClawReadTool" in s:
            targets.append(fp)

    if not targets:
        raise SystemExit("[err] no bundles with createOpenClawReadTool found under dist/")

    patched = 0
    skipped = 0
    for fp in sorted(targets):
        did, msg = patch_bundle(fp)
        print(msg)
        if did:
            patched += 1
        else:
            skipped += 1

    print(f"Done. patched={patched} skipped={skipped} targets={len(targets)}")


if __name__ == "__main__":
    main()

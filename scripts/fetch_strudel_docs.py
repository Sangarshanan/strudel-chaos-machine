"""
Strudel docs for reference.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
SOUNDS_PATH = ROOT / "src" / "knowledge" / "sounds.json"

_fetch_JS = r"""
async () => {
    function safeKeys(obj) {
        if (!obj) return [];
        try { return Object.keys(obj); } catch (e) { return []; }
    }
    const out = { names: new Set(), banks: new Set() };

    // 1. window.soundMap (most current builds)
    try {
        if (window.soundMap && typeof window.soundMap.get === 'function') {
            const data = window.soundMap.get().data || window.soundMap.get();
            safeKeys(data).forEach(k => out.names.add(k));
        }
    } catch (e) { /* ignore */ }

    // 2. window._strudel
    try {
        const s = window._strudel;
        if (s && s.sounds) safeKeys(s.sounds).forEach(k => out.names.add(k));
        if (s && s.banks) safeKeys(s.banks).forEach(k => out.banks.add(k));
    } catch (e) { /* ignore */ }

    // 3. Public helper functions some builds expose
    for (const helper of ['getSounds', 'getSoundIndex']) {
        try {
            if (typeof window[helper] === 'function') {
                const res = window[helper]();
                if (res && typeof res === 'object') {
                    safeKeys(res).forEach(k => out.names.add(k));
                }
            }
        } catch (e) { /* ignore */ }
    }

    // 4. Some builds attach to window.strudel
    try {
        const s = window.strudel;
        if (s && s.sounds) safeKeys(s.sounds).forEach(k => out.names.add(k));
    } catch (e) { /* ignore */ }

    return {
        sounds: Array.from(out.names).sort(),
        banks: Array.from(out.banks).sort(),
    };
}
"""


def _classify(name: str) -> str:
    if name.startswith("gm_"):
        return "gm_samples"
    if name in {"sine", "sawtooth", "square", "triangle", "supersaw", "fm",
                "white", "pink", "brown"}:
        return "synths"
    if len(name) <= 4 and name.isalpha():
        return "drums"
    return "vcsl_samples"


async def main() -> int:
    print(f"[fetch] opening strudel.cc (this may take a few seconds)")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto("https://strudel.cc", wait_until="domcontentloaded")
            try:
                await page.wait_for_selector(".cm-content", timeout=20_000)
            except Exception:
                print("[fetch] warn: editor selector not found, continuing")
            # Give the sound registry a moment to populate after first eval.
            await asyncio.sleep(3)
            data = await page.evaluate(_fetch_JS)
        finally:
            await browser.close()

    strudel_sounds: list[str] = data.get("sounds", [])
    strudel_banks: list[str] = data.get("banks", [])
    print(f"[fetch] found {len(strudel_sounds)} sounds, "
          f"{len(strudel_banks)} banks")

    if not strudel_sounds and not strudel_banks:
        print("[fetch] no data extracted; baseline left unchanged.")
        return 1

    with SOUNDS_PATH.open("r", encoding="utf-8") as f:
        bundle = json.load(f)

    # Merge strudel sounds into the right categories.
    buckets: dict[str, set[str]] = {
        key: set(bundle.get(key, []))
        for key in ("synths", "drums", "gm_samples", "vcsl_samples")
    }
    for name in strudel_sounds:
        buckets[_classify(name)].add(name)
    for key, values in buckets.items():
        bundle[key] = sorted(values)

    if strudel_banks:
        bundle["banks"] = sorted(set(bundle.get("banks", [])) | set(strudel_banks))

    bundle["source"] = "strudel from strudel.cc + curated baseline"

    with SOUNDS_PATH.open("w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, sort_keys=False)
        f.write("\n")

    print(f"[fetch] wrote merged catalog to {SOUNDS_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

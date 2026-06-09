"""Read/write the Strudel.cc CodeMirror buffer and trigger evaluation."""

import sys
from playwright.async_api import Page

READ_BUFFER_JS = r"""
() => {
    // Try CodeMirror 6 view via several known attachment points.
    const candidates = Array.from(document.querySelectorAll('.cm-editor'));
    for (const el of candidates) {
        const view = (el.cmView && el.cmView.view)
            || el.CodeMirror
            || (el._view);
        if (view && view.state && view.state.doc) {
            try { return view.state.doc.toString(); }
            catch (e) { /* fall through */ }
        }
    }
    const content = document.querySelector('.cm-content');
    if (!content) return '';
    const lines = content.querySelectorAll('.cm-line');
    if (lines.length === 0) return content.innerText || '';
    return Array.from(lines).map(l => l.textContent).join('\n');
}
"""

# Resolve a CodeMirror 6 EditorView from the page. Tries the public-ish
# attachment points first, then falls back to scanning the editor DOM
# subtree for any element exposing `.cmView.view` (which is how CM6
# attaches its EditorView to plugin/widget DOM internally).
_FIND_VIEW_SRC = r"""
        function findView() {
            const editors = Array.from(document.querySelectorAll('.cm-editor'));
            for (const el of editors) {
                if (el.cmView && el.cmView.view) return el.cmView.view;
                if (el.CodeMirror && el.CodeMirror.state) return el.CodeMirror;
                if (el._view && el._view.state) return el._view;
                const walker = document.createTreeWalker(el, NodeFilter.SHOW_ELEMENT);
                let n = walker.currentNode;
                while (n) {
                    if (n.cmView && n.cmView.view) return n.cmView.view;
                    n = walker.nextNode();
                }
            }
            return null;
        }
"""

WRITE_BUFFER_JS = r"""
(text) => {
""" + _FIND_VIEW_SRC + r"""
    const view = findView();
    if (!view) return { ok: false, reason: 'no-view' };
    try {
        view.dispatch({
            changes: { from: 0, to: view.state.doc.length, insert: text }
        });
        return { ok: true };
    } catch (e) {
        return { ok: false, reason: 'dispatch: ' + (e && e.message || e) };
    }
}
"""

_FOCUS_EDITOR_JS = (
    "() => { const e = document.querySelector('.cm-content');"
    " if (e && e.focus) e.focus(); }"
)


# Python wrappers to read and write the strudel editor buffer.

async def read_buffer(page: Page) -> str:
    try:
        value = await page.evaluate(READ_BUFFER_JS)
    except Exception as exc:
        print(f"[warn] could not read buffer: {exc}", file=sys.stderr)
        return ""
    return value or ""


async def write_buffer(page: Page, text: str) -> bool:
    """Try CM6 transaction first, fall back to select-all + type."""
    try:
        result = await page.evaluate(WRITE_BUFFER_JS, text)
    except Exception as exc:
        print(f"[warn] write JS threw: {exc}", file=sys.stderr)
        result = {"ok": False, "reason": f"threw: {exc}"}

    if isinstance(result, dict) and result.get("ok"):
        return True

    reason = (
        (result or {}).get("reason", "unknown")
        if isinstance(result, dict) else result
    )
    print(f"[warn] CM6 dispatch failed ({reason}); falling back to keyboard",
          file=sys.stderr)

    try:
        await page.evaluate(_FOCUS_EDITOR_JS)
        modifier = "Meta" if sys.platform == "darwin" else "Control"
        await page.keyboard.press(f"{modifier}+a")
        await page.keyboard.press("Delete")
        # `insert_text` is faster than `type` and skips per-char delays.
        await page.keyboard.insert_text(text)
        return True
    except Exception as exc:
        print(f"[warn] keyboard fallback failed: {exc}", file=sys.stderr)
        return False


async def trigger_play(page: Page) -> None:
    """Re-evaluate the patch so playback picks up the new buffer."""
    try:
        await page.evaluate(_FOCUS_EDITOR_JS)
        await page.keyboard.press("Control+Enter")
    except Exception as exc:
        print(f"[warn] could not trigger play: {exc}", file=sys.stderr)

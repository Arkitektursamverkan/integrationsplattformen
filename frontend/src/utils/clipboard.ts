/**
 * Copy `text` to the clipboard, with a fallback for insecure contexts.
 *
 * `navigator.clipboard.writeText` is only available in secure contexts
 * (HTTPS / localhost). On plain HTTP (which is how IP is typically accessed
 * on internal IPs) the call resolves silently without copying. We fall back
 * to a hidden textarea + the legacy `document.execCommand("copy")`.
 *
 * Returns true if the copy was reported as successful, false otherwise.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall through to the legacy path below.
    }
  }

  if (typeof document === "undefined") return false;
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "0";
    ta.style.left = "0";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    ta.setSelectionRange(0, text.length);
    // execCommand is deprecated but still works in every browser for the
    // synchronous copy-from-selected-element case we need here.
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

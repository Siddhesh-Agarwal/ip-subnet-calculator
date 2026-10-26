"""Small Custom Components v2 pieces used across the app.

The components are deliberately front-end only: the copy buttons never need a
server round-trip, and the visualisations are data-in, pixels-out.
"""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

_COPY_CSS = """
:host { display: block; }
.field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .75rem;
  box-sizing: border-box;
  min-height: 54px;
  padding: .5rem .7rem;
  background: var(--st-secondary-background-color, #fafafa);
  border: 1px solid var(--st-border-color, #e4e4e7);
  border-radius: var(--st-base-radius, 6px);
  cursor: pointer;
  transition: border-color .15s ease, background .15s ease;
}
.field:hover { border-color: var(--st-primary-color, #2563eb); }
.field:focus-visible { outline: 2px solid var(--st-primary-color, #2563eb); outline-offset: 2px; }
.field.copied { border-color: var(--st-green-color, #16a34a); }
.body { min-width: 0; flex: 1; }
.label {
  margin-bottom: .12rem;
  color: var(--st-gray-color, #71717a);
  font-size: .68rem;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
}
.value {
  color: var(--st-text-color, #111827);
  font-family: var(--st-code-font, ui-monospace, monospace);
  font-size: .82rem;
  line-height: 1.35;
  overflow-wrap: anywhere;
}
.hint {
  flex: 0 0 auto;
  color: var(--st-gray-color, #71717a);
  font-size: .68rem;
  opacity: 0;
  transition: opacity .15s ease;
}
.field:hover .hint, .field.copied .hint { opacity: 1; }
.field.copied .hint { color: var(--st-green-color, #16a34a); }
.button {
  display: inline-flex;
  align-items: center;
  gap: .4rem;
  padding: .38rem .65rem;
  color: var(--st-text-color, #111827);
  background: var(--st-secondary-background-color, #fafafa);
  border: 1px solid var(--st-border-color, #e4e4e7);
  border-radius: var(--st-button-radius, 6px);
  font-family: var(--st-font, sans-serif);
  font-size: .8rem;
  cursor: pointer;
  transition: border-color .15s ease, color .15s ease;
}
.button:hover { border-color: var(--st-primary-color, #2563eb); }
.button:focus-visible { outline: 2px solid var(--st-primary-color, #2563eb); outline-offset: 2px; }
.button.copied { color: var(--st-green-color, #16a34a); border-color: var(--st-green-color, #16a34a); }
.button svg { width: 14px; height: 14px; flex: 0 0 auto; }
"""

_COPY_JS = """
export default function (component) {
  const { data, parentElement } = component
  const field = parentElement.querySelector("#field")
  if (!field) return
  const label = parentElement.querySelector("#label")
  const value = parentElement.querySelector("#value")
  const hint = parentElement.querySelector("#hint")
  if (label) label.textContent = data?.label ?? ""
  if (value) value.textContent = data?.value ?? ""
  field.setAttribute("aria-label", `Copy ${data?.label ?? "value"}`)

  const copyText = async (text) => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text)
        return true
      }
    } catch (err) { /* fall through */ }
    try {
      const area = document.createElement("textarea")
      area.value = text
      area.setAttribute("readonly", "")
      area.style.position = "fixed"
      area.style.opacity = "0"
      document.body.appendChild(area)
      area.select()
      const ok = document.execCommand("copy")
      area.remove()
      return ok
    } catch (err) {
      return false
    }
  }

  const flash = (ok) => {
    if (!hint) return
    hint.textContent = ok ? "Copied" : "Copy failed"
    field.classList.toggle("copied", ok)
    window.setTimeout(() => {
      hint.textContent = "Copy"
      field.classList.remove("copied")
    }, 1400)
  }

  const run = () => copyText(String(data?.value ?? "")).then(flash)
  field.onclick = run
  field.onkeydown = (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      run()
    }
  }
}
"""

_BUTTON_JS = """
export default function (component) {
  const { data, parentElement } = component
  const button = parentElement.querySelector("#button")
  if (!button) return
  const label = parentElement.querySelector("#label")
  if (label) label.textContent = data?.label ?? ""

  const copyText = async (text) => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text)
        return true
      }
    } catch (err) { /* fall through */ }
    try {
      const area = document.createElement("textarea")
      area.value = text
      area.setAttribute("readonly", "")
      area.style.position = "fixed"
      area.style.opacity = "0"
      document.body.appendChild(area)
      area.select()
      const ok = document.execCommand("copy")
      area.remove()
      return ok
    } catch (err) {
      return false
    }
  }

  const original = () => String(data?.label ?? "Copy")
  button.onclick = async () => {
    const ok = await copyText(String(data?.value ?? ""))
    button.classList.toggle("copied", ok)
    if (label) label.textContent = ok ? "Copied" : "Copy failed"
    window.setTimeout(() => {
      button.classList.remove("copied")
      if (label) label.textContent = original()
    }, 1400)
  }
}
"""

_FIELD = st.components.v2.component(
    "ipcalc_copy_field",
    html="""
    <div id="field" class="field" role="button" tabindex="0" aria-label="Copy value">
      <div class="body">
        <div id="label" class="label"></div>
        <div id="value" class="value"></div>
      </div>
      <span id="hint" class="hint">Copy</span>
    </div>
    """,
    css=_COPY_CSS,
    js=_COPY_JS,
)

_BUTTON = st.components.v2.component(
    "ipcalc_copy_button",
    html="""
    <button id="button" class="button" type="button">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <rect x="9" y="9" width="13" height="13" rx="2"></rect>
        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
      </svg>
      <span id="label">Copy</span>
    </button>
    """,
    css=_COPY_CSS,
    js=_BUTTON_JS,
)


def copy_field(label: str, value: Any, *, key: str) -> None:
    """A full-width click-to-copy field."""
    _FIELD(key=key, data={"label": label, "value": str(value)}, width="stretch")


def copy_button(label: str, value: Any, *, key: str) -> None:
    """A compact click-to-copy button."""
    _BUTTON(key=key, data={"label": label, "value": str(value)}, width="content")


# ---------------------------------------------------------------------------
# Binary view
# ---------------------------------------------------------------------------

_BINARY = st.components.v2.component(
    "ipcalc_binary_view",
    html="""
    <div id="wrap" class="wrap" role="img">
      <div id="legend" class="legend"></div>
      <div id="bits" class="bits"></div>
      <div id="labels" class="labels"></div>
    </div>
    """,
    css="""
    :host { display: block; }
    .wrap { font-family: var(--st-code-font, ui-monospace, monospace); }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: .9rem;
      margin-bottom: .45rem;
      color: var(--st-gray-color, #71717a);
      font-family: var(--st-font, sans-serif);
      font-size: .7rem;
    }
    .swatch { display: inline-flex; align-items: center; gap: .3rem; }
    .dot { width: .55rem; height: .55rem; border-radius: 2px; }
    .dot.net { background: var(--st-blue-color, #3b82f6); }
    .dot.host { background: var(--st-gray-color, #a1a1aa); }
    .bits { display: flex; flex-wrap: wrap; align-items: center; gap: .2rem 0; }
    .group { display: inline-flex; gap: 2px; margin-right: .4rem; }
    .bit {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: .86rem;
      height: 1.55rem;
      border-radius: 3px;
      font-size: .76rem;
      font-weight: 600;
      color: var(--st-text-color, #111827);
    }
    .net {
      background: var(--st-blue-background-color, #dbeafe);
      color: var(--st-blue-text-color, #1e40af);
      border: 1px solid color-mix(in srgb, var(--st-blue-color, #3b82f6) 35%, transparent);
    }
    .host {
      background: var(--st-gray-background-color, #f1f5f9);
      color: var(--st-gray-text-color, #334155);
      border: 1px solid var(--st-border-color, #e2e8f0);
    }
    .boundary { box-shadow: -2px 0 0 0 var(--st-primary-color, #2563eb); margin-left: 2px; }
    .sep { color: var(--st-gray-color, #71717a); font-weight: 600; margin: 0 .02rem; }
    .labels { display: flex; flex-wrap: wrap; gap: .28rem; margin-top: .25rem; }
    .group-label { color: var(--st-gray-color, #71717a); font-size: .64rem; }
    .compact .bit { width: .56rem; font-size: .6rem; font-weight: 500; }
    .compact .group { margin-right: .22rem; }
    """,
    js="""
    export default function (component) {
      const { data, parentElement } = component
      const bits = String(data?.bits ?? "")
      const prefix = Number(data?.prefix ?? 0)
      const groupSize = Number(data?.group ?? 8)
      const separator = data?.separator ?? "."
      const bitsEl = parentElement.querySelector("#bits")
      const labelsEl = parentElement.querySelector("#labels")
      const legendEl = parentElement.querySelector("#legend")
      const wrap = parentElement.querySelector("#wrap")
      if (!bitsEl) return
      wrap.setAttribute(
        "aria-label",
        `${bits.length}-bit address with the network/host boundary after bit ${prefix}`
      )
      bitsEl.textContent = ""
      labelsEl.textContent = ""
      legendEl.textContent = ""
      if (bits.length > 64) wrap.classList.add("compact")

      const legend = (text, cls) => {
        const item = document.createElement("span")
        item.className = "swatch"
        const dot = document.createElement("span")
        dot.className = "dot " + cls
        const label = document.createElement("span")
        label.textContent = text
        item.append(dot, label)
        return item
      }
      legendEl.append(
        legend("network bits", "net"),
        legend("host bits", "host"),
        legend(`boundary /${prefix}`, "net")
      )

      const groups = []
      for (let i = 0; i < bits.length; i += groupSize) {
        groups.push(bits.slice(i, i + groupSize))
      }
      let bitIndex = 0
      groups.forEach((chunk, groupIndex) => {
        const group = document.createElement("span")
        group.className = "group"
        for (const char of chunk) {
          const bit = document.createElement("span")
          const isNetwork = bitIndex < prefix
          bit.className = "bit " + (isNetwork ? "net" : "host")
          if (bitIndex === prefix) bit.classList.add("boundary")
          bit.textContent = char
          group.appendChild(bit)
          bitIndex += 1
        }
        bitsEl.appendChild(group)
        if (groupIndex < groups.length - 1) {
          const sep = document.createElement("span")
          sep.className = "sep"
          sep.textContent = separator
          bitsEl.appendChild(sep)
        }
        const label = document.createElement("span")
        label.className = "group-label"
        label.textContent = data?.group_labels?.[groupIndex] ?? ""
        labelsEl.appendChild(label)
      })
    }
    """,
)


def binary_view(
    bits: str,
    *,
    prefixlen: int,
    version: int,
    group_labels: list[str],
    key: str,
) -> None:
    _BINARY(
        key=key,
        data={
            "bits": bits,
            "prefix": prefixlen,
            "group": 8 if version == 4 else 16,
            "separator": "." if version == 4 else ":",
            "group_labels": group_labels,
        },
        width="stretch",
    )


# ---------------------------------------------------------------------------
# IPAM bar
# ---------------------------------------------------------------------------

_IPAM = st.components.v2.component(
    "ipcalc_ipam_bar",
    html="""
    <div class="wrap">
      <div id="summary" class="summary"></div>
      <div id="bar" class="bar" role="img"></div>
      <div id="legend" class="legend"></div>
    </div>
    """,
    css="""
    :host { display: block; }
    .summary {
      color: var(--st-gray-color, #71717a);
      font-family: var(--st-font, sans-serif);
      font-size: .72rem;
      margin-bottom: .35rem;
    }
    .bar {
      position: relative;
      width: 100%;
      height: 34px;
      background: var(--st-secondary-background-color, #f4f4f5);
      border: 1px solid var(--st-border-color, #e4e4e7);
      border-radius: var(--st-base-radius, 6px);
      overflow: hidden;
    }
    .seg {
      position: absolute;
      top: 0;
      bottom: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      color: #fff;
      font-family: var(--st-code-font, monospace);
      font-size: .58rem;
      white-space: nowrap;
      text-shadow: 0 1px 2px rgba(0,0,0,.45);
      border-right: 1px solid rgba(255,255,255,.25);
    }
    .seg.free {
      color: var(--st-gray-color, #71717a);
      background: repeating-linear-gradient(
        -45deg,
        transparent,
        transparent 4px,
        var(--st-border-color, #e4e4e7) 4px,
        var(--st-border-color, #e4e4e7) 5px
      );
      text-shadow: none;
    }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: .4rem .9rem;
      margin-top: .45rem;
      color: var(--st-gray-color, #71717a);
      font-family: var(--st-font, sans-serif);
      font-size: .68rem;
    }
    .item { display: inline-flex; align-items: center; gap: .3rem; }
    .swatch { width: .55rem; height: .55rem; border-radius: 2px; border: 1px solid var(--st-border-color, #e4e4e7); }
    """,
    js="""
    export default function (component) {
      const { data, parentElement } = component
      const segments = data?.segments ?? []
      const summary = parentElement.querySelector("#summary")
      const bar = parentElement.querySelector("#bar")
      const legend = parentElement.querySelector("#legend")
      if (!bar) return
      bar.textContent = ""
      bar.setAttribute("aria-label", data?.summary ?? "IPAM allocation map")
      legend.textContent = ""
      if (summary) summary.textContent = data?.summary ?? ""

      const host = parentElement.host ?? parentElement
      const raw = getComputedStyle(host).getPropertyValue("--st-chart-categorical-colors").trim()
      const palette = raw ? raw.split(",").map((value) => value.trim()).filter(Boolean) : []
      const fallback = ["#2563eb", "#0d9488", "#7c3aed", "#db2777", "#ea580c", "#0891b2", "#65a30d"]
      const colors = palette.length ? palette : fallback

      let allocatedIndex = 0
      let freeLegendAdded = false
      segments.forEach((segment) => {
        const isFree = segment.kind === "free"
        const el = document.createElement("div")
        el.className = "seg " + (isFree ? "free" : "allocated")
        el.style.left = `${segment.start}%`
        el.style.width = `max(${segment.width}%, 2px)`
        const color = isFree ? "" : colors[allocatedIndex % colors.length]
        if (color) el.style.background = color
        if (!isFree) allocatedIndex += 1
        el.title = `${segment.label}\\n${segment.cidr}\\n${segment.size_label}`
        if (!isFree && segment.width > 12) el.textContent = segment.short_label || ""
        bar.appendChild(el)

        if (isFree && freeLegendAdded) return
        const item = document.createElement("span")
        item.className = "item"
        const swatch = document.createElement("span")
        swatch.className = "swatch"
        swatch.style.background = isFree
          ? "repeating-linear-gradient(-45deg, transparent, transparent 2px, var(--st-border-color) 2px, var(--st-border-color) 3px)"
          : color
        const text = document.createElement("span")
        text.textContent = isFree ? "Free space" : `${segment.label} · ${segment.cidr}`
        item.append(swatch, text)
        legend.appendChild(item)
        if (isFree) freeLegendAdded = true
      })
    }
    """,
)


def ipam_bar(
    segments: list[dict[str, Any]],
    *,
    summary: str,
    key: str,
) -> None:
    _IPAM(
        key=key,
        data={"segments": segments, "summary": summary},
        width="stretch",
    )


def safe_html(value: str) -> str:
    return html.escape(value)

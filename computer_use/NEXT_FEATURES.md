# Next Features

## Phase 5: Stale + Crop-Verify for Cross-Device

**Goal**: Detect when cached element positions are stale (app updated, screen changed, device switch) before clicking.

**How it works**:
- On `record_hit`, store a small screenshot crop (~50x50px) around the element as a reference image
- On cache lookup, take a fresh crop at the cached position and compare to the stored reference
- If similarity is below threshold, treat as cache miss instead of clicking the wrong thing
- ~2s added latency per element verification

**When it matters**:
- Multi-device setups (laptop + external monitor)
- After app UI updates (buttons moved/resized)
- Long-lived cache entries that may have drifted

**Impact**: Reliability, not speed. Prevents misclicks from stale cache entries.

---

## Phase 6: Predictive Pre-Caching

**Goal**: Use sequence tracking data to pre-load the next likely element before it's requested.

**How it works**:
- After each cache hit, query the `sequences` table for the most likely next element
- Pre-load that entry into the in-memory dict so the next lookup is instant
- Uses existing `find_path()` BFS and sequence counts

**When it matters**:
- High-frequency workflows where even sub-millisecond savings compound
- Cold cache scenarios where SQLite I/O is the bottleneck

**Impact**: Minimal (~0.05s per step). Cache lookups are already fast. Low priority.

---

## Dead Key Sequence Typing

**Goal**: Replace clipboard paste fallback with proper dead key simulation for composed characters (e.g. accent + letter).

**Why**: Currently, characters that require dead key combos (like `^` then `e` to produce `e with circumflex` on French AZERTY) are pasted via `wl-copy -o` + Ctrl+V. This works but overwrites the user's clipboard and fails in apps that block paste.

**How it works**:
- Build a dead key composition table per layout from xkb compose rules
- For composed characters, send the dead key press followed by the base key press
- Fall back to clipboard paste only for characters that have no dead key sequence

**When it matters**:
- Apps that intercept or block Ctrl+V (terminals, some editors)
- Workflows where preserving clipboard contents matters

**Impact**: Reliability. Current clipboard approach works for most cases but is not universal.

---

## Other Ideas

- **App-name normalization**: Fix wsl2/UWP app-name splitting (known bug #6). Merge cache entries across app-name variants so hits aren't split between `applicationframehost.exe` and `wsl2`.
- **Bridge daemon `element_at_point`**: Native COM path for sub-10ms accessibility lookups instead of PowerShell (~200ms). Would make Layer 2 nearly free.
- **WinUI3 property fallback**: Use `AutomationId` or `HelpText` when UIA `.Name` is empty (known bug #4). Would improve semantic caching for modern Windows apps.

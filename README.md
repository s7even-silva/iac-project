# gh-pages: interactive content for the IAC 2026 iPoster

Branch without shared history with `main`. GitHub Pages serves it at
`https://s7even-silva.github.io/iac-project/`, and each box of the iPoster
(IAC-26,A1,IPB,42) embeds one page as an iframe. iPosters only accepts
iframes from approved domains; `github.io` is on that list.

| Path | Box | Content |
|---|---|---|
| `box1/` | 1 · Why active shielding | Rigidity explorer: path through a uniform 2 m field layer, SEP and GCR rigidity spectra |
| `box2/`–`box4/` | 2–4 | Pending |

- `assets/common.css`: shared look, the poster palette "deep space and
  magnetic shield". Each color has one meaning in the poster and in every
  figure: cyan = field and active shield, amber = Sun, SEP and HTS coils,
  indigo = GCR (second GCR species in light indigo, always dashed),
  coral = dose and risk figures only. Dark only, to match the poster.
- `data/spectra.js`: built by `tools/build_spectra.py` from the OLTARIS CSVs
  on `main` (`geant4/ActiveShield_Sim/data/sources/oltaris`). Loaded with a
  `<script>` tag, so the pages need no fetch and also open from `file://`.
- Every box must also have a static image or MP4 in the iPoster, in case the
  iframe does not load at the venue.

Rebuild the data from a checkout of `main` next to this worktree:

    python3 tools/build_spectra.py ../iac-project/geant4/ActiveShield_Sim/data/sources/oltaris

Preview: open `box1/index.html` in a browser.

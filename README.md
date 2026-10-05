# gh-pages: interactive content for the IAC 2026 iPoster

Branch without shared history with `main`. Each box of the iPoster
(IAC-26,A1,IPB,42) embeds one page of this site as an iframe. iPosters only
accepts iframes from approved domains; `github.io` is on that list.

Stack: Vue 3 + Vite + TypeScript, d3-scale/d3-shape for the charts, Inter and
JetBrains Mono bundled with the site (no font CDN, so nothing changes if the
venue network is slow). Each box is its own HTML entry, so an iframe only
loads its own code.

| Page | Box | Content |
|---|---|---|
| `/` | — | Index of the boxes |
| `/storyboard/` | — | Talk storyboard (2026-10-04): the four rooms, their scenes, the spoken script and presenter notes |
| `/room1/`–`/room4/` | 1–4 | **What each iPoster iframe loads.** One room of the storyboard alone (kiosk mode): a 16:9 slide that fills the window, with its controls, caption and counter. Click to advance, left third to go back |
| `/box1/` | 1 (old) | First rigidity explorer (Vue). Superseded by `/room1/`; kept until the poster is switched over |

The storyboard and the four rooms are static files in `public/` (copied
as they are into `docs/` by `npm run build`). They are generated from one
template: each `room<N>/index.html` is the storyboard page with
`window.KIOSK` set to the room id (`rain`, `shield`, `dose`, `error`).
The field slices drawn as iron filings are precomputed by `tools/field_slice.py`
(Biot-Savart, embedded in the page). Edit `public/storyboard/index.html` only, then run `python3 tools/build_rooms.py`
and `npm run build`.

## Work on it

    npm install
    npm run dev        # http://localhost:5173/iac-project/
    npm run build      # type-check, then build into docs/

GitHub Pages serves `docs/` from this branch
(`https://s7even-silva.github.io/iac-project/`), so **run `npm run build`
and commit `docs/` together with the source**.

## Layout

- `src/styles/tokens.css`: the palette and type. Exact poster palette,
  flat (no glow or shadows), dark only. One meaning per color, in the poster
  and in every figure: cyan = field and active shield, amber = Sun, SEP and
  HTS coils, indigo = GCR (second GCR species dashed), coral = dose and risk
  figures only. Text kept to a minimum: labels, icons and diagrams first.
- `src/components/`: shared pieces (panel, stat tile, segmented control,
  slider).
- `src/lib/physics.ts`: rigidity, energy and formatting helpers.
- `src/data/spectra.json`: built by `tools/build_spectra.py` from the OLTARIS
  CSVs on `main`, and bundled into the page (no fetch at the venue):

      python3 tools/build_spectra.py ../iac-project/geant4/ActiveShield_Sim/data/sources/oltaris

- `src/boxN/`, `boxN/index.html`: one app per box. A new box also needs its
  entry in `vite.config.ts`.

Every box must also have a static image or MP4 in the iPoster, in case the
iframe does not load at the venue.

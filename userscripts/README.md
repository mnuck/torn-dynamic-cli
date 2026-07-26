# userscripts/

Tampermonkey/Violentmonkey scripts that add things to torn.com itself. These
are the one part of this repo that runs in the browser rather than against the
API — some data only exists in the page.

## Install

Open the `.user.js` file's raw URL with Tampermonkey installed, or paste the
contents into a new script. They're plain ES5 with `@grant none` — no build
step, no bundler, no dependencies.

## `torn-race-standings.user.js`

Adds a button to the race header that reveals **final standings instantly**,
rendered inline below the player, instead of waiting out the race animation.

The result was already there the whole time: Torn delivers every driver's full
per-segment time series up front in the `racingData` payload, base64-encoded.
The button just decodes it and sums each driver's segments for an exact finish
time. Nothing is scraped or guessed.

Notes:

- **The request is only ever made on a manual click**, never automatically on
  page load. It reads the anti-CSRF token from the `rfc_v` cookie the way the
  page's own code does.
- Works on both race-log pages and the live racing view. The live view has no
  `raceID` in the URL, so it's read from the driver list's
  `data-id="<raceID>-<userID>"` attributes.
- Survives in-app race switching via a `MutationObserver` — Torn swaps races
  without a page load, which would otherwise leave a stale button.
- Anchors to the `.title-black` header rather than `.race-player-container`,
  because the header is present in every race state (finished, paused, live)
  and the container is not.

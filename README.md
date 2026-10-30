# Card Counting Drill

Desktop card counting practice app for Windows and macOS.

Available card styles:

- Standard poker cards
- Poker cards numbered 1 to 10
- Poker cards numbered 1 to 7 plus Jack, Queen, King
- Full 52-card poker deck with 0–2 jokers
- Double 52-card poker deck with 0–4 jokers
- Trevisane card scans (PNG) or traced vectors (SVG)

The size slider ranges from 100% to 250% and remembers its setting. Choose to reveal 1–5 cards at a time; that setting is remembered too.

## Download the app

Download the latest Windows `.exe` or macOS `.dmg` from the [GitHub Releases page](https://github.com/Cremasc0/card-memorising-app/releases/latest). The macOS build is universal for Intel and Apple Silicon Macs.

The macOS app is not signed or notarized. To open it the first time, try to open it, then use **System Settings → Privacy & Security → Open Anyway** if macOS blocks it. See [Apple's instructions](https://support.apple.com/en-gb/102445).

## Run from source

Install Node.js, then run `npm ci` and `npm start` from this folder.

## Build

- Windows portable app: `npm run build:win`
- macOS universal `.dmg` and `.zip`: `npm run build:mac`

Builds are placed in `dist`. Pushing a version tag such as `v1.1.1` runs GitHub Actions for both platforms and publishes the installers to GitHub Releases. `workflow_dispatch` can build the platform artifacts without publishing a release.

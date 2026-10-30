# Card Counting Drill

Windows desktop app for practising card counting with selectable decks:

- Standard poker cards
- Poker cards numbered 1 to 10
- Poker cards numbered 1 to 7 plus Jack, Queen, King
- Full 52-card poker deck with 0–2 jokers
- Double 52-card deck with 0–4 jokers
- Vector artwork for all poker ranks, suits, and the available jokers
- Trevisane card scans (PNG)
- Trevisane traced cards (SVG)

## Run from source

Install Node.js, then run `npm install` and `npm start` from this folder.

## Build the portable Windows app

Run `npm run build:win`. The portable executable will be created in `dist-win`.
It includes the app and all card images, so it can be moved and opened directly.

The card size slider ranges from 100% to 250%, remembers your setting, and starts at 190%.
Choose to reveal 1–5 cards at a time; this setting is remembered too.

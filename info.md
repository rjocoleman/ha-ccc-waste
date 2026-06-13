# Christchurch City Council Kerbside

Next bin collection dates for any Christchurch address, straight from the council's own data.

- One sensor per bin (rubbish, recycling, organic) with the next collection date and a `days_until` attribute.
- A calendar entity for native "remind me X before collection" automations.
- Public-holiday date shifts handled automatically, flagged with `temporary_change`.
- No API keys, no scraping. Polls every 12 hours and stays out of your way.

Add it, type part of your address, pick the match, done.

See the [README](https://github.com/rjocoleman/ha-ccc-waste) for dashboard (Mushroom) and automation examples.

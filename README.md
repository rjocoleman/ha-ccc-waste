# Christchurch City Council Kerbside

A Home Assistant integration for Christchurch City Council (CCC) kerbside collection. It gives you one sensor per bin (rubbish, recycling, organic) with the next collection date, plus a calendar entity you can trigger automations off.

It talks to the same credential-free endpoints the council website uses. No API keys, no scraping, no cookies. It polls every 12 hours because collection dates barely move, so it stays quiet and only needs a new release when CCC actually changes something.

This integration only supports Christchurch. That is the point. It is small, focused, and easy to keep working.

## What you get

- A device per property, with a sensor for each bin material present at your address.
- Each sensor's state is the next collection date (a timestamp), with handy attributes:
  - `days_until` - whole days until the next collection
  - `collection_day` - the route day, e.g. Tuesday
  - `temporary_change` - true when a public holiday has shifted the date
  - `original_date` - the pre-shift date when `temporary_change` is true
  - `container_type` - the bin size, e.g. 140L WB
- A calendar entity listing upcoming collections as all-day events, so you can use native calendar triggers.

## Installing through HACS

This is a custom repository. The quickest way is the button below, which opens HACS on your Home Assistant with this repo pre-filled:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rjocoleman&repository=ha-ccc-waste&category=integration)

Then download it and restart Home Assistant.

Or add it by hand:

1. In Home Assistant, open HACS.
2. Open the three-dot menu, choose **Custom repositories**.
3. Add `https://github.com/rjocoleman/ha-ccc-waste` with category **Integration**.
4. Search for **Christchurch City Council Kerbside** and download it.
5. Restart Home Assistant.

## Setting it up

1. Go to **Settings -> Devices & services -> Add integration**.
2. Search for **Christchurch City Council Kerbside**.
3. Type part of your street address (for example `110 Montreal`) and submit.
4. If there is more than one match, pick your address from the list.

That is it. The integration resolves your address to a council rating unit and creates the sensors and calendar.

### Changing your address later

Open the integration, choose **Reconfigure**, and look up a new address. No need to delete and re-add.

## Dashboard with Mushroom

The sensors work with any standard entity card. For nicer chips, [Mushroom](https://github.com/piitaya/lovelace-mushroom) is a good fit. Install it separately through HACS.

Your entity IDs depend on your address. Check them under **Developer tools -> States** (they look like `sensor.<your_address>_rubbish`). Swap them into the examples below.

A template card that colours by proximity:

```yaml
type: custom:mushroom-template-card
primary: Rubbish
secondary: >-
  {% set d = state_attr('sensor.ccc_rubbish', 'days_until') %}
  {% if d is none %}Unknown
  {% elif d == 0 %}Today
  {% elif d == 1 %}Tomorrow
  {% else %}In {{ d }} days{% endif %}
icon: mdi:trash-can
icon_color: >-
  {% set d = state_attr('sensor.ccc_rubbish', 'days_until') %}
  {% if d is none %}grey
  {% elif d <= 1 %}red
  {% elif d <= 3 %}orange
  {% else %}green{% endif %}
```

A row of chips, one per bin. The `is not none` guard keeps them tidy if a
sensor is briefly unavailable:

```yaml
type: custom:mushroom-chips-card
chips:
  - type: template
    icon: mdi:trash-can
    content: >-
      {% set d = state_attr('sensor.ccc_rubbish', 'days_until') %}
      {{ d ~ 'd' if d is not none else '?' }}
  - type: template
    icon: mdi:recycle
    content: >-
      {% set d = state_attr('sensor.ccc_recycling', 'days_until') %}
      {{ d ~ 'd' if d is not none else '?' }}
  - type: template
    icon: mdi:leaf
    content: >-
      {% set d = state_attr('sensor.ccc_organic', 'days_until') %}
      {{ d ~ 'd' if d is not none else '?' }}
```

## Automations

### Using the calendar (recommended)

Trigger a set time before any collection. This fires for every event on the calendar:

```yaml
triggers:
  - trigger: calendar
    entity_id: calendar.ccc_collections
    event: start
    offset: "-12:00:00"  # 12 hours before the all-day event starts
actions:
  - action: notify.mobile_app_your_phone
    data:
      message: "{{ trigger.calendar_event.summary }} is collected tomorrow."
```

### Using a sensor attribute

If you want to react to a specific bin, key off `days_until`:

```yaml
triggers:
  - trigger: numeric_state
    entity_id: sensor.ccc_rubbish
    attribute: days_until
    below: 2
actions:
  - action: notify.mobile_app_your_phone
    data:
      message: "Put the rubbish out, it is collected soon."
```

## Removing it

Go to **Settings -> Devices & services**, open the integration, and delete the entry. The device and its entities are removed with it. You can then remove it from HACS.

## Troubleshooting

- **No matching address found.** Try a shorter or different part of the address (just the number and street). The lookup uses the council's own address service.
- **No kerbside collection for this address.** Some properties (for example rural or eco-drop addresses) are not on a kerbside route, so there is nothing to show.
- **Could not connect.** The council service was unreachable. The integration retries automatically; if it persists, the council endpoint may be down.
- **A date looks off around a public holiday.** Check the `temporary_change` and `original_date` attributes. The council shifts collections by a day around holidays and the integration follows that.

Diagnostics (from the integration's three-dot menu) include the computed schedule with your address, rating unit and coordinates redacted.

## How dates are worked out

The council's API returns dates that are sometimes stale by design and expects the consumer to roll them forward. This integration replicates the council's own logic exactly:

- It uses the corrected forward date field (`next_planned_date_app`).
- It rolls that date forward in whole cycles until it is today or later: weekly for organic, fortnightly for rubbish and recycling.
- It then applies any public-holiday override for that exact date (a single shift, matching the council's behaviour) and flags it as a temporary change.

All date maths is done in `Pacific/Auckland` local dates so holiday matches line up correctly.

## Licence

MIT.

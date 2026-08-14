# Value IP PDU

Home Assistant integration for the **VALUE 8-port IP PDU** (OEM: LIU-0816-WN, 16 A, IEC-320 C13 x8) — the rack power strip reachable at `http://<ip>/` with the classic Microchip TCP/IP web UI.

Provides per-outlet **switch** control (ON/OFF), per-outlet **power-cycle buttons** (ON/OFF cycle), and total **power metering** fed from the device's current sensor: current, computed power, accumulated energy, temperature, and humidity.

> **No official Home Assistant integration exists for this device.** This integration talks directly to the device's built-in HTTP interface (HTTP Basic auth), so no cloud or external service is involved (`local_polling`).

## Features

| Entity | Type | Notes |
|---|---|---|
| Outlet 1–8 | Switch | Turn each of the 8 C13 outlets on/off |
| Outlet 1–8 cycle | Button | Power-cycle (ON/OFF) a single outlet |
| Total current | Sensor | A (measured by the PDU) |
| Total power | Sensor | W = voltage × current (computed) |
| Total energy | Sensor | kWh (accumulated, survives HA restarts) |
| Voltage used | Sensor | V (diagnostic — shows which voltage source was used) |
| Temperature | Sensor | °C (built-in sensor) |
| Humidity | Sensor | % (built-in sensor) |

All entities are grouped under a single **Value IP PDU** device.

## Energy Dashboard

The **Total power** sensor (`sensor.*_total_power`, `device_class: power`) is all you need to add the PDU to the HA Energy Dashboard:

Settings → **Energy** → *Electricity grid* → **Add consumption** → *Use an entity* → select `Total power` (or `Total energy`).

## Power calculation & voltage source

The PDU's HTTP API **does not expose voltage** (the device measures it but never serves it). Power is therefore computed as `W = voltage × current`, where *voltage* is resolved in this order:

1. **Voltage source sensor** — an HA entity you select in the options (e.g. a rack PDU meter or smart plug that already measures the feed voltage). Read live on every poll.
2. **Nominal voltage** — configurable constant, default `230 V`, used when no source sensor is configured.

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories**
2. Add `https://github.com/jaggr2/home-assistant-value-pdu` as an **Integration**
3. Search for **Value IP PDU** → **Download** → restart Home Assistant
4. Settings → Devices & services → **Add integration** → **Value IP PDU**

### Manual

```bash
git clone https://github.com/jaggr2/home-assistant-value-pdu.git
cp -r home-assistant-value-pdu/custom_components/value_pdu <config>/custom_components/
```

Restart Home Assistant, then add the integration from **Settings → Devices & services**.

## Configuration

During setup you provide:

- **Host** — IP / hostname of the PDU (e.g. `192.168.1.4`)
- **Username / Password** — HTTP Basic auth credentials (device default `admin` / `admin`)
- **Poll interval** — default 30 s (min 10 s)
- **Nominal voltage** — default `230 V`
- **Voltage source sensor** — optional; any HA sensor with `device_class: voltage`

**Username, password, poll interval, nominal voltage and voltage source can all be changed later** via the entry's **Configure** (options) dialog — the integration reloads automatically, so credential changes don't require removing and re-adding the entry.

### `value_pdu.cycle_outlet` service

Power-cycles an outlet for use in automations (buttons cover this in the UI):

```yaml
service: value_pdu.cycle_outlet
data:
  outlet: 3   # 0-based index 0..7
```

## Device API reference

The device exposes a small HTTP surface (all responses gzip-encoded):

- `GET /status.xml` — telemetry:
  - `cur0` / `curBan` → total current (A)
  - `tempBan` → temperature (°C), `humBan` → humidity (%)
  - `outletStat0` … `outletStat7` → `on` / `off`
  - `stat0` / `statBan` → `normal` | `curwarning` | `curoverload` | `volwarning` | `voloverload` | `tempwarning` | `humwarning`
- `GET /control_outlet.htm?outlet0=1&outlet3=1&op=X` — control selected outlets with `op`: `0` = ON, `1` = OFF, `2` = ON/OFF cycle

## Troubleshooting

- **Cannot connect**: verify the host is reachable (`curl -u admin:admin http://<ip>/`) and that the username/password are correct.
- **Power shows 0 W**: the device reports 0.0 A (no load). Check the LED display on the unit.
- **Voltage source not updating**: the source entity must report a positive numeric state (`device_class: voltage`). Otherwise the nominal constant is used — see the **Voltage used** diagnostic sensor.

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

## License

Apache-2.0. This project is not affiliated with VALUE or Home Assistant.

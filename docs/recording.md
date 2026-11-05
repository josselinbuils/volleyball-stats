# Recording a match

Everything the pipeline sees comes from one fixed camera: where it stands and how it is set matter more than anything else.

In short: one fixed camera on a sideline, aligned with the net, framing both end lines, filming 4K (2.7K minimum) at 50 fps with everything locked.

- [Camera placement](#camera-placement)
- [Hardware](#hardware)
- [Camera settings](#camera-settings-osmo-action-3)
- [Before the first match](#before-the-first-match)
- [Lens calibration](#lens-calibration)

## Camera placement

- One fixed camera on a sideline, aligned with the net, about 6 m from the sideline, 3.6 m high.
- It frames both end lines. No auto-tracking or panning camera.
- It sits on a light stand (Manfrotto 1004BAC):
  - the stand's base on the floor behind a handball goal post;
  - the column strapped to the post (80 × 80 mm) with two straps, one low and one at ~1.8 m;
  - only on an anchored goal. Without a goal: sandbags on the stand legs.

## Hardware

- [x] DJI Osmo Action 3 Standard Combo
- [x] microSD SanDisk Extreme 256 GB
- [x] 5 m USB-C charging cable
- [x] Manfrotto 1004BAC light stand
- [x] Three-prong to 1/4" adapter: Insta360 1/4" to 3 Pin Adapter
- [x] 2 straps, 25 mm, ~2 m, no hooks (gentle on the stand column)
- [ ] Cord loop (any, e.g. paracord), camera frame to stand column, with a little slack
- [x] Power bank, ~10,000 mAh
- [x] Fan: [JISULIFE pocket fan, 4,500 mAh](https://www.amazon.fr/dp/B09PDMZKQW), held on the stand
      column by two velcro straps and a cord over a strip of foam, at its lowest speed, 80 cm below the
      camera, blowing up at it. Closer, its air rumbles on the mics.
      Without a fan, the still camera overheats within about 30 minutes at 22 °C (4K or 2.7K, 50 fps).
      With it, it recorded 2 h 49 min at 4K 50 fps on the power bank, a bit hot; no visible shake.
      Its noise on the mics (dBFS, lower is quieter) is a low rumble under 1 kHz; whistles are
      still detected in every case. If the camera runs hot, raise the speed before moving the fan closer.

  | Fan | Speed 1 | Speed 2 | Speed 3 |
  | --- | --- | --- | --- |
  | 80 cm, vertical | −47 | −42 | −33 |
  | 80 cm, turned to the camera | −46 | −42 | −36 |
  | 50 cm, turned to the camera | −32 (+14 dB rumble) | −28 (+14 dB rumble) | −25 (+11 dB rumble) |

- Only if needed: sandbags (free-standing stand), ball head (if the camera hinge slips), bike
  handlebar mount.

## Camera settings (Osmo Action 3)

In short: 4K (2.7K minimum) at 50 fps, Standard field of view, everything locked, shutter 1/250 or
faster.

| Setting | Réglage | Where | Value | Why |
| --- | --- | --- | --- | --- |
| Resolution | Résolution | Swipe up | 4K (16:9) | Ball and jersey numbers; the ball model reads 16:9 |
| Frame rate | Fréquence d'images | Swipe up | 50 fps | No flicker under 50 Hz lighting |
| Loop recording | Enregistrement en boucle | Swipe up, top left | Off | Would overwrite the start of the match |
| Stabilisation | Stabilisation | Swipe up, top right | Off (no RockSteady, no HorizonBalancing) | Fixed camera; stabilisation warps each frame |
| Mode | Mode | Parameters icon | PRO | Locked exposure |
| Field of view | Champ de vision | PRO | Standard; Wide or Ultra Wide only if the stand is too close to frame the court | 6 m from the sideline it frames the whole court; wider ones shrink the players and bend the lines |
| Shutter speed | Vitesse d'obturation | PRO, Exposure: Manual | 1/250, 1/500 if the gym is bright | Sharp ball |
| ISO | ISO | PRO, Exposure: Manual | Lowest correct one, set at the gym (often 800–3200) | Locked exposure |
| White balance | Balance des blancs | PRO | Manual, set at the gym (often 4500–5500 K under LEDs) | Stable jersey colours for the teams |
| Colour | Couleur | PRO | Normal, not D-Cinelike | Natural colours for the teams |
| Enhanced image quality | Qualité d'image améliorée | PRO | Off, On only facing sunlit windows | Made for strong light contrast; more power and heat |
| Wind noise reduction | Réduction du bruit du vent | PRO, audio | On | Less fan rumble; the whistle comes through |
| Directional audio | Audio directionnel | PRO, audio | Off | The whistle comes from anywhere around the court |
| Video compression | Compression vidéo | Swipe down, Settings | Compatibility (H.264) or Efficiency (HEVC, smaller files) | Both decode on the GPU |
| Anti-flicker | Anti-scintillement | Swipe down, Settings | 50 Hz | French power grid |
| Screen off when recording | Écran éteint pendant l'enregistrement | Swipe down, Settings | Shortest delay | Less heat |
| Auto power off | Arrêt automatique | Swipe down, Settings | 30 min (the longest) | No stop before the first serve; the 2-hour test checks it never stops a recording |

- Resolution, frame rate, field of view and stabilisation stay the same for the lens calibration and
  every match. ISO and white balance change with the gym only.
- There is no bitrate setting: the camera records at up to 130 Mbps, about 120 GB for 2 hours.
- The French names are approximate: the menus may word them slightly differently.

## Before the first match

- [x] Check the SD card with [F3](https://github.com/AltraMayor/f3) or H2testw.
- [x] Set the [camera settings](#camera-settings-osmo-action-3), ISO and white balance aside.
- [x] Record 2 hours at home, 4K 50 fps, on the power bank through the 5 m cable: no cut, no
      overheating.
- [x] Calibrate the lens in Standard (see [below](#lens-calibration)).
- [ ] At the gym: get approval for the handball goals and check they are anchored. Check the framing
      from the stand shows both end lines and the near corners.

## Lens calibration

Without it, the court mapping is off by 0.3–1.4 m on wide footage the camera did not straighten (see
the [court benchmark](../benchmarks/court/README.md)). Film the board in the matches' field of view.
Standard straightens most of it in the camera but still moves the 4K frame's corners by about 66 px
and its side edges by 41 px. On the first match the court sat in the frame's straight middle band:
the lens moved court positions by 5 cm at most (13 cm in the free zone).

1. Print the [board](checkerboard.png) on A4 landscape, fit to page.
2. Keep it flat: tape it on a wall or door and move the camera, or show it full screen on a TV.
3. Film it for a minute at about 1 m, from several angles. Watching the camera screen, place the
   whole board in each corner, at the middle of each edge and in the centre, 2 s each.
4. Run `uv run python -m volleyball_stats.lens calibrate VIDEO`. It writes `outputs/lens.json`, to
   pass as `--lens` to the court commands. The Osmo Action 3's, in Standard at 4K, is
   [`lens_osmo_action3_standard_4k.json`](lens_osmo_action3_standard_4k.json).

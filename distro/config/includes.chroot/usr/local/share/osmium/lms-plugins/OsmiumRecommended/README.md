# Osmium Recommended (LMS plugin)

Surfaces the appliance's **Consigliati / Recommended** list inside Lyrion Music
Server, so it shows up in **Material Skin**, the classic web UI and control apps
(Squeezer, iPeng) — not only in the Qt kiosk.

## What it does

It registers one home-screen "app" whose feed reads the list the box already
computes offline (the `hifi-recommend` job, `hifi_recommend.py`) and serves as
JSON on the loopback:

```
GET http://127.0.0.1:8000/recommendations
```

Each recommendation becomes a playable menu item:

- **Local-library album** (`play_kind: album_id`) → native library actions
  (`browselibrary` / `playlistcontrol` by `album_id`): real album browse, play,
  add and artwork.
- **Streaming album** (`play_kind: url`, Qobuz / Tidal / Deezer) → a playlist
  built from the captured tracklist. Playback needs the matching service plugin
  installed and logged in.

When the list is empty or recommendations are off, it shows a single
explanatory line instead of an error.

There is no recommendation logic here: the plugin is a thin reader of the API.

## How it is installed

On the Osmium appliance it is **not** installed from a repository. It ships in
the image under `/usr/local/share/osmium/lms-plugins/OsmiumRecommended` and is
re-asserted into the server's writable plugin dir on every boot by
`hifi-lyrion-plugins-ensure.sh`. An OTA update that ships a newer version
(bumped `<version>` in `install.xml`) updates it on the next boot.

`repo.xml` is only for installing it by hand on a third-party Lyrion server.

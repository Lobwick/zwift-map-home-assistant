"""Constants for Zwift Map."""

from datetime import timedelta

DOMAIN = "zwift_map"
VERSION = "0.2.0"

CONF_PLAYER_ID = "player_id"

# Poll the relay every 2 s while riding (Zwift Companion's own pace), and the
# profile every 30 s otherwise to notice when a ride starts.
ONLINE_INTERVAL = timedelta(seconds=2)
OFFLINE_INTERVAL = timedelta(seconds=30)
# On HTTP 429 the online interval grows by this much (up to the max) and
# shrinks back slowly after successful polls.
RATE_LIMIT_STEP_S = 1.0
RATE_LIMIT_DECAY_S = 0.1
RATE_LIMIT_MAX_S = 15.0
# The relay can keep serving the last state after a ride ends: a world clock
# that stops moving for this long means the rider left.
STALE_STATE_AFTER = timedelta(seconds=60)
# How often a growing route track is written to disk.
TRACK_SAVE_INTERVAL = timedelta(seconds=60)

TRACKS_DIR = "zwift_map/tracks"
ZWIFTHACKS_DIR = "zwift_map/zwifthacks"
GAME_INFO_FILE = "zwift_map/game_info.json"
GAME_INFO_MAX_AGE_S = 24 * 3600
STORAGE_VERSION = 1

STATIC_URL = "/zwift_map_static"
MAPS_STATIC_URL = "/zwift_map_maps"
CARD_FILENAME = "zwift-map-card.js"
